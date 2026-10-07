# -*- coding: utf-8 -*-
"""nosa_utils.links — IStructE SMDSC 6.3 link rules (T8.37)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import links  # noqa: E402


def test_minimum_shear_ratio_is_0_085_percent_for_c30():
    assert abs(100 * links.rho_w_min(30) - 0.0876) < 0.001


def test_pitch_limits():
    assert links.pitch_limits_mm(540.0, 2) == (100.0, 300.0)
    least, most = links.pitch_limits_mm(300.0, 6, compression_bar_dia_mm=16.0)
    assert least == 125.0 and most == 192.0                    # 12 phi' governs


def test_legs_across_the_width():
    assert links.legs_needed(300.0, 40.0, 8.0, 540.0) == 2
    assert links.legs_needed(700.0, 40.0, 10.0, 640.0) == 4   # 610 inside, legs every 300


def test_beam_review():
    pitch, notes = links.beam_review(300, 600, 40, 8, 20, 200, 2, 30)
    assert pitch == 200 and notes == []
    pitch, notes = links.beam_review(300, 400, 40, 8, 20, 400, 2, 30)
    assert pitch == 250 and notes                               # 0.75 d = 257 -> 250
    _p, notes = links.beam_review(700, 1100, 40, 8, 25, 300, 2, 30)
    joined = u' '.join(notes)
    assert u'vertical legs' in joined and u'open links' in joined and u'side bars' in joined
    assert u'under the minimum' in joined                       # H8 x2 at 300 on 700 wide


def test_column_rules():
    assert links.column_link_dia_min_mm(32.0, 400.0) == 8.0 and links.column_link_dia_min_mm(40.0, 500.0) == 10.0
    assert links.column_max_pitch_mm(16.0, 300.0) == 300.0 and links.column_max_pitch_mm(12.0, 450.0) == 240.0
    small = {'shape': 'rect', 'width_mm': 400.0, 'depth_mm': 400.0}
    pitch, dense, notes = links.column_review(small, 40, 8, 16, 8, (3, 3), 300, 150, True, False)
    assert pitch == 300 and dense == 150 and notes == []          # middle bar 144 mm from a corner
    rect = {'shape': 'rect', 'width_mm': 450.0, 'depth_mm': 450.0}
    _p, _d, notes = links.column_review(rect, 40, 8, 16, 8, (3, 3), 300, 150, True, False)
    assert len(notes) == 1 and u'169 mm' in notes[0]              # SMDSC Fig. 6.24: tie it
    pitch, dense, notes = links.column_review(rect, 40, 8, 16, 12, (4, 4), 400, 300, True, False)
    assert pitch == 300 and dense == 175                         # 0.6 x 300 = 180 -> 175
    big = {'shape': 'rect', 'width_mm': 600.0, 'depth_mm': 600.0}
    _p, _d, notes = links.column_review(big, 40, 8, 16, 16, (5, 5), 300, 150, True, False)
    assert any(u'restrained' in n for n in notes)               # middle bar 244 mm from a corner
    _p, _d, notes = links.column_review(big, 40, 8, 16, 16, (5, 5), 300, 150, True, True)
    assert not any(u'restrained' in n for n in notes)            # alternate bars tied
    circle = {'shape': 'circle', 'diameter_mm': 400.0}
    _p, _d, notes = links.column_review(circle, 40, 8, 16, 4, (0, 0), 250, 150, True, False)
    assert any(u'at least 6' in n for n in notes)


def test_starter_links():
    assert links.starter_link_levels_mm(1000.0, 100.0) == [1000.0, 700.0, 400.0, 100.0]   # H10-300
    assert links.starter_link_levels_mm(500.0, 100.0) == [500.0, 300.0, 100.0]            # 3 at least
    assert links.starter_link_levels_mm(150.0, 100.0) == []                               # no room
    from nosa_utils import standards
    assert standards.FOUNDATION_LEVEL_TOLERANCE_MM == 150.0


def test_lap_link_pitch():
    from nosa_utils import laps
    assert laps.lap_link_pitch_mm(16.0, 825.0, 8.0) is None              # under H20: the links there do
    assert laps.lap_link_pitch_mm(25.0, 1300.0, 8.0) == 200.0            # 2 H8 legs a link: 3 per third
    assert laps.lap_transverse_ok(25.0, 100.0, 1300.0, 8.0, 2, 200.0)
    assert not laps.lap_transverse_ok(25.0, 100.0, 1300.0, 8.0, 2, 225.0)


def test_mc4_top_detail():
    assert links.mc4_min_slab_depth_mm(16.0) == 200.0 and links.mc4_min_slab_depth_mm(25.0) == 250.0
    assert links.mc4_min_slab_depth_mm(32.0) == 300.0 and links.mc4_min_slab_depth_mm(40.0) == 400.0
    corners_and_mids = [(-150.0, 150.0), (0.0, 150.0), (150.0, 150.0), (-150.0, -150.0), (0.0, -150.0),
                        (150.0, -150.0)]
    assert links.mc4_pairs(corners_and_mids, 'u') == [(-150.0, -150.0, 150.0), (0.0, -150.0, 150.0),
                                                       (150.0, -150.0, 150.0)]
    assert links.mc4_pairs([(-150.0, 0.0), (150.0, 0.0)], 'v') == [(0.0, -150.0, 150.0)]


def test_helix_pieces():
    one = links.helix_pieces_mm(2900.0, 100.0, 175.0, stock_mm=50000.0)
    assert one == [(0.0, 2900.0)]
    pieces = links.helix_pieces_mm(2900.0, 100.0, 175.0)          # 1.1 m a turn: 10 turns in 12 m
    assert pieces[0] == (0.0, 900.0) and pieces[1][0] == 800.0    # next piece laps one turn
    assert abs(pieces[-1][0] + pieces[-1][1] - 2900.0) < 1e-6
