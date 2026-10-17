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
    """A link zone under a beam elevation: '(n@pitch)', the pitch rounded to the mm (SMDSC 4th ed. Fig. 6.24)."""
    return u'({}@{:.0f})'.format(count, spacing_mm)


def total_callout(label, total, note=u''):
    """
    The one calling-up of a mark drawn in several zones: its label without centres ('26H8-06'), the count
    the total of the zones ('43H8-06'), then what kind of bar it is ('43H8-06 LINKS', SMDSC 6.2.3).
    """
    text = re.sub(u'^[0-9]+', u'{}'.format(total), (label or u'').strip())
    return u'{} {}'.format(text, note) if note else text


_NOTES = ((('11', '12'), u'L-BARS'), (('13', '21', '22', '23', '24', '25'), u'U-BARS'),
          (('31', '32', '33', '34', '35', '36', '41', '44', '46', '47', '51', '52', '56', '63', '64', '67', '75'),
           u'LINKS'))


_ROLE_NOTES = {u'spacer': u'SPACERS'}


def bar_note(shape_code, in_twos=False, layer=u''):
    """
    What kind of bar, written after its calling-up (user 2026-10-10, SMDSC drawings): 'L-BARS', 'U-BARS',
    'LINKS', 'LINKS IN 2s' for two links at each position; '' for straight bars and other shapes. A bar's role
    goes before its shape: spacer bars between layers are 'SPACERS' (4H25-01 SPACERS, user 2026-10-11).
    """
    role = _ROLE_NOTES.get((layer or u'').strip().lower())
    if role:
        return role
    code = (shape_code or u'').strip()
    for codes, note in _NOTES:
        if code in codes:
            return u'LINKS IN 2s' if note == u'LINKS' and in_twos else note
    return u''


def curtailment_dims(bars, supports, tol=1.0):
    """
    What to dimension along a beam elevation (T9.3, SMDSC 4th ed. 3.13 / Fig. 6.24): bars [(x0, x1, layer)],
    supports [(x0, x1)] (view mm). Each bar end that stops in a span is dimensioned from the face of the nearest
    support ('cut', face, end, layer); two bars of one layer overlapping are a lap ('lap', start, end, layer).
    Ends inside a support are anchored there and need no dimension.
    """
    out = []

    def in_support(x):
        return any(a - tol <= x <= b + tol for a, b in supports)

    for x0, x1, layer in bars:
        for end in (x0, x1):
            if in_support(end) or not supports:
                continue
            faces = [x for s in supports for x in s]
            face = min(faces, key=lambda f: abs(f - end))
            if abs(face - end) > tol:
                out.append(('cut', min(face, end), max(face, end), layer))
    ordered = sorted(bars)
    for i, (a0, a1, la) in enumerate(ordered):
        for b0, b1, lb in ordered[i + 1:]:
            if la != lb or b0 >= a1 - tol:
                continue
            lo, hi = max(a0, b0), min(a1, b1)
            if hi - lo > tol and not (abs(a0 - b0) < tol and abs(a1 - b1) < tol):
                out.append(('lap', lo, hi, la))
    seen, unique = set(), []
    for d in out:
        key = (d[0], round(d[1]), round(d[2]), d[3])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


CLUSTER_MM = 500.0


