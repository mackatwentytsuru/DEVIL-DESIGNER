import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
EXIT_PASSED, EXIT_ERROR, EXIT_QA_FAILED = 0, 2, 3


def parse(argv):
    parser = argparse.ArgumentParser(prog='dd_cli', description='Make one Devil Designer garment without the editor.')
    parser.add_argument('--garment', required=True, choices=('tee', 'tank', 'skirt'))
    parser.add_argument('--body', default='A', help='Built-in test body key (A or B) or the name of a mesh object.')
    parser.add_argument('--body-file', help='A .blend file to open first; --body then names the body object in it.')
    parser.add_argument('--fabric', default='cotton')
    parser.add_argument('--placement', default='fitted', choices=('fitted', 'starter'))
    parser.add_argument('--quality', type=int)
    parser.add_argument('--frames', type=int)
    parser.add_argument('--spacing', type=float, help='Mesh spacing in metres (default 0.02).')
    parser.add_argument('--clearance', type=float, help='Initial body clearance in metres (default 0.03).')
    parser.add_argument('--weld', type=float, help='Seam weld distance in metres (default 0.01).')
    parser.add_argument('--self-collision', choices=('on', 'off'))
    parser.add_argument('--self-distance', type=float, help='Self collision distance in metres (default 0.003).')
    parser.add_argument('--gravity-hold', type=int, help='Frames without gravity while seams close (default 30).')
    parser.add_argument('--sewing-force', type=float, help='Maximum sewing force (default 50).')
    parser.add_argument('--self-collision-from', type=int, help='Frame offset where self collision starts (default 0).')
    parser.add_argument('--seam-band', type=int, help='Face rings around seams left out of self collision (default 0).')
    parser.add_argument('--out', required=True, help='Output folder for report.json and other files.')
    parser.add_argument('--export', default='', help='Comma list of fbx,obj.')
    parser.add_argument('--target', default='cc5', choices=('cc5', 'ue', 'blender'))
    parser.add_argument('--thickness', type=float, default=0.0, help='Solidify thickness in metres for export.')
    parser.add_argument('--armature', help='Armature object name for optional weight transfer on export.')
    parser.add_argument('--save-blend', action='store_true')
    parser.add_argument('--render', action='store_true', help='Write an 8-view x 2-light contact sheet.')
    return parser.parse_args(argv)


def tuning(args):
    values = dict(self_collision=None if args.self_collision is None else args.self_collision == 'on',
                  self_distance=args.self_distance, gravity_hold=args.gravity_hold, sewing_force=args.sewing_force,
                  self_collision_from=args.self_collision_from, seam_band=args.seam_band)
    return {key: value for key, value in values.items() if value is not None}


def open_scene(args):
    import bpy
    if args.body_file:
        bpy.ops.wm.open_mainfile(filepath=str(Path(args.body_file).resolve()))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    if args.body in ('A', 'B'):
        return args.body
    body = bpy.data.objects.get(args.body)
    if body is None or body.type != 'MESH':
        raise ValueError(f'No mesh object named {args.body!r} in the scene.')
    return body


def run(args):
    import bpy
    if hasattr(bpy.types.Scene, 'dd_document') and 'devil_designer' not in sys.modules:
        raise RuntimeError('An installed Devil Designer is already enabled. Run Blender with --factory-startup.')
    sys.path.insert(0, str(ROOT))
    from devil_designer import api
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    body = open_scene(args)
    result = api.make_garment(args.garment, body, args.fabric, quality=args.quality, frames=args.frames,
                              spacing=args.spacing, clearance=args.clearance, weld_distance=args.weld,
                              placement=args.placement, **tuning(args))
    report = result.report
    formats = [item.strip().lower() for item in args.export.split(',') if item.strip()]
    if formats:
        from devil_designer import garment_export
        armature = bpy.data.objects.get(args.armature) if args.armature else None
        report['exports'] = garment_export.export_garment(result.garment, out / f'{args.garment}_{report["body"]}',
                                                          formats, args.target, args.thickness, armature, result.body)
    if args.render:
        from tools import dd_views
        report['pictures'] = dd_views.contact_sheet(result.garment, result.body, out / f'{args.garment}_{report["body"]}_sheet.png')
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(out / 'garment.blend'))
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('DD_REPORT', json.dumps(dict(passed=report['qa']['passed'], failed=report['qa']['failed'],
                                        seconds=report['seconds'], seams=report['metrics']['seams'])), flush=True)
    return EXIT_PASSED if report['qa']['passed'] else EXIT_QA_FAILED


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    try:
        code = run(parse(argv))
    except (ValueError, RuntimeError, OSError) as failure:
        print('DD_ERROR', str(failure), flush=True)
        code = EXIT_ERROR
    sys.exit(code)


if __name__ == '__main__':
    main()
