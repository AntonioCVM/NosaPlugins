# -*- coding: utf-8 -*-
"""nosa_utils.tag_rules: categories recommended per view and NOSA tag type choice (T7.4)."""
import os
import sys
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import tag_rules as tr  # noqa: E402


class TagRulesTests(unittest.TestCase):

    def test_sheets_schedules_and_3d_are_not_tagged(self):
        for view_type in ('DrawingSheet', 'Schedule', 'ThreeD', 'Legend', 'DraftingView'):
            self.assertEqual(tr.recommend(view_type), [])

    def test_plans_carry_the_structure_and_stairs(self):
        keys = tr.recommend('EngineeringPlan', u'NOSA GA PLAN', u'First floor')
        self.assertEqual(keys, ['columns', 'framing', 'walls', 'floors', 'foundations', 'stair_landings'])

    def test_foundation_plans_add_piles_and_rc_plans_add_rebar(self):
        keys = tr.recommend('EngineeringPlan', u'NOSA RC PLAN', u'Foundation plan', rebar_visible=True)
        self.assertIn('piles', keys)
        self.assertIn('rebar', keys)
        self.assertNotIn('rebar', tr.recommend('EngineeringPlan', u'NOSA RC PLAN', u'L1'))

    def test_sections_tag_the_rebar_they_show(self):
        self.assertIn('rebar', tr.recommend('Detail', u'NOSA RC Section', u'B1', rebar_visible=True))
        self.assertNotIn('stair_landings', tr.recommend('Section'))

    def test_tag_type_choice_follows_material_and_view(self):
        framing = [u'Mark 45º', u'Mark', u'R.C Beam tag / comment', u'Steel beam tag / comment']
        self.assertEqual(tr.pick_tag_type(framing, 'framing', 'concrete'), 2)
        self.assertEqual(tr.pick_tag_type(framing, 'framing', 'steel'), 3)
        self.assertEqual(tr.pick_tag_type(framing, 'framing', 'section'), 0)
        rebar = [u'Mark only - Dot', u'Full label - Dot', u'Full label - Arrow', u'Mark only - Arrow']
        self.assertEqual(tr.pick_tag_type(rebar, 'rebar', 'plan'), 1)
        self.assertEqual(tr.pick_tag_type(rebar, 'rebar', 'section'), 0)
        self.assertEqual(tr.pick_tag_type([u'Other'], 'walls'), 0)

    def test_piles_are_columns_of_a_pile_family(self):
        self.assertTrue(tr.is_pile(u'NOSA Micro Pile'))
        self.assertFalse(tr.is_pile(u'Concrete Rectangular'))


class MraPickTests(unittest.TestCase):
    """tag_engine.mra_pick: Multi-Rebar Annotation type for rebar sets in plans (T8.15)."""

    def test_dots_before_no_dots(self):
        from nosa_utils import tag_engine
        names = [u'Zone label - Mark only', u'Zone label - No dots', u'Zone label - Dots']
        self.assertEqual(tag_engine.mra_pick(names), 2)

    def test_first_when_nothing_matches(self):
        from nosa_utils import tag_engine
        self.assertEqual(tag_engine.mra_pick([u'MRA A', u'MRA B']), 0)


if __name__ == '__main__':
    unittest.main()
