import math
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

GARMENT_KINDS = ('tee', 'tank', 'skirt')
FABRICS = ('SILK', 'KNIT', 'COTTON', 'LINEN', 'DENIM', 'LEATHER')
BASE_SETTINGS = dict(quality=14, frames=240, spacing=.02, clearance=.03, weld_distance=.01, self_collision=True,
                     self_distance=.003, gravity_hold=30, sewing_force=50.0, self_collision_from=0,
                     seam_band=0)
RECIPES = {
    'tee': dict(BASE_SETTINGS, weld_distance=.015, self_collision_from=50),
    'tank': dict(BASE_SETTINGS, seam_band=1),
    'skirt': dict(BASE_SETTINGS, seam_band=1),
}
TRACE_EVERY = 20
PLACEMENTS = ('fitted', 'starter')


@dataclass
class GarmentResult:
    garment: object
    simulation: object
    body: object
    report: dict = field(default_factory=dict)

    @property
    def passed(self):
        return bool(self.report.get('qa', {}).get('passed'))


def normalize_fabric(fabric):
    name = str(fabric).strip().upper()
    if name not in FABRICS:
        raise ValueError(f'Unknown fabric {fabric!r}. Choose one of: {", ".join(FABRICS)}.')
    return name


def normalize_kind(kind):
    name = str(kind).strip().lower()
    if name not in GARMENT_KINDS:
        raise ValueError(f'Unknown garment {kind!r}. Choose one of: {", ".join(GARMENT_KINDS)}.')
    return name


def ensure_registered():
    import bpy
    if hasattr(bpy.types.Scene, 'dd_document'):
        return False
    from . import register
    register()
    return True


@contextmanager
def quiet_handlers():
    import bpy
    from . import live_panels
    handlers = bpy.app.handlers.depsgraph_update_post
    attached = live_panels.capture_updates in handlers
    if attached:
        handlers.remove(live_panels.capture_updates)
    try:
        yield
    finally:
        if attached and live_panels.capture_updates not in handlers:
            handlers.append(live_panels.capture_updates)


def resolve_body(body, context):
    from . import testbodies
    if isinstance(body, (str, testbodies.BodySpec)):
        return testbodies.make_body(body)
    if body is None or getattr(body, 'type', None) != 'MESH' or body.name not in context.scene.objects:
        raise ValueError('Pass a body key (A, B), a BodySpec, or a mesh object in the current scene.')
    return body


def settings_for(kind, overrides):
    values = dict(RECIPES[kind])
    for key, value in overrides.items():
        if value is not None:
            if key not in values:
                raise ValueError(f'Unknown setting {key}.')
            values[key] = value
    if not 5 <= int(values['quality']) <= 40 or not 10 <= int(values['frames']) <= 1000:
        raise ValueError('Quality must be 5-40 steps and frames 10-1000.')
    return values


def apply_scene_settings(scene, values):
    scene.dd_quality = int(values['quality'])
    scene.dd_frames = int(values['frames'])
    scene.dd_spacing = float(values['spacing'])
    scene.dd_clearance = float(values['clearance'])
    scene.dd_weld_distance = float(values['weld_distance'])
    scene.dd_self_collision = bool(values['self_collision'])
    scene.frame_start = 1
    scene.frame_set(1)


def seam_band(simulation, rings):
    import json
    neighbours = {}
    for polygon in simulation.data.polygons:
        for vertex in polygon.vertices:
            neighbours.setdefault(vertex, set()).update(polygon.vertices)
    band = {index for pair in json.loads(simulation.get('dd_sewing_pairs', '[]')) for index in pair}
    frontier = set(band)
    for _ in range(rings):
        frontier = {other for vertex in frontier for other in neighbours.get(vertex, ())} - band
        band |= frontier
    group = simulation.vertex_groups.new(name='DD Seam Band')
    group.add(sorted(band), 1.0, 'REPLACE')
    return group


def tune_cloth(simulation, values, start):
    cloth = next(modifier for modifier in simulation.modifiers if modifier.type == 'CLOTH')
    collision = cloth.collision_settings
    collision.self_distance_min = float(values['self_distance'])
    cloth.settings.sewing_force_max = float(values['sewing_force'])
    if values['self_collision'] and int(values['seam_band']) > 0:
        band = seam_band(simulation, int(values['seam_band']))
        collision.vertex_group_self_collisions = band.name
    delay = int(values['self_collision_from'])
    if values['self_collision'] and delay > 0:
        for frame, state in ((start, False), (start + delay - 1, False), (start + delay, True)):
            collision.use_self_collision = state
            collision.keyframe_insert('use_self_collision', frame=frame)
    return cloth


