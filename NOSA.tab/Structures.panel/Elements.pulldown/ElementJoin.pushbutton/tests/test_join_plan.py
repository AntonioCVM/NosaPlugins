# -*- coding: utf-8 -*-
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('join_plan', os.path.join(_HERE, '..', 'lib', 'join_plan.py'))
plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan)


def box(x, y, z, size=1.0):
    return (x, y, z, x + size, y + size, z + size)


class PairTests(unittest.TestCase):
    def test_finds_overlapping_and_close_boxes_only(self):
        boxes = [box(0, 0, 0), box(0.5, 0, 0), box(1.05, 0, 0), box(50, 50, 50)]
        self.assertEqual(plan.candidate_pairs(boxes, 0.0), [(0, 1), (1, 2)])
        self.assertIn((0, 2), plan.candidate_pairs(boxes, 0.1))

    def test_unknown_boxes_are_ignored(self):
        self.assertEqual(plan.candidate_pairs([None, box(0, 0, 0), None], 0.0), [])

    def test_long_element_crossing_many_cells(self):
        boxes = [(0, 0, 0, 500, 1, 1), box(250, 0, 0), box(400, 5, 5)]
        self.assertEqual(plan.candidate_pairs(boxes, 0.0), [(0, 1)])

    def test_huge_box_goes_through_the_fallback(self):
        boxes = [(-1e4, -1e4, -1e4, 1e4, 1e4, 1e4), box(3, 3, 3)]
        self.assertEqual(plan.candidate_pairs(boxes, 0.0), [(0, 1)])

    def test_same_result_as_brute_force(self):
        boxes = [box(i * 0.7 % 23, i * 1.3 % 17, i * 0.9 % 11, 1.5) for i in range(120)]
        brute = [(i, j) for i in range(120) for j in range(i + 1, 120)
                 if plan.boxes_touch(boxes[i], boxes[j], 0.2)]
        self.assertEqual(plan.candidate_pairs(boxes, 0.2), brute)


class DecideTests(unittest.TestCase):
    def test_not_joined_overlapping_is_joined_with_the_higher_rank_dominant(self):
        self.assertEqual(plan.decide(0, 2, False, None, True)[:2], (u'join', u'a'))
        self.assertEqual(plan.decide(3, 1, False, None, True)[:2], (u'join', u'b'))

    def test_touching_only_is_skipped_unless_overlap_is_not_required(self):
        self.assertEqual(plan.decide(0, 1, False, None, False)[0], u'skip')
        self.assertEqual(plan.decide(0, 1, False, None, False, require_overlap=False)[0], u'join')

    def test_unknown_overlap_does_not_block_the_join(self):
        self.assertEqual(plan.decide(0, 1, False, None, None)[0], u'join')

    def test_correct_order_is_left_alone(self):
        self.assertEqual(plan.decide(0, 1, True, True, None)[0], u'ok')
        self.assertEqual(plan.decide(1, 0, True, False, None)[0], u'ok')

    def test_wrong_order_is_fixed_only_when_asked(self):
        self.assertEqual(plan.decide(0, 1, True, False, None)[:2], (u'fix', u'a'))
        self.assertEqual(plan.decide(1, 0, True, True, None)[:2], (u'fix', u'b'))
        self.assertEqual(plan.decide(0, 1, True, False, None, fix_existing=False)[0], u'ok')

    def test_equal_ranks_never_reorder(self):
        self.assertEqual(plan.decide(1, 1, True, False, None)[:2], (u'ok', None))
        self.assertEqual(plan.decide(1, 1, False, None, True)[:2], (u'join', None))

    def test_unranked_pairs_are_skipped(self):
        self.assertEqual(plan.decide(None, None, False, None, True)[0], u'skip')
        self.assertEqual(plan.decide(0, None, False, None, True)[:2], (u'join', u'a'))

    def test_forced_dominant_ignores_ranks(self):
        self.assertEqual(plan.decide(5, 0, False, None, True, forced=u'a')[:2], (u'join', u'a'))
        self.assertEqual(plan.decide(0, 5, True, True, None, forced=u'b')[:2], (u'fix', u'b'))


if __name__ == '__main__':
    unittest.main()
