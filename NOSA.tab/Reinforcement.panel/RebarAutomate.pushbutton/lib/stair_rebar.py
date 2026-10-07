# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — cast-in-place stairs (T7.8). Pure geometry, mm, no Revit.

Each straight flight is worked in its own frame: s along the walking line from the first
riser, v across the width (right-handed with s and z), z absolute level. At every knee the
face that turns inwards (re-entrant) is not bent round the corner: those bars run straight
on and anchor in the opposite face (EC2 9.2 / IStructE detailing manual, knee joints). The
convex face keeps continuous bars. Top and bottom flight bars are staggered half a spacing
across the width so the layers that meet in a landing never sit on the same spot.

Starters (user decision 2026-10-03, both faces): L bars cast into the support below with the
foot on its bottom mat, or straight bars post-installed with resin into an existing support;
each rises to the flight's knee and is cranked to the slope, contact-lapped l0 with its bar.
Landing U-bars (same date): on the edges no flight reaches, one U per edge bar, contact-lapped,
legs max(40 phi, 2h) like slab edges; with them the bars stop straight inside the U.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import math

_MIN_LEG_MM = 50.0
MIN_STARTER_FOOT_MM = 450.0
A_MIN_MM = 500.0                 # SMDSC MST1: 'A' = max(0.1 design span, tension anchorage, 500)
NO_FINISH_TOP_COVER_MM = 10.0    # SMDSC 6.8: 10 mm more top cover where the stair has no finish
UBAR_AREA_SHARE = 0.5            # SMDSC MST1: landing U-bars 50 % of the main bottom area
BAR_SIZES_MM = (8, 10, 12, 16, 20, 25, 32, 40)


def a_length_mm(span_mm, anchorage_mm):
    """SMDSC MST1 'A': how far the top bars reach into the flight from each knee (25 mm up)."""
    a = max(0.1 * float(span_mm), float(anchorage_mm), A_MIN_MM)
    return 25.0 * math.ceil(a / 25.0 - 1e-9)


def landing_ubar_dia_mm(u_dia, u_spacing, main_dia, main_spacing):
    """The smallest bar from u_dia up whose U-bars at u_spacing give 50 % of the main bottom area (MST1)."""
    need = UBAR_AREA_SHARE * main_dia ** 2 / float(main_spacing)
    for size in BAR_SIZES_MM:
        if size >= u_dia - 1e-6 and size ** 2 / float(u_spacing) >= need - 1e-9:
            return float(size)
    return float(BAR_SIZES_MM[-1])


def lower_tops(runs, landings, extra_mm):
    """Copies of the runs and landings with their top faces extra_mm lower, for the bars only (no finish)."""
    out_runs = []
    for run in runs:
        r = dict(run)
        r['pitch_z0'] = run['pitch_z0'] - extra_mm / _cos(run['slope'])
        r['lower'] = dict(run['lower'], top=run['lower']['top'] - extra_mm)
        r['upper'] = dict(run['upper'], top=run['upper']['top'] - extra_mm)
        out_runs.append(r)
    return out_runs, [dict(landing, top=landing['top'] - extra_mm) for landing in landings]


def _slope_span(pts):
    """Index i of the rising segment pts[i] -> pts[i + 1] of a flight bar, or None."""
    for i in range(len(pts) - 1):
        if pts[i + 1][0] - pts[i][0] > 1.0 and pts[i + 1][1] - pts[i][1] > 1.0:
            return i
    return None


def split_top_bar(pts, run, cover, dia, a_mm, min_gap_mm=100.0):
    """
    SMDSC MST1: the flight top bar as two bars, each reaching 'A' along the slope from its knee;
    (lower, upper, (s_a, s_b)) or None when they would meet (keep it continuous).
    """
    i = _slope_span(pts)
    if i is None:
        return None
    _bottom, line = flight_lines(run, cover, dia, dia)
    ds = a_mm * _cos(run['slope'])
    s_a, s_b = pts[i][0] + ds, pts[i + 1][0] - ds
    if s_b - s_a < min_gap_mm * _cos(run['slope']):
        return None
    lower = _dedupe(pts[:i + 1] + [(s_a, line.z(s_a))])
    upper = _dedupe([(s_b, line.z(s_b))] + pts[i + 1:])
    return lower, upper, (s_a, s_b)


