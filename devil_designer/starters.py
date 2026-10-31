from .core import Session, EdgeRef,arrangement_record


def make_edge(doc, pattern_id, index, rev=False):
    e = doc.edge(pattern_id, index)
    if rev:
        return EdgeRef(e.pattern, e.start, e.end, 1.0, 0.0, e.path)
    return e


def create_tee_starter(measurements, fabric='COTTON'):
    m = measurements or {
        'chest': 96.0,
        'waist': 80.0,
        'hip': 96.0,
        'torso_length': 40.0,
        'shoulder_width': 44.0,
        'arm_length': 36.0,
    }
    half_chest = (m['chest'] / 2 + 6.0) / 200
    half_waist = (m['waist'] / 2 + 6.0) / 200
    torso_h = max(0.40, (m['torso_length'] + 15.0) / 100)
    half_sh = max(half_chest * 0.95, (m['shoulder_width'] + 6.0) / 400)
    neck_w = 0.09
    armhole_drop = 0.22
    sleeve_ext = 0.14
    waist_y = m.get('waist_y', 0.62 * (m['height'] / 100 if 'height' in m else 1.70))
    base_y = max(0.0, waist_y - 0.15)

    front_pts = [
        (-half_waist, base_y),
        (half_waist, base_y),
        (half_chest, base_y + torso_h - armhole_drop),
        (half_sh + sleeve_ext, base_y + torso_h - armhole_drop * 0.4),
        (half_sh + sleeve_ext, base_y + torso_h - 0.04),
        (half_sh, base_y + torso_h - 0.02),
        (neck_w, base_y + torso_h),
        (0.0, base_y + torso_h - 0.08),
        (-neck_w, base_y + torso_h),
        (-half_sh, base_y + torso_h - 0.02),
        (-(half_sh + sleeve_ext), base_y + torso_h - 0.04),
        (-(half_sh + sleeve_ext), base_y + torso_h - armhole_drop * 0.4),
        (-half_chest, base_y + torso_h - armhole_drop),
    ]

    back_offset = 0.85
    back_pts = [(x + back_offset, y) for x, y in front_pts]
    back_pts[7] = (back_offset, base_y + torso_h - 0.02)

    s = Session()
    s.add(front_pts)
    s.document.patterns[-1].name = 'Tee front'
    s.document.patterns[-1].preset = fabric

    s.add(back_pts)
    s.document.patterns[-1].name = 'Tee back'
    s.document.patterns[-1].preset = fabric

    f_id = s.document.patterns[0].id
    b_id = s.document.patterns[1].id

    s.sew_chains([make_edge(s.document, f_id, 1)], [make_edge(s.document, b_id, 12)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 12, rev=True)], [make_edge(s.document, b_id, 1)], reverse=False)
    s.sew_chains([make_edge(s.document, f_id, 2)], [make_edge(s.document, b_id, 11)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 11, rev=True)], [make_edge(s.document, b_id, 2)], reverse=False)
    s.sew_chains([make_edge(s.document, f_id, 4)], [make_edge(s.document, b_id, 9)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 9, rev=True)], [make_edge(s.document, b_id, 4)], reverse=False)
    s.sew_chains([make_edge(s.document, f_id, 5)], [make_edge(s.document, b_id, 8)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 8, rev=True)], [make_edge(s.document, b_id, 5)], reverse=False)

    for pattern,point in zip(s.document.patterns,('front','back')):
        pattern.arrangement=arrangement_record('chest',point,version=2)
    return s.document


def create_tank_starter(measurements, fabric='COTTON'):
    m = measurements or {
        'chest': 96.0,
        'waist': 80.0,
        'hip': 96.0,
        'torso_length': 40.0,
        'shoulder_width': 44.0,
    }
    half_chest = (m['chest'] / 2 + 4.0) / 200
    half_waist = (m['waist'] / 2 + 4.0) / 200
    torso_h = max(0.40, (m['torso_length'] + 12.0) / 100)
    half_sh = max(half_chest * 0.80, (m['shoulder_width'] + 2.0) / 400)
    neck_w = 0.10
    armhole_drop = 0.24
    waist_y = m.get('waist_y', 0.62 * (m['height'] / 100 if 'height' in m else 1.70))
    base_y = max(0.0, waist_y - 0.15)

    front_pts = [
        (-half_waist, base_y),
        (half_waist, base_y),
        (half_chest, base_y + torso_h - armhole_drop),
        (half_sh * 0.75, base_y + torso_h - 0.02),
        (neck_w + 0.03, base_y + torso_h),
        (0.0, base_y + torso_h - 0.12),
        (-(neck_w + 0.03), base_y + torso_h),
        (-half_sh * 0.75, base_y + torso_h - 0.02),
        (-half_chest, base_y + torso_h - armhole_drop),
    ]

    back_offset = 0.85
    back_pts = [(x + back_offset, y) for x, y in front_pts]
    back_pts[5] = (back_offset, base_y + torso_h - 0.03)

    s = Session()
    s.add(front_pts)
    s.document.patterns[-1].name = 'Tank front'
    s.document.patterns[-1].preset = fabric

    s.add(back_pts)
    s.document.patterns[-1].name = 'Tank back'
    s.document.patterns[-1].preset = fabric

    f_id = s.document.patterns[0].id
    b_id = s.document.patterns[1].id

    s.sew_chains([make_edge(s.document, f_id, 1)], [make_edge(s.document, b_id, 8)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 8, rev=True)], [make_edge(s.document, b_id, 1)], reverse=False)
    s.sew_chains([make_edge(s.document, f_id, 3)], [make_edge(s.document, b_id, 6)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 6, rev=True)], [make_edge(s.document, b_id, 3)], reverse=False)

    for pattern,point in zip(s.document.patterns,('front','back')):
        pattern.arrangement=arrangement_record('chest',point,version=2)
    return s.document


