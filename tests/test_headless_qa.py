import math
import unittest
from devil_designer import qa
from devil_designer.placement_fit import clip_at, convex_hull, offset_hull, outline_span, point_on_curve, resample_from
from devil_designer.starters import create_fitted_skirt_starter, create_set_in_tee_starter, fitted_landmarks


def grid_faces(columns, rows):
    faces = []
    for row in range(rows):
        for column in range(columns):
            corner = row * (columns + 1) + column
            faces.append((corner, corner + 1, corner + columns + 2, corner + columns + 1))
    return faces


class TopologyTests(unittest.TestCase):
    def test_open_grid_has_one_boundary_loop_and_component(self):
        faces = grid_faces(3, 2)
        self.assertEqual(len(qa.boundary_loops(faces)), 1)
        self.assertEqual(qa.component_count(12, faces), 1)

    def test_closed_tube_has_two_openings(self):
        columns = 6
        faces = [(column, (column + 1) % columns, columns + (column + 1) % columns, columns + column) for column in range(columns)]
        self.assertEqual(len(qa.boundary_loops(faces)), 2)

    def test_separate_patches_are_counted(self):
        faces = [(0, 1, 2), (3, 4, 5)]
        self.assertEqual(qa.component_count(6, faces), 2)
        self.assertEqual(len(qa.boundary_loops(faces)), 2)


class MetricTests(unittest.TestCase):
    def test_hem_front_back_difference_uses_minus_y_as_front(self):
        points = [(math.cos(a), math.sin(a), .5 + (.02 if math.sin(a) < 0 else 0.0)) for a in [i * math.tau / 16 + .1 for i in range(16)]]
        stats = qa.hem_stats(points)
        self.assertAlmostEqual(stats['front_back'], .02, places=6)
        self.assertGreater(stats['std'], 0)

    def test_uv_flip_and_range_detection(self):
        good = [[(0, 0), (.5, 0), (0, .5)], [(.5, 0), (.5, .5), (0, .5)]]
        self.assertEqual(qa.uv_sanity(good), dict(flipped=0, degenerate=0, out_of_range=0))
        flipped = good + [[(0, 0), (0, .5), (.5, 0)]]
        self.assertEqual(qa.uv_sanity(flipped)['flipped'], 1)
        self.assertEqual(qa.uv_sanity([[(0, 0), (1.2, 0), (0, 1)]])['out_of_range'], 1)

    def test_stretch_ignores_sliver_edges_and_counts_spikes(self):
        points = [[(0, 0, 0), (.02, 0, 0), (0, .06, 0)]]
        uvs = [[(0, 0), (.02, 0), (0, .02)]]
        ratios = qa.stretch_ratios(points, uvs, 1.0)
        self.assertEqual(len(ratios), 3)
        self.assertEqual(qa.stretch_summary(ratios)['spikes'], 1)
        self.assertEqual(qa.stretch_ratios(points, [[(0, 0), (.001, 0), (0, .001)]], 1.0), [])

    def test_judge_applies_thresholds_in_one_place(self):
        metrics = dict(seams=dict(open=0), topology=dict(components=1, openings=2),
                       penetration=dict(fraction=0.0, max_depth=0.0), self_intersection=dict(fraction=0.0),
                       stretch=dict(p99=1.1, spikes=0), uv=dict(flipped=0, out_of_range=0),
                       hem=dict(std=.005, front_back=.01))
        self.assertTrue(qa.judge(metrics, 'skirt')['passed'])
        metrics['hem']['front_back'] = qa.THRESHOLDS['hem_front_back_max'] + .01
        verdict = qa.judge(metrics, 'skirt')
        self.assertEqual(verdict['failed'], ['hem_front_back'])
        self.assertTrue(qa.judge(metrics, 'skirt', {'hem_front_back_max': 1.0})['passed'])
        self.assertTrue(qa.judge(dict(metrics, topology=dict(components=1, openings=4)), 'tank')['passed'])


class PlacementGeometryTests(unittest.TestCase):
    def test_hull_offset_and_resample_keep_perimeter(self):
        square = [(-.1, -.1), (.1, -.1), (.1, .1), (-.1, .1), (0, 0)]
        self.assertEqual(len(convex_hull(square)), 4)
        expanded = offset_hull(square, .02)
        curve, total = resample_from(expanded, (0, 0), (0, -1))
        self.assertAlmostEqual(total, .8 + math.tau * .02, delta=.01)
        start = point_on_curve(curve, total, 0.0)
        self.assertAlmostEqual(start[0], 0.0, places=3)
        self.assertLess(start[1], -.1)

    def test_outline_span_and_clip_ramp(self):
        triangle = [(0, 0), (1, 0), (.5, 1)]
        self.assertAlmostEqual(outline_span(triangle, .5), .5)
        clip = (1.0, .15, 1.2, .2)
        self.assertEqual(clip_at(clip, .9), 0.0)
        self.assertAlmostEqual(clip_at(clip, 1.1), .175)
        self.assertAlmostEqual(clip_at(clip, 1.5), .2)
        self.assertEqual(clip_at(None, 1.5), 0.0)


class FittedPatternTests(unittest.TestCase):
    def test_set_in_tee_has_four_pieces_and_balanced_seams(self):
        document = create_set_in_tee_starter(None)
        document.validate()
        document.validate_seams()
        self.assertEqual([pattern.name for pattern in document.patterns],
                         ['Tee front', 'Tee back', 'Tee left sleeve', 'Tee right sleeve'])
        self.assertEqual(len(document.seams), 10)
        for seam in document.seams:
            self.assertLess(document.seam_stats(seam)[3], 5.0)

    def test_set_in_tee_sleeve_opening_fits_an_arm(self):
        document = create_set_in_tee_starter({'bicep': 26.0, 'height': 160.0})
        sleeve = document.find(next(p.id for p in document.patterns if p.name == 'Tee left sleeve'))
        cuff = max(x for x, _ in sleeve.points) - min(x for x, _ in sleeve.points)
        self.assertGreater(cuff, .26)

    def test_fitted_skirt_side_seams_start_level_and_hem_rises_at_sides(self):
        document = create_fitted_skirt_starter(None)
        document.validate_seams()
        front = document.patterns[0]
        hem = sorted(front.points[:7])
        self.assertGreater(hem[0][1], hem[3][1])
        for seam in document.seams:
            first = document.edge_point(*document.chain_position(seam.side(0), 0.0))
            second = document.edge_point(*document.chain_position(seam.side(1), 1.0))
            self.assertAlmostEqual(first[1], second[1], places=6)

    def test_landmarks_default_from_height(self):
        values = fitted_landmarks({'height': 180.0})
        self.assertAlmostEqual(values['waist_y'], .62 * 1.8)
        self.assertGreater(values['shoulder_y'], values['armpit_y'])


if __name__ == '__main__':
    unittest.main()
