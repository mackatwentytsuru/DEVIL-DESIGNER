import math
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class BodySpec:
    name: str
    height: float
    shoulder_width: float
    bust: float
    waist: float
    hip: float
    arm_angle: float
    leg_gap: float
    underbust_ratio: float = .86
    bust_depth: float = .78


BODIES = {
    'A': BodySpec('A', 1.60, .37, .84, .64, .90, 30.0, .16),
    'B': BodySpec('B', 1.75, .44, .98, .80, .96, 45.0, .26, underbust_ratio=.93, bust_depth=.70),
}
RING_SEGMENTS = 40
VOXEL_SIZE = .007
SMOOTH_REPEAT = 6
TARGET_FACES = 30000


def ellipse_axes(circumference, ratio):
    if not circumference > 0 or not ratio > 0:
        raise ValueError('Body girths and depth ratios must be positive.')
    factor = math.pi * (3 * (1 + ratio) - math.sqrt((3 + ratio) * (1 + 3 * ratio)))
    half_width = circumference / factor
    return half_width, half_width * ratio


def validate_spec(spec):
    values = (spec.height, spec.shoulder_width, spec.bust, spec.waist, spec.hip, spec.leg_gap)
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError('Body measurements must be positive metres.')
    if not 1.2 <= spec.height <= 2.2:
        raise ValueError('Body height must be between 1.2 m and 2.2 m.')
    if not 0 <= spec.arm_angle <= 80:
        raise ValueError('Arm angle is measured from the torso side and must be 0-80 degrees.')
    if not spec.waist < min(spec.bust, spec.hip) * 1.05:
        raise ValueError('Waist should be smaller than bust and hip for a dress form.')
    return spec


def torso_sections(spec):
    height = spec.height
    scale = height / 1.6
    hip = ellipse_axes(spec.hip, .74)
    waist = ellipse_axes(spec.waist, .74)
    bust = ellipse_axes(spec.bust, spec.bust_depth)
    under = ellipse_axes(spec.bust * spec.underbust_ratio, .74)
    high_hip = ellipse_axes((spec.hip + spec.waist) / 2 + .01, .72)
    armpit = ellipse_axes(spec.bust * .93, .66)
    shoulder = spec.shoulder_width / 2
    return [
        (.452, hip[0] * .55, hip[1] * .6, .01),
        (.47, hip[0] * .86, hip[1] * .9, .012),
        (.50, hip[0], hip[1], .012),
        (.565, high_hip[0], high_hip[1], .006),
        (.62, waist[0], waist[1], 0.0),
        (.675, under[0], under[1], -.004),
        (.72, bust[0], bust[1], -.012),
        (.755, armpit[0], armpit[1], -.004),
        (.785, shoulder - .015 * scale, .07 * scale, 0.0),
        (.81, shoulder - .03 * scale, .062 * scale, 0.0),
        (.825, .085 * scale, .055 * scale, 0.0),
        (.835, .06 * scale, .05 * scale, 0.0),
    ]


def limb_frames(axis):
    from mathutils import Vector
    axis = Vector(axis).normalized()
    side = axis.cross(Vector((0, 1, 0)))
    if side.length < 1e-6:
        side = Vector((1, 0, 0))
    side.normalize()
    return axis, side, axis.cross(side).normalized()


def arm_sections(spec, side):
    from mathutils import Vector
    height = spec.height
    scale = height / 1.6
    theta = math.radians(spec.arm_angle)
    joint = Vector((side * (spec.shoulder_width / 2 - .04 * scale), 0.0, .79 * height))
    axis, across, depth = limb_frames((side * math.sin(theta), 0.0, -math.cos(theta)))
    upper, fore = .186 * height, .146 * height
    stations = [(0.0, .05, .05), (.25 * upper, .046, .044), (upper, .034, .033),
                (upper + .3 * fore, .037, .035), (upper + fore, .026, .021)]
    sections = [(joint + axis * distance, across, depth, a * scale, b * scale) for distance, a, b in stations]
    hand_center = joint + axis * (upper + fore + .054 * height)
    return sections, (hand_center, axis, across, depth, (.054 * height, .017 * scale, .045 * scale))


def leg_sections(spec, side):
    from mathutils import Vector
    height = spec.height
    scale = height / 1.6
    girth = spec.hip / .9
    top = Vector((side * ellipse_axes(spec.hip, .74)[0] * .47, .01, .50 * height))
    ankle = Vector((side * spec.leg_gap / 2, .015, .04 * height))
    axis, across, depth = limb_frames(ankle - top)
    stations = [(0.0, .088 * girth), (.09, .085 * girth), (.47, .053), (.66, .058), (1.0, .032)]
    length = (ankle - top).length
    sections = [(top + axis * (length * fraction), across, depth, radius * scale, radius * scale)
                for fraction, radius in stations]
    foot = (Vector((side * spec.leg_gap / 2, -.045 * scale, .035 * scale)), (.042 * scale, .125 * scale, .035 * scale))
    return sections, foot


def add_ring(bm, center, across, depth, radius_across, radius_depth, count):
    return [bm.verts.new(center + across * (radius_across * math.cos(angle)) + depth * (radius_depth * math.sin(angle)))
            for angle in (math.tau * index / count for index in range(count))]