class Line(object):
    """z = z0 + slope * s."""

    def __init__(self, z0, slope):
        self.z0, self.slope = float(z0), float(slope)

    def z(self, s):
        return self.z0 + self.slope * s

    def s_at(self, z):
        return (z - self.z0) / self.slope

    def offset(self, dz):
        return Line(self.z0 + dz, self.slope)


def _cos(slope):
    return 1.0 / math.sqrt(1.0 + slope * slope)


def flight_lines(run, cover, dia_b, dia_t):
    """Axis lines of the bottom (soffit) and top (pitch line through the inner step corners) bars."""
    c = 1.0 / _cos(run['slope'])
    bottom = Line(run['soffit_z0'], run['slope']).offset((cover + dia_b / 2.0) * c)
    top = Line(run['pitch_z0'], run['slope']).offset(-(cover + dia_t / 2.0) * c)
    return bottom, top


def _dedupe(points):
    out = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append((float(p[0]), float(p[1])))
    return out


def _edge_inset(end, cover, dia):
    """(inset of the bar axis from a landing's free edge, closing leg wanted)."""
    u_dia = end.get('u_dia')
    if u_dia:
        return cover + u_dia + dia / 2.0, False         # stops straight inside the edge U-bar
    return cover + dia / 2.0, True


def bottom_bar(run, cover, dia, anchorage, slab_anchor=True, starter=False):
    """Flight bottom bar as (s, z) points from the lower end to the upper end."""
    line, _top = flight_lines(run, cover, dia, dia)
    half = cover + dia / 2.0
    lower, upper = run['lower'], run['upper']
    pts = []
    level = lower['bottom'] + half
    s_knee = line.s_at(level)
    if lower['kind'] == 'landing':
        inset, leg = _edge_inset(lower, cover, dia)
        s_end = lower['s_far'] + inset
        if leg:
            pts.append((s_end, lower['top'] - half))                  # closing leg at the free edge
        pts.append((s_end, level))
    elif not starter:
        pts.append((max(half, s_knee - anchorage), level))
    pts.append((s_knee, level))                                    # convex knee: bent round it
    top_level = upper['top'] - half
    s_up = line.s_at(top_level)                                    # re-entrant knee: straight on
    if upper['kind'] == 'landing':
        inset, leg = _edge_inset(upper, cover, dia)
        s_far = upper['s_far'] - inset
        if s_up >= s_far - dia:
            pts.append((s_far, line.z(s_far)))
        else:
            pts += [(s_up, top_level), (s_far, top_level)]
            if leg:
                pts.append((s_far, upper['bottom'] + half))
    elif slab_anchor:
        pts += [(s_up, top_level), (s_up + anchorage, top_level)]       # lapped into the floor slab
    else:
        s_end = run['length'] - half
        pts.append((s_end, line.z(s_end)))
    return _dedupe(pts)


def top_bar(run, cover, dia, anchorage, slab_anchor=True, starter=False):
    """Flight top bar: anchored in the bottom face below the lower knee, continuous over the upper one."""
    _bottom, line = flight_lines(run, cover, dia, dia)
    half = cover + dia / 2.0
    lower, upper = run['lower'], run['upper']
    level = lower['bottom'] + half
    s_down = line.s_at(level)
    if lower['kind'] == 'landing':
        inset, _leg = _edge_inset(lower, cover, dia)
        pts = [(max(lower['s_far'] + inset + dia, s_down - anchorage), level), (s_down, level)]
    elif starter:
        pts = [(s_down, level)]                                    # the top starter laps from here
    else:
        pts = [(max(half, s_down - anchorage), level), (s_down, level)]
    top_level = upper['top'] - half
    s_up = line.s_at(top_level)
    if upper['kind'] == 'landing':
        inset, leg = _edge_inset(upper, cover, dia)
        s_far = upper['s_far'] - inset
        pts += [(s_up, top_level), (s_far, top_level)]
        if leg:
            pts.append((s_far, upper['bottom'] + half))
    elif slab_anchor:
        pts += [(s_up, top_level), (s_up + anchorage, top_level)]
    else:
        s_end = min(s_up, run['length'] - half)
        pts.append((s_end, line.z(s_end)))
    return _dedupe(pts)


