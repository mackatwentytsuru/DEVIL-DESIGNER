import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
VIEW_COUNT = 8
LIGHTINGS = ('soft', 'hard')
GARMENT_COLOR = (.72, .16, .24, 1.0)
BODY_COLOR = (.62, .62, .66, 1.0)


def principled(name, color, roughness):
    import bpy
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = color
    shader.inputs['Roughness'].default_value = roughness
    return material


def dress_materials(garment, body):
    for obj, material in ((garment, principled('DD View Garment', GARMENT_COLOR, .85)),
                          (body, principled('DD View Body', BODY_COLOR, .55))):
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.material_index = 0


def isolate(scene, keep):
    hidden = []
    for obj in scene.objects:
        if obj not in keep and not obj.hide_render and obj.type in {'MESH', 'CURVE', 'EMPTY'}:
            obj.hide_render = True
            hidden.append(obj)
    return hidden


def setup_render(scene, size, samples):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    for transform in ('Standard', 'Filmic', 'AgX'):
        try:
            scene.view_settings.view_transform = transform
            break
        except TypeError:
            continue


def light_rig(scene, kind):
    import bpy
    world = bpy.data.worlds.get('DD View World') or bpy.data.worlds.new('DD View World')
    world.use_nodes = True
    background = next(node for node in world.node_tree.nodes if node.type == 'BACKGROUND')
    background.inputs['Color'].default_value = (.86, .88, .91, 1)
    background.inputs['Strength'].default_value = .55 if kind == 'soft' else .12
    scene.world = world
    lamp = bpy.data.lights.new('DD View ' + kind, 'AREA' if kind == 'soft' else 'SUN')
    if kind == 'soft':
        lamp.energy, lamp.size = 220.0, 2.5
    else:
        lamp.energy, lamp.angle = 4.5, math.radians(1.0)
    light = bpy.data.objects.new(lamp.name, lamp)
    scene.collection.objects.link(light)
    return light


def place_light(light, kind, centre, angle):
    from mathutils import Vector
    if kind == 'soft':
        offset = Vector((-1.6, -2.4, 1.8))
    else:
        offset = Vector((-3.0, -.4, .6))
    rotated = Vector((offset.x * math.cos(angle) - offset.y * math.sin(angle),
                      offset.x * math.sin(angle) + offset.y * math.cos(angle), offset.z))
    light.location = centre + rotated
    light.rotation_euler = (centre - light.location).to_track_quat('-Z', 'Y').to_euler()


def framing(garment):
    from mathutils import Vector
    corners = [garment.matrix_world @ Vector(corner) for corner in garment.bound_box]
    low = Vector([min(point[axis] for point in corners) for axis in range(3)])
    high = Vector([max(point[axis] for point in corners) for axis in range(3)])
    centre = (low + high) / 2
    span = max(high.z - low.z, high.x - low.x, high.y - low.y)
    return centre, span * 1.35


def render_views(scene, camera, light, kind, centre, scale, folder, stem):
    from mathutils import Vector
    paths = []
    for index in range(VIEW_COUNT):
        angle = math.tau * index / VIEW_COUNT
        camera.location = centre + Vector((5 * math.sin(angle), -5 * math.cos(angle), 0))
        camera.rotation_euler = (centre - camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.ortho_scale = scale
        place_light(light, kind, centre, angle)
        path = folder / f'{stem}_{kind}_{index * 360 // VIEW_COUNT:03d}.png'
        scene.render.filepath = str(path)
        import bpy
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    return paths


def compose(rows, path, size):
    import bpy
    import numpy
    width, height = size
    sheet = numpy.ones((height * len(rows), width * VIEW_COUNT, 4), dtype=numpy.float32)
    for row_index, row in enumerate(rows):
        for column, view in enumerate(row):
            image = bpy.data.images.load(str(view))
            pixels = numpy.array(image.pixels[:], dtype=numpy.float32).reshape(image.size[1], image.size[0], image.channels)
            top = (len(rows) - 1 - row_index) * height
            sheet[top:top + height, column * width:(column + 1) * width, :pixels.shape[2]] = pixels
            bpy.data.images.remove(image)
    output = bpy.data.images.new('DD Contact Sheet', width * VIEW_COUNT, height * len(rows), alpha=False)
    output.pixels.foreach_set(sheet.ravel())
    output.filepath_raw = str(path)
    output.file_format = 'PNG'
    output.save()
    bpy.data.images.remove(output)
    return path


def contact_sheet(garment, body, path, size=(320, 480), samples=24):
    import bpy
    scene = bpy.context.scene
    path = Path(path)
    folder = path.parent / (path.stem + '_views')
    folder.mkdir(parents=True, exist_ok=True)
    dress_materials(garment, body)
    hidden = isolate(scene, {garment, body})
    setup_render(scene, size, samples)
    camera_data = bpy.data.cameras.new('DD View Camera')
    camera_data.type = 'ORTHO'
    camera = bpy.data.objects.new('DD View Camera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    centre, scale = framing(garment)
    rows = []
    try:
        for kind in LIGHTINGS:
            light = light_rig(scene, kind)
            rows.append(render_views(scene, camera, light, kind, centre, scale, folder, path.stem))
            bpy.data.objects.remove(light)
    finally:
        for obj in hidden:
            obj.hide_render = False
        bpy.data.objects.remove(camera)
    compose(rows, path, size)
    return dict(sheet=str(path), views=[str(view) for row in rows for view in row],
                layout='rows: soft key light, hard side light; columns: 0-315 degrees, 0 = front, turning to the left side')


def main():
    import bpy
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(prog='dd_views')
    parser.add_argument('--blend', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--samples', type=int, default=24)
    args = parser.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()))
    scene = bpy.context.scene
    garment = next(obj for obj in scene.objects if obj.get('dd_kind') == 'final')
    body = next(obj for obj in scene.objects if obj.get('dd_test_body') or obj.type == 'MESH' and not obj.get('dd_kind'))
    print('DD_VIEWS', contact_sheet(garment, body, args.out, samples=args.samples)['sheet'], flush=True)


if __name__ == '__main__':
    main()
