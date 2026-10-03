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
    stock_mm, overlapping lap_mm, with every lap centred in the central third of a clear span.
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
        for span in spans:
            length = span['x1'] - span['x0']
            lo, hi = span['x0'] + length / 3.0, span['x1'] - length / 3.0
            centre = min(hi, start + stock_mm - lap_mm / 2.0)
            if centre < lo or centre - lap_mm / 2.0 <= start + lap_mm:
                continue
            if best is None or centre > best:
                best = centre
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