def upper_knee_bar(run, cover, dia, dia_t, anchorage):
    """Upper landing bottom bars carried straight into the flight up to the top bars (re-entrant knee)."""
    upper = run['upper']
    if upper['kind'] != 'landing':
        return None
    _bottom, top = flight_lines(run, cover, dia, dia_t)
    half = cover + dia / 2.0
    level = upper['bottom'] + half
    s_in = top.s_at(level)
    # inside the top bars' closing legs, or inside the edge U-bar
    s_far = upper['s_far'] - cover - max(dia_t, upper.get('u_dia') or 0.0) - dia / 2.0
    if s_far - s_in < _MIN_LEG_MM:
        return None
    return [(s_in, level), (s_far, level)]


def lower_knee_bar(run, cover, dia, dia_b, anchorage):
    """Lower landing top bars carried straight into the flight down to the bottom bars."""
    lower = run['lower']
    if lower['kind'] != 'landing':
        return None
    bottom, _top = flight_lines(run, cover, dia_b, dia)
    half = cover + dia / 2.0
    level = lower['top'] - half
    s_in = bottom.s_at(level)
    s_far = lower['s_far'] + cover + max(dia_b, lower.get('u_dia') or 0.0) + dia / 2.0
    if s_in - s_far < _MIN_LEG_MM:
        return None
    return [(s_far, level), (s_in, level)]


def starter_bars(run, cover, dia_b, dia_t, starter_dia, lap, support):
    """
    Starters at a flight that starts on a support (no lower landing), both faces:
    [(label, layer, points, lapped face 'bottom'|'top')]. Each rises at its bar's knee on the
    base, is cranked to the slope and laps l0 along that bar.
    support: {'mode': 'cast', 'foot_z': level of the foot axis} (foot on the support's bottom
             mat; bottom-face feet point up the flight, top-face feet back, like an open U), or
             {'mode': 'post', 'embed': drilled embedment below the base}.
    """
    if run['lower']['kind'] != 'floor':
        return []
    bottom, top = flight_lines(run, cover, dia_b, dia_t)
    base = run['lower']['bottom']
    ds, dz = _cos(run['slope']), _cos(run['slope']) * run['slope']
    foot = max(MIN_STARTER_FOOT_MM, 12.0 * starter_dia)
    out = []
    for label, line, dia, sign, face in ((u'Stair Starter Bottom', bottom, dia_b, 1.0, 'bottom'),
                                         (u'Stair Starter Top', top, dia_t, -1.0, 'top')):
        z_knee = base + cover + dia / 2.0
        s_knee = line.s_at(z_knee)
        lap_end = (s_knee + lap * ds, z_knee + lap * dz)
        if support['mode'] == 'cast':
            z_foot = support['foot_z']
            pts = [(s_knee + sign * foot, z_foot), (s_knee, z_foot), (s_knee, z_knee), lap_end]
        else:
            pts = [(s_knee, base - support['embed']), (s_knee, z_knee), lap_end]
        out.append((label, u'stair_starter', _dedupe(pts), face))
    return out


