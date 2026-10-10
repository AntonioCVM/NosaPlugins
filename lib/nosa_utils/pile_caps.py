# -*- coding: utf-8 -*-
"""
Pile caps of IStructE SMDSC 6.7 / Table 6.10 laid out as tie bands: the 3- and 7-pile caps carry their
design bars in bands over the lines joining the piles (one layer per direction), nominal H16 at 200
above them and lacers round the cap's own outline. Plan geometry in mm, no Revit.
"""
import math

BAND_PILE_COUNTS = (3, 7)        # Table 6.10: the caps not detailed as an orthogonal mat
NOMINAL_DIA_MM = 16.0            # Table 6.10: nominal H16 ...
NOMINAL_PITCH_MM = 200.0         # ... at 200
MIN_BAND_BARS = 3
ANGLE_TOLERANCE_DEG = 3.0


def uses_tie_bands(n_piles):
    """True for the caps Table 6.10 details with bars over the pile lines (3 and 7 piles)."""
    return n_piles in BAND_PILE_COUNTS


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n)


def _axis_angle(u):
    """Direction of a line in degrees, 0 <= a < 180."""
    return math.degrees(math.atan2(u[1], u[0])) % 180.0


def _neighbours(piles, i, j):
    """Gabriel neighbours: no other pile inside the circle on the pair as diameter."""
    mid = ((piles[i][0] + piles[j][0]) / 2.0, (piles[i][1] + piles[j][1]) / 2.0)
    r = math.hypot(*_sub(piles[j], piles[i])) / 2.0
    return all(math.hypot(*_sub(piles[k], mid)) > r * (1.0 + 1e-6)
               for k in range(len(piles)) if k not in (i, j))


def tie_lines(piles):
    """
    Lines joining neighbouring piles (Gabriel neighbours: the hexagon edges and spokes of a 7-pile
    group, the sides of a 3-pile triangle), collinear pairs merged:
    [{'angle', 'u', 'point', 'piles': [index...]}], grouped by direction, then by offset.
    """
    n = len(piles)
    pairs = [(i, j, math.hypot(*_sub(piles[j], piles[i]))) for i in range(n) for j in range(i + 1, n)]
    if not pairs:
        return []
    d_min = min(d for _i, _j, d in pairs)
    lines = []
    for i, j, d in pairs:
        if not _neighbours(piles, i, j):
            continue
        u = _unit(_sub(piles[j], piles[i]))
        if u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0):
            u = (-u[0], -u[1])
        for line in lines:
            if (abs(_cross(line['u'], u)) < math.sin(math.radians(ANGLE_TOLERANCE_DEG))
                    and abs(_cross(line['u'], _sub(piles[i], line['point']))) < 0.05 * d_min):
                line['piles'].update((i, j))
                break
        else:
            lines.append({'u': u, 'point': piles[i], 'piles': set((i, j))})
    for line in lines:
        line['angle'] = _axis_angle(line['u'])
        line['piles'] = sorted(line['piles'])
    groups = direction_groups(lines)
    return [line for group in groups for line in group]


def direction_groups(lines):
    """Lines grouped by direction, each group a list sorted by offset across it; groups by angle."""
    groups = []
    for line in sorted(lines, key=lambda l: l['angle']):
        for g in groups:
            diff = abs(g[0]['angle'] - line['angle'])
            if min(diff, 180.0 - diff) < ANGLE_TOLERANCE_DEG:
                g.append(line)
                break
        else:
            groups.append([line])
    for g in groups:
        normal = (-g[0]['u'][1], g[0]['u'][0])
        g.sort(key=lambda l: _dot(l['point'], normal))
    return groups


def clip_to_convex(polygon, point, u):
    """(t0, t1) of the line point + t u inside a convex polygon, or None."""
    t0, t1 = -1e12, 1e12
    area = sum(_cross(polygon[k], polygon[(k + 1) % len(polygon)]) for k in range(len(polygon)))
    sign = 1.0 if area > 0 else -1.0
    for k in range(len(polygon)):
        a, b = polygon[k], polygon[(k + 1) % len(polygon)]
        edge = _sub(b, a)
        inward = (-edge[1] * sign, edge[0] * sign)          # left normal of a CCW loop
        num = _dot(_sub(point, a), inward)                  # >= 0 inside
        den = _dot(u, inward)
        if abs(den) < 1e-12:
            if num < 0:
                return None
            continue
        t = -num / den
        if den > 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    return (t0, t1) if t1 - t0 > 1.0 else None


def band_bar_count(band_mm, pitch_mm):
    """Bars in one tie band: across the pile, at the given pitch, at least three."""
    return max(MIN_BAND_BARS, int(band_mm // pitch_mm) + 1)


def band_offsets_mm(n, pitch_mm):
    """Offsets of n bars at pitch_mm, centred on the pile line."""
    return [(k - (n - 1) / 2.0) * pitch_mm for k in range(n)]


def layout(polygon, piles, pitch_mm, band_mm):
    """
    Tie bands of a cap: polygon = the bar-centre outline (cover already taken off), piles = plan centres.
    [{'angle', 'bars': [((x0, y0), (x1, y1))], 'reach_mm': least bar length past the edge piles}] — one
    entry per direction, lowest layer first.
    """
    layers = []
    for group in direction_groups(tie_lines(piles)):
        bars, reach = [], None
        n = band_bar_count(band_mm, pitch_mm)
        for line in group:
            u = line['u']
            normal = (-u[1], u[0])
            ts = [_dot(_sub(piles[i], line['point']), u) for i in line['piles']]
            for off in band_offsets_mm(n, pitch_mm):
                p = (line['point'][0] + normal[0] * off, line['point'][1] + normal[1] * off)
                span = clip_to_convex(polygon, p, u)
                if span is None:
                    continue
                t0, t1 = span
                bars.append(((p[0] + u[0] * t0, p[1] + u[1] * t0), (p[0] + u[0] * t1, p[1] + u[1] * t1)))
                r = min(min(ts) - t0, t1 - max(ts))
                reach = r if reach is None else min(reach, r)
        if bars:
            layers.append({'angle': group[0]['angle'], 'bars': bars, 'reach_mm': reach or 0.0})
    return layers
