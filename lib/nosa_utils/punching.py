# -*- coding: utf-8 -*-
"""
Punching shear at slab-column connections (EC2 6.4 with the UK National Annex) and the layout of
shear stud rails round the column (EC2 9.4.3 / IStructE SMDSC 6.2: first perimeter 0.5 d from the
face, perimeters 0.75 d apart, the last within 1.5 d of u_out, studs no further apart round a
perimeter than 1.5 d inside u1 and 2 d outside it). Plan geometry in mm in the column's own frame
(centre at the origin, c1 along x, c2 along y); stresses in N/mm2. No Revit.
"""
import math

GAMMA_C = 1.5
ALPHA_CC_SHEAR = 1.0       # UK NA: alpha_cc = 1.0 for shear
K_MAX = 2.0                # UK NA 6.4.5(3): vEd at u1 <= 2 vRd,c with shear reinforcement
FYWD_MPA = 435.0           # 500 / 1.15
FIRST_PERIMETER = 0.5      # x d from the column face (SMDSC; EC2 0.3 d to 0.5 d)
PERIMETER_PITCH = 0.75     # x d
LAST_INSIDE_UOUT = 1.5     # x d: the last perimeter within k d of u_out
TANGENTIAL_INSIDE_U1 = 1.5
TANGENTIAL_OUTSIDE_U1 = 2.0
RAIL_OVERHANG_MM = 50.0
MIN_PERIMETERS = 2
STEP_MM = 5.0


def _floor_step(x, step=STEP_MM):
    return step * math.floor(x / step + 1e-9)


def point_in_polygon(x, y, polygon):
    inside = False
    n = len(polygon)
    for k in range(n):
        (x0, y0), (x1, y1) = polygon[k], polygon[(k + 1) % n]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def _outline(col, a, step=10.0):
    """Points round the column at distance a from its faces (rounded corners), closed."""
    if col.get('d'):
        r = col['d'] / 2.0 + a
        n = max(16, int(2.0 * math.pi * r / step))
        return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    hx, hy = col['c1'] / 2.0, col['c2'] / 2.0
    pts = []
    corners = [(hx, hy, 0.0), (-hx, hy, 90.0), (-hx, -hy, 180.0), (hx, -hy, 270.0)]
    for k, (cx, cy, start) in enumerate(corners):
        nx, ny = corners[(k + 1) % 4][0], corners[(k + 1) % 4][1]
        m = max(2, int(math.pi * a / 2.0 / step)) if a > 0 else 1
        for j in range(m + 1):
            t = math.radians(start + 90.0 * j / m)
            pts.append((cx + a * math.cos(t), cy + a * math.sin(t)))
        # straight run to the next corner's arc start
        t = math.radians(start + 90.0)
        p0 = (cx + a * math.cos(t), cy + a * math.sin(t))
        p1 = (nx + a * math.cos(t), ny + a * math.sin(t))
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        for j in range(1, int(length / step)):
            f = j * step / length
            pts.append((p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f))
    return pts