def flight_distribution(run, cover, dia_b, dia_t, dia_d):
    """Two lines (bottom, top) along which transverse bars are spaced: ((s0, z0), (s1, z1))."""
    c = 1.0 / _cos(run['slope'])
    bottom = Line(run['soffit_z0'], run['slope']).offset((cover + dia_b + dia_d / 2.0) * c)
    top = Line(run['pitch_z0'], run['slope']).offset(-(cover + dia_t + dia_d / 2.0) * c)
    lower, upper = run['lower'], run['upper']
    lo_b = bottom.s_at(lower['bottom'] + cover + dia_b + dia_d / 2.0)
    hi_b = bottom.s_at(upper['bottom'] if upper['kind'] == 'landing' else upper['top'] - cover)
    lo_t = top.s_at(lower['bottom'] + cover + dia_b + dia_d / 2.0 if lower['kind'] == 'landing'
                    else lower['bottom'] + cover + dia_t + dia_d / 2.0)
    hi_t = top.s_at(upper['top'] - cover - dia_t - dia_d / 2.0)
    if upper['kind'] != 'landing':          # the floor slab beyond is another element
        hi_b, hi_t = min(hi_b, run['length']), min(hi_t, run['length'])
    lines = []
    for line, s0, s1 in ((bottom, lo_b, hi_b), (top, lo_t, hi_t)):
        if s1 - s0 > _MIN_LEG_MM:
            lines.append(((s0, line.z(s0)), (s1, line.z(s1))))
        else:
            lines.append(None)
    return lines


def width_layout(v_min, v_max, cover, dia, spacing, stagger=False):
    """
    (first v, array length, bar count) across the width. The plain grid fills the width at no
    more than `spacing`; a staggered set takes the midpoints between its bars (one bar fewer),
    so two layers that meet in a landing never share a position.
    """
    first = v_min + cover + dia / 2.0
    width = max(0.0, v_max - cover - dia / 2.0 - first)
    count = int(math.ceil(width / spacing - 1e-9)) + 1 if width > 0 else 1
    pitch = width / (count - 1) if count > 1 else 0.0
    if not stagger:
        return first, width, count
    if count < 2:
        return first, 0.0, 1
    return first + pitch / 2.0, pitch * (count - 2), count - 1


def spaced_count(length, spacing):
    """(count, pitch) of a fixed-number set filling length at no more than spacing."""
    if length <= 0:
        return 1, 0.0
    count = int(math.ceil(length / spacing - 1e-9)) + 1
    return count, length / (count - 1)


def uncovered(interval, strips, min_width):
    """Parts of interval (lo, hi) not covered by any strip, wider than min_width."""
    parts = [interval]
    for lo, hi in strips:
        nxt = []
        for a, b in parts:
            if hi <= a or lo >= b:
                nxt.append((a, b))
                continue
            if lo > a:
                nxt.append((a, lo))
            if hi < b:
                nxt.append((hi, b))
        parts = nxt
    return [(a, b) for a, b in parts if b - a >= min_width]


