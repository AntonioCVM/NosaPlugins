# -*- coding: utf-8 -*-
"""
nosa_utils.joint_resolution - proposals for beam bars that clash with a column's bars where the beam enters it
(docs/NUDOS_VIGA_PILAR_DISENO.md, draft for the user's approval, 2026-10-26). No Revit, nothing applied: each
clashing beam bar gets R1 (shift the whole bar sideways in its layer), else R2 (crank it locally before the joint,
compression bars only), else R3 (left flagged for manual review), with every check and its limit listed.
Positions are across the beam (mm, 0 at its centre line), one layer at a time.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from nosa_utils import rebar_qa, standards

CRANK_SLOPE = 10.0          # SMDSC 4th ed. MD C2 (column_rebar.CRANK_SLOPE): crank length >= 10 x offset
MAX_CRANK_MM = 75.0         # SMDSC (column_rebar.MAX_CRANK_OFFSET_MM)
VIBRATOR_GAP_MM = 75.0      # SMDSC 4th ed. 4.2 / MD B1


def centre_gap_mm(dia_a, dia_b, aggregate_mm=rebar_qa.AGGREGATE_MM):
    """Centre to centre two bars need: their real sizes (ribs) plus the minimum clear gap (EC2 8.2(2))."""
    return rebar_qa.REAL_DIA * (dia_a + dia_b) / 2.0 + rebar_qa.min_clear_mm(max(dia_a, dia_b), aggregate_mm)


def clashes(layer, column_bars, column_dia, aggregate_mm=rebar_qa.AGGREGATE_MM):
    """[(bar index, nearest column bar, clear gap mm, needed mm)] of the beam bars too close to a column bar."""
    out = []
    for i, (y, dia) in enumerate(layer):
        if not column_bars:
            break
        c = min(column_bars, key=lambda x: abs(x - y))
        clear = abs(c - y) - rebar_qa.REAL_DIA * (column_dia + dia) / 2.0
        need = rebar_qa.min_clear_mm(max(column_dia, dia), aggregate_mm)
        if clear < need - 0.5:
            out.append((i, c, clear, need))
    return out


def _clear_of(y, dia, others, aggregate_mm):
    """The closest other bar's clear gap shortfall: [] when every one is far enough."""
    bad = []
    for oy, od in others:
        if abs(oy - y) < centre_gap_mm(dia, od, aggregate_mm) - 0.5:
            bad.append((oy, od))
    return bad


def _gaps(positions, dias):
    return rebar_qa.gaps_clear(positions, dias)


def _check(name, ok, value, limit):
    return {'check': name, 'ok': bool(ok), 'value': value, 'limit': limit}


def propose(layer, supports, cage_half_mm, corners=(0, -1), tie_held=(), top=False, aggregate_mm=rebar_qa.AGGREGATE_MM):
    """
    Proposals for one layer of a beam (line) over its supports.
    layer: [(y, dia)] the layer's bars across the beam; supports: [{'name', 'column_bars': [y], 'column_dia',
    'compression': bool (the layer is in compression there), 'room_mm': straight length free for a crank before the
    column face}]; cage_half_mm: b/2 - cover - link (the farthest a bar centre may be is that less its radius);
    corners: indices of the corner bars (never moved); tie_held: indices held by interior ties (not shifted); top:
    the top layer (its poker gap is kept).
    Returns [{'bar', 'rule': 'R1' | 'R2' | 'R3', 'support', 'shift_mm' | 'crank_mm', 'checks', 'reason'}].
    """
    n = len(layer)
    corner_idx = set((c % n) for c in corners) if n else set()
    positions = [y for y, _d in layer]
    dias = [d for _y, d in layer]
    pitch = min([b - a for a, b in zip(sorted(positions), sorted(positions)[1:])] or [0.0])
    gap_before = min(_gaps(positions, dias) or [float('inf')])
    keeps_poker = top and gap_before >= VIBRATOR_GAP_MM - 0.5
    found = {}
    for s in supports:
        for i, c, clear, need in clashes(layer, s['column_bars'], s['column_dia'], aggregate_mm):
            found.setdefault(i, []).append((s, c, clear, need))
    out = []
    for i in sorted(found):
        y, dia = layer[i]
        hits = found[i]
        why = u'; '.join(u'{}: {:.0f} mm clear to the column bar at {:.0f} ({:.0f} needed)'.format(
            s['name'], clear, c, need) for s, c, clear, need in hits)
        if i in corner_idx:
            out.append({'bar': i, 'rule': u'R3', 'support': None, 'checks': [],
                        'reason': why + u' - a corner bar stays in its link corner (P3): manual review'})
            continue
        r1 = _shift(i, layer, positions, dias, supports, cage_half_mm, pitch, keeps_poker, tie_held, aggregate_mm)
        if r1 is not None:
            out.append(dict(r1, bar=i, rule=u'R1', support=None, reason=why))
            continue
        cranks = [_crank(i, layer, positions, s, cage_half_mm, aggregate_mm) for s, _c, _cl, _n in hits]
        if all(c is not None and c['ok'] for c in cranks):
            for (s, _c, _cl, _n), c in zip(hits, cranks):
                out.append({'bar': i, 'rule': u'R2', 'support': s['name'], 'crank_mm': c['crank_mm'],
                            'checks': c['checks'], 'reason': why})
            continue
        failed = [ch for c in cranks if c is not None for ch in c['checks'] if not ch['ok']]
        out.append({'bar': i, 'rule': u'R3', 'support': None, 'checks': failed,
                    'reason': why + u' - no shift or crank meets every check: manual review (second layer, smaller '
                                    u'bars or the column bars moved, all design changes)'})
    return out


