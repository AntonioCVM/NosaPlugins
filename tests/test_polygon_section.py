# -*- coding: utf-8 -*-
"""polygon_section (T8.58): L and T columns."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import polygon_section as ps  # noqa: E402

L = [(-300, -300), (300, -300), (300, -50), (-50, -50), (-50, 300), (-300, 300)]
T = [(-400, 50), (-125, 50), (-125, -300), (125, -300), (125, 50), (400, 50), (400, 300), (-400, 300)]


def _inside(poly, p):
    return ps._inside(poly, p[0], p[1])


def test_square_cornered_sections():
    assert ps.square_cornered(L) and ps.square_cornered(T)
    octagon = [(100, 0), (70, 70), (0, 100), (-70, 70), (-100, 0), (-70, -70), (0, -100), (70, -70)]
    assert not ps.square_cornered(octagon)              # a faceted circle stays a circle
    assert ps.layout(octagon, 40, 10, 20) is None


def test_l_column_gets_one_link_per_leg_and_bars_inside():
    out = ps.layout(L, 40.0, 10.0, 20.0)
    assert len(out['links']) == 2
    for x, y in out['bars']:
        assert _inside(L, (x, y))
        # at least cover + link + half bar from every side: check against the inset outline
        assert _inside(ps.inset(L, 40.0 + 10.0 + 10.0 - 0.6), (x, y))
    # a bar at the re-entrant corner of the bar line
    assert any(abs(x - (-50 - 60)) < 1 and abs(y - (-50 - 60)) < 1 for x, y in out['bars'])
    # every link corner holds a bar (moved in by link/2 + bar/2)
    for link in out['links']:
        for cx, cy in link:
            assert any(abs(abs(cx - x) - 15) < 1 and abs(abs(cy - y) - 15) < 1 for x, y in out['bars'])


def test_t_column_flange_and_web_and_max_gap():
    out = ps.layout(T, 40.0, 10.0, 20.0, max_gap_mm=200.0)
    assert len(out['links']) == 2
    top = sorted(x for x, y in out['bars'] if abs(y - 240) < 1)      # bars along the flange's top
    gaps = [b - a for a, b in zip(top, top[1:])]
    assert gaps and max(gaps) <= 200.0 + 1e-6


def test_rotated_l_keeps_its_layout():
    import math
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    turned = [(x * c - y * s, x * s + y * c) for x, y in L]
    a, b = ps.layout(L, 40, 10, 20), ps.layout(turned, 40, 10, 20)
    assert len(a['bars']) == len(b['bars']) and len(a['links']) == len(b['links'])
