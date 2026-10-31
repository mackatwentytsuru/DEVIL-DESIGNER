import sys
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from devil_designer import api, garment_export
from tools.workspace import prepare_scratch

checks = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    checks.append(message)
    print('PASS:', message, flush=True)


def simple_rig(body):
    data = bpy.data.armatures.new('Test Rig')
    rig = bpy.data.objects.new('Test Rig', data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    with bpy.context.temp_override(object=rig, active_object=rig):
        bpy.ops.object.mode_set(mode='EDIT')
        for name, head, tail in (('spine', (0, 0, .8), (0, 0, 1.3)), ('thigh_l', (.08, 0, .8), (.08, 0, .4)),
                                 ('thigh_r', (-.08, 0, .8), (-.08, 0, .4))):
            bone = data.edit_bones.new(name)
            bone.head, bone.tail = head, tail
        bpy.ops.object.mode_set(mode='OBJECT')
    groups = {name: body.vertex_groups.new(name=name) for name in ('spine', 'thigh_l', 'thigh_r')}
    for vertex in body.data.vertices:
        name = 'spine' if vertex.co.z > .8 else 'thigh_l' if vertex.co.x > 0 else 'thigh_r'
        groups[name].add([vertex.index], 1.0, 'REPLACE')
    return rig


bpy.ops.wm.read_factory_settings(use_empty=True)
result = api.make_garment('skirt', 'A', 'cotton', frames=60)
check(result.report['metrics']['topology']['faces'] > 1000, 'headless skirt produced a mesh')
check(result.report['seconds']['simulation'] > 0, 'simulation time reported')
out = prepare_scratch() / 'headless_export'
report = garment_export.export_garment(result.garment, out / 'skirt', ['fbx', 'obj'], 'cc5', .001)
check(report['pieces'] == ['Skirt front', 'Skirt back'], 'empty duplicate piece groups from Keep are ignored')
for item in report['files']:
    check(item['passed'], f"{item['file']} re-imports with matching faces, UVs and bounds ({item['bounds_error_m']} m)")
    check(item['uv_in_unit_square'], f"{item['file']} keeps pattern UVs inside 0-1")
    check(item['materials'] == ['DD_Skirt_back', 'DD_Skirt_front'], f"{item['file']} keeps one material per pattern piece")
check(report['files'][0]['faces'] == 2 * result.report['metrics']['topology']['faces'] + sum(
    result.report['metrics']['topology']['opening_sizes']), 'solidify thickness doubles faces and closes the rim')
rig = simple_rig(result.body)
rigged = garment_export.export_garment(result.garment, out / 'skirt_rigged', ['fbx'], 'ue', 0.0, rig, result.body)
check(rigged['weights']['bones'] == 3 and rigged['weights']['unweighted_vertices'] == 0, 'skin weights transferred from the body')
check(rigged['files'][0]['armature'] and rigged['files'][0]['passed'], 'rigged FBX re-imports with its armature')
check({'spine', 'thigh_l', 'thigh_r'} <= set(rigged['files'][0]['groups']), 'bone vertex groups survive the FBX round trip')
print(f'ALL {len(checks)} HEADLESS EXPORT CHECKS PASSED', flush=True)
