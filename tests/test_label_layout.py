# -*- coding: utf-8 -*-
"""nosa_utils.label_layout: tags moved apart, nearest free spot first, obstacles respected."""
import os
import sys
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils.label_layout import candidate_offsets, deoverlap  # noqa: E402


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _moved(rect, d):
    return (rect[0] + d[0], rect[1] + d[1], rect[2] + d[0], rect[3] + d[1])


class LabelLayoutTests(unittest.TestCase):

    def test_separate_tags_stay_put(self):
        rects = [(0, 0, 10, 2), (0, 5, 10, 7)]
        self.assertEqual(deoverlap(rects, gap=0.5), [(0.0, 0.0), (0.0, 0.0)])

    def test_stacked_tags_end_up_clear_of_each_other(self):
        rects = [(0, 0, 10, 2)] * 5                      # five tags on the same spot
        moves = deoverlap(rects, gap=0.5)
        placed = [_moved(r, d) for r, d in zip(rects, moves)]
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                self.assertFalse(_overlap(placed[i], placed[j]), (placed[i], placed[j]))
        self.assertEqual(moves[0], (0.0, 0.0))
        self.assertEqual(moves[1], (0.0, 2.5))          # one height + gap up, the nearest spot

    def test_existing_tags_are_obstacles(self):
        moves = deoverlap([(0, 0, 10, 2)], obstacles=[(0, 0, 10, 2)], gap=0.5)
        self.assertNotEqual(moves[0], (0.0, 0.0))
        self.assertFalse(_overlap(_moved((0, 0, 10, 2), moves[0]), (0, 0, 10, 2)))

    def test_candidates_start_at_home_and_grow(self):
        offsets = candidate_offsets(10, 2, 0.5, rings=2)
        self.assertEqual(offsets[0], (0.0, 0.0))
        self.assertEqual(len(offsets), (2 * 2 + 1) ** 2)
        self.assertEqual(offsets[1], (0.0, 2.5))            # one height up comes first
        self.assertLess(offsets.index((0.0, 5.0)), offsets.index((5.25, 0.0)))   # stack before sliding


if __name__ == '__main__':
    unittest.main()


class TagLayoutTests(unittest.TestCase):

    def test_crossing_detection(self):
        from nosa_utils.label_layout import segments_cross
        self.assertTrue(segments_cross((0, 0), (10, 10), (0, 10), (10, 0)))
        self.assertFalse(segments_cross((0, 0), (10, 0), (0, 5), (10, 5)))

    def test_crossed_leaders_are_swapped(self):
        from nosa_utils.label_layout import layout_tags, segments_cross
        # two tags whose natural spots are taken: each ends far from its anchor, leaders crossing
        anchors = [(0.0, 0.0), (10.0, 0.0)]
        rects = [(9.0, 9.0, 11.0, 10.0), (-1.0, 9.0, 1.0, 10.0)]   # tag 0 above anchor 1 and vice versa
        moves = layout_tags(anchors, rects, gap=0.5, leader_after=1.5)
        heads = [((r[0] + r[2]) / 2 + m[0], (r[1] + r[3]) / 2 + m[1]) for r, m in zip(rects, moves)]
        self.assertEqual(moves[0][:2], (-10.0, 0.0))       # swapped: each tag over its own anchor
        self.assertTrue(moves[0][2] and moves[1][2])       # still far from their anchors: leaders
        self.assertFalse(segments_cross(anchors[0], heads[0], anchors[1], heads[1]))

    def test_tags_in_place_need_no_leader(self):
        from nosa_utils.label_layout import layout_tags
        moves = layout_tags([(0.0, 0.0)], [(-1.0, 0.5, 1.0, 1.5)], gap=0.5)
        self.assertEqual(moves, [(0.0, 0.0, False)])


class RelocateTests(unittest.TestCase):

    def test_a_crossing_that_cannot_swap_is_moved(self):
        from nosa_utils.label_layout import layout_tags, segments_cross
        # tags of different widths whose swap would overlap a third tag: one must move instead
        anchors = [(0.0, 0.0), (10.0, 0.0), (5.0, 12.0)]
        rects = [(9.0, 9.0, 11.0, 10.0), (-3.0, 9.0, 1.0, 10.0), (-1.0, 11.0, 11.0, 12.0)]
        moves = layout_tags(anchors, rects, gap=0.5, leader_after=1.5)
        heads = [((r[0] + r[2]) / 2 + m[0], (r[1] + r[3]) / 2 + m[1]) for r, m in zip(rects, moves)]
        lead = [m[2] for m in moves]
        for i in range(3):
            for j in range(i + 1, 3):
                if lead[i] and lead[j]:
                    self.assertFalse(segments_cross(anchors[i], heads[i], anchors[j], heads[j]))

