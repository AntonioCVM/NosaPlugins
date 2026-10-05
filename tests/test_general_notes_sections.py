# -*- coding: utf-8 -*-
"""nosa_utils.general_notes_sections: 0900 sections a project can leave out (hide + close the gap)."""
import os
import sys
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import general_notes_sections as gs  # noqa: E402

# two columns: A (x 0) with three sections, B (x 150) with two
HEADINGS = [(u'concrete', 0.0, 500.0), (u'masonry', 2.0, 400.0), (u'timber', 1.0, 300.0),
            (u'steel', 150.0, 500.0), (u'piling', 151.0, 350.0)]


class SectionsTests(unittest.TestCase):

    def test_heading_key_uses_the_first_line(self):
        table = [(u'masonry', u'Masonry', r'^masonry\b'), (u'steel', u'Steelwork', r'^structural steel')]
        self.assertEqual(gs.heading_key(u'MASONRY\rAll blockwork…', table), u'masonry')
        self.assertEqual(gs.heading_key(u'Structural steelwork', table), u'steel')
        self.assertIsNone(gs.heading_key(u'Notes on masonry', table))

    def test_columns_group_by_x_and_sort_top_down(self):
        cols = gs.columns(HEADINGS)
        self.assertEqual([[h[0] for h in c] for c in cols], [[u'concrete', u'masonry', u'timber'],
                                                             [u'steel', u'piling']])

    def test_items_go_to_the_nearest_heading_above_in_their_column(self):
        items = [(1, 5.0, 100.0, 450.0), (2, 5.0, 100.0, 350.0), (3, 160.0, 250.0, 200.0),
                 (4, 5.0, 100.0, 600.0)]           # 4 is above every heading: sheet title
        out = gs.assign(HEADINGS, items)
        self.assertEqual(out[u'concrete'], [1])
        self.assertEqual(out[u'masonry'], [2])
        self.assertEqual(out[u'piling'], [3])
        self.assertNotIn(4, sum(out.values(), []))

    def test_hidden_section_frees_its_band_for_the_ones_below(self):
        bottoms = {u'timber': 220.0, u'piling': 250.0}
        out = gs.shifts(HEADINGS, bottoms, {u'masonry'})
        self.assertEqual(out[u'concrete'], 0.0)
        self.assertEqual(out[u'masonry'], 0.0)
        self.assertEqual(out[u'timber'], 100.0)        # heading 400 -> next heading 300
        self.assertEqual(out[u'steel'], 0.0)

    def test_last_section_hidden_frees_down_to_its_bottom(self):
        out = gs.shifts(HEADINGS, {u'timber': 220.0}, {u'concrete', u'timber'})
        self.assertEqual(out[u'masonry'], 100.0)
        self.assertEqual(out[u'timber'], 0.0)

    def test_state_round_trip_and_bad_json(self):
        text = gs.dump_state([u'timber'], {u'masonry': 100.0, u'concrete': 0.0},
                             {u'masonry': [7, 5], u'concrete': [1], u'timber': [9]})
        self.assertEqual(gs.load_state(text), {u'hidden': [u'timber'], u'shift': {u'masonry': 100.0},
                                               u'members': {u'masonry': [5, 7], u'timber': [9]},
                                               u'geometry': {}})
        self.assertEqual(gs.load_state(u'not json'), {u'hidden': [], u'shift': {}, u'members': {}, u'geometry': {}})
        geo = gs.load_state(gs.dump_state([u'timber'], {}, {u'timber': [9]},
                                          {u'timber': [453.0, 589.0, 504.0], u'masonry': [453.0, 504.0, 300.0]}))
        self.assertEqual(geo[u'geometry'], {u'timber': [453.0, 589.0, 504.0]})

    def test_moved_section_is_assigned_back_home(self):
        # concrete hidden at home (500); masonry (home 400) moved up 100 mm onto concrete's band
        current = [(u'concrete', 0.0, 500.0), (u'masonry', 2.0, 500.0)]
        items = [(1, 5.0, 90.0, 450.0, 440.0),      # concrete note, never moved
                 (2, 5.0, 90.0, 450.0, 440.0)]      # masonry note, now at 450 (home 350)
        state = {u'shift': {u'masonry': 100.0}, u'members': {u'masonry': [2]}}
        home_h, home_i = gs.home_layout(current, items, state)
        self.assertEqual([h[2] for h in home_h], [500.0, 400.0])
        self.assertEqual((home_i[1][3], home_i[1][4]), (350.0, 340.0))
        out = gs.assign(home_h, home_i)
        self.assertEqual(out, {u'concrete': [1], u'masonry': [2]})


if __name__ == '__main__':
    unittest.main()
