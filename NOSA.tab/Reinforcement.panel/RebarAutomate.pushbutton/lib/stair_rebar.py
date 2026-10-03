# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — cast-in-place stairs (T7.8). Pure geometry, mm, no Revit.

Each straight flight is worked in its own frame: s along the walking line from the first
riser, v across the width (right-handed with s and z), z absolute level. At every knee the
face that turns inwards (re-entrant) is not bent round the corner: those bars run straight
on and anchor in the opposite face (EC2 9.2 / IStructE detailing manual, knee joints). The
convex face keeps continuous bars. Top and bottom flight bars are staggered half a spacing
across the width so the layers that meet in a landing never sit on the same spot.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import math

_MIN_LEG_MM = 50.0


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


def bottom_bar(run, cover, dia, anchorage, slab_anchor=True):
    """Flight bottom bar as (s, z) points from the lower end to the upper end."""
    line, _top = flight_lines(run, cover, dia, dia)
    half = cover + dia / 2.0
    lower, upper = run['lower'], run['upper']
    pts = []
    level = lower['bottom'] + half
    s_knee = line.s_at(level)
    if lower['kind'] == 'landing':
        s_end = lower['s_far'] + half
        pts += [(s_end, lower['top'] - half), (s_end, level)]       # closing leg at the free edge
    else:
        s_end = max(half, s_knee - anchorage)
        pts.append((s_end, level))
    pts.append((s_knee, level))                                    # convex knee: bent round it
    top_level = upper['top'] - half
    s_up = line.s_at(top_level)                                    # re-entrant knee: straight on
    if upper['kind'] == 'landing':
        s_far = upper['s_far'] - half
        if s_up >= s_far - dia:
            pts.append((s_far, line.z(s_far)))
        else:
            pts += [(s_up, top_level), (s_far, top_level), (s_far, upper['bottom'] + half)]
    elif slab_anchor:
        pts += [(s_up, top_level), (s_up + anchorage, top_level)]       # lapped into the floor slab
    else:
        s_end = run['length'] - half
        pts.append((s_end, line.z(s_end)))
    return _dedupe(pts)


def top_bar(run, cover, dia, anchorage, slab_anchor=True):
    """Flight top bar: anchored in the bottom face below the lower knee, continuous over the upper one."""
    _bottom, line = flight_lines(run, cover, dia, dia)
    half = cover + dia / 2.0
    lower, upper = run['lower'], run['upper']
    level = lower['bottom'] + half
    s_down = line.s_at(level)
    if lower['kind'] == 'landing':
        s_stop = max(lower['s_far'] + half + dia, s_down - anchorage)
    else:
        s_stop = max(half, s_down - anchorage)
    pts = [(s_stop, level), (s_down, level)]
    top_level = upper['top'] - half
    s_up = line.s_at(top_level)
    if upper['kind'] == 'landing':
        s_far = upper['s_far'] - half
        pts += [(s_up, top_level), (s_far, top_level), (s_far, upper['bottom'] + half)]
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
    s_far = upper['s_far'] - cover - dia_t - dia / 2.0      # inside the top bars' closing legs
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
    s_far = lower['s_far'] + cover + dia_b + dia / 2.0     # inside the bottom bars' closing legs
    if s_in - s_far < _MIN_LEG_MM:
        return None
    return [(s_far, level), (s_in, level)]


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
                 top_dia=None, top_spacing=None, slab_anchor=True):
    """
    Every set of one flight in its local frame.
    run: length, slope, soffit_z0, pitch_z0, v_min, v_max and lower/upper ends
         {'kind': 'landing'|'floor', 'top', 'bottom', 's_far'}.
    slab_anchor: with no landing at the top, lap the bars into the floor slab beyond (else stop
                 at the end face).
    Returns a list of {'label','layer','dia','points':[(s,z)],'axis':'v'|'slope',
                       'first','array','spacing'} (for axis 'v' points are in the s-z plane at v=first;
                       for axis 'slope' the bar runs across the width and is spaced along the slope).
    """
    top_dia = top_dia or main_dia
    top_spacing = top_spacing or main_spacing
    sets = []

    def along(label, layer, dia, spacing, pts, stagger):
        if pts and len(pts) >= 2:
            first, array, count = width_layout(run['v_min'], run['v_max'], cover, dia, spacing, stagger)
            sets.append({'label': label, 'layer': layer, 'dia': dia, 'points': pts, 'axis': 'v',
                         'first': first, 'array': array, 'count': count, 'spacing': spacing})

    along(u'Stair Flight Bottom', u'stair_bottom', main_dia, main_spacing,
          bottom_bar(run, cover, main_dia, anchorage, slab_anchor), True)
    along(u'Stair Flight Top', u'stair_top', top_dia, top_spacing,
          top_bar(run, cover, top_dia, anchorage, slab_anchor), False)
    along(u'Stair Upper Knee', u'stair_knee', main_dia, main_spacing,
          upper_knee_bar(run, cover, main_dia, top_dia, anchorage), False)
    along(u'Stair Lower Knee', u'stair_knee', top_dia, top_spacing,
          lower_knee_bar(run, cover, top_dia, main_dia, anchorage), True)

    bottom_line, top_line = flight_distribution(run, cover, main_dia, top_dia, dist_dia)
    v0 = run['v_min'] + cover + dist_dia / 2.0
    v1 = run['v_max'] - cover - dist_dia / 2.0
    for label, line in ((u'Stair Flight Distribution Bottom', bottom_line),
                        (u'Stair Flight Distribution Top', top_line)):
        if line is None:
            continue
        (s0, z0), (s1, z1) = line
        length = math.hypot(s1 - s0, z1 - z0)
        sets.append({'label': label, 'layer': u'stair_distribution', 'dia': dist_dia,
                     'points': [(s0, z0)], 'v_range': (v0, v1), 'axis': 'slope',
                     'direction': ((s1 - s0) / length, (z1 - z0) / length),
                     'array': length, 'spacing': dist_spacing})
    return sets


