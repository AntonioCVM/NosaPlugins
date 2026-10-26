# -*- coding: utf-8 -*-
"""
nosa_utils.joint_resolution - proposals for beam bars that clash with a column's bars where the beam enters it
(docs/NUDOS_VIGA_PILAR_DISENO.md; rules approved by the user 2026-10-26 for development and tests in copies, every
proposal confirmed case by case, nothing applied here). Each clashing beam bar gets R1 (shift the whole bar sideways
in its layer), else R2 (crank it locally before the joint, compression bars only, proven by the model's forces), else
R3 (left flagged for manual review), with every check, its value and its limit. Positions across the beam are mm
from its centre line, one layer at a time; positions along it are mm along its axis.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from nosa_utils import rebar_qa, standards

CRANK_SLOPE = 10.0          # SMDSC 4th ed. MD C2 (column_rebar.CRANK_SLOPE): crank length >= 10 x offset (1:10)
MAX_CRANK_MM = 75.0         # SMDSC (column_rebar.MAX_CRANK_OFFSET_MM)
MAX_CRANK_DIAS = 2.0        # user 2026-10-26, decision 2: offset <= min(75 mm, 2 dia.)
MAX_SHIFT_MM = 50.0         # user 2026-10-26, decision 3: |delta| <= s/2 and <= 50 mm
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
    """The other bars [(y, dia)] closer to y than their minimum centre gap ([] when every one is far enough)."""
    return [(oy, od) for oy, od in others if abs(oy - y) < centre_gap_mm(dia, od, aggregate_mm) - 0.5]


def _check(name, ok, value, limit):
    return {'check': name, 'ok': bool(ok), 'value': value, 'limit': limit}


def compression_proven(support):
    """
    R2's condition (user 2026-10-26, decision 1): the bar is in compression at the joint in every combination, by
    the model's forces. support['forces']: None when the model has none, else {'compression_all': bool,
    'tension_any': bool} for this layer at this support (load reversal, cantilevers and horizontal actions in).
    """
    forces = support.get('forces')
    return bool(forces) and bool(forces.get('compression_all')) and not forces.get('tension_any')


def propose(layer, supports, cage_half_mm, corners=(0, -1), tie_held=(), top=False, parallel=(),
            aggregate_mm=rebar_qa.AGGREGATE_MM):
    """
    Proposals for one layer of a beam (line) over its supports.
    layer: [(y, dia)] the layer's bars across the beam; supports: [{'name', 'column_bars': [y], 'column_dia', 'forces'
    (compression_proven), 'face_mm' (the column face along the beam), 'toward' (+1 / -1: from the span into the
    column), 'span_mm' ((a, b): the clear span the crank must stay in), 'zones_mm' ([(a, b)] anchorage and lap
    zones it must keep out of)}]; cage_half_mm: b/2 - cover - link (a bar's centre at most that less its radius);
    corners: indices of the corner bars (never moved); tie_held: indices held by interior ties (not shifted); top:
    the top layer (its poker gap is kept); parallel: [(y, dia)] of other bars at the layer's level along the beam
    (a secondary beam's, the slab's, hairpins' legs) a shifted or cranked bar must keep s_min from.
    Returns [{'bar', 'rule': 'R1' | 'R2' | 'R3', 'support', 'shift_mm' | 'crank_mm', 'checks', 'reason'}].
    """
    n = len(layer)
    corner_idx = set((c % n) for c in corners) if n else set()
    positions = [y for y, _d in layer]
    dias = [d for _y, d in layer]
    pitch = min([b - a for a, b in zip(sorted(positions), sorted(positions)[1:])] or [0.0])
    gap_before = min(rebar_qa.gaps_clear(positions, dias) or [float('inf')])
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
        r1 = _shift(i, layer, positions, dias, supports, cage_half_mm, pitch, keeps_poker, tie_held, parallel,
                    aggregate_mm)
        if r1 is not None and all(c['ok'] for c in r1['checks']):
            out.append(dict(r1, bar=i, rule=u'R1', support=None, reason=why))
            continue
        cranks = [_crank(i, layer, positions, s, cage_half_mm, parallel, aggregate_mm) for s, _c, _cl, _n in hits]
        if all(c is not None and c['ok'] for c in cranks):
            for (s, _c, _cl, _n), c in zip(hits, cranks):
                out.append({'bar': i, 'rule': u'R2', 'support': s['name'], 'crank_mm': c['crank_mm'],
                            'checks': c['checks'], 'reason': why})
            continue
        failed = [ch for c in cranks if c is not None for ch in c['checks'] if not ch['ok']]
        if r1 is not None:
            failed = [ch for ch in r1['checks'] if not ch['ok']] + failed
        out.append({'bar': i, 'rule': u'R3', 'support': None, 'checks': failed,
                    'reason': why + u' - no shift or crank meets every check: manual review (second layer, smaller '
                                    u'bars or the column bars moved, all design changes)'})
    return out


def _shift(i, layer, positions, dias, supports, cage_half_mm, pitch, keeps_poker, tie_held, parallel,
           aggregate_mm):
    """
    R1: the smallest sideways shift of bar i that clears every support and keeps every check; when none keeps them
    all, the nearest one tried with its checks (to say why), or None when the bar may not move at all.
    """
    if i in tie_held:
        return None
    y, dia = layer[i]
    others = [(positions[k], dias[k]) for k in range(len(layer)) if k != i]
    candidates = set()
    for s in supports:
        cc = centre_gap_mm(s['column_dia'], dia, aggregate_mm)
        for c in s['column_bars']:
            candidates.update((c - cc - y, c + cc - y))
    for o_y, o_dia in parallel:
        # just clear of a secondary beam's, the slab's or a hairpin's bar on either side (case F)
        cc = centre_gap_mm(o_dia, dia, aggregate_mm)
        candidates.update((o_y - cc - y, o_y + cc - y))
    limit = min(pitch / 2.0, MAX_SHIFT_MM)
    first = None
    for delta in sorted(candidates, key=lambda d: (abs(d), d)):
        p = y + delta
        checks = [
            _check(u'cover: inside the link cage (EC2 4.4.1)', abs(p) <= cage_half_mm - dia / 2.0 + 0.5,
                   round(abs(p) + dia / 2.0, 1), cage_half_mm),
            _check(u'clear to the layer (EC2 8.2(2))', not _clear_of(p, dia, others, aggregate_mm), round(p, 1),
                   u'>= max(bar, agg + 5, 20)'),
            _check(u'shift within half the pitch and 50 mm (P2, decision 3)', abs(delta) <= limit + 0.5,
                   round(abs(delta), 1), round(limit, 1)),
            _check(u'clear along its length of secondary beam, slab and hairpin bars (EC2 8.2(2), decision 3)',
                   not _clear_of(p, dia, list(parallel), aggregate_mm), round(p, 1), u'>= max(bar, agg + 5, 20)'),
        ]
        for s in supports:
            near = [c for c in s['column_bars']
                    if abs(c - p) < centre_gap_mm(s['column_dia'], dia, aggregate_mm) - 0.5]
            checks.append(_check(u'clear to the column bars at {} (EC2 8.2(2))'.format(s['name']), not near,
                                 round(p, 1), u'>= max(bar, agg + 5, 20)'))
        if keeps_poker:
            new = [p if k == i else positions[k] for k in range(len(layer))]
            gap = max(rebar_qa.gaps_clear(new, dias) or [0.0])
            checks.append(_check(u'poker gap kept (SMDSC 4.2 / MD B1)', gap >= VIBRATOR_GAP_MM - 0.5,
                                 round(gap, 1), VIBRATOR_GAP_MM))
        result = {'shift_mm': round(delta, 1), 'checks': checks}
        if all(ch['ok'] for ch in checks):
            return result
        if first is None:
            first = result
    return first


def _crank_interval(support, length):
    """The stretch along the beam a crank of this length takes, ending at the column's face."""
    face, toward = support.get('face_mm'), support.get('toward', 1.0)
    if face is None:
        return None
    a, b = face - toward * length, face
    return (min(a, b), max(a, b))


def _crank(i, layer, positions, support, cage_half_mm, parallel, aggregate_mm):
    """R2 at one support: the smallest local offset that clears it, with every check of decision 2."""
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
    limit = min(MAX_CRANK_MM, MAX_CRANK_DIAS * dia)
    straight = standards.min_end_projection_mm(dia)
    length = CRANK_SLOPE * abs(best) + 2.0 * straight
    stretch = _crank_interval(support, length)
    span = support.get('span_mm')
    zones = support.get('zones_mm') or []
    in_span = stretch is not None and span is not None and min(span) - 0.5 <= stretch[0] and \
        stretch[1] <= max(span) + 0.5
    clear_zones = stretch is not None and not any(stretch[0] < max(z) - 0.5 and min(z) + 0.5 < stretch[1]
                                                  for z in zones)
    checks = [
        _check(u'compression at the joint in every combination, by the model\'s forces (EC2 8.3, decision 1)',
               compression_proven(support), support.get('forces'), u'compression_all, no tension'),
        _check(u'offset <= min(75 mm, 2 dia.) (SMDSC, decision 2)', abs(best) <= limit + 0.5, round(abs(best), 1),
               limit),
        _check(u'slope 1:10 or flatter, 5d straights each side (SMDSC MD C2, Table B1)', True, round(length, 1),
               u'1:{:.0f}'.format(CRANK_SLOPE)),
        _check(u'crank within the clear span (decision 2)', in_span, stretch, span),
        _check(u'crank out of the anchorage and lap zones (EC2 8.4, 8.7, decision 2)', clear_zones, stretch, zones),
        _check(u'cranked bar wholly inside the link cage (EC2 4.4.1, decision 2)',
               max(abs(p), abs(y)) <= cage_half_mm - dia / 2.0 + 0.5, round(max(abs(p), abs(y)) + dia / 2.0, 1),
               cage_half_mm),
        _check(u'clear to the layer at the joint (EC2 8.2(2))', not _clear_of(p, dia, others, aggregate_mm),
               round(p, 1), u'>= max(bar, agg + 5, 20)'),
        _check(u'clear to secondary beam, slab and hairpin bars (EC2 8.2(2), decision 2)',
               not _clear_of(p, dia, list(parallel), aggregate_mm), round(p, 1), u'>= max(bar, agg + 5, 20)'),
        _check(u'bend mandrel (BS 8666 Table 2)', True, standards.standard_mandrel_mm(dia),
               standards.standard_mandrel_mm(dia)),
    ]
    return {'crank_mm': round(best, 1), 'checks': checks, 'ok': all(ch['ok'] for ch in checks)}
