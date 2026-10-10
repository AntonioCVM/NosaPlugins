# -*- coding: utf-8 -*-
"""IStructE SMDSC Table 6.10 tie bands for 3- and 7-pile caps (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import pile_caps as pc  # noqa: E402

# the v30 template families: 3-pile cap 2000 x 1800 with chamfers, 7-pile cap 2500 x 4200
CAP3 = [(-1000, -750), (1000, -750), (1000, 50), (500, 1050), (-500, 1050), (-1000, 50)]
PILES3 = [(0, 600), (-550, -300), (550, -300)]
CAP7 = [(-1250, -2100), (1250, -2100), (1250, 2100), (-1250, 2100)]
PILES7 = [(0, 1725), (-875, 863), (875, 862), (0, 0), (-875, -863), (875, -862), (0, -1725)]


def _inset(poly, d):
    # the caps above are convex and symmetrical enough for a plain scale towards the centre
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    out = []
    for x, y in poly:
        r = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        out.append((cx + (x - cx) * (r - d) / r, cy + (y - cy) * (r - d) / r))
    return out


def test_only_3_and_7_pile_caps_take_tie_bands():
    assert pc.uses_tie_bands(3) and pc.uses_tie_bands(7)
    assert not any(pc.uses_tie_bands(n) for n in (1, 2, 4, 5, 6, 8, 9))


def test_three_piles_tie_round_the_triangle():
    lines = pc.tie_lines(PILES3)
    assert len(lines) == 3
    assert sorted(round(l['angle']) for l in lines) == [0, 59, 121]


def test_seven_piles_three_directions_of_rows():
    groups = pc.direction_groups(pc.tie_lines(PILES7))
    assert len(groups) == 3
    assert sorted(len(g) for g in groups) == [3, 3, 3]
    vertical = [g for g in groups if abs(g[0]['angle'] - 90.0) < 1.0][0]
    assert [len(l['piles']) for l in vertical] == [2, 3, 2]


def test_clip_to_convex():
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert pc.clip_to_convex(sq, (0, 50), (1, 0)) == (0.0, 100.0)
    assert pc.clip_to_convex(list(reversed(sq)), (50, 50), (0, 1)) == (-50.0, 50.0)
    assert pc.clip_to_convex(sq, (0, 150), (1, 0)) is None


def test_band_layout_of_the_three_pile_cap():
    poly = _inset(CAP3, 85)
    layers = pc.layout(poly, PILES3, 150.0, 300.0)
    assert len(layers) == 3
    assert all(len(l['bars']) == 3 for l in layers)
    for layer in layers:
        for a, b in layer['bars']:
            assert pc.clip_to_convex(CAP3, a, (1, 0)) is not None    # every bar end inside the cap
        assert layer['reach_mm'] > 0
    bottom = [l for l in layers if abs(l['angle']) < 1.0][0]
    assert all(abs(a[1] - b[1]) < 1e-6 for a, b in bottom['bars'])


def test_bar_counts():
    assert pc.band_bar_count(300, 150) == 3 and pc.band_bar_count(600, 150) == 5
    assert pc.band_offsets_mm(3, 150) == [-150.0, 0.0, 150.0]
