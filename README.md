# Devil Designer

A movable 2D clothing-pattern editor and cloth authoring tool for Blender.

## Documentation

Full documentation, user guides, pattern drafting manuals, and simulation references are hosted at:

**https://artbyo3.github.io/DEVIL-DESIGNER/**

## Installation

Download `devil_designer-0.10.0.zip` from [Releases](https://github.com/Artbyo3/DEVIL-DESIGNER/releases) or build it locally with `python tools/build.py`, then install in Blender via **Edit > Preferences > Add-ons > Install from Disk...**.

For full setup details, requirements, and upgrading instructions, see the [Installation Guide](https://artbyo3.github.io/DEVIL-DESIGNER/install/).

## Links

- [Documentation](https://artbyo3.github.io/DEVIL-DESIGNER/)
- [Releases](https://github.com/Artbyo3/DEVIL-DESIGNER/releases)
- [Issues](https://github.com/Artbyo3/DEVIL-DESIGNER/issues)
- License: [GPL-3.0-or-later](LICENSE)

## Fork notes

This repository is a GPL-3.0-or-later fork of Devil Designer by Artbyo3. All credit for the
add-on, its editor and its cloth workflow goes to the original author; the license, author
metadata and file headers are unchanged. The fork adds a headless (no editor window) garment
pipeline and leaves the editor behaviour as it was. Details: [HEADLESS.md](HEADLESS.md).

Changes in this fork:

- `devil_designer/api.py`: `make_garment()` runs pattern -> dress a body -> cloth -> kept mesh
  from a script and returns a JSON-ready report.
- `devil_designer/placement_fit.py`: measures the body (girths, armpit, shoulders, arm axes) from
  mesh slices and places panels around smoothed body sections; sleeves wrap around the arms.
- `devil_designer/starters.py`: two new patterns, a set-in-sleeve tee and a fitted skirt. The
  original starters are unchanged.
- `devil_designer/qa.py`: numeric checks (open seams, openings, body penetration, self
  intersection, stretch spikes, UV sanity, hem evenness) with one threshold table.
- `devil_designer/garment_export.py`: FBX/OBJ export with per-piece materials, optional
  thickness and optional skin-weight transfer, verified by re-importing the file.
- `devil_designer/testbodies.py`: two procedural dress-form bodies for tests.
- `tools/dd_cli.py`, `tools/dd_views.py`: command line runner and 8-view contact sheets.
- `tools/dev.py`: the `DD_BLENDER` environment variable selects the Blender executable.