def create_skirt_starter(measurements, fabric='COTTON'):
    m = measurements or {
        'waist': 80.0,
        'hip': 96.0,
    }
    half_waist = (m['waist'] / 2 + 4.0) / 200
    half_hip = (m['hip'] / 2 + 12.0) / 200
    skirt_len = 0.48
    waist_y = m.get('waist_y', 0.62 * (m['height'] / 100 if 'height' in m else 1.70))
    base_y = max(0.0, waist_y - skirt_len)

    front_pts = [
        (-half_hip, base_y),
        (half_hip, base_y),
        (half_waist, base_y + skirt_len),
        (-half_waist, base_y + skirt_len),
    ]

    back_offset = 0.85
    back_pts = [(x + back_offset, y) for x, y in front_pts]

    s = Session()
    s.add(front_pts)
    s.document.patterns[-1].name = 'Skirt front'
    s.document.patterns[-1].preset = fabric

    s.add(back_pts)
    s.document.patterns[-1].name = 'Skirt back'
    s.document.patterns[-1].preset = fabric

    f_id = s.document.patterns[0].id
    b_id = s.document.patterns[1].id

    s.sew_chains([make_edge(s.document, f_id, 1)], [make_edge(s.document, b_id, 3)], reverse=True)
    s.sew_chains([make_edge(s.document, f_id, 3, rev=True)], [make_edge(s.document, b_id, 1)], reverse=False)

    for pattern,point in zip(s.document.patterns,('front','back')):
        pattern.arrangement=arrangement_record('waist',point,version=2)
    return s.document


STARTER_GENERATORS = {
    'STARTER_TEE': ('Tee', create_tee_starter, 'BODICE'),
    'STARTER_TANK': ('Tank', create_tank_starter, 'BODICE'),
    'STARTER_SKIRT': ('Skirt', create_skirt_starter, 'SKIRT'),
}


def fitted_landmarks(measurements):
    m = dict(measurements or {})
    height = m.get('height', 170.0) / 100
    values = dict(height=height, chest=m.get('chest', 96.0) / 100, waist=m.get('waist', 80.0) / 100,
                  hip=m.get('hip', 96.0) / 100, shoulder_width=m.get('shoulder_width', 44.0) / 100,
                  bicep=m.get('bicep', 17.0 * height) / 100)
    values['waist_y'] = m.get('waist_y', .62 * height)
    values['hip_y'] = m.get('hip_y', .51 * height)
    values['armpit_y'] = m.get('armpit_y', .75 * height)
    values['shoulder_y'] = m.get('shoulder_y', .815 * height)
    values['neck_y'] = m.get('neck_y', .835 * height)
    return values


def polyline_length(points):
    return sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** .5 for a, b in zip(points, points[1:]))


def armhole_curve(under, shoulder, count=3):
    control = (shoulder[0], under[1] + .3 * (shoulder[1] - under[1]))
    points = []
    for index in range(1, count):
        t = index / count
        points.append(tuple((1 - t) ** 2 * under[axis] + 2 * t * (1 - t) * control[axis] + t * t * shoulder[axis]
                            for axis in range(2)))
    return points


def sleeve_cap(width, cap_height, count=4):
    half = width / 2
    return [(half * (1 - index / count), cap_height * (1 - (1 - index / count) ** 2) ** .75)
            for index in range(count + 1)]