def perimeter_mm(col, a, polygon=None):
    """Length of the perimeter a from the column faces, only the part inside the slab polygon."""
    pts = _outline(col, a)
    total = 0.0
    for k in range(len(pts)):
        p, q = pts[k], pts[(k + 1) % len(pts)]
        if polygon is None or point_in_polygon((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0, polygon):
            total += math.hypot(q[0] - p[0], q[1] - p[1])
    return total


def v_rd_c(d_mm, rho_l, fck):
    """vRd,c (EC2 6.47, UK NA): 0.12 k (100 rho fck)^1/3, at least 0.035 k^1.5 fck^0.5."""
    k = min(1.0 + math.sqrt(200.0 / d_mm), 2.0)
    rho = min(rho_l, 0.02)
    return max(0.18 / GAMMA_C * k * (100.0 * rho * fck) ** (1.0 / 3.0), 0.035 * k ** 1.5 * math.sqrt(fck))


def v_rd_max(fck):
    """vRd,max at the column face (UK NA 6.4.5(3)): 0.5 nu fcd."""
    nu = 0.6 * (1.0 - fck / 250.0)
    return 0.5 * nu * ALPHA_CC_SHEAR * fck / GAMMA_C


def _distance_to(col, target, polygon, hi):
    lo = 0.0
    if perimeter_mm(col, hi, polygon) < target:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if perimeter_mm(col, mid, polygon) < target:
            lo = mid
        else:
            hi = mid
    return hi


def design(ved_kn, beta, col, d_mm, rho_l, fck, stud_dia_mm, polygon=None):
    """
    EC2 6.4 check and stud layout of one connection. Returns {'needed', 'ok', 'notes', 'u0', 'u1',
    'v_ed0', 'v_ed1', 'v_rd_c', 'v_rd_max', 'asw_mm2', 'u_out', 'a_out', 'perimeters': [a...],
    'studs_per_perimeter', 'rails': [...]} — lengths mm, stresses N/mm2.
    """
    notes = []
    ved = ved_kn * 1000.0
    u0 = perimeter_mm(col, 0.0, polygon)
    u1 = perimeter_mm(col, 2.0 * d_mm, polygon)
    out = {'needed': False, 'ok': True, 'notes': notes, 'u0': u0, 'u1': u1, 'perimeters': [], 'rails': [],
           'asw_mm2': 0.0, 'studs_per_perimeter': 0}
    out['v_ed0'] = beta * ved / (u0 * d_mm)
    out['v_rd_max'] = v_rd_max(fck)
    out['v_ed1'] = beta * ved / (u1 * d_mm)
    out['v_rd_c'] = vc = v_rd_c(d_mm, rho_l, fck)
    if out['v_ed0'] > out['v_rd_max']:
        out['ok'] = False
        notes.append(u'vEd {:.2f} N/mm2 at the column face exceeds vRd,max {:.2f} (EC2 6.4.5(3)): a bigger column, '
                     u'a thicker slab or a column head is needed.'.format(out['v_ed0'], out['v_rd_max']))
        return out
    if out['v_ed1'] <= vc:
        notes.append(u'vEd {:.2f} <= vRd,c {:.2f} N/mm2 at u1: no punching shear reinforcement needed.'.format(
            out['v_ed1'], vc))
        return out
    out['needed'] = True
    if out['v_ed1'] > K_MAX * vc:
        out['ok'] = False
        notes.append(u'vEd {:.2f} at u1 exceeds {:.1f} vRd,c = {:.2f} N/mm2 (UK NA 6.4.5(3)): shear studs cannot '
                     u'carry it; a thicker slab or a bigger column is needed.'.format(out['v_ed1'], K_MAX, K_MAX * vc))
        return out
    sr = _floor_step(PERIMETER_PITCH * d_mm)
    a1 = _floor_step(FIRST_PERIMETER * d_mm)
    fywd_ef = min(250.0 + 0.25 * d_mm, FYWD_MPA)
    asw = (out['v_ed1'] - 0.75 * vc) * u1 * d_mm / (1.5 * (d_mm / sr) * fywd_ef)
    out['asw_mm2'] = asw
    out['u_out'] = u_out = beta * ved / (vc * d_mm)
    out['a_out'] = a_out = _distance_to(col, u_out, polygon, 20.0 * d_mm)
    n = max(MIN_PERIMETERS, int(math.ceil((a_out - LAST_INSIDE_UOUT * d_mm - a1) / sr - 1e-9)) + 1)
    out['perimeters'] = [a1 + k * sr for k in range(n)]
    stud_area = math.pi * stud_dia_mm ** 2 / 4.0
    out['studs_per_perimeter'] = need = int(math.ceil(asw / stud_area - 1e-9))
    out['rails'] = rail_layout(col, out['perimeters'], need, d_mm, polygon)
    out['fywd_ef'] = fywd_ef
    out['sr'] = sr
    return out


def _rails_for(col, n):
    """n radial rail lines [(start on the face, unit direction)]: four at the corners, the rest across the faces."""
    if col.get('d'):
        r = col['d'] / 2.0
        return [((r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)),
                 (math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n))) for k in range(n)]
    hx, hy = col['c1'] / 2.0, col['c2'] / 2.0
    s = 1.0 / math.sqrt(2.0)
    rails = [((hx, hy), (s, s)), ((-hx, hy), (-s, s)), ((-hx, -hy), (-s, -s)), ((hx, -hy), (s, -s))]
    extra = max(n - 4, 0)
    per_x = int(round(extra * col['c1'] / (2.0 * (col['c1'] + col['c2'])))) if extra else 0
    per_y = int(math.ceil((extra - 2 * per_x) / 2.0)) if extra else 0
    for k in range(per_x):
        x = -hx + col['c1'] * (k + 1) / (per_x + 1)
        rails += [((x, hy), (0.0, 1.0)), ((x, -hy), (0.0, -1.0))]
    for k in range(per_y):
        y = -hy + col['c2'] * (k + 1) / (per_y + 1)
        rails += [((hx, y), (1.0, 0.0)), ((-hx, y), (-1.0, 0.0))]
    return rails


def rail_layout(col, perimeters, studs_needed, d_mm, polygon=None):
    """
    Rails [{'start', 'end', 'dir', 'studs': [(x, y)]}] round the column: as many as the studs each
    perimeter needs and the tangential spacing (1.5 d inside u1, 2 d outside) asks for; rails and studs
    outside the slab dropped.
    """
    n = max(studs_needed, 4 if not col.get('d') else 3)
    for a in perimeters:
        limit = (TANGENTIAL_INSIDE_U1 if a <= 2.0 * d_mm else TANGENTIAL_OUTSIDE_U1) * d_mm
        n = max(n, int(math.ceil(perimeter_mm(col, a) / limit - 1e-9)))
    for _ in range(64):
        rails = []
        for start, u in _rails_for(col, n):
            studs = [(start[0] + u[0] * a, start[1] + u[1] * a) for a in perimeters]
            if polygon is not None:
                studs = [p for p in studs if point_in_polygon(p[0], p[1], polygon)]
            if not studs:
                continue
            a_first = perimeters[0] - RAIL_OVERHANG_MM
            a_last = perimeters[len(studs) - 1] + RAIL_OVERHANG_MM
            rails.append({'dir': u, 'studs': studs,
                          'start': (start[0] + u[0] * a_first, start[1] + u[1] * a_first),
                          'end': (start[0] + u[0] * a_last, start[1] + u[1] * a_last)})
        inside_first = sum(1 for r in rails if r['studs'])
        if inside_first >= studs_needed:
            return rails
        n += 1
    return rails


def stud_height_mm(slab_mm, top_cover_mm, bottom_cover_mm, rail_mm):
    """Overall stud height: the head at the top cover, the rail on the bottom cover."""
    return slab_mm - top_cover_mm - bottom_cover_mm - rail_mm
