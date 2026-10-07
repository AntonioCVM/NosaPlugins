# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — continuous beams over several spans (T7.2). Pure 1D layout, mm, no Revit.

User decisions (2026-10-03): the user selects the spans of one line; top bars are continuous
hanger bars lapped in the central third of a span (where hogging is nil), plus extra bars over
every intermediate support reaching 0.25 L of the longer adjacent clear span past each face
(IStructE / EC2 simplified curtailment); bottom bars belong to each span and run straight into
an intermediate support at least 10 phi (EC2 9.2.1.5); one set of diameters for every span.
x is the distance along the line from the start of the first span's clear length.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

MAX_SUPPORT_GAP_MM = 1500.0
SUPPORT_BAR_FRACTION = 0.25


def order_spans(spans, max_gap_mm=MAX_SUPPORT_GAP_MM):
    """
    spans: [{'id', 'x0', 'x1'}] clear lengths along the line (any order).
    Returns (ordered spans, supports [{'left', 'right', 'x0', 'x1', 'width'}], warnings); the
    supports are the gaps between consecutive spans (a column or wall between their ends).
    """
    ordered = sorted(spans, key=lambda s: s['x0'])
    supports, warnings = [], []
    for left, right in zip(ordered[:-1], ordered[1:]):
        gap = right['x0'] - left['x1']
        if gap < -1.0:
            warnings.append(u'beams {} and {} overlap by {:.0f} mm — not one line of spans.'.format(
                left['id'], right['id'], -gap))
        elif gap > max_gap_mm:
            warnings.append(u'{:.0f} mm between beams {} and {} — too wide for one support; '
                            u'treated as two separate lines.'.format(gap, left['id'], right['id']))
        supports.append({'left': left['id'], 'right': right['id'], 'x0': left['x1'],
                         'x1': right['x0'], 'width': max(gap, 0.0),
                         'continuous': -1.0 <= gap <= max_gap_mm})
    return ordered, supports, warnings


def support_bar_range(support, left_span, right_span, fraction=SUPPORT_BAR_FRACTION):
    """Extra top bars over an intermediate support: fraction x the longer clear span past each face."""
    reach = fraction * max(left_span['x1'] - left_span['x0'], right_span['x1'] - right_span['x0'])
    return support['x0'] - reach, support['x1'] + reach


def bottom_anchor_into_support(bar_dia, support_width, clearance=10.0):
    """
    (straight length past the support face, note) for span bottom bars at an intermediate
    support: at least 10 phi (EC2 9.2.1.5(2)), but the bars of the two spans must not meet.
    """
    wanted = max(10.0 * bar_dia, 100.0)
    room = support_width / 2.0 - clearance
    if room >= wanted:
        return wanted, None
    length = max(room, 0.0)
    return length, (u'support only {:.0f} mm wide: bottom bars enter it {:.0f} mm (EC2 asks for '
                    u'{:.0f} mm, 10 phi) — lap them across the support or widen it.'.format(
                        support_width, length, wanted))


def lap_cuts(x_start, x_end, spans, stock_mm, lap_mm):
    """
    Segments [(x0, x1)] of one continuous bar from x_start to x_end, each no longer than
    stock_mm, overlapping lap_mm. SMDSC 6.3: a top-bar lap lies wholly in the central third of a
    clear span, at mid-span when the stock length reaches it; only a lap longer than the third
    falls back to a centre inside it. The farthest span that fits keeps the laps fewest.
    Returns (segments, warnings).
    """
    segments, warnings = [], []
    start = x_start
    guard = 0
    while x_end - start > stock_mm + 1e-6:
        guard += 1
        if guard > 100:
            break
        best = None
        reach = start + stock_mm - lap_mm / 2.0          # farthest lap centre one stock length allows
        for whole in (True, False):
            for span in spans:
                length = span['x1'] - span['x0']
                lo, hi = span['x0'] + length / 3.0, span['x1'] - length / 3.0
                if whole:
                    lo, hi = lo + lap_mm / 2.0, hi - lap_mm / 2.0
                    if hi < lo:
                        continue
                centre = min((span['x0'] + span['x1']) / 2.0, hi, reach)
                if centre < lo or centre - lap_mm / 2.0 <= start + lap_mm:
                    continue
                if best is None or centre > best:
                    best = centre
            if best is not None:
                break
        if best is None:
            best = start + stock_mm - lap_mm / 2.0
            warnings.append(u'no central third within one stock length from {:.0f} mm — lap placed '
                            u'at {:.0f} mm.'.format(start - x_start, best - x_start))
        segments.append((start, best + lap_mm / 2.0))
        start = best - lap_mm / 2.0
    segments.append((start, x_end))
    return segments, warnings


def support_bar_slots(n_hangers, n_extra):
    """
    Where the extra support bars go across the width: ('between', i) = midway between hanger
    bars i and i+1 in the top layer; ('second', i) = under hanger bar i in a second layer.
    """
    slots = []
    between = list(range(max(n_hangers - 1, 0)))
    # fill from the middle outwards so a short list stays symmetrical
    middle = (len(between) - 1) / 2.0
    between.sort(key=lambda i: (abs(i - middle), i))
    for i in between[:n_extra]:
        slots.append(('between', i))
    remaining = n_extra - len(slots)
    under = list(range(n_hangers))
    middle = (len(under) - 1) / 2.0
    under.sort(key=lambda i: (-abs(i - middle), i))       # corners first: they carry the links
    for i in under[:max(remaining, 0)]:
        slots.append(('second', i))
    return sorted(slots, key=lambda s: (s[0] != 'between', s[1]))