def build_landing(landing, cover, main_dia, dist_dia, dist_spacing, infill_spacing, strips,
                  parallel_runs):
    """
    Landing slab in the frame of its first flight: transverse bars (along v) top and bottom over
    the whole landing, plus bars along s where no flight continues through (stairwell gap of a
    dog-leg). Without parallel flights (quarter landing) the bars along s cover the full width.
    landing: s_min, s_max, v_min, v_max, top, bottom.
    """
    sets = []
    s0 = landing['s_min'] + cover + main_dia + dist_dia / 2.0
    s1 = landing['s_max'] - cover - main_dia - dist_dia / 2.0
    v0 = landing['v_min'] + cover + dist_dia / 2.0
    v1 = landing['v_max'] - cover - dist_dia / 2.0
    for label, z in ((u'Stair Landing Transverse Top', landing['top'] - cover - main_dia - dist_dia / 2.0),
                     (u'Stair Landing Transverse Bottom', landing['bottom'] + cover + main_dia + dist_dia / 2.0)):
        if s1 - s0 > _MIN_LEG_MM and v1 - v0 > _MIN_LEG_MM:
            sets.append({'label': label, 'layer': u'stair_landing', 'dia': dist_dia,
                         'points': [(s0, z)], 'v_range': (v0, v1), 'axis': 'slope',
                         'direction': (1.0, 0.0), 'array': s1 - s0, 'spacing': dist_spacing})
    width = (landing['v_min'] + cover, landing['v_max'] - cover)
    gaps = uncovered(width, strips if parallel_runs else [], main_dia * 2.0)
    half = cover + main_dia / 2.0
    sa, sb = landing['s_min'] + half, landing['s_max'] - half
    for lo, hi in gaps:
        for label, top_face in ((u'Stair Landing Top', True), (u'Stair Landing Bottom', False)):
            if top_face:
                pts = [(sa, landing['bottom'] + half), (sa, landing['top'] - half),
                       (sb, landing['top'] - half), (sb, landing['bottom'] + half)]
            else:
                pts = [(sa + main_dia, landing['bottom'] + half), (sb - main_dia, landing['bottom'] + half)]
            first, array, count = width_layout(lo, hi, 0.0, main_dia, infill_spacing, not top_face)
            sets.append({'label': label, 'layer': u'stair_landing', 'dia': main_dia, 'points': pts,
                         'axis': 'v', 'first': first, 'array': array, 'count': count,
                         'spacing': infill_spacing})
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
