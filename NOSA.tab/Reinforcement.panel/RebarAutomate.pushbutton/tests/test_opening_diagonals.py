# -*- coding: utf-8 -*-
"""Checks for floor_rebar.opening_corner_diagonals_mm: 45° bars at opening corners (D3 / T4.6)."""
import math
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib')
sys.path.insert(0, _LIB)
import slab_topology as topo  # noqa: E402
import floor_rebar  # noqa: E402

COVER = 30.0
DIA = 12.0
HALF = 480.0
raw_outer = [(0.0, 0.0), (6000.0, 0.0), (6000.0, 6000.0), (0.0, 6000.0)]
raw_hole = [(2500.0, 2500.0), (3500.0, 2500.0), (3500.0, 3300.0), (2500.0, 3300.0)]
outer = topo.offset_polygon_mm(raw_outer, COVER)
holes = [topo.offset_polygon_mm(raw_hole, -COVER)]

segments, skipped = floor_rebar.opening_corner_diagonals_mm(
    topo, [raw_hole], outer, holes, COVER, DIA, HALF)
assert skipped == 0 and len(segments) == 4, (len(segments), skipped)
for (x0, y0), (x1, y1) in segments:
    assert abs(math.hypot(x1 - x0, y1 - y0) - 2 * HALF) < 1e-6, 'full length both sides'
    assert abs(abs(x1 - x0) - abs(y1 - y0)) < 1e-6, 'bar at 45°'
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    corner = min(raw_hole, key=lambda v: math.hypot(v[0] - mx, v[1] - my))
    d = math.hypot(mx - corner[0], my - corner[1])
    assert abs(d - (math.sqrt(2) * COVER + DIA)) < 1e-6, 'bar clear of the cover corner'
    for t in [i / 20.0 for i in range(21)]:
        assert topo.point_in_material_mm(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, outer, holes)
print('opening_corner_diagonals_mm: four 45° bars, clear of the opening: OK')

# An opening near the slab edge: the corners with no room are skipped, not built outside.
edge_hole = [(200.0, 2500.0), (1200.0, 2500.0), (1200.0, 3500.0), (200.0, 3500.0)]
segments, skipped = floor_rebar.opening_corner_diagonals_mm(
    topo, [edge_hole], outer, [topo.offset_polygon_mm(edge_hole, -COVER)], COVER, DIA, HALF)
assert len(segments) == 2 and skipped == 2, (len(segments), skipped)
print('opening_corner_diagonals_mm: corners against the slab edge are skipped: OK')

# L-shaped opening: the re-entrant corner gets no bar.
l_hole = [(2000.0, 2000.0), (3500.0, 2000.0), (3500.0, 2800.0), (2800.0, 2800.0),
          (2800.0, 3500.0), (2000.0, 3500.0)]
segments, skipped = floor_rebar.opening_corner_diagonals_mm(
    topo, [l_hole], outer, [topo.offset_polygon_mm(l_hole, -COVER)], COVER, DIA, HALF)
assert len(segments) == 5 and skipped == 0, (len(segments), skipped)
print('opening_corner_diagonals_mm: no bar at a re-entrant opening corner: OK')
print('\nALL OPENING DIAGONAL CHECKS PASSED')


def test_neighbouring_diagonals_cross_in_contact():
    # two corners' diagonals crossing beside the opening: the second goes up a level; a third clear of both stays
    a = ((0.0, 0.0), (1000.0, 1000.0))
    b = ((0.0, 1000.0), (1000.0, 0.0))
    c = ((3000.0, 0.0), (4000.0, 1000.0))
    assert floor_rebar.diagonal_levels([a, b, c]) == [0, 1, 0]
    assert floor_rebar.diagonal_levels([a, c]) == [0, 0]


test_neighbouring_diagonals_cross_in_contact()
print('diagonal_levels: crossing diagonals at two levels: OK')


def test_trimmers_kept_off_the_mat_rows():
    rows = [0.0, 150.0, 300.0]
    two = floor_rebar.clear_of_rows([2.0, 52.0], rows, 16.0, 16.0, 1.0)           # 2 mm into the row at 0
    assert all(abs(t - r) >= 1.1 * 16.0 + 25.0 for t in two for r in rows) and abs(two[1] - two[0] - 50.0) < 1e-6
    three = floor_rebar.clear_of_rows([2.0, 52.0, 102.0], rows, 16.0, 16.0, 1.0)  # no room for 25 mm: in contact
    assert all(abs(t - r) >= 1.1 * 16.0 - 1e-6 for t in three for r in rows)


test_trimmers_kept_off_the_mat_rows()
print('clear_of_rows: trimmers off the mat rows: OK')
