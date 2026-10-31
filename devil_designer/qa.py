import math
import statistics

THRESHOLDS = {
    'seam_gap_tolerance': .01,
    'open_seams_max': 0,
    'components_expected': 1,
    'penetration_fraction_max': .01,
    'penetration_depth_max': .01,
    'self_intersection_fraction_max': .01,
    'stretch_p99_max': 1.35,
    'stretch_min_rest': .003,
    'spike_ratio': 2.0,
    'spike_excess': .01,
    'spikes_max': 0,
    'uv_flips_max': 0,
    'uv_out_of_range_max': 0,
    'hem_std_max': .02,
    'hem_front_back_max': .03,
}
EXPECTED_OPENINGS = {'tee': 4, 'tank': 4, 'skirt': 2}
HEM_CHECKED = {'skirt'}


def edge_key(first, second):
    return (first, second) if first < second else (second, first)


def boundary_edges(faces):
    counts = {}
    for face in faces:
        for first, second in zip(face, face[1:] + face[:1]):
            key = edge_key(first, second)
            counts[key] = counts.get(key, 0) + 1
    return [key for key, count in counts.items() if count == 1]


def boundary_loops(faces):
    neighbours = {}
    for first, second in boundary_edges(faces):
        neighbours.setdefault(first, []).append(second)
        neighbours.setdefault(second, []).append(first)
    loops = []
    seen = set()
    for start in sorted(neighbours):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        pending = [start]
        while pending:
            current = pending.pop()
            for other in neighbours[current]:
                if other not in seen:
                    seen.add(other)
                    loop.append(other)
                    pending.append(other)
        loops.append(loop)
    return loops


def component_count(vertex_count, faces):
    parent = list(range(vertex_count))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    used = set()
    for face in faces:
        used.update(face)
        for other in face[1:]:
            parent[root(other)] = root(face[0])
    return len({root(index) for index in used})


def summary(values):
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return dict(count=0, max=0.0, mean=0.0, p99=0.0)
    ordered = sorted(values)
    return dict(count=len(values), max=ordered[-1], mean=sum(ordered) / len(ordered),
                p99=ordered[min(len(ordered) - 1, int(.99 * len(ordered)))])


def hem_stats(points, center=(0.0, 0.0)):
    if len(points) < 3:
        return dict(count=len(points), std=0.0, front=0.0, back=0.0, front_back=0.0, mean=0.0, min=0.0, max=0.0)
    heights = [point[2] for point in points]
    front = [point[2] for point in points if point[1] < center[1]]
    back = [point[2] for point in points if point[1] >= center[1]]
    front_mean = sum(front) / len(front) if front else 0.0
    back_mean = sum(back) / len(back) if back else 0.0
    return dict(count=len(points), std=statistics.pstdev(heights), mean=sum(heights) / len(heights),
                min=min(heights), max=max(heights), front=front_mean, back=back_mean,
                front_back=front_mean - back_mean if front and back else 0.0)


def signed_area(points):
    return sum(points[index][0] * points[index - 1][1] - points[index - 1][0] * points[index][1]
               for index in range(len(points))) / 2


def uv_sanity(face_uvs):
    areas = [signed_area(uvs) for uvs in face_uvs]
    positive = sum(1 for value in areas if value > 1e-14)
    negative = sum(1 for value in areas if value < -1e-14)
    outside = sum(1 for uvs in face_uvs for u, v in uvs if not (-1e-6 <= u <= 1 + 1e-6 and -1e-6 <= v <= 1 + 1e-6))
    return dict(flipped=min(positive, negative), degenerate=len(areas) - positive - negative, out_of_range=outside)


def stretch_ratios(face_points, face_uvs, uv_scale, minimum_rest=THRESHOLDS['stretch_min_rest']):
    ratios = []
    for points, uvs in zip(face_points, face_uvs):
        for index in range(len(points)):
            rest = math.dist(uvs[index], uvs[index - 1]) * uv_scale
            if rest >= minimum_rest:
                length = math.dist(points[index], points[index - 1])
                ratios.append((length / rest, length - rest))
    return ratios


def stretch_summary(ratios):
    values = summary([ratio for ratio, _ in ratios])
    values['spikes'] = sum(1 for ratio, excess in ratios
                           if ratio > THRESHOLDS['spike_ratio'] and excess > THRESHOLDS['spike_excess']) // 2
    return values


def judge(metrics, kind, thresholds=None):
    limits = dict(THRESHOLDS, **(thresholds or {}))
    checks = {
        'open_seams': metrics['seams']['open'] <= limits['open_seams_max'],
        'components': metrics['topology']['components'] == limits['components_expected'],
        'openings': metrics['topology']['openings'] == EXPECTED_OPENINGS.get(kind, metrics['topology']['openings']),
        'penetration_fraction': metrics['penetration']['fraction'] <= limits['penetration_fraction_max'],
        'penetration_depth': metrics['penetration']['max_depth'] <= limits['penetration_depth_max'],
        'self_intersection': metrics['self_intersection']['fraction'] <= limits['self_intersection_fraction_max'],
        'stretch': metrics['stretch']['p99'] <= limits['stretch_p99_max'],
        'spikes': metrics['stretch']['spikes'] <= limits['spikes_max'],
        'uv_flips': metrics['uv']['flipped'] <= limits['uv_flips_max'],
        'uv_range': metrics['uv']['out_of_range'] <= limits['uv_out_of_range_max'],
    }
    if kind in HEM_CHECKED:
        checks['hem_even'] = metrics['hem']['std'] <= limits['hem_std_max']
        checks['hem_front_back'] = abs(metrics['hem']['front_back']) <= limits['hem_front_back_max']
    failed = sorted(name for name, passed in checks.items() if not passed)
    return dict(passed=not failed, failed=failed, checks=checks, thresholds=limits)


