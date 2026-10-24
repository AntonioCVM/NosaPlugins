# -*- coding: utf-8 -*-
"""T7.3 Create Views: scale choice, sheet packing, sheet numbers (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import view_plan as vp  # noqa: E402


def test_member_sections_at_smdsc_1_20():
    assert vp.choose_scale('member_section', 600.0, 800.0) == 20
    assert vp.choose_scale('member_section', 1200.0, 3000.0) == 20
    assert vp.choose_scale('member_section', 3000.0, 8000.0) == 50


def test_elevations_at_smdsc_1_50_stepping_up_when_tall():
    assert vp.choose_scale('column_elevation', 1000.0, 3500.0) == 50
    assert vp.choose_scale('column_elevation', 1000.0, 24000.0) == 50
    assert vp.choose_scale('column_elevation', 1000.0, 60000.0) == 100
    assert vp.choose_scale('elevation', 9000.0, 900.0) == 50


def test_slab_sections_and_plans():
    assert vp.choose_scale('slab_section', 8000.0, 600.0) == 25
    assert vp.choose_scale('slab_section', 20000.0, 600.0) == 50
    assert vp.choose_scale('slab_section', 40000.0, 600.0) == 100
    assert vp.choose_scale('plan', 15000.0, 12000.0) == 50
    assert vp.choose_scale('plan', 60000.0, 30000.0) == 200


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_layout_keeps_views_apart_and_inside_the_area():
    sizes = [(200.0, 274.0), (250.0, 534.0), (150.0, 534.0), (200.0, 200.0)]
    placed = vp.layout(sizes)
    rects = []
    for (w, h), (sheet, cx, cy) in zip(sizes, placed):
        assert sheet == 0
        r = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
        assert vp.A1_AREA[0] - 1e-6 <= r[0] and r[2] <= vp.A1_AREA[2] + 1e-6
        assert vp.A1_AREA[1] - 1e-6 <= r[1] and r[3] <= vp.A1_AREA[3] + 1e-6
        rects.append(r)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _overlap(rects[i], rects[j])


def test_overflow_opens_a_second_sheet():
    placed = vp.layout([(660.0, 534.0), (660.0, 534.0)])
    assert [p[0] for p in placed] == [0, 1]


def test_next_sheet_numbers_skip_the_taken_ones():
    assert vp.next_sheet_numbers(['4500', '4501', '4503'], 3) == ['4502', '4504', '4505']
    assert vp.next_sheet_numbers([], 1) == ['4500']


def test_coarser_scale_steps_through_the_candidates():
    assert vp.coarser_scale('elevation', 50) == 100
    assert vp.coarser_scale('elevation', 100) is None
    assert vp.coarser_scale('member_section', 20) == 50


def test_layout_keeps_the_legend_corner_free():
    box = (610.0, 25.0, 715.0, 215.0)
    placed = vp.layout([(400.0, 250.0), (300.0, 250.0)], reserved=(box,))
    for (w, h), (sheet, cx, cy) in zip([(400.0, 250.0), (300.0, 250.0)], placed):
        r = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
        assert not _overlap(r, box)


def test_section_offsets_try_the_middle_first():
    offsets = vp.section_offsets(0.0, 1000.0)
    assert offsets[0] == 500.0 and offsets[1] == 400.0 and offsets[2] == 600.0
    assert all(0.0 < o < 1000.0 for o in offsets)


def test_title_width_reads_the_title_on_sheet_first():
    assert vp.title_width_mm(u'Beam B10-B11 - Section mid span 2', u'Section mid span 2') == 18 * 3.0 + 10.0
    assert vp.title_width_mm(u'Plan') == 4 * 3.0 + 10.0


def test_layout_rows_keeps_reading_order_and_lines_up_levels():
    # two elevations whose level datum lies at different depths below their tops, then two sections
    streams = [[(100.0, 200.0, 150.0), (100.0, 230.0, 180.0)], [(60.0, 60.0, None), (60.0, 60.0, None)]]
    out = vp.layout_rows(streams)
    (s1, x1, y1), (s2, x2, y2), (s3, x3, y3), (s4, x4, y4) = out
    assert x1 < x2 and x3 < x4 and s1 == s2 == s3 == s4 == 0
    datum1 = y1 + 100.0 - 150.0
    datum2 = y2 + 115.0 - 180.0
    assert abs(datum1 - datum2) < 1e-6                     # level with each other
    assert y3 + 30.0 < min(y1 - 100.0, y2 - 115.0)          # the sections on the next line down
    assert abs(y3 - y4) < 1e-6


def test_layout_rows_wraps_and_opens_a_new_sheet():
    out = vp.layout_rows([[(400.0, 300.0, None)] * 4])
    assert [o[0] for o in out] == [0, 1, 2, 3]             # one A1 line each: too wide for two, too tall for two


def test_next_mark():
    assert vp.next_mark(u'C', [u'C1', u'C2', u'C3', u'C21']) == u'C4'
    assert vp.next_mark(u'PC', [u'PC10']) == u'PC1'
    assert vp.next_mark(u'B', []) == u'B1'


def test_packed_blocks_fill_the_sheet():
    # a plan with its two sections, a second member and two small details: one sheet, details beside, not below
    blocks = [([(300.0, 250.0, None)], [(140.0, 80.0), (140.0, 80.0)]),
              ([(300.0, 250.0, None)], [(140.0, 80.0)]),
              ([(120.0, 120.0, None)], []), ([(120.0, 120.0, None)], [])]
    out = vp.layout_packed(blocks)
    assert set(s for s, _x, _y in out) == set([0])
    boxes = []
    sizes = [(300.0, 250.0), (140.0, 80.0), (140.0, 80.0), (300.0, 250.0), (140.0, 80.0), (120.0, 120.0),
             (120.0, 120.0)]
    for (s, x, y), (w, h) in zip(out, sizes):
        b = (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)
        assert vp.A1_AREA[0] - 1e-6 <= b[0] and b[2] <= vp.A1_AREA[2] + 1e-6
        assert vp.A1_AREA[1] - 1e-6 <= b[1] and b[3] <= vp.A1_AREA[3] + 1e-6
        for o in boxes:
            assert not (b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3])
        boxes.append(b)
    # sections under their plan
    assert out[1][2] < out[0][2] and out[2][2] < out[0][2]


def test_arrange_block_rows_of_sections():
    w, h, c = vp.arrange_block([(200.0, 100.0, None)], [(150.0, 50.0), (150.0, 50.0)], gap=20.0)
    assert w == 200.0 and len(c) == 3
    assert c[1][1] == c[2][1] - 70.0 or c[2][1] == c[1][1] + 70.0     # two rows: 150 + 20 + 150 > 200


def test_layout_blocks_sections_under_their_elevations():
    blocks = [([(60.0, 300.0, 250.0), (60.0, 300.0, 250.0)], [(50.0, 50.0)]),
              ([(60.0, 280.0, 230.0), (60.0, 280.0, 230.0)], [(40.0, 60.0)])]
    p = vp.layout_blocks(blocks, area=(0.0, 0.0, 800.0, 600.0), gap=10.0)
    assert len(p) == 6
    # datums level: block 2 is 20 shorter above its datum, so its top 20 lower
    assert abs((p[0][2] + 150.0) - (p[3][2] + 140.0 + 20.0)) < 1e-6
    # each section centred under its pair of elevations, feet level
    assert abs(p[2][1] - (p[0][1] + p[1][1]) / 2.0) < 1e-6
    assert abs((p[2][2] - 25.0) - (p[5][2] - 30.0)) < 1e-6
    assert p[2][2] < p[0][2] - 150.0


def test_continuation_sheets_named_by_their_members():
    # 2026-10-24 audit (M7, m5): 'Slabs reinforcement (2)' held S2, whose bars still pointed at 4502
    titles = (u'Slab', u'Beam', u'Column')
    assert vp.member_of_view(u'Slab S2 - Section C-C', titles) == u'S2'
    assert vp.member_of_view(u'Beam B3-B4 - Elevation', titles) == u'B3-B4'
    assert vp.member_of_view(u'TD OP1 - SLAB OPENING TRIMMING', titles) == u''
    assert vp.holds(u'B3-B4', u'B4') and vp.holds(u'S2', u'S2') and not vp.holds(u'S21', u'S2')
    assert vp.sheet_names(u'Slabs reinforcement', [[u'S1', u'S1', u'S3'], [u'S2', u'']]) ==         [u'Slabs reinforcement - S1, S3', u'Slabs reinforcement - S2']
    assert vp.sheet_names(u'Columns reinforcement', [[u'C1', u'C2']]) == [u'Columns reinforcement']


def test_members_that_do_not_touch_the_drawn_one_are_strangers():
    # 2026-10-24 audit (m3): W2's elevation showed a 28 mm strip of the pad F1, 1.4 m off the wall
    wall = ((0.0, 0.0, 0.0), (6000.0, 300.0, 3000.0))
    pad = ((-1500.0, -600.0, -1000.0), (0.0 - 1400.0, 900.0, -500.0))
    base = ((-200.0, -400.0, -500.0), (6200.0, 700.0, 0.0))
    assert not vp.boxes_touch(wall, pad) and vp.boxes_touch(wall, base)
