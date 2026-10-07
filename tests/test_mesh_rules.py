# -*- coding: utf-8 -*-
"""nosa_utils.mesh_rules — IStructE SMDSC 6.2 slabs and 6.7 foundations (T8.39/T8.41)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import mesh_rules as mr  # noqa: E402


def test_minimum_ratio_matches_smdsc():
    assert abs(mr.min_ratio(30) - 0.0015) < 0.00002          # SMDSC 6.2: 0.0015 for C30/37
    assert abs(mr.min_ratio(28) - 0.0014) < 0.00005          # SMDSC 6.7: 0.0014 (rounded) for C28/35


def test_slab_review():
    s, ts, notes = mr.slab_review(200, 25, 10, 10, 200, 30)
    assert s == 200 and notes == []                           # H10 at 200 in 200 mm: 393 >= 0.15 % d
    s, _ts, _notes = mr.slab_review(120, 25, 10, 10, 450, 30)
    assert s == 350                                           # 3h = 360 -> 350
    s, _ts, notes = mr.slab_review(200, 25, 8, 8, 450, 30)
    assert s == 400                                           # 400 governs
    assert any(u'As,min' in n for n in notes) and any(u'H10' in n for n in notes)


def test_foundation_review():
    assert mr.foundation_max_pitch_mm(0.004) == 300 and mr.foundation_max_pitch_mm(0.008) == 225
    assert mr.foundation_max_pitch_mm(0.012) == 175
    s, _ts, notes = mr.foundation_review(600, 75, 16, 16, 200, 30)
    assert s == 200 and notes == []
    s, _ts, notes = mr.foundation_review(600, 50, 12, 12, 350, 30, piled=True)
    joined = u' '.join(notes)
    assert s == 300 and u'H16' in joined and u'100 mm' in joined


def test_stair_review():
    m, d, t, notes = mr.stair_review(150, 25, 12, 150, 10, 200, 30, top_dia=10, top_spacing=200)
    assert (m, d, t) == (150, 200, 200) and notes == []
    m, d, t, notes = mr.stair_review(120, 25, 16, 400, 6, 500, 30, top_dia=10, top_spacing=500)
    assert m == 350 and d == 400 and t == 350                   # 3h = 360, 3.5h = 420
    assert any(u'20 %' in n for n in notes)                     # H6@400 = 71 < 0.2 x H16@350 = 115


def test_footing_band():
    assert mr.footing_band_mm(1500, 450, 430) is None              # 1500 < 1.5 x 1740
    assert mr.footing_band_mm(3000, 450, 400) == 1650.0            # 3000 > 1.5 x 1650
    band, left, right = mr.band_layout_mm(0, 3000, 16, 600, 2400)
    assert len(band) == 12 and band[0] == 600 and band[-1] == 2400  # 12 of 16 >= 2/3 under the column
    assert left == [0.0, 300.0] and right == [2700.0, 3000.0]       # outer strips at <= 300
    assert len(band) >= 2 * (len(left) + len(right))
    assert mr.band_layout_mm(0, 3000, 16, 1400, 1500) is None       # band closer than 100 mm


def test_edge_ubars_carry_half_the_bottom_area():
    assert mr.edge_ubar_dia_mm(10, 200, 12, 200) == 10.0          # 100 >= 0.5 x 144
    assert mr.edge_ubar_dia_mm(10, 200, 16, 150) == 16.0          # 0.5 x 256/150 = 0.85 > 144/200
    assert mr.edge_ubar_dia_mm(10, 300, 20, 150) == 20.0          # 400/300 = 0.5 x 400/150 exactly


def test_slab_holes():
    assert mr.slab_hole_class(150, 100) == u'ignore' and mr.slab_hole_class(300, 300) == u'bottom'
    assert mr.slab_hole_class(600, 300) == u'both' and mr.slab_hole_class(1200, 300) == u'design'
    assert mr.trimmers_per_side(300, 200) == 1 and mr.trimmers_per_side(600, 200) == 2
    assert mr.trimmers_per_side(1000, 150) == 4                     # 7 bars cut: 4 each side
