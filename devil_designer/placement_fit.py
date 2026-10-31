import math

GRID_STEP = .005
CURVE_SAMPLES = 256
MIN_GAP = .006
SIDE_GAP = 1.03
GRAVITY_HOLD = 30
GRAVITY_RAMP = 20
TOP_WINDOW = .08
WIDTH_LOOKUP = 10


def convex_hull(points):
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return ordered

    def turn(origin, first, second):
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])

    lower, upper = [], []
    for point in ordered:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def offset_hull(points, clearance, directions=16):
    expanded = [(x + clearance * math.cos(math.tau * index / directions), y + clearance * math.sin(math.tau * index / directions))
                for x, y in convex_hull(points) for index in range(directions)]
    return convex_hull(expanded)


def ray_crossing(polygon, center, direction):
    best = None
    for index in range(len(polygon)):
        start, end = polygon[index - 1], polygon[index]
        edge = (end[0] - start[0], end[1] - start[1])
        denominator = direction[0] * edge[1] - direction[1] * edge[0]
        if abs(denominator) < 1e-15:
            continue
        offset = (start[0] - center[0], start[1] - center[1])
        distance = (offset[0] * edge[1] - offset[1] * edge[0]) / denominator
        fraction = (offset[0] * direction[1] - offset[1] * direction[0]) / denominator
        if distance > 0 and -1e-9 <= fraction <= 1 + 1e-9 and (best is None or distance < best[0]):
            best = (distance, index - 1 if index else len(polygon) - 1, fraction)
    return best


def resample_from(polygon, center, direction, samples=CURVE_SAMPLES):
    crossing = ray_crossing(polygon, center, direction)
    if crossing is None:
        raise ValueError('Body section does not surround its centre.')
    _, index, fraction = crossing
    start = polygon[index]
    end = polygon[(index + 1) % len(polygon)]
    first = (start[0] + fraction * (end[0] - start[0]), start[1] + fraction * (end[1] - start[1]))
    ring = [first] + [polygon[(index + 1 + step) % len(polygon)] for step in range(len(polygon))] + [first]
    lengths = [0.0]
    for a, b in zip(ring, ring[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    total = lengths[-1]
    curve = []
    cursor = 0
    for sample in range(samples):
        target = total * sample / samples
        while lengths[cursor + 1] < target:
            cursor += 1
        span = max(1e-12, lengths[cursor + 1] - lengths[cursor])
        t = (target - lengths[cursor]) / span
        curve.append((ring[cursor][0] + t * (ring[cursor + 1][0] - ring[cursor][0]),
                      ring[cursor][1] + t * (ring[cursor + 1][1] - ring[cursor][1])))
    return curve, total


def point_on_curve(curve, total, arc):
    position = (arc % total) / total * len(curve)
    index = int(position) % len(curve)
    t = position - int(position)
    start, end = curve[index], curve[(index + 1) % len(curve)]
    return (start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1]))


def outline_span(points, height):
    crossings = []
    for index in range(len(points)):
        (x0, y0), (x1, y1) = points[index - 1], points[index]
        if (y0 - height) * (y1 - height) <= 0 and abs(y1 - y0) > 1e-12:
            crossings.append(x0 + (height - y0) / (y1 - y0) * (x1 - x0))
    return max(crossings) - min(crossings) if len(crossings) >= 2 else 0.0