def solid_spans(intervals, length_mm, min_gap_mm=10.0, min_span_mm=50.0):
    """
    Spans [(x0, x1)] of one beam element from the extents of its solid pieces along the axis: a
    column or wall the beam runs through (joined, cutting it) splits the solid; each gap wider
    than min_gap_mm is an intermediate support. [(0, length)] when the solid is in one piece.
    """
    pieces = sorted((max(a, 0.0), min(b, length_mm)) for a, b in intervals if b - a >= min_span_mm)
    spans = []
    for a, b in pieces:
        if spans and a - spans[-1][1] < min_gap_mm:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    if not spans:
        return [(0.0, length_mm)]
    spans[0] = (0.0, spans[0][1]) if spans[0][0] < min_gap_mm else spans[0]
    spans[-1] = (spans[-1][0], length_mm) if length_mm - spans[-1][1] < min_gap_mm else spans[-1]
    return spans


# Additional bars: IStructE Standard Method of Detailing (SMDSC) 6.3.2 simplified rules for beams
# (user decision 2026-10-06, replacing the Concrete Centre version of 2026-10-05). Valid for
# substantially uniform loads, Qk <= Gk, three or more spans differing by no more than 15 %.
# L = effective span = clear span + d.
HOG_LONG_SHARE = 0.60                   # at least 60 % of the support bars ...
HOG_LONG = 0.25                         # ... run 0.25 L past the support face
HOG_SHORT, HOG_SHORT_DIA = 0.15, 45.0   # none stops short of max(0.15 L, 45 bar diameters)
SAG_INTERNAL, SAG_EXTERIOR, SAG_SIMPLE = 0.15, 0.10, 0.08   # span bars stop this far from the support
SPAN_VARIATION = 0.15


def shift_al_mm(d_mm):
    """al the detailer assumes when the designer gives none (SMDSC 6.3.2): 1.25 d."""
    return 1.25 * d_mm


def effective_span_mm(clear_mm, d_mm):
    """L for the simplified rules: need not be taken greater than the clear span + d."""
    return clear_mm + d_mm


def hogging_reaches_mm(span_mm, bar_dia_mm):
    """(short, long) reach of the support bars past the support face into a span of effective length span_mm."""
    short = max(HOG_SHORT * span_mm, HOG_SHORT_DIA * bar_dia_mm)
    return short, max(HOG_LONG * span_mm, short)


def hogging_groups(n_bars):
    """(long, short) counts: at least 60 % of the bars run to 0.25 L, the rest stop at the short reach."""
    long_ = min(n_bars, int(-(-HOG_LONG_SHARE * n_bars // 1)))
    return long_, n_bars - long_


def sagging_range_mm(x0, x1, start_kind, end_kind, d_mm=0.0):
    """
    Extent of the extra bottom (span) bars between support faces x0..x1: they stop 0.15 L from an
    internal support, 0.1 L from an exterior (monolithic) one and 0.08 L from a simple support.
    kinds: 'internal' | 'exterior' | 'simple'. None if nothing is left.
    """
    span = effective_span_mm(x1 - x0, d_mm)
    cut = {'internal': SAG_INTERNAL, 'exterior': SAG_EXTERIOR, 'simple': SAG_SIMPLE}
    a = x0 + cut[start_kind] * span
    b = x1 - cut[end_kind] * span
    return (a, b) if b - a > 1.0 else None


FLEX_BOTTOM_GAP_MM = 25.0     # SMDSC 4.2.3 / MB1 flexible detailing: span bottom bars stop 25 from the face
FLEX_TOP_GAP_MM = 50.0        # ... hanger bars 50 from it
FLEX_SPLICE_SHARE = 0.30      # bottom splice bars over an internal support: 30 % of the span bars


def splice_bar_count(n_bottom):
    """Bottom splice bars over an internal support (SMDSC MB1): 30 % of the span bars, at least two."""
    return max(2, int(-(-FLEX_SPLICE_SHARE * n_bottom // 1)))


def flexible_hanger_runs(x_start, x_end, supports):
    """Hanger bar runs that stop FLEX_TOP_GAP_MM short of every continuous support (SMDSC MB1)."""
    runs, a = [], x_start
    for sup in supports:
        if sup.get('continuous'):
            runs.append((a, sup['x0'] - FLEX_TOP_GAP_MM))
            a = sup['x1'] + FLEX_TOP_GAP_MM
    runs.append((a, x_end))
    return [(p, q) for p, q in runs if q - p > 100.0]


def simplified_rules_warnings(spans_mm):
    """Why the SMDSC simplified curtailment may not apply to these clear spans (designer to confirm)."""
    out = []
    if len(spans_mm) < 3:
        out.append(u'SMDSC 6.3.2 simplified curtailment assumes three or more spans ({} here): check the bar '
                   u'lengths against the bending moment diagram.'.format(len(spans_mm)))
    if spans_mm and max(spans_mm) > 0 and (max(spans_mm) - min(spans_mm)) > SPAN_VARIATION * max(spans_mm):
        out.append(u'spans differ by more than 15 % ({:.0f} to {:.0f} mm): the SMDSC simplified curtailment '
                   u'does not apply; check against the bending moment diagram.'.format(min(spans_mm), max(spans_mm)))
    return out