def add_tube(bm, sections, count=RING_SEGMENTS):
    rings = [add_ring(bm, *section, count) for section in sections]
    for first, second in zip(rings, rings[1:]):
        for index in range(count):
            following = (index + 1) % count
            bm.faces.new((first[index], first[following], second[following], second[index]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def add_ellipsoid(bm, center, axes, radii):
    import bmesh
    from mathutils import Matrix
    basis = Matrix((axes[0] * radii[0], axes[1] * radii[1], axes[2] * radii[2])).transposed().to_4x4()
    basis.translation = center
    bmesh.ops.create_uvsphere(bm, u_segments=RING_SEGMENTS, v_segments=RING_SEGMENTS // 2, radius=1.0, matrix=basis)


def build_parts(spec):
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    height = spec.height
    scale = height / 1.6
    across, depth = Vector((1, 0, 0)), Vector((0, 1, 0))
    add_tube(bm, [(Vector((0.0, offset, fraction * height)), across, depth, a, b)
                  for fraction, a, b, offset in torso_sections(spec)], RING_SEGMENTS * 2)
    add_tube(bm, [(Vector((0.0, .01, .79 * height)), across, depth, .052 * scale, .055 * scale),
                  (Vector((0.0, .015, .90 * height)), across, depth, .05 * scale, .052 * scale)])
    add_ellipsoid(bm, Vector((0.0, .005, .935 * height)), (across, depth, Vector((0, 0, 1))),
                  (.075 * scale, .092 * scale, .108 * scale))
    for side in (-1, 1):
        sections, hand = arm_sections(spec, side)
        add_tube(bm, sections)
        center, axis, hand_across, hand_depth, radii = hand
        add_ellipsoid(bm, center, (axis, hand_across, hand_depth), radii)
        sections, foot = leg_sections(spec, side)
        add_tube(bm, sections)
        add_ellipsoid(bm, foot[0], (across, depth, Vector((0, 0, 1))), foot[1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def make_body(spec, name=None, collection=None):
    import bpy
    spec = validate_spec(BODIES[spec] if isinstance(spec, str) else spec)
    bm = build_parts(spec)
    raw = bpy.data.meshes.new('DD Test Body Parts')
    bm.to_mesh(raw)
    bm.free()
    obj = bpy.data.objects.new(name or 'DD Test Body ' + spec.name, raw)
    (collection or bpy.context.scene.collection).objects.link(obj)
    remesh = obj.modifiers.new('Union', 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = VOXEL_SIZE
    smooth = obj.modifiers.new('Soften', 'SMOOTH')
    smooth.factor = .5
    smooth.iterations = SMOOTH_REPEAT
    depsgraph = bpy.context.evaluated_depsgraph_get()
    merged = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    obj.modifiers.clear()
    obj.data = merged
    bpy.data.meshes.remove(raw)
    triangles = sum(len(polygon.vertices) - 2 for polygon in merged.polygons)
    if triangles > TARGET_FACES:
        decimate = obj.modifiers.new('Reduce', 'DECIMATE')
        decimate.ratio = TARGET_FACES / triangles
        decimate.use_collapse_triangulate = True
        depsgraph = bpy.context.evaluated_depsgraph_get()
        reduced = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        obj.modifiers.clear()
        obj.data = reduced
        bpy.data.meshes.remove(merged)
    obj.data.name = obj.name
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj['dd_test_body'] = spec.name
    for key, value in asdict(spec).items():
        obj['dd_body_' + key] = value
    return obj


def tape_girth(mesh, matrix, world, height, limit):
    from .measurements import slice_mesh_z
    from .placement_fit import convex_hull
    points = [point for segment in slice_mesh_z(mesh, matrix, height, world) for point in segment if abs(point[0]) <= limit]
    hull = convex_hull(points)
    return sum(math.dist(hull[index - 1], hull[index]) for index in range(len(hull))) if len(hull) > 2 else 0.0


def body_report(obj):
    import bmesh
    mesh = obj.data
    matrix = obj.matrix_world
    world = [matrix @ vertex.co for vertex in mesh.vertices]
    height = max(point.z for point in world) - min(point.z for point in world)
    limit = obj.get('dd_body_shoulder_width', .4) / 2 - .02
    girths = {key: tape_girth(mesh, matrix, world, min(point.z for point in world) + fraction * height, limit)
              for key, fraction in (('bust', .72), ('waist', .62), ('hip', .50))}
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        open_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
        components = 0
        seen = set()
        for vertex in bm.verts:
            if vertex.index in seen:
                continue
            components += 1
            pending = [vertex]
            seen.add(vertex.index)
            while pending:
                current = pending.pop()
                for edge in current.link_edges:
                    other = edge.other_vert(current)
                    if other.index not in seen:
                        seen.add(other.index)
                        pending.append(other)
    finally:
        bm.free()
    low = [min(point[axis] for point in world) for axis in range(3)]
    high = [max(point[axis] for point in world) for axis in range(3)]
    return dict(name=obj.get('dd_test_body', obj.name), height=height, girths=girths, open_edges=open_edges,
                components=components, vertices=len(mesh.vertices), faces=len(mesh.polygons),
                bounds=[low, high])
