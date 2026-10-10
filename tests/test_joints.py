# -*- coding: utf-8 -*-
"""T8.49 joint coordination rules (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import joints  # noqa: E402


def test_leg_step():
    assert joints.leg_step_mm(20.0, 20.0) == 50.0          # 22 + 25 = 47 -> 50
    assert joints.leg_step_mm(20.0, 16.0) == 45.0          # 19.8 + 25
    assert joints.leg_step_mm(32.0, 32.0) == 70.0          # 35.2 + 32


def test_nested_legs():
    assert joints.nested_leg_insets_mm(20.0, 20.0) == {'support': 0.0, 'bottom': 50.0}
    assert joints.nested_leg_insets_mm(20.0, 20.0, 16.0) == {'support': 45.0, 'bottom': 90.0}


def test_drops():
    assert joints.slab_on_beam_drop_mm(25.0, (12.0, 12.0), 30.0) == 19.0
    assert joints.slab_on_beam_drop_mm(25.0, (10.0, 10.0), 50.0) == 0.0
    assert joints.secondary_drop_mm(20.0) == 20.0 and joints.secondary_drop_mm(None) == 0.0


def test_beam_bars_between_column_bars():
    cols = [-150.0, 0.0, 150.0]
    assert joints.bars_between(cols, [-75.0, 75.0], 25.0, 20.0) == []
    hits = joints.bars_between(cols, [-140.0, 75.0], 25.0, 20.0)
    assert len(hits) == 1 and hits[0][0] == -140.0