def build_document(kind, measurements, fabric, placement):
    from . import starters
    if placement == 'starter':
        generator = starters.STARTER_GENERATORS['STARTER_' + kind.upper()][1]
    else:
        generator = dict(tee=starters.create_set_in_tee_starter, tank=starters.create_tank_starter,
                         skirt=starters.create_fitted_skirt_starter)[kind]
    return generator(measurements, fabric)


def seam_state(simulation, depsgraph, tolerance):
    from .qa import seam_gaps
    gaps = seam_gaps(simulation, depsgraph)
    return dict(open=sum(1 for gap in gaps if gap > tolerance), max_gap=max(gaps, default=0.0),
                mean_gap=sum(gaps) / len(gaps) if gaps else 0.0)


def simulate(context, values, hold):
    from . import garment, layering
    from .placement_fit import hold_gravity
    scene = context.scene
    tolerance = values['weld_distance']
    simulation = garment.compile_garment(context)
    layering.configure_collision_collection(context, simulation)
    cloth = tune_cloth(simulation, values, scene.frame_start)
    if hold and values['gravity_hold'] > 0:
        hold_gravity(simulation, scene.frame_start, int(values['gravity_hold']))
    trace = []
    started = time.perf_counter()
    for frame in range(scene.frame_start, cloth.point_cache.frame_end + 1):
        scene.frame_set(frame)
        if (frame - scene.frame_start) % TRACE_EVERY == 0 or frame == cloth.point_cache.frame_end:
            state = seam_state(simulation, context.evaluated_depsgraph_get(), tolerance)
            trace.append(dict(frame=frame, **{key: round(value, 5) for key, value in state.items()}))
    return simulation, trace, time.perf_counter() - started


def dress(context, body, measurements, placement, clearance):
    from . import placement_fit
    if placement == 'starter':
        return measurements, None
    model = placement_fit.BodyModel(body, context.evaluated_depsgraph_get())
    landmarks, arms = placement_fit.body_landmarks(model)
    return dict(measurements, **landmarks), (model, arms, landmarks)


def make_garment(kind, body='A', fabric='COTTON', quality=None, frames=None, spacing=None, clearance=None,
                 weld_distance=None, context=None, placement='fitted', thresholds=None, **settings):
    import bpy
    from . import garment, qa, placement_fit
    from .measurements import estimate_body_measurements
    context = context or bpy.context
    kind, fabric = normalize_kind(kind), normalize_fabric(fabric)
    if placement not in PLACEMENTS:
        raise ValueError(f'Unknown placement {placement!r}. Choose one of: {", ".join(PLACEMENTS)}.')
    values = settings_for(kind, dict(settings, quality=quality, frames=frames, spacing=spacing, clearance=clearance,
                                     weld_distance=weld_distance))
    ensure_registered()
    started = time.perf_counter()
    with quiet_handlers():
        scene = context.scene
        body = resolve_body(body, context)
        apply_scene_settings(scene, values)
        scene.dd_avatar = body
        measurements, fitted = dress(context, body, estimate_body_measurements(body, scene) or {}, placement,
                                     values['clearance'])
        document = build_document(kind, measurements, fabric, placement)
        if fitted:
            placement_fit.prepare_document(document)
        scene.dd_document = document.dumps()
        garment.build_panels(context)
        lift = placement_fit.top_lift(fitted[0], document, fitted[2]) if fitted and kind != 'skirt' else 0.0
        profile = placement_fit.top_profile(fitted[0], fitted[2]) if fitted and kind != 'skirt' else (None, 0.0)
        dressing = placement_fit.dress_panels(context, document, *fitted, values['clearance'], lift, profile) if fitted else {}
        simulation, trace, sim_seconds = simulate(context, values, bool(fitted))
        final, unwelded = garment.keep_drape(context)
        scene['dd_unwelded_seams'] = unwelded
        low, high = garment.bounds(body)
        metrics = qa.measure(final, simulation, body, context.evaluated_depsgraph_get(), kind,
                             garment.document(scene).uv_layout['scale'], ((low.x + high.x) / 2, (low.y + high.y) / 2),
                             garment.document(scene), values['weld_distance'])
    verdict = qa.judge(metrics, kind, thresholds)
    report = dict(kind=kind, fabric=fabric, body=body.get('dd_test_body', body.name), placement=placement,
                  settings=values, measurements={key: value for key, value in measurements.items()
                                                 if isinstance(value, (int, float, bool))},
                  dressing=dressing, seconds=dict(simulation=round(sim_seconds, 2),
                                                  total=round(time.perf_counter() - started, 2)),
                  unwelded_seams=unwelded, trace=trace, metrics=metrics, qa=verdict)
    final['dd_qa_passed'] = verdict['passed']
    return GarmentResult(final, simulation, body, finite_report(report))


def finite_report(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: finite_report(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_report(item) for item in value]
    return value
