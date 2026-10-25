# -*- coding: utf-8 -*-
"""Phase 10 T10.7: EC2 minimum steel and maximum pitch of meshes (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import min_steel as ms  # noqa: E402


def test_slab_limits_250():
    as_min, main, sec = ms.slab_limits(250.0, cover=30.0, dia=12.0, fck=32.0)
    # d = 214; 0.26 x 3.02 / 500 = 0.00157 > 0.0013 -> 336 mm2/m
    assert 330.0 < as_min < 340.0
    assert main == 400.0 and sec == 450.0
    assert ms.slab_limits(100.0)[1] == 300.0


def test_wall_limits_200():
    v, hz, pv, ph = ms.wall_limits(200.0)
    assert v == 200.0 and hz == 100.0 and pv == 400.0 and ph == 400.0


def test_lightest_and_check():
    dia, pitch = ms.lightest(336.0, 400.0)
    assert (dia, pitch) == (10, 225.0)
    assert ms.provided(dia, pitch) >= 336.0
    assert ms.check(10, 300.0, 336.0, 400.0)
    assert not ms.check(12, 300.0, 336.0, 400.0)
    assert ms.check(12, 450.0, 200.0, 400.0) == [u'pitch 450 > 400']
