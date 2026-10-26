# -*- coding: utf-8 -*-
"""nosa_utils.joint_resolution - beam/column joint clash proposals (draft rules, docs/NUDOS_VIGA_PILAR_DISENO.md)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import joint_resolution as jr  # noqa: E402

COL = {'name': u'C1', 'column_bars': [-162.0, 0.0, 162.0], 'column_dia': 20.0, 'compression': False, 'room_mm': 0.0}


def test_centre_gap_is_real_sizes_plus_the_minimum_clear():
    assert abs(jr.centre_gap_mm(20.0, 20.0) - 47.0) < 1e-9          # 1.1 x 20 + max(20, 25, 20)


def test_a_corner_joint_shifts_the_middle_bar_of_a_350_beam():
    # 350 x 600 beam, cover 40, H10 links: cage half 125; 3H20 at -115 / 0 / 115; 450 column, 3H20 a face
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    out = jr.propose(layer, [COL], 125.0)
    assert len(out) == 1 and out[0]['bar'] == 1 and out[0]['rule'] == u'R1'
    assert abs(out[0]['shift_mm']) == 47.0 and all(c['ok'] for c in out[0]['checks'])


def test_d_a_300_beam_with_3h20_has_no_room_and_is_left_flagged():
    # the 4-storey building's beams: 3H20 at -90 / 0 / 90 in a 300 beam, the middle bar on the column's middle bar
    layer = [(-90.0, 20.0), (0.0, 20.0), (90.0, 20.0)]
    out = jr.propose(layer, [dict(COL, compression=True, room_mm=2000.0)], 100.0)
    assert [o['rule'] for o in out] == [u'R3']
    assert any(not c['ok'] for c in out[0]['checks'])                # the crank fails a check, which is named
    assert u'manual review' in out[0]['reason']


def test_b_e_a_line_needs_one_shift_good_at_every_support():
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    left = dict(COL, name=u'C1')
    right = dict(COL, name=u'C2', column_bars=[-162.0, -47.0, 162.0])   # -47 is taken at C2
    out = jr.propose(layer, [left, right], 125.0)
    assert out[0]['rule'] == u'R1' and out[0]['shift_mm'] > 0           # +47 clears both, -47 would hit C2
    for c in out[0]['checks']:
        assert c['ok'], c


def test_r2_cranks_a_compression_bar_that_cannot_shift_and_never_a_tension_one():
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    support = dict(COL, compression=True, room_mm=1000.0)
    out = jr.propose(layer, [support], 125.0, tie_held=(1,))          # held by a tie: no shift
    assert [o['rule'] for o in out] == [u'R2'] and abs(out[0]['crank_mm']) == 47.0
    length = [c for c in out[0]['checks'] if c['check'].startswith(u'crank')][0]['value']
    assert length == 10 * 47.0 + 2 * 5 * 20.0                          # 1:10 plus two 5d straights
    tension = jr.propose(layer, [dict(support, compression=False)], 125.0, tie_held=(1,))
    assert [o['rule'] for o in tension] == [u'R3']


def test_corner_bars_are_never_moved_and_clear_bars_are_left_alone():
    layer = [(-162.0, 20.0), (0.0, 20.0), (162.0, 20.0)]                # corner bars on the column's corner bars
    out = jr.propose(layer, [dict(COL, column_bars=[-162.0, 162.0])], 175.0)
    assert [o['rule'] for o in out] == [u'R3', u'R3'] and [o['bar'] for o in out] == [0, 2]
    assert jr.propose([(-90.0, 20.0), (90.0, 20.0)], [dict(COL, column_bars=[-162.0, 162.0])], 100.0) == []


def test_the_top_layer_keeps_its_poker_gap():
    layer = [(-117.0, 16.0), (0.0, 16.0), (117.0, 16.0)]                # gaps of about 99 mm: the poker fits
    out = jr.propose(layer, [COL], 125.0, top=True)
    poker = [c for c in out[0]['checks'] if c['check'].startswith(u'poker')]
    assert out[0]['rule'] == u'R1' and poker and poker[0]['ok']