def world_mesh(obj, depsgraph=None, evaluated=False):
    target = obj.evaluated_get(depsgraph) if evaluated and depsgraph is not None else obj
    mesh = target.data if not evaluated else target.to_mesh()
    try:
        matrix = obj.matrix_world
        points = [tuple(matrix @ vertex.co) for vertex in mesh.vertices]
        faces = [tuple(polygon.vertices) for polygon in mesh.polygons]
        uv_layer = mesh.uv_layers.active
        face_uvs = [[tuple(uv_layer.data[loop].uv) for loop in polygon.loop_indices] for polygon in mesh.polygons] if uv_layer else []
        return points, faces, face_uvs
    finally:
        if evaluated:
            target.to_mesh_clear()


def seam_gaps(simulation, depsgraph):
    import json
    pairs = json.loads(simulation.get('dd_sewing_pairs', '[]'))
    points, _, _ = world_mesh(simulation, depsgraph, evaluated=True)
    return [math.dist(points[first], points[second]) for first, second in pairs]


def body_tree(body, depsgraph):
    from mathutils.bvhtree import BVHTree
    points, faces, _ = world_mesh(body, depsgraph, evaluated=True)
    return BVHTree.FromPolygons(points, faces)


def penetration(points, tree):
    from mathutils import Vector
    depths = []
    for point in points:
        location, normal, _, distance = tree.find_nearest(Vector(point))
        if location is not None and (Vector(point) - location).dot(normal) < 0:
            depths.append(distance)
    return dict(inside=len(depths), fraction=len(depths) / max(1, len(points)),
                max_depth=max(depths, default=0.0), mean_depth=sum(depths) / len(depths) if depths else 0.0)


def self_intersection(points, faces):
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons(points, faces)
    involved = set()
    pairs = 0
    for first, second in tree.overlap(tree):
        if first >= second or set(faces[first]) & set(faces[second]):
            continue
        pairs += 1
        involved.update((first, second))
    return dict(pairs=pairs, faces=len(involved), fraction=len(involved) / max(1, len(faces)))


def measure(final, simulation, body, depsgraph, kind, uv_scale, center=(0.0, 0.0), document=None, tolerance=None):
    gaps = seam_gaps(simulation, depsgraph)
    points, faces, face_uvs = world_mesh(final)
    loops = boundary_loops(faces)
    hem = min(loops, key=lambda loop: sum(points[index][2] for index in loop) / len(loop)) if loops else []
    tolerance = THRESHOLDS['seam_gap_tolerance'] if tolerance is None else tolerance
    face_points = [[points[index] for index in face] for face in faces]
    return dict(
        seams=dict(pairs=len(gaps), open=sum(1 for gap in gaps if gap > tolerance), tolerance=tolerance, **{
            'gap_' + key: value for key, value in summary(gaps).items() if key != 'count'}),
        topology=dict(vertices=len(points), faces=len(faces), components=component_count(len(points), faces),
                      openings=len(loops), opening_sizes=sorted(len(loop) for loop in loops)),
        penetration=penetration(points, body_tree(body, depsgraph)),
        self_intersection=self_intersection(points, faces),
        stretch=stretch_summary(stretch_ratios(face_points, face_uvs, uv_scale)),
        initial_stretch=initial_stretch(simulation, uv_scale),
        uv=uv_sanity(face_uvs),
        hem=hem_stats([points[index] for index in hem], center),
        seam_detail=seam_detail(simulation, depsgraph, document, tolerance) if document else [],
    )


def seam_detail(simulation, depsgraph, document, tolerance):
    import json
    records = json.loads(simulation.get('dd_sewing_inspection', '{}'))
    points, _, _ = world_mesh(simulation, depsgraph, evaluated=True)
    rows = []
    for seam in document.seams:
        pairs = records.get(seam.id, {}).get('pairs', [])
        gaps = [math.dist(points[first], points[second]) for first, second in pairs]
        names = [document.find(seam.side(index)[0].pattern).name for index in (0, 1)]
        worst = max(range(len(gaps)), key=gaps.__getitem__) if gaps else None
        where = [round(value, 3) for value in points[pairs[worst][0]]] if worst is not None else []
        rows.append(dict(seam=' / '.join(names), pairs=len(gaps), open=sum(1 for gap in gaps if gap > tolerance),
                         max_gap=max(gaps, default=0.0), worst_at=where))
    return rows


def initial_stretch(simulation, uv_scale):
    points, faces, face_uvs = world_mesh(simulation)
    return stretch_summary(stretch_ratios([[points[index] for index in face] for face in faces], face_uvs, uv_scale))
