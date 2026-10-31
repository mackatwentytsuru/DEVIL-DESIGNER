# Headless garments (fork addition)

Make a Tee, Tank or Skirt on a body from a script, without opening the pattern editor:
pattern -> dress the body -> Blender cloth -> kept triangle mesh with pattern UVs -> FBX/OBJ.
Every run writes a JSON report with numeric pass/fail checks, so a script (or a person) can
decide whether the garment is usable without looking at it first.

Marks used below: **[tested]** = checked by a test or a measured run in this fork;
**[not tested]** = written from documentation or experience, not run here.

## Requirements

- Blender 5.2 or newer. **[tested: 5.2.3 portable build, Windows]**
- Run Blender with `--background --factory-startup`. Factory startup stops an installed copy of
  the add-on from loading, so the source in this repository is the one that runs. The command
  line tool refuses to run when another copy is already registered. **[tested]**
- No GPU is needed. Simulation and the contact-sheet renders run on the CPU. **[tested]**

## One garment from the command line

```
blender --background --factory-startup --python tools/dd_cli.py -- --garment tee --body A --fabric cotton --out OUTDIR
```

- `--garment tee|tank|skirt`, `--body A|B` (built-in test bodies) or the name of a mesh object
  together with `--body-file scene.blend`.
- `--fabric silk|knit|cotton|linen|denim|leather`.
- `--save-blend` writes `OUTDIR/garment.blend`; `--render` writes the contact sheet;
  `--export fbx,obj --target cc5|ue|blender [--thickness 0.001] [--armature NAME]` writes files.
- Tuning flags (defaults come from the per-garment recipe): `--quality --frames --spacing
  --clearance --weld --self-collision on|off --self-collision-from N --seam-band N
  --gravity-hold N --sewing-force F --placement fitted|starter`.
- Exit code 0 = QA passed, 3 = QA failed (files are still written), 2 = error. **[tested]**
- `OUTDIR/report.json` holds everything; the log also prints one `DD_REPORT {...}` line.

## Python API

```python
import sys; sys.path.insert(0, REPO)
from devil_designer import api, garment_export
result = api.make_garment('skirt', 'B', 'silk')          # GarmentResult
result.garment, result.body, result.report['qa']['passed']
garment_export.export_garment(result.garment, OUT / 'skirt_B', ['fbx', 'obj'], 'cc5', .001)
```

`make_garment(kind, body='A', fabric='COTTON', quality=None, frames=None, spacing=None,
clearance=None, weld_distance=None, placement='fitted', thresholds=None, **settings)` registers
the add-on when needed, detaches the add-on's depsgraph handler while it works (see pitfalls),
and returns the kept garment object, the simulation object, the body and the report.

## What "fitted" placement does

The editor's starter arrangement records put every panel centre at the middle of a body volume.
Starter patterns, however, are drawn in absolute heights above the floor, so on a 1.6 m A-pose
body the tee landed about 10 cm and the skirt about 19 cm too high, and the wide upper rows of
the tee were wrapped around the neck section. Headless runs therefore use `placement_fit.py`:

1. Slice the body mesh, keep the torso (and legs) loops, drop separated arms, and measure waist,
   hip and chest girths, armpit height, shoulder-top heights and the arm axes. These replace the
   add-on's `estimate_body_measurements`, whose widths include A-pose arms (waist found 8 cm too
   high and chest 93 cm instead of 84 cm on test body A). **[tested]**
2. Build the pattern from those landmarks (the new set-in-sleeve tee and fitted skirt; the tank
   uses the original starter, lifted until its straps clear the shoulder surface). **[tested]**
3. Wrap each torso panel around the offset convex hull of the body section at its own height.
   Rows are widened only when the panels would overlap at the sides. For tops the arms are
   clipped from the section with a limit that grows from the armpit to the shoulder, and each
   section is merged with the 8 cm below it, so the shape changes smoothly with height. Sleeves
   are wrapped around the measured arm axis. Vertices closer than 6 mm to the body are pushed
   out. **[tested]**
