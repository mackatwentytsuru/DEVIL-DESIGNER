import math
from pathlib import Path

FORMATS = ('fbx', 'obj')
TARGETS = ('cc5', 'ue', 'blender')
OBJ_SCALE = {'cc5': 100.0, 'ue': 100.0, 'blender': 1.0}
MAX_INFLUENCES = 4
PIECE_PREFIX = 'Piece '


def duplicate_copy(name, names):
    return len(name) > 4 and name[-4] == '.' and name[-3:].isdigit() and name[:-4] in names


def piece_names(obj):
    names = [group.name[len(PIECE_PREFIX):] for group in obj.vertex_groups if group.name.startswith(PIECE_PREFIX)]
    return [name for name in names if not duplicate_copy(name, names)]


def material_name(piece):
    return 'DD_' + ''.join(character if character.isalnum() else '_' for character in piece).strip('_')


def with_object(obj, operator, **values):
    import bpy
    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
        return operator(**values)


def export_copy(garment, thickness):
    import bpy
    copy = garment.copy()
    copy.data = garment.data.copy()
    copy.name = garment.name + ' Export'
    bpy.context.scene.collection.objects.link(copy)
    copy.modifiers.clear()
    for key in list(copy.keys()):
        del copy[key]
    pieces = piece_names(garment)
    for group in list(copy.vertex_groups):
        if not group.name.startswith(PIECE_PREFIX) or group.name[len(PIECE_PREFIX):] not in pieces:
            copy.vertex_groups.remove(group)
    copy.data.materials.clear()
    for piece in pieces:
        material = bpy.data.materials.get(material_name(piece)) or bpy.data.materials.new(material_name(piece))
        copy.data.materials.append(material)
    attribute = copy.data.attributes.get('dd_piece')
    if attribute is not None:
        for polygon, item in zip(copy.data.polygons, attribute.data):
            polygon.material_index = max(0, min(len(pieces) - 1, item.value - 1))
    if thickness > 0:
        solidify = copy.modifiers.new('Fabric Thickness', 'SOLIDIFY')
        solidify.thickness = thickness
        solidify.offset = 1.0
        solidify.use_even_offset = True
        with_object(copy, bpy.ops.object.modifier_apply, modifier=solidify.name)
    return copy


def transfer_weights(obj, body, armature):
    import bpy
    bones = {bone.name for bone in armature.data.bones}
    names = [group.name for group in body.vertex_groups if group.name in bones]
    if not names:
        raise ValueError('The body has no vertex groups named after the armature bones.')
    for name in names:
        if name not in obj.vertex_groups:
            obj.vertex_groups.new(name=name)
    transfer = obj.modifiers.new('Skin Weights', 'DATA_TRANSFER')
    transfer.object = body
    transfer.use_vert_data = True
    transfer.data_types_verts = {'VGROUP_WEIGHTS'}
    transfer.vert_mapping = 'POLYINTERP_NEAREST'
    transfer.layers_vgroup_select_src = 'ALL'
    transfer.layers_vgroup_select_dst = 'NAME'
    with_object(obj, bpy.ops.object.modifier_apply, modifier=transfer.name)
    modifier = obj.modifiers.new('Armature', 'ARMATURE')
    modifier.object = armature
    world = obj.matrix_world.copy()
    obj.parent = armature
    obj.matrix_world = world
    with_object(obj, bpy.ops.object.vertex_group_limit_total, group_select_mode='BONE_DEFORM', limit=MAX_INFLUENCES)
    with_object(obj, bpy.ops.object.vertex_group_normalize_all, group_select_mode='BONE_DEFORM', lock_active=False)
    unweighted = sum(1 for vertex in obj.data.vertices
                     if sum(item.weight for item in vertex.groups if obj.vertex_groups[item.group].name in bones) < .5)
    return dict(bones=len(names), unweighted_vertices=unweighted)


