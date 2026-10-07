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
