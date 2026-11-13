# -*- coding: utf-8 -*-
"""T8.50 robustness ties (SMDSC 5.1.9), no Revit."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import ties  # noqa: E402


def test_tie_forces():
    assert ties.ft_kn(3) == 32.0 and ties.ft_kn(12) == 60.0
    assert ties.peripheral_kn(5) == 40.0
    assert abs(ties.internal_kn_per_m(10.0, 7.5, 5) - 80.0) < 1e-9          # 10/7.5 x 7.5/5 x 40
    assert ties.internal_kn_per_m(3.0, 4.0, 5) == 40.0                       # never under Ft
    assert ties.column_tie_kn(5, 3.0, 1000.0) == 48.0                        # 2Ft = 80 capped at 3/2.5 x 40
    assert ties.column_tie_kn(5, 3.0, 4000.0) == 120.0                       # 3 % of the load
    assert ties.internal_max_spacing_m(6.0) == 9.0


def test_steel():
    assert ties.area_mm2(40.0) == 80.0
    assert ties.bars_needed(40.0, 10.0) == 2 and ties.bars_needed(80.0, 12.0) == 2 and ties.bars_needed(80.0, 16.0) == 1


def test_continuity():
    assert ties.coverage([(0.0, 6000.0), (5400.0, 12000.0)], 0.0, 12000.0, lap_mm=500.0) == (1.0, [], [])
    share, gaps, joints = ties.coverage([(0.0, 6000.0), (6000.0, 12000.0)], 0.0, 12000.0, lap_mm=500.0)
    assert share == 1.0 and gaps == [] and joints == [6000.0]              # end to end: no lap
    share, gaps, joints = ties.coverage([(0.0, 5000.0), (7000.0, 12000.0)], 0.0, 12000.0)
    assert abs(share - 10.0 / 12.0) < 1e-9 and gaps == [(5000.0, 7000.0)] and joints == []