def select_only(objects):
    import bpy
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def write_file(obj, path, fmt, target, armature):
    import bpy
    objects = [obj] + ([armature] if armature is not None else [])
    select_only(objects)
    if fmt == 'fbx':
        bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True,
                                 object_types={'MESH', 'ARMATURE'} if armature is not None else {'MESH'},
                                 apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', global_scale=1.0,
                                 axis_forward='-Z', axis_up='Y', use_mesh_modifiers=True, mesh_smooth_type='FACE',
                                 add_leaf_bones=False, bake_anim=False, use_armature_deform_only=True, path_mode='STRIP')
    else:
        bpy.ops.wm.obj_export(filepath=str(path), export_selected_objects=True, global_scale=OBJ_SCALE[target],
                              forward_axis='NEGATIVE_Z', up_axis='Y', export_uv=True, export_normals=True,
                              export_materials=True, export_vertex_groups=True, path_mode='STRIP')


def bounds(objects):
    from mathutils import Vector
    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return [[min(point[axis] for point in corners) for axis in range(3)],
            [max(point[axis] for point in corners) for axis in range(3)]]


def reimport(path, fmt, target):
    import bpy
    before = set(bpy.data.objects)
    if fmt == 'fbx':
        importer = bpy.ops.import_scene.fbx if hasattr(bpy.types, 'IMPORT_SCENE_OT_fbx') else bpy.ops.wm.fbx_import
        importer(filepath=str(path))
    else:
        bpy.ops.wm.obj_import(filepath=str(path), global_scale=1 / OBJ_SCALE[target], forward_axis='NEGATIVE_Z', up_axis='Y')
    return [obj for obj in bpy.data.objects if obj not in before]


def check_reimport(path, fmt, target, reference):
    import bpy
    imported = reimport(path, fmt, target)
    try:
        meshes = [obj for obj in imported if obj.type == 'MESH']
        if not meshes:
            raise ValueError(f'{path.name} re-imported without a mesh.')
        mesh = meshes[0]
        uv_layer = mesh.data.uv_layers.active
        uvs = [tuple(item.uv) for item in uv_layer.data] if uv_layer else []
        low, high = bounds(meshes)
        expected = bounds([reference])
        error = max(abs(a - b) for a, b in zip(low + high, expected[0] + expected[1]))
        return dict(file=path.name, vertices=len(mesh.data.vertices), faces=len(mesh.data.polygons),
                    expected_vertices=len(reference.data.vertices), expected_faces=len(reference.data.polygons),
                    uv=bool(uvs), uv_in_unit_square=all(-1e-5 <= u <= 1 + 1e-5 and -1e-5 <= v <= 1 + 1e-5 for u, v in uvs),
                    materials=sorted(slot.material.name.split('.')[0] for slot in mesh.material_slots if slot.material),
                    groups=sorted(group.name for group in mesh.vertex_groups)[:12],
                    armature=any(obj.type == 'ARMATURE' for obj in imported), bounds_error_m=round(error, 6),
                    passed=len(mesh.data.polygons) == len(reference.data.polygons) and bool(uvs) and error < 1e-3)
    finally:
        for obj in imported:
            data = obj.data
            bpy.data.objects.remove(obj)
            if data is not None and data.users == 0 and isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)


def export_garment(garment, base_path, formats, target='cc5', thickness=0.0, armature=None, body=None):
    import bpy
    formats = [fmt.lower() for fmt in formats]
    if any(fmt not in FORMATS for fmt in formats) or target not in TARGETS:
        raise ValueError(f'Formats must be in {FORMATS} and target in {TARGETS}.')
    if not math.isfinite(thickness) or not 0 <= thickness <= .02:
        raise ValueError('Thickness must be between 0 and 0.02 m.')
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    copy = export_copy(garment, thickness)
    report = dict(target=target, thickness=thickness, pieces=piece_names(garment), files=[])
    try:
        if armature is not None:
            if body is None:
                raise ValueError('Weight transfer needs the weighted body mesh as well as the armature.')
            report['weights'] = transfer_weights(copy, body, armature)
        for fmt in formats:
            path = base_path.with_suffix('.' + fmt)
            write_file(copy, path, fmt, target, armature)
            report['files'].append(check_reimport(path, fmt, target, copy))
    finally:
        mesh = copy.data
        bpy.data.objects.remove(copy)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    report['passed'] = all(item['passed'] for item in report['files'])
    return report