def solve_cap_height(width, target, count=4):
    low, high = .01, .3
    for _ in range(60):
        middle = (low + high) / 2
        if polyline_length(sleeve_cap(width, middle, count)) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def tee_body_outline(lm, neck_drop):
    half_body = max(lm['chest'], lm['hip'] * .98) / 4 + .03
    half_shoulder = lm['shoulder_width'] / 2 + .01
    neck_w = .075 * lm['height'] / 1.7
    hem_y = lm['waist_y'] - .15
    under = (half_body, lm['armpit_y'] - .04)
    shoulder = (half_shoulder, lm['shoulder_y'] + .01)
    right = [(half_body, hem_y), under] + armhole_curve(under, shoulder) + [shoulder, (neck_w, lm['neck_y'] + .01)]
    left = [(-x, y) for x, y in reversed(right)]
    return [left[-1]] + right + [(0.0, lm['neck_y'] + .01 - neck_drop)] + left[:-1]


def sew_indices(session, first, first_edges, second, second_edges):
    document = session.document
    session.sew_chains([document.edge(first, index) for index in first_edges],
                       [document.edge(second, index) for index in second_edges])


def create_set_in_tee_starter(measurements, fabric='COTTON'):
    lm = fitted_landmarks(measurements)
    front = tee_body_outline(lm, .08)
    back = [(x + .85, y) for x, y in tee_body_outline(lm, .02)]
    armhole = polyline_length(front[2:6]) * 1.03
    width = min(lm['bicep'] + .07, 2 * (armhole ** 2 - .06 ** 2) ** .5)
    cap = sleeve_cap(width, solve_cap_height(width, armhole))
    cuff = width - .02
    sleeve = [(-cuff / 2, -.1), (cuff / 2, -.1)] + cap + [(-x, y) for x, y in reversed(cap[:-1])]
    origin = min(y for _, y in front) - .45
    s = Session()
    outlines = (('Tee front', front), ('Tee back', back),
                ('Tee left sleeve', [(x + 1.7, y + origin) for x, y in sleeve]),
                ('Tee right sleeve', [(x + 2.25, y + origin) for x, y in sleeve]))
    for name, outline in outlines:
        s.add(outline)
        s.document.patterns[-1].name = name
        s.document.patterns[-1].preset = fabric
    f_id, b_id, l_id, r_id = (pattern.id for pattern in s.document.patterns)
    last = len(front) - 1
    for first, first_edges, second, second_edges in (
            (f_id, [1], b_id, [last]), (f_id, [last], b_id, [1]),
            (f_id, [5], b_id, [last - 4]), (f_id, [last - 4], b_id, [5]),
            (f_id, [2, 3, 4], l_id, [6, 7, 8, 9]), (b_id, [last - 3, last - 2, last - 1], l_id, [2, 3, 4, 5]),
            (f_id, [last - 3, last - 2, last - 1], r_id, [2, 3, 4, 5]), (b_id, [2, 3, 4], r_id, [6, 7, 8, 9]),
            (l_id, [1], l_id, [len(sleeve) - 1]), (r_id, [1], r_id, [len(sleeve) - 1])):
        sew_indices(s, first, first_edges, second, second_edges)
    for pattern, point in zip(s.document.patterns, ('front', 'back')):
        pattern.arrangement = arrangement_record('chest', point, version=2)
    return s.document


def create_fitted_skirt_starter(measurements, fabric='COTTON', hem_segments=6):
    lm = fitted_landmarks(measurements)
    half_waist = (lm['waist'] + .025) / 4
    half_hip = (lm['hip'] + .04) / 4
    length = .3 * lm['height']
    hem_y = lm['waist_y'] - length
    half_hem = half_hip + .06 * length / .48
    rise = (length ** 2 + (half_hem - half_waist) ** 2) ** .5 - length
    hip_y = max(hem_y + .05, min(lm['hip_y'], lm['waist_y'] - .1))
    hem = [(-half_hem + 2 * half_hem * index / hem_segments, hem_y + rise * (2 * index / hem_segments - 1) ** 2)
           for index in range(hem_segments + 1)]
    outline = hem + [(half_hip, hip_y), (half_waist, lm['waist_y']), (-half_waist, lm['waist_y']), (-half_hip, hip_y)]
    s = Session()
    for name, offset in (('Skirt front', 0.0), ('Skirt back', .85)):
        s.add([(x + offset, y) for x, y in outline])
        s.document.patterns[-1].name = name
        s.document.patterns[-1].preset = fabric
    f_id, b_id = (pattern.id for pattern in s.document.patterns)
    right, left = [hem_segments, hem_segments + 1], [hem_segments + 3, hem_segments + 4]
    sew_indices(s, f_id, right, b_id, left)
    sew_indices(s, f_id, left, b_id, right)
    for pattern, point in zip(s.document.patterns, ('front', 'back')):
        pattern.arrangement = arrangement_record('waist', point, version=2)
    return s.document