def single_clusters(bars, reach_mm=CLUSTER_MM):
    """
    Loose single bars that make one group on a drawing (user 2026-10-12: the eight bars of a round column are
    '8H20-01', not the five an elevation shows; trimmers each side of an opening are their own group): bars
    [(id, key, (x, y, z) start, (x, y, z) end)] in mm, key their mark, type and layer. Two bars of one key join
    when parallel, overlapping along their length and no more than reach_mm apart. Returns {id: (group, size)}.
    """
    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def unit(a):
        n = dot(a, a) ** 0.5 or 1.0
        return (a[0] / n, a[1] / n, a[2] / n)

    def near(a, b):
        if a[1] != b[1]:
            return False
        u, v = unit(sub(a[3], a[2])), unit(sub(b[3], b[2]))
        if abs(dot(u, v)) < PARALLEL:
            return False
        t0, t1 = sorted((dot(a[2], u), dot(a[3], u)))
        s0, s1 = sorted((dot(b[2], u), dot(b[3], u)))
        if min(t1, s1) - max(t0, s0) <= 0.0:
            return False
        w = sub(b[2], a[2])
        across = sub(w, tuple(u[i] * dot(w, u) for i in range(3)))
        return dot(across, across) ** 0.5 <= reach_mm
    parent = list(range(len(bars)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(bars)):
        for j in range(i + 1, len(bars)):
            if near(bars[i], bars[j]):
                parent[root(j)] = root(i)
    sizes = {}
    for i in range(len(bars)):
        sizes[root(i)] = sizes.get(root(i), 0) + 1
    return dict((bars[i][0], (root(i), sizes[root(i)])) for i in range(len(bars)))


ARROW_PAPER_MM = 6.0


def end_arrow(end, outward, side, text_w, text_h, scale, gap, row=0):
    """
    Where a bar's end mark goes (user 2026-10-12: a horizontal arrow to where the bar stops, its mark at the tail):
    the arrow runs along the bar, `row` steps of the text height to the side `side` (unit, view mm) of it, its tip
    level with the end. Returns (tip, text centre, text box).
    """
    off = (row + 0.5) * text_h + gap
    tip = (end[0] + side[0] * off, end[1] + side[1] * off)
    along = ARROW_PAPER_MM * scale + (text_w if abs(outward[0]) >= abs(outward[1]) else text_h) / 2.0
    c = (tip[0] - outward[0] * along, tip[1] - outward[1] * along)
    return tip, c, (c[0] - text_w / 2.0, c[1] - text_h / 2.0, c[0] + text_w / 2.0, c[1] + text_h / 2.0)


def junction_fraction(slot):
    """
    Where along its typical bar a set's indicator line crosses it: a quarter of the bar away from the slot the typical
    bar takes in its set, so it never runs along the typical bar of the set across it, which stands at the same slot
    (user 2026-10-12, the two U-bar sets of a pile cap).
    """
    return slot + 0.25 if slot <= 0.5 else slot - 0.25


SUPPORT_TEXT = u'SUPPORT'


def support_chain(supports, tol=1.0):
    """
    T9.17 (SMDSC 4th ed. 6.3, MD B1): the points of the dimension string under a beam elevation through the faces
    of its supports [(a, b)] and the text under each segment: SUPPORT across a support, '' across a clear span.
    ([x], [label per segment]); ([], []) with no support.
    """
    xs = []
    for a, b in sorted(supports):
        for x in (a, b):
            if not xs or x - xs[-1] > tol:
                xs.append(x)
    labels = []
    for x0, x1 in zip(xs, xs[1:]):
        m = (x0 + x1) / 2.0
        labels.append(SUPPORT_TEXT if any(a - tol <= m <= b + tol for a, b in supports) else u'')
    return (xs, labels) if len(xs) >= 2 else ([], [])


def arc_stations(length_mm, step_mm=None, least_mm=500.0):
    """
    T9.17 curved beam plan: the chainages (mm along its axis) set out on the plan, from 0 to its length: at a round
    step (a sixth of the length up to 500 mm, at least 500) and at its end.
    """
    if length_mm <= 0.0:
        return []
    if step_mm is None:
        step_mm = max(least_mm, least_mm * round(length_mm / 6.0 / least_mm))
    out, ch = [], 0.0
    while ch < length_mm - 0.25 * step_mm:
        out.append(ch)
        ch += step_mm
    out.append(length_mm)
    return out


def chainage_text(ch_mm):
    """'CH 2000' for a station 2000 mm along a curved beam."""
    return u'CH {:.0f}'.format(ch_mm)
