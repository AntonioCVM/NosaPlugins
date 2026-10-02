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
        self.assertEqual(len(offsets), 1 + 8 * 2)
        self.assertIn((0.0, 2.5), offsets[:3])


if __name__ == '__main__':
    unittest.main()
