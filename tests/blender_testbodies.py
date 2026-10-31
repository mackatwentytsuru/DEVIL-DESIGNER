import json
import sys
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from devil_designer import testbodies

checks = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    checks.append(message)
    print('PASS:', message, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
reports = {}
for key, spec in testbodies.BODIES.items():
    body = testbodies.make_body(key)
    report = testbodies.body_report(body)
    reports[key] = report
    print('BODY', json.dumps(report), flush=True)
    check(report['open_edges'] == 0, f'body {key} is closed')
    check(report['components'] == 1, f'body {key} is one watertight shell')
    check(abs(report['height'] - spec.height) < .02, f'body {key} height is {spec.height} m')
    check(abs(report['bounds'][0][2]) < .005, f'body {key} stands on z=0')
    check(abs((report['bounds'][0][0] + report['bounds'][1][0]) / 2) < .01, f'body {key} is centred on x')
    for girth in ('bust', 'waist', 'hip'):
        measured = report['girths'][girth]
        target = getattr(spec, girth)
        check(abs(measured - target) / target < .08, f'body {key} {girth} {measured:.3f} m within 8% of {target} m')
    check(report['faces'] <= testbodies.TARGET_FACES * 1.05, f'body {key} collider stays light')
    front = min(v.co.y for v in body.data.vertices if abs(v.co.z - .72 * spec.height) < .01)
    back = max(v.co.y for v in body.data.vertices if abs(v.co.z - .72 * spec.height) < .01)
    check(-front > back - .03, f'body {key} faces -Y (bust forward)')
check(reports['A']['bounds'][1][0] < reports['B']['bounds'][1][0], 'body B spreads its arms wider than body A')
for bad in (testbodies.BodySpec('X', 3.0, .4, .9, .7, .9, 30, .2), testbodies.BodySpec('Y', 1.6, .4, .9, .7, .9, 95, .2)):
    try:
        testbodies.validate_spec(bad)
    except ValueError:
        checks.append('invalid spec refused')
    else:
        raise AssertionError('invalid body spec accepted')
print(f'ALL {len(checks)} TEST BODY CHECKS PASSED', flush=True)
