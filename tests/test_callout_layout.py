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
    # a third one, both baselines taken: pushed further out
    r3 = cl.place_inline({'a': (400.0, 3020.0), 'b': (1800.0, 3020.0), 'length': 1500.0, 'height': 125.0},
                         SLAB, placed, 75.0, 150.0)
    assert r3['outside'] and not any(cl.overlap(r3['box'], q['box']) for q in (r, r2))


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
