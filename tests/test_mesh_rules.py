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