def _shift(i, layer, positions, dias, supports, cage_half_mm, pitch, keeps_poker, tie_held, aggregate_mm):
    """R1: the smallest sideways shift of bar i that clears every support, stays in its cage and layer."""
    if i in tie_held:
        return None
    y, dia = layer[i]
    others = [(positions[k], dias[k]) for k in range(len(layer)) if k != i]
    candidates = set()
    for s in supports:
        cc = centre_gap_mm(s['column_dia'], dia, aggregate_mm)
        for c in s['column_bars']:
            candidates.update((c - cc - y, c + cc - y))
    for delta in sorted(candidates, key=lambda d: (abs(d), d)):
        p = y + delta
        checks = [
            _check(u'cover: inside the link cage (EC2 4.4.1)', abs(p) <= cage_half_mm - dia / 2.0 + 0.5,
                   round(abs(p) + dia / 2.0, 1), cage_half_mm),
            _check(u'clear to the layer (EC2 8.2(2))', not _clear_of(p, dia, others, aggregate_mm), round(p, 1),
                   u'>= max(bar, agg + 5, 20)'),
            _check(u'shift within half the pitch (P2)', abs(delta) <= pitch / 2.0 + 0.5, round(abs(delta), 1),
                   round(pitch / 2.0, 1)),
        ]
        for s in supports:
            near = [c for c in s['column_bars']
                    if abs(c - p) < centre_gap_mm(s['column_dia'], dia, aggregate_mm) - 0.5]
            checks.append(_check(u'clear to the column bars at {} (EC2 8.2(2))'.format(s['name']), not near,
                                 round(p, 1), u'>= max(bar, agg + 5, 20)'))
        if keeps_poker:
            new = [p if k == i else positions[k] for k in range(len(layer))]
            gap = max(_gaps(new, dias) or [0.0])
            checks.append(_check(u'poker gap kept (SMDSC 4.2 / MD B1)', gap >= VIBRATOR_GAP_MM - 0.5,
                                 round(gap, 1), VIBRATOR_GAP_MM))
        if all(ch['ok'] for ch in checks):
            return {'shift_mm': round(delta, 1), 'checks': checks}
    return None


def _crank(i, layer, positions, support, cage_half_mm, aggregate_mm):
    """R2 at one support: the smallest local offset that clears it, with the crank's own checks."""
    y, dia = layer[i]
    others = [(positions[k], layer[k][1]) for k in range(len(layer)) if k != i]
    cc = centre_gap_mm(support['column_dia'], dia, aggregate_mm)
    best = None
    for c in support['column_bars']:
        for e in (c - cc - y, c + cc - y):
            p = y + e
            if any(abs(cb - p) < cc - 0.5 for cb in support['column_bars']):
                continue
            if best is None or abs(e) < abs(best):
                best = e
    if best is None:
        return None
    p = y + best
    length = CRANK_SLOPE * abs(best) + 2.0 * standards.min_end_projection_mm(dia)
    checks = [
        _check(u'bar in compression at the joint (deviation force, EC2 8.3)', support.get('compression', False),
               support.get('compression', False), True),
        _check(u'offset (SMDSC)', abs(best) <= MAX_CRANK_MM + 0.5, round(abs(best), 1), MAX_CRANK_MM),
        _check(u'crank 1:10 and 5d straights fit before the face (SMDSC MD C2, Table B1)',
               length <= support.get('room_mm', 0.0) + 0.5, round(length, 1), support.get('room_mm', 0.0)),
        _check(u'cover: inside the link cage (EC2 4.4.1)', abs(p) <= cage_half_mm - dia / 2.0 + 0.5,
               round(abs(p) + dia / 2.0, 1), cage_half_mm),
        _check(u'clear to the layer at the joint (EC2 8.2(2))', not _clear_of(p, dia, others, aggregate_mm),
               round(p, 1), u'>= max(bar, agg + 5, 20)'),
        _check(u'bend mandrel (BS 8666 Table 2)', True, standards.standard_mandrel_mm(dia),
               standards.standard_mandrel_mm(dia)),
    ]
    return {'crank_mm': round(best, 1), 'checks': checks, 'ok': all(ch['ok'] for ch in checks)}
