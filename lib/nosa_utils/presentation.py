# -*- coding: utf-8 -*-
"""
IStructE SMDSC 6.2.2 presentation of bars on plans and elevations, no Revit: which sets are drawn as one
typical bar, quantities in brackets for a mark in several zones, 'Alt.' / 'Stg.' between sets, and the
short 30 degree obliques at curtailed bar ends. Sets are described in the view's own 2D frame (mm):
{'id', 'mark', 'count', 'bar_dir': (x, y), 'spread_dir': (x, y) or None, 'first': (x, y), 'last': (x, y),
 'ends': ((x, y), (x, y)), 'spacing'}.
"""
import math
import re

TICK_ANGLE_DEG = 30.0
TICK_PAPER_MM = 3.0
PARALLEL = 0.99
MIN_OVERLAP = 0.5


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def is_typical_bar_set(bar_dir_3d_dot_view, spread_in_view):
    """A set drawn as one typical bar: its bars lie in the view plane (not cut) and it spreads across the view."""
    return abs(bar_dir_3d_dot_view) < 0.5 and spread_in_view


def zone_labels(sets):
    """{id: '(n)'} for every set whose mark appears in more than one zone of the view (SMDSC 6.2.2)."""
    by_mark = {}
    for s in sets:
        if s.get('mark'):
            by_mark.setdefault(s['mark'], []).append(s)
    out = {}
    for group in by_mark.values():
        if len(group) > 1:
            for s in group:
                out[s['id']] = u'({})'.format(s['count'])
    return out


def _interval(s, axis):
    a, b = _dot(s['first'], axis), _dot(s['last'], axis)
    return min(a, b), max(a, b)


def _overlap(i, j):
    lo, hi = max(i[0], j[0]), min(i[1], j[1])
    span = min(i[1] - i[0], j[1] - j[0])
    return (hi - lo) / span if span > 1e-6 else (1.0 if abs(i[0] - j[0]) < 1.0 else 0.0)


def relation(a, b, tol_mm=5.0):
    """
    'Alt.' when two sets of different marks interleave (same spacing, half a pitch apart), 'Stg.' when bars of
    one mark are staggered (their zones overlap, the bars shifted along their length); else None.
    """
    if not a.get('spread_dir') or not b.get('spread_dir'):
        return None
    if abs(_dot(a['bar_dir'], b['bar_dir'])) < PARALLEL or abs(_dot(a['spread_dir'], b['spread_dir'])) < PARALLEL:
        return None
    axis = a['spread_dir']
    if _overlap(_interval(a, axis), _interval(b, axis)) < MIN_OVERLAP:
        return None
    bar_axis = a['bar_dir']
    ea = sorted(_dot(p, bar_axis) for p in a['ends'])
    eb = sorted(_dot(p, bar_axis) for p in b['ends'])
    if ea[1] <= eb[0] + tol_mm or eb[1] <= ea[0] + tol_mm:
        return None                                     # end to end: two runs, not one zone
    sa, sb = a.get('spacing') or 0.0, b.get('spacing') or 0.0
    if not sa or abs(sa - sb) > tol_mm:
        return None
    shift = abs(_dot(_sub(a['first'], b['first']), axis)) % sa
    if abs(shift - sa / 2.0) > tol_mm:
        return None                                     # not interleaved half a pitch apart
    if a['mark'] != b['mark']:
        return u'Alt.'
    if abs(ea[0] - eb[0]) > tol_mm or abs(ea[1] - eb[1]) > tol_mm:
        return u'Stg.'
    return None


def relations(sets):
    """[(id_a, id_b, 'Alt.' | 'Stg.')] for every related pair of sets in a view."""
    out = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            r = relation(sets[i], sets[j])
            if r:
                out.append((sets[i]['id'], sets[j]['id'], r))
    return out


def curtailed(end_mm, member_lo_mm, member_hi_mm, cover_mm, bar_dia_mm, margin_mm=25.0):
    """A straight bar end stopping inside the member (not at its end cover): drawn with a 30 degree oblique."""
    reach = cover_mm + 2.0 * bar_dia_mm + margin_mm
    return member_lo_mm + reach < end_mm < member_hi_mm - reach


def tick(end, outward, side, scale):
    """The short 30 degree oblique at a curtailed bar end (SMDSC 6.2.2): ((x, y), (x, y)) in view mm."""
    length = TICK_PAPER_MM * scale
    a = math.radians(TICK_ANGLE_DEG)
    d = (outward[0] * math.cos(a) + side[0] * math.sin(a), outward[1] * math.cos(a) + side[1] * math.sin(a))
    return end, (end[0] + d[0] * length, end[1] + d[1] * length)


def see_drawing(rebar_drawing, view_drawing):
    """'SEE DRG nnnn' when a bar is detailed on another drawing than the one this view sits on, else None."""
    if rebar_drawing and view_drawing and rebar_drawing.strip() != view_drawing.strip():
        return u'SEE DRG {}'.format(rebar_drawing.strip())
    return None


def layer_slots(sets):
    """
    {id: fraction} placing each typical bar and its indicator line: sets drawn over each other (parallel bars,
    overlapping zones) share the zone at 1/(m+1), 2/(m+1)... in the order of their 'layer' (B1, B2, T1, T2),
    so no two typical bars or indicator lines coincide. A set on its own sits at the middle.
    """
    groups = []
    for s in sorted(sets, key=lambda s: (s.get('layer') or u'', s['id'])):
        if not s.get('spread_dir'):
            continue
        for g in groups:
            o = g[0]
            if abs(_dot(o['bar_dir'], s['bar_dir'])) >= PARALLEL and \
                    _overlap(_interval(o, o['spread_dir']), _interval(s, o['spread_dir'])) > 0.0:
                g.append(s)
                break
        else:
            groups.append([s])
    out = {}
    for g in groups:
        for k, s in enumerate(g):
            out[s['id']] = (k + 1.0) / (len(g) + 1.0)
    return out


def face(z_mm, lo_mm, hi_mm):
    """'top' or 'bottom': the face of a member (lo..hi through its depth) a bar at z_mm lies nearer."""
    return u'top' if z_mm > (lo_mm + hi_mm) / 2.0 else u'bottom'


def zone_quantity(count, spacing_mm):
    """A link zone under a beam elevation (SMDSC 6.2.3): 'n/pitch', the pitch rounded to the mm."""
    return u'{}/{:.0f}'.format(count, spacing_mm)


def total_callout(label, total, links=False):
    """
    The one calling-up of a mark drawn in several zones: its label without centres ('26H8-06'), the count
    the total of the zones ('43H8-06'); ' LINKS' after the links of a beam (SMDSC 6.2.3).
    """
    text = re.sub(u'^\d+', u'{}'.format(total), (label or u'').strip())
    return text + u' LINKS' if links else text