4. Hold gravity at zero for 30 frames while the seams close, then ramp it in. **[tested]**

Blender cloth uses the placed 3D panel as its rest shape (not the flat pattern), so any
distortion in the placement stays in the result. The report therefore includes
`metrics.initial_stretch` next to `metrics.stretch`.

## QA metrics and thresholds

All limits are in `devil_designer/qa.py`, `THRESHOLDS`, and can be overridden per call with
`make_garment(..., thresholds={...})`. `report.qa` has `passed`, `failed` (names of failed
checks), `checks` and the limits used.

| Check | Measured as | Pass when |
| --- | --- | --- |
| `open_seams` | sewing pairs farther apart than the weld distance at the kept frame | 0 |
| `components` | connected pieces of the kept mesh | 1 |
| `openings` | boundary loops (tee/tank 4: hem, neck, 2 armholes or cuffs; skirt 2) | equals expected |
| `penetration_fraction` / `_depth` | garment vertices on the inner side of the nearest body face | <= 1 % and <= 10 mm |
| `self_intersection` | faces that intersect a non-neighbouring face | <= 1 % of faces |
| `stretch` | 99th percentile of edge length / pattern length (edges >= 3 mm) | <= 1.35 |
| `spikes` | edges over 2x their pattern length and more than 10 mm longer | 0 |
| `uv_flips`, `uv_range` | faces with minority UV winding; UVs outside 0-1 | 0 |
| `hem_even`, `hem_front_back` (skirt) | std of hem heights; front mean minus back mean | <= 2 cm; <= 3 cm |

The report also lists `metrics.seam_detail` (open pairs and worst gap per seam, with its
location) and `trace` (open pairs every 20 frames) for debugging.

## Export for Character Creator and Unreal Engine

`garment_export.export_garment(garment, base_path, ['fbx', 'obj'], target, thickness, armature, body)`
works on a copy: it keeps the pattern UVs, gives each pattern piece its own material
(`DD_<piece name>`), keeps one vertex group per piece, optionally adds outward Solidify
thickness, and optionally transfers skin weights from a weighted body (Data Transfer, nearest
face interpolated, at most 4 influences, normalized) and parents to the armature.

- FBX: metres in Blender, `apply_scale_options='FBX_SCALE_UNITS'`, forward -Z, up Y. Re-imported
  into Blender with the same face count, UVs and bounds within 1 mm. **[tested]**
- OBJ: centimetres for `cc5`/`ue` (scale 100), forward -Z, up Y, i.e. (x, z, -y), materials and
  piece groups. **[tested by re-import]**
- Rigged FBX: bone vertex groups and the armature survive the round trip. **[tested with a
  three-bone test rig only]**
- Import into Character Creator 5 as clothing and into Unreal Engine as a skeletal or static
  mesh. **[not tested]** Use FBX for Unreal Engine and either file for Character Creator; check
  the size on import and turn on two-sided materials or export with thickness.

## Contact sheets

