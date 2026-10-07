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
