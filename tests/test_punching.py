# -*- coding: utf-8 -*-
"""Punching shear (EC2 6.4, UK NA) and shear stud rail layout (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import punching as pu  # noqa: E402

COL = {'c1': 400.0, 'c2': 400.0}


def _close(a, b, tol=0.01):
    assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)


def test_perimeters():
    _close(pu.perimeter_mm(COL, 0.0), 1600.0)
    _close(pu.perimeter_mm(COL, 400.0), 1600.0 + 2.0 * math.pi * 400.0)
    _close(pu.perimeter_mm({'d': 400.0}, 400.0), math.pi * 1200.0)
    # an edge column flush with the slab edge at x = 200: about half the round part and one face drop out
    slab = [(-5000, -5000), (200, -5000), (200, 5000), (-5000, 5000)]
    _close(pu.perimeter_mm(COL, 400.0, slab), 400.0 * 3 + math.pi * 400.0, 0.02)


def test_resistances():
    _close(pu.v_rd_c(200.0, 0.01, 32.0), 0.762, 0.005)
    _close(pu.v_rd_c(200.0, 0.001, 32.0), 0.035 * 2 ** 1.5 * 32 ** 0.5, 0.005)   # vmin governs
    _close(pu.v_rd_max(32.0), 5.58, 0.005)


def test_design_of_an_interior_column():
    r = pu.design(600.0, 1.15, COL, 200.0, 0.01, 32.0, 10.0)
    assert r['needed'] and r['ok']
    _close(r['v_ed1'], 0.839, 0.01)
    _close(r['asw_mm2'], 366.7, 0.02)
    assert r['perimeters'] == [100.0, 250.0]
    assert r['studs_per_perimeter'] == 5
    assert len(r['rails']) == 12 and all(len(rl['studs']) == 2 for rl in r['rails'])
    # the last perimeter within 1.5 d of u_out
    assert r['perimeters'][-1] >= r['a_out'] - 1.5 * 200.0


def test_light_load_and_overload():
    assert not pu.design(200.0, 1.15, COL, 200.0, 0.01, 32.0, 10.0)['needed']
    over = pu.design(1400.0, 1.15, COL, 200.0, 0.01, 32.0, 10.0)
    assert over['needed'] and not over['ok'] and u'2.0 vRd,c' in over['notes'][0]
    crush = pu.design(5000.0, 1.15, COL, 200.0, 0.01, 32.0, 10.0)
    assert not crush['ok'] and u'vRd,max' in crush['notes'][0]


def test_tangential_spacing_and_edge_rails():
    r = pu.design(600.0, 1.15, COL, 200.0, 0.01, 32.0, 10.0)
    for a in r['perimeters']:
        limit = (1.5 if a <= 400.0 else 2.0) * 200.0
        assert pu.perimeter_mm(COL, a) / len(r['rails']) <= limit + 1e-6
    slab = [(-5000, -5000), (200, -5000), (200, 5000), (-5000, 5000)]
    edge = pu.design(400.0, 1.4, COL, 200.0, 0.01, 32.0, 10.0, polygon=slab)
    assert edge['needed']
    assert all(pu.point_in_polygon(x, y, slab) for rl in edge['rails'] for x, y in rl['studs'])
    assert all(len(rl['studs']) >= 1 for rl in edge['rails'])


def test_stud_height():
    assert pu.stud_height_mm(250.0, 25.0, 25.0, 6.0) == 194.0
