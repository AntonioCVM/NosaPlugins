# -*- coding: utf-8 -*-
"""T8.53 water-retaining structures, SMDSC chapter 9 (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import water_retaining as wr  # noqa: E402


def test_crack_width():
    assert wr.crack_width_mm(0) is None and wr.crack_width_mm(2) == 0.0
    assert wr.crack_width_mm(1, 1.0, 300.0) == 0.2
    assert wr.crack_width_mm(1, 9.0, 300.0) == 0.05
    assert abs(wr.crack_width_mm(1, 4.5, 300.0) - 0.125) < 1e-9          # hD/hw = 15


def test_review():
    main, dist, notes = wr.review(140.0, 30.0, 300.0, 200.0, tightness=1, label=u'Wall 1')
    assert main == 250.0 and dist == 150.0
    text = u' '.join(notes)
    assert u'150 mm of tightness class 1' in text and u'cover 30' in text and u'joint' in text
    main, dist, notes = wr.review(300.0, 45.0, 200.0, 150.0, tightness=0)
    assert (main, dist) == (200.0, 150.0) and len(notes) == 1
