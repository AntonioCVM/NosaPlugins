# -*- coding: utf-8 -*-
"""T7.8 stairs: flight and landing bars stay in the concrete and cross at re-entrant knees (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import math  # noqa: E402
import stair_rebar as sr  # noqa: E402

COVER = 40.0
RISER, TREAD = 176.5, 280.0
SLOPE = RISER / TREAD


def first_flight():
    """Revit 2024 'Concrete Stair': 10 risers 176.5 / 280, 150 mm landing at 1765, floor start."""
    return {'length': 2520.0, 'slope': SLOPE, 'soffit_z0': -193.0, 'pitch_z0': 0.0,
            'v_min': -500.0, 'v_max': 500.0, 'risers': 10, 'riser': RISER, 'tread': TREAD,
            'lower': {'kind': 'floor', 'top': 0.0, 'bottom': 0.0, 's_far': 0.0},
            'upper': {'kind': 'landing', 'top': 1765.0, 'bottom': 1615.0, 's_far': 3520.0}}


def second_flight():
    """Same flight starting from that landing (dog-leg), landing 1000 mm deep behind its first riser."""
    run = first_flight()
    run.update({'soffit_z0': 1765.0 - 193.0, 'pitch_z0': 1765.0})
    run['lower'] = {'kind': 'landing', 'top': 1765.0, 'bottom': 1615.0, 's_far': -1000.0}
    run['upper'] = {'kind': 'floor', 'top': 3530.0, 'bottom': None, 's_far': 2520.0}
    return run


def inside(run, s, z, cover=COVER, tol=1.0):
    """Point within the concrete of the flight and its landings, cover respected."""
    lower, upper = run['lower'], run['upper']
    soffit = sr.Line(run['soffit_z0'], run['slope'])
    pitch = sr.Line(run['pitch_z0'], run['slope'])
    c = cover / sr._cos(run['slope'])
    if lower['kind'] == 'landing' and lower['s_far'] - tol <= s <= 0.0:
        return lower['bottom'] + cover - tol <= z <= lower['top'] - cover + tol and \
            s >= lower['s_far'] + cover - tol
    if upper['kind'] == 'landing' and s >= run['length']:
        floor = min(upper['bottom'], soffit.z(s))       # the soffit runs on under the landing
        return floor + cover - tol <= z <= upper['top'] - cover + tol and s <= upper['s_far'] - cover + tol
    floor_z = max(soffit.z(s) + c, lower['bottom'] + cover if lower['kind'] == 'floor' else -1e9)
    if upper['kind'] == 'landing':
        floor_z = max(soffit.z(s) + c, -1e9) if s > 0 else floor_z
    ceiling = pitch.z(s) + RISER - cover          # the stepped top is at least a riser above the pitch line
    if upper['kind'] == 'landing':
        ceiling = min(max(ceiling, pitch.z(s)), upper['top'] - cover)
    return floor_z - tol <= z <= ceiling + tol


def _sets(run):
    return sr.build_flight(run, COVER, 12.0, 200.0, 8.0, 200.0, anchorage=480.0)


def _by_label(sets, label):
    return [s for s in sets if s['label'] == label]


def test_bottom_bar_bends_round_the_convex_start_and_crosses_into_the_landing_top():
    run = first_flight()
    pts = sr.bottom_bar(run, COVER, 12.0, 480.0)
    assert abs(pts[0][1] - 46.0) < 1e-6 and abs(pts[0][0] - 46.0) < 1e-6   # along the base, at cover
    # straight on past the upper knee up to the landing top, then to the free edge with a closing leg
    assert abs(pts[-3][1] - (1765.0 - 46.0)) < 1e-6 and pts[-3][0] > 2520.0
    assert pts[-2] == (3520.0 - 46.0, 1765.0 - 46.0)
    assert pts[-1] == (3520.0 - 46.0, 1615.0 + 46.0)


def test_top_bar_is_continuous_over_the_upper_knee_and_anchored_at_the_base():
    pts = sr.top_bar(first_flight(), COVER, 12.0, 480.0)
    assert abs(pts[0][1] - 46.0) < 1e-6                      # anchored in the bottom face at the start
    assert pts[-2] == (3474.0, 1719.0) and pts[-1] == (3474.0, 1661.0)


def test_every_flight_bar_stays_in_the_concrete():
    for run in (first_flight(), second_flight()):
        for st in _sets(run):
            if st['axis'] != 'v':
                continue
            for s, z in st['points']:
                if run['upper']['kind'] == 'floor' and s > run['length']:
                    assert abs(z - (run['upper']['top'] - COVER - st['dia'] / 2.0)) < 1e-6  # lapped into the slab
                    continue
                assert inside(run, s, z), (st['label'], s, z)


def test_knee_bars_cross_from_the_landings_into_the_flight():
    up = _by_label(_sets(first_flight()), u'Stair Upper Knee')[0]['points']
    _bottom, top = sr.flight_lines(first_flight(), COVER, 12.0, 12.0)
    assert abs(up[0][1] - (1615.0 + 46.0)) < 1e-6
    assert abs(top.z(up[0][0]) - up[0][1]) < 1e-6           # reaches the top bars inside the flight
    low = _by_label(_sets(second_flight()), u'Stair Lower Knee')[0]['points']
    assert abs(low[0][1] - (1765.0 - 46.0)) < 1e-6 and low[1][0] > 0.0


def test_layers_meeting_in_a_landing_are_staggered():
    sets = _sets(first_flight())
    bottom = _by_label(sets, u'Stair Flight Bottom')[0]
    top = _by_label(sets, u'Stair Flight Top')[0]
    pitch = top['array'] / (top['count'] - 1)
    tops = [top['first'] + i * pitch for i in range(top['count'])]
    bottoms = [bottom['first'] + i * pitch for i in range(bottom['count'])]
    assert bottom['count'] == top['count'] - 1 and pitch <= 200.0
    assert min(abs(b - t) for b in bottoms for t in tops) > pitch / 2.0 - 1e-6


def test_distribution_runs_along_both_faces_of_the_flight():
    dist = [s for s in _sets(first_flight()) if s['axis'] == 'slope']
    assert len(dist) == 2
    for st in dist:
        ds, dz = st['direction']
        assert abs(dz / ds - SLOPE) < 1e-6 and st['array'] > 2000.0


def test_dog_leg_landing_gets_bars_in_the_stairwell_gap_only():
    landing = {'s_min': 2438.0, 's_max': 3520.0, 'v_min': -500.0, 'v_max': 2024.0,
               'top': 1765.0, 'bottom': 1615.0}
    sets = sr.build_landing(landing, COVER, 12.0, 8.0, 200.0, 200.0,
                            strips=[(-500.0, 500.0), (1024.0, 2024.0)], parallel_runs=True)
    infill = [s for s in sets if s['axis'] == 'v']
    assert len(infill) == 2
    for st in infill:
        assert 500.0 <= st['first'] and st['first'] + st['array'] <= 1024.0 and st['count'] >= 2
    transverse = [s for s in sets if s['axis'] == 'slope']
    assert len(transverse) == 2 and all(s['v_range'] == (-456.0, 1980.0) for s in transverse)


def test_uncovered_strips():
    assert sr.uncovered((0.0, 100.0), [(10.0, 20.0), (50.0, 120.0)], 5.0) == [(0.0, 10.0), (20.0, 50.0)]


def test_without_slab_anchor_the_bars_stop_at_the_end_face():
    run = second_flight()
    for st in sr.build_flight(run, COVER, 12.0, 200.0, 8.0, 200.0, 480.0, slab_anchor=False):
        if st['axis'] == 'v':
            assert max(p[0] for p in st['points']) <= run['length'] - COVER + 1e-6, st['label']


def test_preview_section_is_closed_and_holds_the_bars():
    import rebar_preview_shapes as ps
    shapes = ps.stair_section_shapes(ps.typical_stair_flight(), COVER, 12, 200, 12, 200, 8, 200, 480)
    outline = shapes[0]['points']
    assert shapes[0]['kind'] == 'outline' and len(outline) > 20
    assert len([s for s in shapes if s['kind'] == 'bar']) == 3
    assert len([s for s in shapes if s['kind'] == 'dot']) > 20


def _starters(mode='cast'):
    support = {'mode': 'cast', 'foot_z': -500.0 + 50.0 + 16.0} if mode == 'cast' else \
        {'mode': 'post', 'embed': 300.0}
    return {'dia': 12.0, 'lap': 600.0, 'support': support}


def test_cast_starters_are_l_bars_cranked_to_the_slope_and_lapped_l0():
    run = first_flight()
    sets = sr.build_flight(run, COVER, 12.0, 200.0, 8.0, 200.0, 480.0, starters=_starters())
    bottom = _by_label(sets, u'Stair Starter Bottom')[0]
    top = _by_label(sets, u'Stair Starter Top')[0]
    for st, sign in ((bottom, 1.0), (top, -1.0)):
        (fx, fz), (kx, kz), (bx, bz), (ex, ez) = st['points']
        assert fz == kz == -434.0 and abs((fx - kx) - sign * 450.0) < 1e-6       # foot on the bottom mat
        assert kx == bx and abs(bz - 46.0) < 1e-6                                # vertical up to the knee
        assert abs(math.hypot(ex - bx, ez - bz) - 600.0) < 1e-6                  # l0 along the slope
        assert abs((ez - bz) / (ex - bx) - SLOPE) < 1e-9
    flight_bottom = _by_label(sets, u'Stair Flight Bottom')[0]
    assert abs(bottom['first'] - flight_bottom['first'] - 12.0) < 1e-6           # contact lap beside it
    assert flight_bottom['points'][0][0] > 200.0                                  # no base leg any more
    assert abs(flight_bottom['points'][0][0] - bottom['points'][2][0]) < 1e-6    # starts where they lap


def test_post_installed_starters_are_straight_into_the_support():
    sets = sr.build_flight(first_flight(), COVER, 12.0, 200.0, 8.0, 200.0, 480.0,
                           starters=_starters('post'))
    pts = _by_label(sets, u'Stair Starter Bottom')[0]['points']
    assert len(pts) == 3 and pts[0][1] == -300.0 and pts[0][0] == pts[1][0]


def test_no_starters_on_a_flight_that_starts_from_a_landing():
    sets = sr.build_flight(second_flight(), COVER, 12.0, 200.0, 8.0, 200.0, 480.0, starters=_starters())
    assert not [s for s in sets if s['layer'] == u'stair_starter']


def test_landing_u_bars_replace_the_closing_legs():
    run = first_flight()
    run['upper']['u_dia'] = 10.0
    top = sr.top_bar(run, COVER, 12.0, 480.0)
    assert top[-1] == (3520.0 - 40.0 - 10.0 - 6.0, 1719.0)                      # straight, inside the U
    landing = {'s_min': 2520.0, 's_max': 3520.0, 'v_min': -500.0, 'v_max': 2024.0,
               'top': 1765.0, 'bottom': 1615.0}
    sets = sr.build_landing(landing, COVER, 12.0, 8.0, 200.0, 200.0,
                            strips=[(-500.0, 500.0), (1024.0, 2024.0)], parallel_runs=True,
                            u_dia=10.0, u_edges=('s_max', 'v_min', 'v_max'), top_dia=12.0, top_spacing=200.0)
    far = [s for s in sets if s['layer'] == u'stair_landing_ubar' and s['axis'] == 'v']
    side = [s for s in sets if s['layer'] == u'stair_landing_ubar' and s['axis'] == 's']
    assert len(far) == 3                                      # two flight strips + the gap
    assert not side                                           # 150 mm, 40 cover: no room to bend them
    (a, _za), (b, zt), (_c, zb), (_d, _zd) = far[0]['points']
    assert b == 3520.0 - 45.0 and b - a == 400.0              # leg max(40 phi, 2h) = 400
    assert zt == 1765.0 - 45.0 and zb == 1615.0 + 45.0
    for st in sets:                                           # nothing reaches past the U back
        if st['axis'] == 'v' and st['layer'] == u'stair_landing':
            assert max(p[0] for p in st['points']) <= 3520.0 - 40.0 - 10.0 - 6.0 + 1e-6


def test_side_u_bars_need_room_for_the_mandrel():
    landing = {'s_min': 2520.0, 's_max': 3520.0, 'v_min': -500.0, 'v_max': 2024.0,
               'top': 1765.0, 'bottom': 1615.0}
    notes = []
    sets = sr.build_landing(landing, COVER, 12.0, 8.0, 200.0, 200.0, [(-500.0, 500.0)], True,
                            u_dia=10.0, u_edges=('v_min', 'v_max'), warnings=notes)
    assert not [s for s in sets if s['layer'] == u'stair_landing_ubar'] and len(notes) == 1
    sets = sr.build_landing(landing, 25.0, 12.0, 8.0, 200.0, 200.0, [(-500.0, 500.0)], True,
                            u_dia=10.0, u_edges=('v_min', 'v_max'))
    side = [s for s in sets if s['layer'] == u'stair_landing_ubar']
    assert len(side) == 2
    (_v0, zt), (_v1, _), (_v2, zb), _ = side[0]['points_vz']
    assert zt - zb - 10.0 >= sr.mandrel_mm(10.0)
    transverse = [s for s in sets if s['axis'] == 'slope']
    assert all(s['v_range'] == (-500.0 + 39.0, 2024.0 - 39.0) for s in transverse)


def test_preview_draws_starters_and_landing_ubars():
    import rebar_preview_shapes as ps
    shapes = ps.stair_section_shapes(ps.typical_stair_flight(), COVER, 12, 200, 12, 200, 8, 200, 480,
                                     ubar_dia=10.0, starter_dia=12.0)
    roles = [s['role'] for s in shapes if s['kind'] == 'bar']
    assert roles.count('starter') == 2 and roles.count('ubar') >= 2
    assert [s for s in shapes if s['kind'] == 'ground']


def test_quarter_landing_of_an_l_stair_covers_its_whole_area():
    landing = {'s_min': 2520.0, 's_max': 3548.0, 'v_min': -500.0, 'v_max': 610.0,
               'top': 1765.0, 'bottom': 1515.0}
    sets = sr.build_landing(landing, COVER, 12.0, 8.0, 200.0, 200.0, [(-500.0, 500.0)], False,
                            u_dia=10.0, u_edges=('s_max', 'v_min'))
    labels = [s['label'] for s in sets]
    assert labels.count(u'Stair Landing Top') == 1 and labels.count(u'Stair Landing Bottom') == 1
    top = [s for s in sets if s['label'] == u'Stair Landing Top'][0]
    # without parallel flights the bars along s fill the full landing width
    assert top['first'] < -400.0 and top['first'] + top['array'] > 500.0
    assert any(s.get('points_vz') for s in sets if s['layer'] == u'stair_landing_ubar')
    assert any(s.get('points') for s in sets if s['layer'] == u'stair_landing_ubar')
