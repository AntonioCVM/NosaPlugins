# -*- coding: utf-8 -*-
"""Calling-up placement on reinforcement drawings (SMDSC 6.2.2) — no Revit."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import callout_layout as cl  # noqa: E402

SLAB = (0.0, 0.0, 8000.0, 7000.0)


def test_exit_distance():
    assert cl.exit_distance((1000.0, 500.0), (-1.0, 0.0), SLAB) == 1000.0
    assert cl.exit_distance((1000.0, 500.0), (0.0, 1.0), SLAB) == 6500.0


def test_inline_goes_out_by_the_nearest_edge_on_the_line():
    placed = []
    item = {'a': (500.0, 3000.0), 'b': (2500.0, 3000.0), 'length': 1500.0, 'height': 125.0}
    r = cl.place_inline(item, SLAB, placed, 75.0, 150.0)
    assert r['end'] == 'a' and r['outside']
    assert abs(r['centre'][1] - 3000.0) < 1e-6                       # on the indicator line
    assert abs(r['box'][2] - (0.0 - 150.0)) < 1e-6                    # just past the slab edge
    # a second zone on the same line takes the baseline at the other end, never on top
    r2 = cl.place_inline({'a': (300.0, 3050.0), 'b': (2000.0, 3050.0), 'length': 1500.0, 'height': 125.0},
                         SLAB, placed, 75.0, 150.0)
    assert not cl.overlap(r['box'], r2['box'])
    assert r2['outside'] and r2['end'] == 'b' and abs(r2['box'][0] - (8000.0 + 150.0)) < 1e-6
    # a third one, both baselines taken: a row beside the baseline, so its leader does not cross the first
    r3 = cl.place_inline({'a': (400.0, 3020.0), 'b': (1800.0, 3020.0), 'length': 1500.0, 'height': 125.0},
                         SLAB, placed, 75.0, 150.0)
    assert r3['outside'] and not any(cl.overlap(r3['box'], q['box']) for q in (r, r2))
    assert abs(r3['box'][2] - r['box'][2]) < 1e-6 and abs(r3['centre'][1] - r['centre'][1]) >= 125.0


def test_vertical_lines_take_vertical_text():
    r = cl.place_inline({'a': (4000.0, 6000.0), 'b': (4000.0, 6500.0), 'length': 1500.0, 'height': 125.0},
                        SLAB, [], 75.0, 150.0)
    assert r['end'] == 'b' and r['box'][1] == 7150.0 and r['box'][2] - r['box'][0] == 125.0


def test_pack_keeps_order_and_spacing():
    pos = cl.pack([100.0, 110.0, 120.0, 900.0], [100.0, 100.0, 100.0, 100.0], 20.0)
    assert pos[1] - pos[0] >= 120.0 - 1e-6 and pos[2] - pos[1] >= 120.0 - 1e-6
    assert abs(pos[1] - 110.0) < 1e-6                                 # the cluster stays centred
    assert pos[3] == 900.0
    assert cl.pack([5.0], [10.0], 1.0) == [5.0]


def test_pointers_rows_outside_the_member():
    beam = (0.0, 0.0, 300.0, 600.0)
    items = [{'id': 1, 'anchor': (60.0, 60.0), 'length': 60.0, 'height': 50.0},
             {'id': 2, 'anchor': (150.0, 60.0), 'length': 60.0, 'height': 50.0},
             {'id': 3, 'anchor': (240.0, 60.0), 'length': 60.0, 'height': 50.0},
             {'id': 4, 'anchor': (150.0, 540.0), 'length': 60.0, 'height': 50.0}]
    out = cl.place_pointers(items, beam, 20.0, 100.0)
    assert out[1]['side'] == 'bottom' and out[4]['side'] == 'top'
    assert all(out[i]['centre'][1] < 0.0 for i in (1, 2, 3)) and out[4]['centre'][1] > 600.0
    xs = sorted(out[i]['centre'][0] for i in (1, 2, 3))
    assert xs[1] - xs[0] >= 80.0 - 1e-6 and xs[2] - xs[1] >= 80.0 - 1e-6


def test_pointers_line_up_their_near_ends():
    beam = (0.0, 0.0, 1000.0, 300.0)
    items = [{'id': 1, 'anchor': (100.0, 280.0), 'length': 400.0, 'height': 100.0, 'vertical': True},
             {'id': 2, 'anchor': (600.0, 280.0), 'length': 200.0, 'height': 100.0, 'vertical': True}]
    out = cl.place_pointers(items, beam, 20.0, 50.0)
    assert abs(out[1]['box'][1] - 350.0) < 1e-6 and abs(out[2]['box'][1] - 350.0) < 1e-6
    assert abs((out[1]['box'][2] - out[1]['box'][0]) - 100.0) < 1e-6      # turned: as wide as the text is high
    lower = cl.place_pointers(items, beam, 20.0, 50.0, edges={'top': 500.0})
    assert abs(lower[1]['box'][1] - 550.0) < 1e-6


def test_crowded_rows():
    assert cl.crowded([0.0, 150.0, 300.0], 140.0, 20.0)
    assert not cl.crowded([0.0, 200.0, 400.0], 140.0, 20.0)


def test_tiers_only_where_bars_are_close():
    desired = [0.0, 150.0, 300.0, 450.0, 500.0, 550.0, 600.0, 900.0]
    t = cl.tiers(desired, [80.0] * 8, 20.0)
    assert t[0] == t[1] == t[2] == t[7] == 0
    assert len(set(t[3:7])) == 2                     # 50 apart, 100 needed: two rows


def test_pointers_go_beyond_free_marks():
    slab = (0.0, 0.0, 2000.0, 250.0)
    items = [{'id': 1, 'anchor': (500.0, 40.0), 'length': 80.0, 'height': 80.0, 'vertical': True, 'free': True,
              'outside': 30.0},
             {'id': 2, 'anchor': (505.0, 40.0), 'length': 300.0, 'height': 80.0, 'vertical': True}]
    out = cl.place_pointers(items, slab, 20.0, 100.0)
    assert out[2]['box'][3] <= out[1]['box'][1] + 1e-6 or out[2]['box'][2] <= out[1]['box'][0] + 1e-6 or         out[2]['box'][0] >= out[1]['box'][2] - 1e-6


def test_free_marks_stand_over_their_bars():
    slab = (0.0, 0.0, 2000.0, 250.0)
    items = [{'id': i, 'anchor': (500.0 + 50.0 * i, 40.0), 'length': 80.0, 'height': 80.0, 'vertical': True,
              'free': True, 'outside': 30.0} for i in range(12)]
    out = cl.place_pointers(items, slab, 20.0, 100.0)
    assert max(abs(out[i]['centre'][0] - items[i]['anchor'][0]) for i in range(12)) <= 40.0 + 1e-6
    assert max(out[i]['box'][3] for i in range(12)) <= -30.0 + 1e-6


def test_place_beside_next_to_the_typical_bar():
    box = (0.0, 0.0, 10000.0, 10000.0)
    placed = []
    # a vertical indicator line through (5000, 5000); text 1000 x 200, landing 125 off, 150 lift
    spot = cl.place_beside((5000.0, 5000.0), (0.0, 1.0), 1000.0, 200.0, box, placed, [], 50.0, 125.0, 150.0)
    c, along, side = spot
    assert along == 1.0 and side == 1.0
    assert abs(c[0] - (5000.0 - 650.0)) < 1e-6 and abs(c[1] - (5000.0 + 275.0)) < 1e-6
    assert placed and not cl.overlap(placed[0], (4999.0, 0.0, 5001.0, 10000.0))
    # the same spot taken: the next one is clear of it
    spot2 = cl.place_beside((5000.0, 5000.0), (0.0, 1.0), 1000.0, 200.0, box, placed, [], 50.0, 125.0, 150.0)
    assert spot2 is not None and not cl.overlap(placed[1], placed[0], 50.0)


def test_place_beside_none_outside_the_member():
    assert cl.place_beside((50.0, 50.0), (1.0, 0.0), 1000.0, 200.0, (0.0, 0.0, 300.0, 300.0), [], [], 50.0,
                           125.0, 150.0) is None


def test_side_of_a_bar_standing_out_is_beside():
    box = (0.0, 0.0, 1000.0, 500.0)
    assert cl.side_of((600.0, 900.0), box) == 'right'
    assert cl.side_of((300.0, 900.0), box) == 'left'
    assert cl.side_of((500.0, 480.0), box) == 'top'


def test_align_rows_level_texts_on_their_lines():
    box = (0.0, 0.0, 10000.0, 6000.0)
    items = {
        'h1': {'a': (1000.0, 2000.0), 'b': (9000.0, 2000.0), 'length': 1500.0, 'height': 250.0},
        'h2': {'a': (500.0, 2100.0), 'b': (9500.0, 2100.0), 'length': 1500.0, 'height': 250.0},
        'v1': {'a': (3000.0, 500.0), 'b': (3000.0, 3000.0), 'length': 1500.0, 'height': 250.0, 'at': 900.0},
    }
    out = cl.align_rows(items, box, 50.0, 400.0, lift=20.0)
    # level indicator lines: their texts in a column right of the member, packed apart in their lines' order
    assert out['h1']['side'] == 'right' and out['h2']['side'] == 'right'
    assert out['h2']['centre'][1] - out['h1']['centre'][1] >= 250.0 + 50.0 - 1e-6
    assert out['h1']['path'][0] == (9000.0, 2000.0)
    # every underline level: its last two points at one height, under its text
    for r in out.values():
        (x0, y0), (x1, y1) = r['path'][-2], r['path'][-1]
        assert abs(y0 - y1) < 1e-6 and r['box'][1] > y1
    # an upright line: left, as it is nearer the left side, the underline leaving it at 'at'
    assert out['v1']['side'] == 'left' and out['v1']['path'][0] == (3000.0, 900.0)
    assert out['v1']['box'][2] <= 0.0
    assert not cl.overlap(out['h1']['box'], out['h2']['box'])


def test_align_rows_clear_of_what_is_placed():
    box = (0.0, 0.0, 10000.0, 6000.0)
    items = {'h': {'a': (2000.0, 3000.0), 'b': (9000.0, 3000.0), 'length': 1000.0, 'height': 250.0}}
    out = cl.align_rows(items, box, 50.0, 400.0, placed=[(10200.0, 2800.0, 11000.0, 3400.0)])
    assert out['h']['box'][0] >= 11000.0


def _cross(p, q, r, s):
    """Proper crossing of an axis-aligned segment pq with rs (touching ends allowed)."""
    if p[1] == q[1] and r[0] == s[0]:
        x, y = r[0], p[1]
        return min(p[0], q[0]) < x < max(p[0], q[0]) and min(r[1], s[1]) < y < max(r[1], s[1])
    if p[0] == q[0] and r[1] == s[1]:
        return _cross(r, s, p, q)
    return False


def test_stack_flush_with_the_member():
    right = cl.stack((100.0, 0.0, 160.0, 20.0), 'right', [(60.0, 5.0), (0.0, 5.0), (40.0, 5.0)], 2.5)
    assert right == [(130.0, 17.5), (100.0, 10.0), (120.0, 2.5)]
    left = cl.stack((0.0, 0.0, 60.0, 12.5), 'left', [(60.0, 5.0), (40.0, 5.0)], 2.5)
    assert left == [(30.0, 10.0), (40.0, 2.5)]


def test_align_rows_jogs_never_cross():
    box = (0.0, 0.0, 10000.0, 6000.0)
    # five level lines bunched at nearly one height, all ending at the left: packed apart, jogged
    items = dict(('h%d' % i, {'a': (0.0 + i, 3000.0 + 40.0 * i), 'b': (8000.0, 3000.0 + 40.0 * i),
                              'length': 1200.0, 'height': 250.0}) for i in range(5))
    out = cl.align_rows(items, box, 50.0, 600.0, lift=20.0)
    segs = [(k, a, b) for k, r in out.items() for a, b in zip(r['path'], r['path'][1:])]
    for k1, a, b in segs:
        for k2, c, d in segs:
            if k1 != k2:
                assert not _cross(a, b, c, d), (k1, k2)