`tools/dd_views.py` renders 8 directions (every 45 degrees, starting at the front and turning
towards the body's left side) under a soft key light and a hard side light with Cycles on the
CPU, 320 x 480 per view, and joins them into one 2560 x 960 sheet (top row soft, bottom row
hard). **[tested, about 20 s per sheet]**

```
blender --background --factory-startup --python tools/dd_views.py -- --blend OUTDIR/garment.blend --out sheet.png
```

## Test bodies

`devil_designer/testbodies.py` builds closed, smooth dress forms (voxel union of lofted torso,
limbs and head; metres; feet on z = 0; facing -Y): A = 160 cm, arms 30 degrees from the torso,
legs 16 cm apart; B = 175 cm, broader, arms 45 degrees, legs 26 cm apart. Girths measured like a tape (convex hull, arms clipped) are within 4 % of the specification. **[tested]**

## Pitfalls

- The add-on's depsgraph handler can rebuild panels when objects are deleted. `api.quiet_handlers()`
  detaches it while the API runs; do the same around your own clean-up code. **[tested]**
- Bodies must be in metres, Z up, facing -Y, with outward normals (penetration uses the nearest
  face normal). **[tested on the test bodies]**
- Fabric names are upper case inside documents (`COTTON`); the API accepts any case. **[tested]**
- Without the add-on registered, its scene properties are not readable with `scene.get()` in
  Blender 5.x; the serialized document is also stored on each panel object (`dd_document`).
- Self collision plus zero-length sewing springs creates zipper ridges along seams. Recipes keep
  one face ring around seams out of self collision (`seam_band=1`) or start self collision after
  the seams have closed (`self_collision_from=50`). **[tested]**
- Narrow A-poses (arms about 30 degrees from the torso) leave little room under the arm: tee
  armhole pairs stop closing at 11-18 mm. All recipes therefore weld seam pairs that end within
  one mesh spacing (20 mm); the report still lists the real gaps. **[tested]**
- Seam gaps vary by about 1 mm between identical runs (multi-threaded solver), so results right
  at a threshold can flip. **[tested]**
- In Blender 5.x the kept mesh gets an empty duplicate of every piece vertex group
  (`Piece X.001`), because group names now live on the mesh. The exporter ignores them. **[tested]**

## Per-garment recipes and measured results

Defaults live in `devil_designer/api.py`, `RECIPES`: quality 14, 240 frames, 2 cm mesh spacing,
3 cm clearance, weld 2 cm, gravity held for 30 frames. Tee: gravity held 60 frames and self
collision from frame 50. Tank and skirt: one face ring around seams left out of self collision.

Measured on the two test bodies (Blender 5.2.3, CPU; seconds = cloth frames only): **[tested]**

| Garment | Body | Fabric | QA | Open seams (max gap) | Openings | Penetration | Self-int. | Stretch p99 | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| skirt | A | cotton | pass | 0 (3.0 mm) | 2 | 0 % | 0 % | 1.20 | 44 |
| skirt | A | silk | pass | 0 (2.9 mm) | 2 | 0 % | 0.36 % | 1.19 | 46 |
| skirt | B | cotton | pass | 0 (2.0 mm) | 2 | 0 % | 0.23 % | 1.13 | 65 |
| skirt | B | silk | pass | 0 (1.5 mm) | 2 | 0 % | 0.15 % | 1.13 | 53 |
| tank | A | cotton | pass | 0 (12.4 mm) | 4 | 0 % | 0.11 % | 1.21 | 32 |
| tank | A | knit | pass | 0 (3.2 mm) | 4 | 0 % | 0 % | 1.19 | 33 |
| tank | B | cotton | pass | 0 (1.5 mm) | 4 | 0 % | 0 % | 1.16 | 48 |
| tank | B | knit | pass | 0 (2.3 mm) | 4 | 0 % | 0 % | 1.16 | 33 |
| tee | A | cotton | pass | 0 (17.6 mm) | 4 | 0 % | 0.50 % | 1.34 | 102 |
| tee | A | knit | pass | 0 (10.3 mm) | 4 | 0 % | 0.24 % | 1.25 | 56 |
| tee | B | cotton | fail (stretch) | 0 (11.4 mm) | 4 | 0 % | 0.28 % | 1.36 | 56 |
| tee | B | knit | pass | 0 (5.2 mm) | 4 | 0 % | 0.10 % | 1.27 | 50 |

Skirt hems: standard deviation 0.7-0.8 cm, front minus back -0.5 to -0.7 cm. The cotton tee sits
at the stretch limit: other settings tried (gravity 30 frames, quality 18, weaker sewing, 1.5 cm
spacing) each fixed one body and broke another; the stretched edges are along the armhole seam.
