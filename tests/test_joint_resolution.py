# -*- coding: utf-8 -*-
"""nosa_utils.joint_resolution - beam/column joint clash proposals (rules approved 2026-10-26, cases A-G)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import joint_resolution as jr  # noqa: E402

# a 450 column, 3H20 a face; its face 225 mm from the beam's start; no forces in the model
COL = {'name': u'C1', 'column_bars': [-162.0, 0.0, 162.0], 'column_dia': 20.0, 'forces': None,
       'face_mm': 225.0, 'toward': -1.0, 'span_mm': (225.0, 5775.0), 'zones_mm': []}
COMPRESSION = {'compression_all': True, 'tension_any': False}


def checks_of(proposal, start):
    return [c for c in proposal['checks'] if c['check'].startswith(start)]


def test_centre_gap_is_real_sizes_plus_the_minimum_clear():
    assert abs(jr.centre_gap_mm(20.0, 20.0) - 47.0) < 1e-9          # 1.1 x 20 + max(20, 25, 20)


def test_a_corner_joint_shifts_the_middle_bar_of_a_350_beam():
    # 350 x 600 beam, cover 40, H10 links: cage half 125; 3H20 at -115 / 0 / 115
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    out = jr.propose(layer, [COL], 125.0)
    assert len(out) == 1 and out[0]['bar'] == 1 and out[0]['rule'] == u'R1'
    assert abs(out[0]['shift_mm']) == 47.0 and all(c['ok'] for c in out[0]['checks'])
    limit = checks_of(out[0], u'shift within')[0]
    assert limit['limit'] == 50.0 and limit['value'] == 47.0       # min(115 / 2, 50)


def test_b_an_interior_joint_is_solved_each_way():
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    for name in (u'C5 x', u'C5 y'):
        out = jr.propose(layer, [dict(COL, name=name)], 125.0)
        assert [o['rule'] for o in out] == [u'R1']


def test_c_a_full_depth_beam_under_a_slab_shifts_as_a_and_leaves_the_slab():
    # the slab's bars beside the beam (parallel, 300 off its centre) are out of reach of the shift
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    out = jr.propose(layer, [COL], 125.0, parallel=[(-300.0, 12.0), (300.0, 12.0)])
    assert out[0]['rule'] == u'R1' and abs(out[0]['shift_mm']) == 47.0


def test_d_a_300_beam_with_3h20_has_no_room_and_is_left_flagged():
    # the 4-storey building's beams: 3H20 at -90 / 0 / 90 in a 300 beam, the middle bar on the column's middle bar
    layer = [(-90.0, 20.0), (0.0, 20.0), (90.0, 20.0)]
    out = jr.propose(layer, [dict(COL, forces=COMPRESSION)], 100.0)
    assert [o['rule'] for o in out] == [u'R3']
    assert any(not c['ok'] for c in out[0]['checks'])                 # each failed check is named
    assert u'manual review' in out[0]['reason']


def test_e_a_line_needs_one_shift_good_at_every_support():
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    right = dict(COL, name=u'C2', column_bars=[-162.0, -47.0, 162.0])     # -47 is taken at C2
    out = jr.propose(layer, [COL, right], 125.0)
    assert out[0]['rule'] == u'R1' and out[0]['shift_mm'] > 0            # +47 clears both, -47 would hit C2
    assert all(c['ok'] for c in out[0]['checks'])


def test_f_a_shift_onto_a_secondary_beam_or_slab_bar_is_refused():
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    # a secondary beam's top bar at +45 along the length: +47 would clash, -47 is clear
    out = jr.propose(layer, [COL], 125.0, top=False, parallel=[(45.0, 16.0)])
    assert out[0]['rule'] == u'R1' and out[0]['shift_mm'] == -47.0
    # both sides taken (slab bars at +45 and -45): no shift keeps s_min along the length -> R3
    both = jr.propose(layer, [COL], 125.0, parallel=[(45.0, 16.0), (-45.0, 16.0)])
    assert [o['rule'] for o in both] == [u'R3'] and both[0]['checks']


def test_g_no_crank_where_the_bar_may_be_in_tension():
    # an intermediate support, the bottom bar held by a tie (no shift): tension in one combination -> R3
    layer = [(-110.0, 25.0), (0.0, 25.0), (110.0, 25.0)]
    support = dict(COL, name=u'C2', forces={'compression_all': False, 'tension_any': True}, face_mm=6225.0,
                   toward=1.0, span_mm=(225.0, 6225.0))
    out = jr.propose(layer, [support], 125.0, tie_held=(1,))
    assert [o['rule'] for o in out] == [u'R3']
    assert any(c['check'].startswith(u'compression') and not c['ok'] for c in out[0]['checks'])
    # no forces in the model at all: R3 too
    assert [o['rule'] for o in jr.propose(layer, [dict(support, forces=None)], 125.0, tie_held=(1,))] == [u'R3']


def test_r2_cranks_a_compression_bar_within_2d_and_keeps_out_of_the_zones():
    # H25 (2d = 50): a 49.8 mm crank (1.1 x 22.5 + 25) is allowed when the forces prove compression in every combination
    layer = [(-110.0, 25.0), (0.0, 25.0), (110.0, 25.0)]
    support = dict(COL, name=u'C2', forces=COMPRESSION, face_mm=6225.0, toward=1.0, span_mm=(225.0, 6225.0))
    out = jr.propose(layer, [support], 125.0, tie_held=(1,))
    assert [o['rule'] for o in out] == [u'R2'] and abs(out[0]['crank_mm']) == 49.8
    assert all(c['ok'] for c in out[0]['checks'])
    assert checks_of(out[0], u'offset')[0]['limit'] == 50.0


def test_r2_offset_over_2d_or_into_a_lap_zone_falls_to_r3():
    layer = [(-115.0, 20.0), (0.0, 20.0), (115.0, 20.0)]
    base = dict(COL, name=u'C2', forces=COMPRESSION, face_mm=6225.0, toward=1.0, span_mm=(225.0, 6225.0))
    over = jr.propose(layer, [base], 125.0, tie_held=(1,))             # 47 mm > 2 x 20 = 40
    assert [o['rule'] for o in over] == [u'R3']
    assert any(c['check'].startswith(u'offset') and not c['ok'] for c in over[0]['checks'])
    lap = jr.propose([(-110.0, 25.0), (0.0, 25.0), (110.0, 25.0)],
                     [dict(base, zones_mm=[(5600.0, 6225.0)])], 125.0, tie_held=(1,))
    assert [o['rule'] for o in lap] == [u'R3']
    assert any(c['check'].startswith(u'crank out of the anchorage') and not c['ok'] for c in lap[0]['checks'])


def test_corner_bars_are_never_moved_and_clear_bars_are_left_alone():
    layer = [(-162.0, 20.0), (0.0, 20.0), (162.0, 20.0)]                # corner bars on the column's corner bars
    out = jr.propose(layer, [dict(COL, column_bars=[-162.0, 162.0])], 175.0)
    assert [o['rule'] for o in out] == [u'R3', u'R3'] and [o['bar'] for o in out] == [0, 2]
    assert jr.propose([(-90.0, 20.0), (90.0, 20.0)], [dict(COL, column_bars=[-162.0, 162.0])], 100.0) == []


def test_the_top_layer_keeps_its_poker_gap():
    layer = [(-117.0, 16.0), (0.0, 16.0), (117.0, 16.0)]                # gaps of about 99 mm: the poker fits
    out = jr.propose(layer, [COL], 125.0, top=True)
    poker = checks_of(out[0], u'poker')
    assert out[0]['rule'] == u'R1' and poker and poker[0]['ok']
