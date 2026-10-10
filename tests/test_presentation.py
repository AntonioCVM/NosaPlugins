# -*- coding: utf-8 -*-
"""SMDSC 6.2.2 bar presentation rules (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import presentation as pr  # noqa: E402


def _set(id_, mark, x0, n, spacing, y0=0.0, y1=3000.0, count=None):
    # bars along y, spread along x
    return {'id': id_, 'mark': mark, 'count': count or n, 'bar_dir': (0.0, 1.0), 'spread_dir': (1.0, 0.0),
            'first': (x0, (y0 + y1) / 2.0), 'last': (x0 + (n - 1) * spacing, (y0 + y1) / 2.0),
            'ends': ((x0, y0), (x0, y1)), 'spacing': spacing}


def test_typical_bar():
    assert pr.is_typical_bar_set(0.0, True)
    assert not pr.is_typical_bar_set(1.0, True)          # bars cut by a section
    assert not pr.is_typical_bar_set(0.0, False)         # seen end-on


def test_zone_quantities():
    sets = [_set(1, u'63', 0, 12, 150), _set(2, u'63', 4000, 8, 150), _set(3, u'64', 0, 5, 200)]
    assert pr.zone_labels(sets) == {1: u'(12)', 2: u'(8)'}


def test_alternate_and_stagger():
    a, b = _set(1, u'63', 0, 10, 300), _set(2, u'64', 150, 10, 300)
    assert pr.relation(a, b) == u'Alt.'
    assert pr.relation(a, _set(3, u'64', 100, 10, 300)) is None          # not half a pitch apart
    c = _set(4, u'63', 150, 10, 300, y0=800.0, y1=3800.0)
    assert pr.relation(a, c) == u'Stg.'
    d = _set(5, u'63', 0, 10, 300, y0=3000.0, y1=6000.0)
    assert pr.relation(a, d) is None                                      # end to end, two runs
    assert pr.relations([a, b, c]) == [(1, 2, u'Alt.'), (1, 4, u'Stg.')]


def test_curtailed_ends_and_ticks():
    assert pr.curtailed(2000.0, 0.0, 6000.0, 40.0, 16.0)
    assert not pr.curtailed(50.0, 0.0, 6000.0, 40.0, 16.0)
    p, q = pr.tick((100.0, 0.0), (1.0, 0.0), (0.0, 1.0), 50)
    assert p == (100.0, 0.0)
    assert abs(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) - 30.0) < 1e-6
    assert abs(math.hypot(q[0] - p[0], q[1] - p[1]) - 150.0) < 1e-6


def test_see_drawing():
    assert pr.see_drawing(u'4002', u'4003') == u'SEE DRG 4002'
    assert pr.see_drawing(u'4002', u'4002') is None
    assert pr.see_drawing(u'', u'4002') is None


def test_layer_slots_spread_coincident_sets():
    a = dict(_set(1, u'01', 0, 20, 150), layer=u'B1')
    b = dict(_set(2, u'02', 75, 20, 150), layer=u'T1')
    c = dict(_set(3, u'03', 9000, 5, 150), layer=u'B1')            # its own zone
    slots = pr.layer_slots([b, a, c])
    assert slots[1] == 1.0 / 3.0 and slots[2] == 2.0 / 3.0 and slots[3] == 0.5
