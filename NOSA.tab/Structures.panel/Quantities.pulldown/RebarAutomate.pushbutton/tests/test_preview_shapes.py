# -*- coding: utf-8 -*-
"""Checks for rebar_preview_shapes: previews show the detailing the generators build (T2.19)."""
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib')
sys.path.insert(0, _LIB)
import rebar_preview_shapes as shapes  # noqa: E402


def _bars(items, role):
    return [s for s in items if s['kind'] == 'bar' and s['role'] == role]


# Dowels: L bars whose foot points away from the column centre, >= 450 mm.
footing = shapes.mat_section_shapes(1500, 500, 40, 16, 16, 150, include_top=True, top_cover_mm=40,
                                    top_dia_x=12, top_dia_y=12, top_spacing_mm=150, dowels=True,
                                    dowel_dia=16, dowel_splice_mm=600, kicker_mm=75)
dowels = _bars(footing, 'dowel')
assert len(dowels) == 2
for bar in dowels:
    (tip_x, _), (corner_x, _), (_, top_y) = bar['points']
    assert abs(tip_x) > abs(corner_x), 'dowel foot must point outwards'
    assert abs(tip_x - corner_x) >= 450.0 - 1e-6 or abs(tip_x) >= 750.0 - 40.0 - 1e-6
    assert abs(top_y - (500 + 75 + 600)) < 1e-6, 'lap measured above the kicker'
print('mat_section_shapes: dowels are L bars, feet out, lap above the kicker: OK')

# Slab edge U-bars: legs of at least 2h.
slab = shapes.mat_section_shapes(3000, 300, 30, 12, 12, 200, include_top=True, top_cover_mm=30,
                                 top_dia_x=10, top_dia_y=10, top_spacing_mm=200, ubars=True,
                                 ubar_dia=10, is_floor=True)
for bar in _bars(slab, 'ubar'):
    leg = abs(bar['points'][0][0] - bar['points'][1][0])
    assert abs(leg - 600.0) < 1e-6, 'slab U-bar leg must be 2h = 600 mm, got {}'.format(leg)
print('mat_section_shapes: slab edge U-bars have 2h legs: OK')

# Column elevation: foundation starters with feet outwards.
elev = shapes.column_elevation_shapes(450, 3000, 40, 20, 10, 200, foundation_starters=True,
                                      starter_dia=20, starter_splice_mm=600, kicker_mm=75)
starters = _bars(elev, 'starter')
assert len(starters) == 2
for bar in starters:
    (tip_x, _), (corner_x, _), _ = bar['points']
    assert abs(tip_x) > abs(corner_x) and abs(tip_x - corner_x) >= 450.0 - 1e-6
print('column_elevation_shapes: starter feet point outwards, 450 mm: OK')

# Column section: one hollow starter inside each vertical.
positions = [(-165.0, -240.0), (165.0, -240.0), (165.0, 240.0), (-165.0, 240.0)]
plan = shapes.column_section_shapes(450, 600, 40, 20, positions, 10, starters=True, starter_dia=20)
hollow = [s for s in plan if s['kind'] == 'dot' and s.get('hollow')]
assert len(hollow) == 4
for dot, (x, y) in zip(hollow, positions):
    assert abs(dot['x']) < abs(x) and abs(dot['y']) < abs(y), 'starter lapped on the inner side'
print('column_section_shapes: starters lapped on the inner side of each vertical: OK')

# Column section: crossties from the preview data are drawn as links (12 bars: straight ties;
# 8 bars on a square column: one interior diamond loop, as column_rebar.build_crosstie_sets builds it).
import rebar_preview  # noqa: E402
for depth, count, loop_segments in ((600, 12, None), (400, 8, 4)):
    data = rebar_preview.compute_column_section_preview(400, depth, 40, 20, count, 10,
                                                        include_crossties=True)
    ties = [(t['x1_mm'], t['y1_mm'], t['x2_mm'], t['y2_mm']) for t in data['crossties']]
    assert ties, 'expected crossties for {} bars'.format(count)
    if loop_segments:
        assert len(ties) == loop_segments, 'single interior bar per side -> closed diamond loop'
        assert all(abs(t[0] - t[2]) > 1 and abs(t[1] - t[3]) > 1 for t in ties), 'diamond sides are diagonal'
    plan = shapes.column_section_shapes(400, depth, 40, 20, [(b['x_mm'], b['y_mm']) for b in data['bars']],
                                        10, crossties=ties)
    assert len(_bars(plan, 'link')) == 1 + len(ties), 'crossties must reach the drawing'
print('column_section_shapes: crossties drawn (straight ties and 8-bar diamond loop): OK')
print('\nALL PREVIEW SHAPES CHECKS PASSED')
