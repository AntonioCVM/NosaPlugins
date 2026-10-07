# -*- coding: utf-8 -*-
"""nosa_utils.wall_rules — IStructE SMDSC 6.5 / MW1 (T8.40)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import wall_rules as wr  # noqa: E402


def test_mw1_table():
    assert wr.mw1_nominal(200) == {'vert_dia': 12, 'vert_spacing': 250, 'horiz_dia': 10, 'horiz_spacing': 200}
    assert wr.mw1_nominal(450)['vert_spacing'] == 200 and wr.mw1_nominal(450)['horiz_spacing'] == 150
    assert wr.mw1_nominal(120) is None and wr.mw1_nominal(900) is None


def test_mw1_nominal_meets_its_own_rules():
    for t in (160, 190, 225, 275, 350, 450, 550, 650, 750):
        n = wr.mw1_nominal(t)
        _v, _h, notes = wr.review(t, n['vert_dia'], n['vert_spacing'], n['horiz_dia'], n['horiz_spacing'])
        assert notes == [], (t, notes)


def test_review():
    vs, hs, notes = wr.review(100, 10, 400, 8, 400)
    assert vs == 300 and hs == 300                                 # min(3t, 400)
    joined = u' '.join(notes)
    assert u'150 mm' in joined and u'robust cage' in joined
    _v, _h, notes = wr.review(200, 32, 100, 12, 200)
    assert any(u'links are needed' in n for n in notes)            # 8 % vertical steel


def test_retaining_review():
    vs, hs, notes = wr.retaining_review(12000.0, 250.0, 200.0, 40.0, label=u'Wall 1')
    assert (vs, hs) == (200.0, 200.0)
    assert any(u'200' in n for n in notes) and any(u'50 mm' in n for n in notes)
    _vs, _hs, notes = wr.retaining_review(35000.0, 150.0, 150.0, 50.0)
    assert len(notes) == 1 and u'30 m' in notes[0]