def build_flight(run, cover, main_dia, main_spacing, dist_dia, dist_spacing, anchorage,
                 top_dia=None, top_spacing=None, slab_anchor=True, starters=None, a_mm=None):
    """
    Every set of one flight in its local frame.
    run: length, slope, soffit_z0, pitch_z0, v_min, v_max and lower/upper ends
         {'kind': 'landing'|'floor', 'top', 'bottom', 's_far'[, 'u_dia']}.
    slab_anchor: with no landing at the top, lap the bars into the floor slab beyond (else stop
                 at the end face).
    starters: None, or {'dia', 'lap', 'support'} (see starter_bars) for a flight on a support.
    a_mm: SMDSC MST1 'A' — the top bars (and their distribution bars) stop this far along the
          slope from each knee; None keeps them continuous.
    Returns a list of {'label','layer','dia','points':[(s,z)],'axis':'v'|'slope',
                       'first','array','count','spacing'} (for axis 'v' points are in the s-z plane
                       at v=first; for axis 'slope' the bar runs across the width and is spaced
                       along the slope).
    """
    top_dia = top_dia or main_dia
    top_spacing = top_spacing or main_spacing
    with_starters = bool(starters) and run['lower']['kind'] == 'floor'
    sets = []

    def along(label, layer, dia, spacing, pts, stagger, shift=0.0, grid_dia=None):
        if pts and len(pts) >= 2:
            first, array, count = width_layout(run['v_min'], run['v_max'], cover, grid_dia or dia,
                                               spacing, stagger)
            sets.append({'label': label, 'layer': layer, 'dia': dia, 'points': pts, 'axis': 'v',
                         'first': first + shift, 'array': array, 'count': count, 'spacing': spacing})

    along(u'Stair Flight Bottom', u'stair_bottom', main_dia, main_spacing,
          bottom_bar(run, cover, main_dia, anchorage, slab_anchor, with_starters), True)
    top_pts = top_bar(run, cover, top_dia, anchorage, slab_anchor, with_starters)
    split = split_top_bar(top_pts, run, cover, top_dia, a_mm) if a_mm else None
    if split:
        along(u'Stair Flight Top', u'stair_top', top_dia, top_spacing, split[0], False)
        along(u'Stair Flight Top', u'stair_top', top_dia, top_spacing, split[1], False)
    else:
        along(u'Stair Flight Top', u'stair_top', top_dia, top_spacing, top_pts, False)
    along(u'Stair Upper Knee', u'stair_knee', main_dia, main_spacing,
          upper_knee_bar(run, cover, main_dia, top_dia, anchorage), False)
    along(u'Stair Lower Knee', u'stair_knee', top_dia, top_spacing,
          lower_knee_bar(run, cover, top_dia, main_dia, anchorage), True)
    if with_starters:
        sd = starters['dia']
        for label, layer, pts, face in starter_bars(run, cover, main_dia, top_dia, sd,
                                                    starters['lap'], starters['support']):
            if face == 'bottom':       # beside each bottom bar, towards +v: a contact lap
                along(label, layer, sd, main_spacing, pts, True, (main_dia + sd) / 2.0, main_dia)
            else:
                along(label, layer, sd, top_spacing, pts, False, (top_dia + sd) / 2.0, top_dia)

    bottom_line, top_line = flight_distribution(run, cover, main_dia, top_dia, dist_dia)
    v0 = run['v_min'] + cover + dist_dia / 2.0
    v1 = run['v_max'] - cover - dist_dia / 2.0
    lines = [(u'Stair Flight Distribution Bottom', bottom_line)]
    if split and top_line is not None:
        (s0, z0), (s1, z1) = top_line
        k = (z1 - z0) / (s1 - s0)
        for a, b in ((s0, min(s1, split[2][0])), (max(s0, split[2][1]), s1)):
            if b - a > _MIN_LEG_MM:
                lines.append((u'Stair Flight Distribution Top', ((a, z0 + k * (a - s0)), (b, z0 + k * (b - s0)))))
    else:
        lines.append((u'Stair Flight Distribution Top', top_line))
    for label, line in lines:
        if line is None:
            continue
        (s0, z0), (s1, z1) = line
        length = math.hypot(s1 - s0, z1 - z0)
        sets.append({'label': label, 'layer': u'stair_distribution', 'dia': dist_dia,
                     'points': [(s0, z0)], 'v_range': (v0, v1), 'axis': 'slope',
                     'direction': ((s1 - s0) / length, (z1 - z0) / length),
                     'array': length, 'spacing': dist_spacing})
    return sets


def mandrel_mm(dia):
    """Minimum mandrel diameter of a bend (EC2 Table 8.1N, BS 8666): 4 phi up to 16 mm, 7 phi above."""
    return (4.0 if dia <= 16.0 else 7.0) * dia


def ubar_fits(leg_axis_gap, u_dia):
    """A U whose leg axes are leg_axis_gap apart can be bent round the minimum mandrel."""
    return leg_axis_gap - u_dia >= mandrel_mm(u_dia) - 1e-6