class BodyModel:
    def __init__(self, body, depsgraph):
        import numpy
        evaluated = body.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            coordinates = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
            mesh.vertices.foreach_get('co', coordinates)
            triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int32)
            mesh.loop_triangles.foreach_get('vertices', triangles)
            matrix = numpy.array(evaluated.matrix_world, dtype=numpy.float64)
        finally:
            evaluated.to_mesh_clear()
        local = coordinates.reshape(-1, 3).astype(numpy.float64)
        self.vertices = local @ matrix[:3, :3].T + matrix[:3, 3]
        triangles = triangles.reshape(-1, 3)
        pairs = numpy.sort(numpy.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
        self.edges, inverse = numpy.unique(pairs, axis=0, return_inverse=True)
        self.triangle_edges = inverse.reshape(-1).reshape(3, -1).T
        self.numpy = numpy
        self.low = float(self.vertices[:, 2].min())
        self.height = float(self.vertices[:, 2].max()) - self.low
        self.axis = (float((self.vertices[:, 0].min() + self.vertices[:, 0].max()) / 2), 0.0)
        hips = self.components(self.low + .5 * self.height)
        core = min(hips, key=lambda points: abs(sum(p[0] for p in points) / len(points) - self.axis[0]))
        self.axis = (self.axis[0], (min(p[1] for p in core) + max(p[1] for p in core)) / 2)
        self.hip_half = (max(p[0] for p in core) - min(p[0] for p in core)) / 2
        self.sections = {}
        self.hulls = {}

    def components(self, height):
        numpy = self.numpy
        signed = self.vertices[:, 2] - height
        signed[numpy.abs(signed) < 1e-9] = 1e-9
        first, second = signed[self.edges[:, 0]], signed[self.edges[:, 1]]
        crossing = first * second < 0
        factor = numpy.where(crossing, first / numpy.where(crossing, first - second, 1.0), 0.0)
        start, end = self.vertices[self.edges[:, 0], :2], self.vertices[self.edges[:, 1], :2]
        points = start + factor[:, None] * (end - start)
        selected = crossing[self.triangle_edges]
        rows = numpy.nonzero(selected.sum(axis=1) == 2)[0]
        parent = {}

        def root(key):
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        for row in rows:
            a, b = (int(edge) for edge, used in zip(self.triangle_edges[row], selected[row]) if used)
            parent.setdefault(a, a)
            parent.setdefault(b, b)
            parent[root(a)] = root(b)
        groups = {}
        for key in parent:
            groups.setdefault(root(key), []).append((float(points[key, 0]), float(points[key, 1])))
        return [group for group in groups.values() if len(group) >= 3]

    def core(self, height):
        groups = self.components(height)
        if not groups:
            return []
        centres = [(sum(p[0] for p in group) / len(group), sum(p[1] for p in group) / len(group)) for group in groups]
        closest = min(range(len(groups)), key=lambda index: math.dist(centres[index], self.axis))
        keep = [index for index in range(len(groups))
                if index == closest or abs(centres[index][0] - self.axis[0]) < self.hip_half]
        return [point for index in keep for point in groups[index]]

    def core_hull(self, key, clip):
        if (key, clip) not in self.hulls:
            points = self.core(key * GRID_STEP)
            if clip:
                points = [point for point in points if abs(point[0] - self.axis[0]) <= clip]
            self.hulls[(key, clip)] = convex_hull(points)
        return self.hulls[(key, clip)]

    def section(self, height, clearance, clip=None, window=0.0):
        key = (round(height / GRID_STEP), round(clearance, 4), clip, round(window, 4))
        if key not in self.sections:
            points = [point for step in range(int(round(window / GRID_STEP)) + 1)
                      for point in self.core_hull(key[0] - step, clip_at(clip, (key[0] - step) * GRID_STEP))]
            if len(points) < 3:
                raise ValueError(f'The body has no cross-section at height {height:.3f} m.')
            hull = offset_hull(points, clearance)
            centre = ((min(p[0] for p in hull) + max(p[0] for p in hull)) / 2, (min(p[1] for p in hull) + max(p[1] for p in hull)) / 2)
            curve, total = resample_from(hull, centre, (0.0, -1.0))
            back = ray_crossing([curve[index] for index in range(len(curve))], centre, (0.0, 1.0))
            back_arc = (back[1] + back[2]) / len(curve) * total
            self.sections[key] = (curve, total, back_arc, centre)
        return self.sections[key]

    def arm(self, side):
        samples = []
        height = self.low + .45 * self.height
        while height < self.low + .85 * self.height:
            lateral = [group for group in self.components(height)
                       if side * (sum(p[0] for p in group) / len(group) - self.axis[0]) > self.hip_half * 1.05]
            if lateral:
                group = min(lateral, key=lambda points: abs(sum(p[0] for p in points) / len(points) - self.axis[0]))
                samples.append((sum(p[0] for p in group) / len(group), sum(p[1] for p in group) / len(group), height,
                                (max(p[1] for p in group) - min(p[1] for p in group)) / 2))
            elif samples:
                break
            height += .01
        if len(samples) < 8:
            raise ValueError('Could not find a separated arm; use an A-pose or T-pose body.')
        armpit = samples[-1][2]
        run = [sample for sample in samples if sample[2] < armpit - .02]
        span = run[-1][2] - run[0][2]
        line = arm_line([sample for sample in run if sample[2] > run[-1][2] - .6 * span], side)
        radii = sorted(sample[3] for sample in run if sample[2] > run[-1][2] - .35 * span)
        return dict(line, radius=radii[(3 * len(radii)) // 4], armpit=armpit)

    def top_profile(self, offset, ceiling):
        vertices = self.vertices
        band = vertices[(abs(abs(vertices[:, 0] - self.axis[0]) - offset) < .01) & (abs(vertices[:, 1] - self.axis[1]) < .07)
                        & (vertices[:, 2] < ceiling)]
        if not len(band):
            raise ValueError(f'No shoulder surface found {offset:.3f} m from the body centre.')
        return float(band[:, 2].max())

    def girth(self, height):
        hull = convex_hull(self.core(height))
        return sum(math.dist(hull[index - 1], hull[index]) for index in range(len(hull))) if len(hull) > 2 else 0.0

    def extreme(self, lower, upper, largest):
        best = None
        height = lower
        while height <= upper:
            value = self.girth(height)
            if value > 0 and (best is None or (value > best[1] if largest else value < best[1])):
                best = (height, value)
            height += .004 * self.height
        if best is None:
            raise ValueError('Could not measure the torso; check that the body is a closed mesh.')
        return best


def arm_line(samples, side):
    count = len(samples)
    mean = [sum(sample[axis] for sample in samples) / count for axis in range(3)]
    variance = sum((sample[2] - mean[2]) ** 2 for sample in samples)
    slopes = [sum((sample[axis] - mean[axis]) * (sample[2] - mean[2]) for sample in samples) / max(variance, 1e-12)
              for axis in range(2)]
    length = math.sqrt(slopes[0] ** 2 + slopes[1] ** 2 + 1)
    down = (-slopes[0] / length, -slopes[1] / length, -1 / length)
    radii = sorted(sample[3] for sample in samples)
    return dict(side=side, point=tuple(mean), down=down, radius=radii[len(radii) // 2])


def axis_point_at(arm, height):
    t = (height - arm['point'][2]) / arm['down'][2]
    return tuple(arm['point'][axis] + t * arm['down'][axis] for axis in range(3))


def arm_angle(arms):
    return sum(math.degrees(math.atan2(math.hypot(arm['down'][0], arm['down'][1]), -arm['down'][2]))
               for arm in arms.values()) / len(arms)


def body_landmarks(model):
    arms = {side: model.arm(side) for side in (1, -1)}
    radius = sum(arm['radius'] for arm in arms.values()) / 2
    armpit = min(arm['armpit'] for arm in arms.values())
    root = sum(abs(axis_point_at(arm, armpit)[0] - model.axis[0]) for arm in arms.values()) / 2
    ceiling = armpit + .12 * model.height
    shoulder_x = root - radius
    shoulder = model.top_profile(shoulder_x, ceiling)
    neck = model.top_profile(.075 * model.height / 1.7 + .005, ceiling)
    low, height = model.low, model.height
    waist = model.extreme(low + .55 * height, min(low + .70 * height, armpit - .05), False)
    hip = model.extreme(low + .42 * height, waist[0] - .06, True)
    chest = model.extreme(waist[0] + .03, armpit - .01, True)
    values = dict(height=round(100 * height, 1), chest=round(100 * chest[1], 1), waist=round(100 * waist[1], 1),
                  hip=round(100 * hip[1], 1), chest_y=chest[0] - low, waist_y=waist[0] - low, hip_y=hip[0] - low,
                  armpit_y=armpit - low, shoulder_y=shoulder - low, neck_y=neck - low,
                  torso_length=round(100 * (neck - waist[0]), 1),
                  shoulder_width=round(200 * shoulder_x, 1), bicep=round(200 * math.pi * radius, 1),
                  arm_angle=round(arm_angle(arms), 1))
    return values, arms


def top_lift(model, document, landmarks, margin=.012):
    ceiling = model.low + landmarks['armpit_y'] + .12 * model.height
    lifts = []
    for pattern in document.patterns:
        if 'sleeve' in pattern.name.casefold():
            continue
        outline = pattern.outline()
        centre = (min(x for x, _ in outline) + max(x for x, _ in outline)) / 2
        top = max(y for _, y in outline)
        for x, y in outline:
            if y > top - .03 and abs(x - centre) > .03:
                lifts.append(model.top_profile(abs(x - centre), ceiling) - model.low + margin - y)
    return max(-.15, min(.15, max(lifts))) if lifts else 0.0


def top_profile(model, landmarks):
    armpit = model.low + landmarks['armpit_y']
    torso = model.core(armpit - .015)
    width = max(abs(point[0] - model.axis[0]) for point in torso) + .005 if torso else landmarks['shoulder_width'] / 200
    clip = (round(armpit, 4), round(width, 4), round(model.low + landmarks['shoulder_y'], 4),
            round(max(width, landmarks['shoulder_width'] / 200 + .01), 4))
    return clip, TOP_WINDOW


def clip_at(clip, height):
    if not clip:
        return 0.0
    low, low_width, high, high_width = clip
    if height <= low:
        return 0.0
    factor = min(1.0, (height - low) / max(1e-6, high - low))
    return round(low_width + factor * (high_width - low_width), 4)


def prepare_document(document):
    for pattern in document.patterns:
        pattern.arrangement = None
        pattern.placement_mode = 'LAYOUT'
        pattern.panel_origin = None
    return document


def torso_positions(model, rest, outline, centre_x, back, widths, clearance, lift, profile):
    positions = []
    for x, y in rest:
        y += lift
        key = round(y / GRID_STEP)
        curve, total, back_arc, centre = model.section(model.low + key * GRID_STEP, clearance, *profile)
        scale = max(1.0, widths(key) * SIDE_GAP / total)
        arc = (back_arc if back else 0.0) + (x - centre_x) / scale
        px, py = point_on_curve(curve, total, arc)
        positions.append((centre[0] + (px - centre[0]) * scale, centre[1] + (py - centre[1]) * scale, model.low + y))
    return positions


def sleeve_positions(model, rest, outline, arm, shoulder_y, clearance):
    from mathutils import Vector
    down = Vector(arm['down'])
    up = Vector((0, 0, 1)) - down * down.z
    up.normalize()
    around = -down.cross(up)
    top = max(y for _, y in outline)
    centre_x = (min(x for x, _ in outline) + max(x for x, _ in outline)) / 2
    anchor = Vector(axis_point_at(arm, model.low + shoulder_y - arm['radius']))
    positions = []
    for x, y in rest:
        radius = max(outline_span(outline, y) / math.tau, arm['radius'] + clearance)
        angle = (x - centre_x) / radius
        point = anchor + down * (top - y) + radius * (up * math.cos(angle) + around * math.sin(angle))
        positions.append(tuple(point))
    return positions


def push_out(positions, tree, gap=MIN_GAP):
    from mathutils import Vector
    moved = 0
    result = []
    for position in positions:
        point = Vector(position)
        location, normal, _, _ = tree.find_nearest(point)
        if location is not None and (point - location).dot(normal) < gap:
            point = location + normal * gap
            moved += 1
        result.append(tuple(point))
    return result, moved


def dress_panels(context, document, model, arms, landmarks, clearance, lift=0.0, profile=(None, 0.0)):
    from mathutils import Matrix
    from . import garment, qa
    tree = qa.body_tree(context.scene.dd_avatar, context.evaluated_depsgraph_get())
    outlines = {pattern.id: pattern.outline() for pattern in document.patterns}
    torso_ids = [pattern.id for pattern in document.patterns if 'sleeve' not in pattern.name.casefold()]
    cache = {}

    def raw_width(key):
        if key not in cache:
            cache[key] = sum(outline_span(outlines[identity], key * GRID_STEP - lift) for identity in torso_ids)
        return cache[key]

    def widths(key):
        return max(raw_width(key + step) for step in range(WIDTH_LOOKUP + 1))

    report = dict(pushed=0, vertices=0, lift=round(lift, 4))
    for panel in garment.generated(context.scene, 'panel'):
        pattern = document.find(panel.get('dd_pattern_id'))
        rest = [tuple(item.vector)[:2] for item in panel.data.attributes['dd_rest'].data]
        outline = outlines[pattern.id]
        name = pattern.name.casefold()
        if 'sleeve' in name:
            arm = arms[1 if 'left' in name else -1]
            positions = sleeve_positions(model, rest, outline, arm, landmarks['shoulder_y'], clearance)
        else:
            centre_x = (min(x for x, _ in outline) + max(x for x, _ in outline)) / 2
            positions = torso_positions(model, rest, outline, centre_x, 'back' in name, widths, clearance, lift, profile)
        positions, moved = push_out(positions, tree)
        panel.matrix_world = Matrix.Identity(4)
        for vertex, position in zip(panel.data.vertices, positions):
            vertex.co = position
        panel.data.update()
        report['pushed'] += moved
        report['vertices'] += len(positions)
    context.view_layer.update()
    return report


def hold_gravity(simulation, start, hold=GRAVITY_HOLD, ramp=GRAVITY_RAMP):
    cloth = next(modifier for modifier in simulation.modifiers if modifier.type == 'CLOTH')
    weights = cloth.settings.effector_weights
    for frame, value in ((start, 0.0), (start + hold, 0.0), (start + hold + ramp, 1.0)):
        weights.gravity = value
        weights.keyframe_insert('gravity', frame=frame)
    return dict(hold=hold, ramp=ramp)
