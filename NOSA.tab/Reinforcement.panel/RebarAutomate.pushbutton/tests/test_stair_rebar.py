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