def feasible_u_edges(thickness, cover, main_dia, u_dia, edges):
    """
    (edges whose U-bars can be bent, notes). The far-edge U laps the outer bars, so its legs sit
    at cover; the side-edge U laps the transverse bars of the inner layer, one main bar further in.
    """
    edges = set(edges)
    notes = []
    if 's_max' in edges and not ubar_fits(thickness - 2.0 * cover - u_dia, u_dia):
        notes.append(u'landing {:.0f} mm thick: an H{:g} U-bar cannot be bent inside the cover '
                     u'(mandrel {:.0f} mm) — far edge left with closing legs.'.format(
                         thickness, u_dia, mandrel_mm(u_dia)))
        edges.discard('s_max')
    side_gap = thickness - 2.0 * (cover + main_dia) - u_dia
    if edges & {'v_min', 'v_max'} and not ubar_fits(side_gap, u_dia):
        notes.append(u'landing {:.0f} mm thick: side-edge U-bars lap the transverse bars in the inner '
                     u'layer, where an H{:g} U only has {:.0f} mm between legs (mandrel {:.0f} mm) — side '
                     u'edges skipped. A smaller U, less cover or a thicker landing fits.'.format(
                         thickness, u_dia, side_gap - u_dia, mandrel_mm(u_dia)))
        edges -= {'v_min', 'v_max'}
    return edges, notes


def ubar_leg(u_dia, thickness, available):
    """Slab free-edge U-bar leg: max(40 phi, 2h), never longer than the room behind the edge."""
    return min(max(40.0 * u_dia, 2.0 * thickness), available)


def build_landing(landing, cover, main_dia, dist_dia, dist_spacing, infill_spacing, strips,
                  parallel_runs, u_dia=None, u_edges=(), top_dia=None, top_spacing=None, warnings=None):
    """
    Landing slab in the frame of its first flight: transverse bars (along v) top and bottom over
    the whole landing, plus bars along s where no flight continues through (stairwell gap of a
    dog-leg). Without parallel flights (quarter landing) the bars along s cover the full width.
    With u_dia, U-bars close the free edges named in u_edges ('s_max', 'v_min', 'v_max').
    landing: s_min, s_max, v_min, v_max, top, bottom.
    """
    top_dia = top_dia or main_dia
    top_spacing = top_spacing or infill_spacing
    u_edges = set(u_edges) if u_dia else set()
    thickness = landing['top'] - landing['bottom']
    if warnings is None:
        warnings = []
    if u_dia:
        u_edges, notes = feasible_u_edges(thickness, cover, main_dia, u_dia, u_edges)
        warnings.extend(notes)
    sets = []
    far_u = 's_max' in u_edges
    s0 = landing['s_min'] + cover + main_dia + dist_dia / 2.0
    s1 = landing['s_max'] - cover - max(main_dia, u_dia if far_u else 0.0) - dist_dia / 2.0
    v0 = landing['v_min'] + cover + (u_dia if 'v_min' in u_edges else 0.0) + dist_dia / 2.0
    v1 = landing['v_max'] - cover - (u_dia if 'v_max' in u_edges else 0.0) - dist_dia / 2.0
    count, pitch = spaced_count(s1 - s0, dist_spacing)
    z_t = landing['top'] - cover - main_dia - dist_dia / 2.0
    z_b = landing['bottom'] + cover + main_dia + dist_dia / 2.0
    for label, z in ((u'Stair Landing Transverse Top', z_t), (u'Stair Landing Transverse Bottom', z_b)):
        if s1 - s0 > _MIN_LEG_MM and v1 - v0 > _MIN_LEG_MM:
            sets.append({'label': label, 'layer': u'stair_landing', 'dia': dist_dia,
                         'points': [(s0, z)], 'v_range': (v0, v1), 'axis': 'slope',
                         'direction': (1.0, 0.0), 'array': s1 - s0, 'count': count,
                         'spacing': dist_spacing})
    width = (landing['v_min'] + cover, landing['v_max'] - cover)
    gaps = uncovered(width, strips if parallel_runs else [], main_dia * 2.0)
    half = cover + main_dia / 2.0
    sa = landing['s_min'] + half
    sb = landing['s_max'] - (cover + u_dia + main_dia / 2.0 if far_u else half)
    infill_grids = []
    for lo, hi in gaps:
        for label, top_face in ((u'Stair Landing Top', True), (u'Stair Landing Bottom', False)):
            if top_face:
                pts = [(sa, landing['bottom'] + half), (sa, landing['top'] - half), (sb, landing['top'] - half)]
                if not far_u:
                    pts.append((sb, landing['bottom'] + half))
            else:
                pts = [(sa + main_dia, landing['bottom'] + half),
                       (sb - (0.0 if far_u else main_dia), landing['bottom'] + half)]
            first, array, n = width_layout(lo, hi, 0.0, main_dia, infill_spacing, not top_face)
            if top_face:
                infill_grids.append((first, array, n))
            sets.append({'label': label, 'layer': u'stair_landing', 'dia': main_dia, 'points': pts,
                         'axis': 'v', 'first': first, 'array': array, 'count': n,
                         'spacing': infill_spacing})

    if not u_edges:
        return sets
    zu_top, zu_bot = landing['top'] - cover - u_dia / 2.0, landing['bottom'] + cover + u_dia / 2.0
    if far_u:
        back = landing['s_max'] - cover - u_dia / 2.0
        leg = ubar_leg(u_dia, thickness, landing['s_max'] - landing['s_min'] - 2.0 * cover)
        pts = [(back - leg, zu_top), (back, zu_top), (back, zu_bot), (back - leg, zu_bot)]
        grids = [(width_layout(lo, hi, cover, top_dia, top_spacing), top_dia) for lo, hi in
                 (strips if parallel_runs else [])]
        grids += [(g, main_dia) for g in infill_grids]
        for (first, array, n), bar_dia in grids:
            sets.append({'label': u'Stair Landing Edge U-Bar', 'layer': u'stair_landing_ubar',
                         'dia': u_dia, 'points': pts, 'axis': 'v',
                         'first': first + (bar_dia + u_dia) / 2.0, 'array': array, 'count': n,
                         'spacing': top_spacing})
    zs_top = landing['top'] - cover - main_dia - u_dia / 2.0      # beside the transverse bars
    zs_bot = landing['bottom'] + cover + main_dia + u_dia / 2.0
    leg = ubar_leg(u_dia, thickness, (landing['v_max'] - landing['v_min']) / 2.0 - cover)
    for edge, back, sign in (('v_min', landing['v_min'] + cover + u_dia / 2.0, 1.0),
                             ('v_max', landing['v_max'] - cover - u_dia / 2.0, -1.0)):
        if edge not in u_edges or s1 - s0 <= _MIN_LEG_MM:
            continue
        pts = [(back + sign * leg, zs_top), (back, zs_top), (back, zs_bot), (back + sign * leg, zs_bot)]
        sets.append({'label': u'Stair Landing Edge U-Bar', 'layer': u'stair_landing_ubar',
                     'dia': u_dia, 'points_vz': pts, 'axis': 's',
                     'first': s0 + (dist_dia + u_dia) / 2.0, 'array': s1 - s0, 'count': count,
                     'spacing': dist_spacing})
    return sets


def section_profile(run, slab_stub=600.0):
    """Closed concrete outline of one flight with its ends, (s, z) points counter-clockwise."""
    lower, upper = run['lower'], run['upper']
    n = int(run.get('risers') or 0)
    riser, tread = float(run.get('riser') or 0.0), float(run.get('tread') or 0.0)
    soffit = Line(run['soffit_z0'], run['slope'])
    base = run['pitch_z0']
    pts = []
    if lower['kind'] == 'landing':
        pts += [(lower['s_far'], lower['bottom']), (lower['s_far'], lower['top'])]
    pts.append((0.0, base))
    for k in range(n):
        pts.append((k * tread, base + (k + 1) * riser))
        if k < n - 1:
            pts.append(((k + 1) * tread, base + (k + 1) * riser))
    if upper['kind'] == 'landing':
        pts += [(upper['s_far'], upper['top']), (upper['s_far'], upper['bottom']),
                (soffit.s_at(upper['bottom']), upper['bottom'])]
    else:
        end = run['length'] + slab_stub
        slab = upper['top'] - 200.0
        pts += [(end, upper['top']), (end, slab), (soffit.s_at(slab), slab)]
    pts.append((soffit.s_at(lower['bottom']), lower['bottom']))
    return _dedupe(pts)
