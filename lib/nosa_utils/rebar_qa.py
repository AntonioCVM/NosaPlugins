# -*- coding: utf-8 -*-
"""
nosa_utils.rebar_qa — reinforcement QA (T8.48, IStructE SMDSC 4.4, 4.6, 5.2): per host and per drawing,
cover against the bar size and the aggregate, clear spacing with the real bar size (+10 %), the vibrator gap of
a beam's top layer, pitches and steel ratios within the element's limits, bars within the stock length, bars
that clash or crowd each other. The rules are pure; audit(doc) reads the model and changes nothing.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

REAL_DIA = 1.10            # SMDSC Table 5.2: a deformed bar is about 10 % over its nominal size
AGGREGATE_MM = 20.0
DELTA_CDEV_MM = 10.0
STOCK_MM = 12000.0         # SMDSC 4.2.4: commercial length
VIBRATOR_GAP_MM = 75.0     # SMDSC MB1: a 75 mm poker gap for every 300 mm of beam width
VIBRATOR_WIDTH_MM = 300.0
CLASH_TOL_MM = 3.0        # modelling tolerance between straight bars
PARALLEL_COS = 0.996
MAX_SEGMENTS = 4000

ERROR, WARNING, INFO = u'Error', u'Warning', u'Info'


class Finding(object):
    """One row of the report (plain names: the WPF grid binds them)."""

    def __init__(self, drawing, host, mark, check, severity, issue, element_id=None):
        self.Drawing = drawing or u''
        self.Host = host or u''
        self.Mark = mark or u''
        self.Check = check
        self.Severity = severity
        self.Issue = issue
        self.ElementId = element_id


def min_clear_mm(dia_mm, aggregate_mm=AGGREGATE_MM):
    """SMDSC 5.2.5 / EC2 8.2: minimum clear distance between bars, max(bar size, aggregate + 5, 20)."""
    return max(float(dia_mm), float(aggregate_mm) + 5.0, 20.0)


def cover_issues(cover_mm, dia_mm, nominal_mm=None, aggregate_mm=AGGREGATE_MM):
    """[(severity, text)]: cover to a bar under its size or the aggregate, or under the nominal less the deviation."""
    out = []
    if cover_mm < dia_mm - 0.5:
        out.append((ERROR, u'cover {:.0f} mm under the bar size {:.0f} (SMDSC 5.2.2)'.format(cover_mm, dia_mm)))
    elif cover_mm < aggregate_mm - 0.5:
        out.append((ERROR, u'cover {:.0f} mm under the aggregate size {:.0f}'.format(cover_mm, aggregate_mm)))
    if nominal_mm and cover_mm < nominal_mm - DELTA_CDEV_MM - 0.5:
        out.append((WARNING, u'cover {:.0f} mm under the nominal {:.0f} less the {:.0f} mm deviation'.format(
            cover_mm, nominal_mm, DELTA_CDEV_MM)))
    return out


def spacing_issue(spacing_mm, dia_mm, aggregate_mm=AGGREGATE_MM):
    """Text when the clear gap between the bars of a set, real size, is under the minimum; else None."""
    clear = spacing_mm - REAL_DIA * dia_mm
    need = min_clear_mm(dia_mm, aggregate_mm)
    if clear < need - 0.5:
        return u'clear gap {:.0f} mm at {:.0f} centres (real size {:.0f}) under {:.0f} (SMDSC 5.2.5)'.format(
            clear, spacing_mm, REAL_DIA * dia_mm, need)
    return None


def max_pitch_mm(kind, depth_mm):
    """Largest pitch of the main bars of a slab, wall or base (SMDSC 6.2, 6.5, 6.7); None for other members."""
    if kind == u'slab':
        return min(3.0 * depth_mm, 400.0)
    if kind == u'wall':
        return min(3.0 * depth_mm, 400.0)
    if kind == u'foundation':
        return 300.0
    return None


def min_ratio(fck_mpa, fyk_mpa=500.0):
    """EC2 9.2.1.1 / 9.3.1.1: 0.26 fctm / fyk, at least 0.0013."""
    fctm = 0.30 * fck_mpa ** (2.0 / 3.0) if fck_mpa <= 50 else 2.12 * math.log(1.0 + (fck_mpa + 8.0) / 10.0)
    return max(0.26 * fctm / fyk_mpa, 0.0013)


def area_per_m(dia_mm, spacing_mm):
    return math.pi * dia_mm ** 2 / 4.0 * 1000.0 / spacing_mm


def ratio_issue(kind, ratio, fck_mpa=32.0):
    """Text when a member's steel ratio is outside its limits (EC2 9.2-9.6); else None."""
    if kind in (u'column', u'wall'):
        if ratio < 0.002 - 1e-9:
            return u'vertical steel {:.2f} % under 0.2 % (EC2 9.5.2 / 9.6.2)'.format(100.0 * ratio)
        if ratio > 0.04 + 1e-9:
            return u'vertical steel {:.2f} % over 4 % (EC2 9.5.2 / 9.6.2)'.format(100.0 * ratio)
    elif kind in (u'slab', u'foundation'):
        need = min_ratio(fck_mpa)
        if ratio < need - 1e-9:
            return u'{:.3f} % of b d under the minimum {:.3f} % (EC2 9.3.1.1)'.format(100.0 * ratio, 100.0 * need)
    return None


def vibrator_issue(width_mm, gaps_clear_mm):
    """Text when a beam's top layer leaves fewer 75 mm poker gaps than one per 300 mm of width; else None."""
    need = max(1, int(width_mm // VIBRATOR_WIDTH_MM))
    have = sum(1 for g in gaps_clear_mm if g >= VIBRATOR_GAP_MM - 0.5)
    if have < need:
        return u'{} gap(s) of 75 mm in the top layer, {} needed for a {:.0f} mm beam (SMDSC MB1)'.format(
            have, need, width_mm)
    return None


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def segment_distance(p1, p2, q1, q2):
    """(shortest distance, |cos| of the angle between them, overlap along the first, the point midway) of two
    3D segments (mm)."""
    d1, d2, r = _sub(p2, p1), _sub(q2, q1), _sub(p1, q1)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    if a < 1e-9 or e < 1e-9:
        return float('inf'), 0.0, 0.0, p1
    c, b = _dot(d1, r), _dot(d1, d2)
    denom = a * e - b * b
    s = min(1.0, max(0.0, (b * f - c * e) / denom)) if denom > 1e-9 else 0.0
    t = (b * s + f) / e
    if t < 0.0:
        t, s = 0.0, min(1.0, max(0.0, -c / a))
    elif t > 1.0:
        t, s = 1.0, min(1.0, max(0.0, (b - c) / a))
    cp = (p1[0] + d1[0] * s, p1[1] + d1[1] * s, p1[2] + d1[2] * s)
    cq = (q1[0] + d2[0] * t, q1[1] + d2[1] * t, q1[2] + d2[2] * t)
    gap = _sub(cp, cq)
    cos = abs(b) / math.sqrt(a * e)
    la = math.sqrt(a)
    u = (d1[0] / la, d1[1] / la, d1[2] / la)
    lo, hi = sorted((_dot(_sub(q1, p1), u), _dot(_sub(q2, p1), u)))
    overlap = max(0.0, min(la, hi) - max(0.0, lo))
    mid = tuple((a + b) / 2.0 for a, b in zip(cp, cq))
    return math.sqrt(_dot(gap, gap)), cos, overlap, mid


def pair_issue(dist_mm, cos, overlap_mm, dia1_mm, dia2_mm, aggregate_mm=AGGREGATE_MM, bend=False):
    """
    (severity, text) when two bars of different sets clash or run side by side too close; else None. bend: one of
    them is in a bend, where a bar seated in a link's corner overlaps its centreline radius by up to the smaller
    bar size (the model's simplification, not a clash); closer than half the touching distance is always a clash.
    """
    touch = (dia1_mm + dia2_mm) / 2.0
    limit = max(touch - (min(dia1_mm, dia2_mm) if bend else CLASH_TOL_MM), 0.5 * touch)
    if dist_mm < limit:
        return ERROR, u'clash: centrelines {:.0f} mm apart, bars {:.0f} + {:.0f}'.format(dist_mm, dia1_mm, dia2_mm)
    if cos >= PARALLEL_COS and overlap_mm > 0.0 and dist_mm > 1.05 * touch:
        clear = dist_mm - REAL_DIA * touch
        need = min_clear_mm(max(dia1_mm, dia2_mm), aggregate_mm)
        if clear < need - 0.5:
            return WARNING, u'congested: clear gap {:.0f} mm to a parallel bar (real size), {:.0f} needed'.format(
                clear, need)
    return None


def _length(a, b):
    return math.sqrt(_dot(_sub(b, a), _sub(b, a)))


def is_lap(dist_mm, cos, overlap_mm, len1_mm, len2_mm, dia1_mm, dia2_mm):
    """
    Two parallel bars on (nearly) one line overlapping over part of their length only: a lap, modelled with the bars
    coincident and fixed in contact on site (EC2 8.7.2), not a clash.
    """
    return (cos >= PARALLEL_COS and dist_mm < (dia1_mm + dia2_mm) / 2.0 and overlap_mm > 0.0 and
            overlap_mm < min(len1_mm, len2_mm) - 1.0)


def gaps_clear(positions_mm, dias_mm):
    """Clear gaps (real size) between neighbouring bars of one layer, positions across the member."""
    pairs = sorted(zip(positions_mm, dias_mm))
    return [b[0] - a[0] - REAL_DIA * (a[1] + b[1]) / 2.0 for a, b in zip(pairs, pairs[1:])]


# ---------------------------------------------------------------------------------------------------------------
# T9.8-T9.12 buildability (IStructE SMDSC 4th ed. 4.2, Fig. 4.2; EC2 9.5.3)

MAX_LAYERS = 2                # more layers in one face of a member congests it (SMDSC 4th ed. 4.2.1)
RESTRAINT_REACH_MM = 150.0    # EC2 9.5.3(6): a bar within 150 mm of a restrained bar needs no link of its own


def face_layers(bars, mid_mm):
    """{'top': n, 'bottom': n}: rows of bars in each face of a section, bars [(across, up, dia)] in mm."""
    out = {}
    for face, keep in ((u'top', lambda up: up > mid_mm), (u'bottom', lambda up: up <= mid_mm)):
        rows = []
        for _a, up, dia in sorted((b for b in bars if keep(b[1])), key=lambda b: b[1]):
            if rows and abs(up - rows[-1]) <= max(dia, 10.0):
                continue
            rows.append(up)
        out[face] = len(rows)
    return out


def congestion_issues(bars, mid_mm, aggregate_mm=AGGREGATE_MM):
    """
    T9.8: [(severity, text)] for one section through a beam or column, bars [(across, up, dia)] mm: more than two
    layers in a face, or bars of one layer closer than the minimum clear gap (real size).
    """
    out = []
    for face, n in sorted(face_layers(bars, mid_mm).items()):
        if n > MAX_LAYERS:
            out.append((WARNING, u'{} layers in the {} face: congested, drawn in a 1:10 section (SMDSC 4th ed. '
                                 u'4.2.1)'.format(n, face)))
    tight = 0
    rows = {}
    for across, up, dia in bars:
        rows.setdefault(round(up / 10.0), []).append((across, dia))
    for row in rows.values():
        row.sort()
        for (a, da), (b, db) in zip(row, row[1:]):
            if b - a - REAL_DIA * (da + db) / 2.0 < min_clear_mm(max(da, db), aggregate_mm) - 0.5:
                tight += 1
    if tight:
        out.append((WARNING, u'{} pair(s) of bars closer than the minimum clear gap: congested, drawn in a 1:10 '
                             u'section'.format(tight)))
    return out


def unrestrained_bars(bars, restraints, link_dia_mm=10.0, reach_mm=RESTRAINT_REACH_MM):
    """
    T9.10, EC2 9.5.3(6) / SMDSC 4th ed. 4.2.2: indexes of a column's bars [(x, y, dia)] neither held in a link's
    corner or a cross-tie's hook (restraints [(x, y)]) nor within reach_mm clear of a bar that is.
    """
    held = []
    for i, (x, y, d) in enumerate(bars):
        tol = d / 2.0 + link_dia_mm + 15.0
        if any(((x - rx) ** 2 + (y - ry) ** 2) ** 0.5 <= tol for rx, ry in restraints):
            held.append(i)
    out = []
    for i, (x, y, d) in enumerate(bars):
        if i in held:
            continue
        near = [((x - bars[j][0]) ** 2 + (y - bars[j][1]) ** 2) ** 0.5 - (d + bars[j][2]) / 2.0 for j in held]
        if not near or min(near) > reach_mm + 0.5:
            out.append(i)
    return out


def joint_vibrator_issue(width_mm, positions_mm, dias_mm):
    """
    T9.9, SMDSC 4th ed. Fig. 4.2: at a beam-column joint the beam's top bars and the column bars through it, across
    the beam, must leave a 75 mm poker gap for every 300 mm of width. Text when they do not; else None.
    """
    issue = vibrator_issue(width_mm, gaps_clear(positions_mm, dias_mm))
    return u'joint: ' + issue if issue else None


GRADES = ((95.0, u'A+'), (85.0, u'A'), (70.0, u'B'))


def buildability(findings):
    """
    T9.12: (score 0-100, grade A+ / A / B / C, errors, warnings) of a drawing's findings: an error costs 15 points,
    a warning 3. A+ ready to issue; A minor points; B to be reviewed with the detailer; C not buildable as drawn.
    """
    errors = sum(1 for f in findings if getattr(f, 'Severity', f) == ERROR)
    warnings = sum(1 for f in findings if getattr(f, 'Severity', f) == WARNING)
    score = max(0.0, 100.0 - 15.0 * errors - 3.0 * warnings)
    grade = u'C'
    for floor, g in GRADES:
        if score >= floor:
            grade = g
            break
    if errors and grade in (u'A+', u'A'):
        grade = u'B'                     # an error is never A
    return score, grade, errors, warnings


# ---------------------------------------------------------------------------------------------------------------
# Revit side (read-only)

_MM = 304.8
_KINDS = (('OST_Floors', u'slab'), ('OST_Walls', u'wall'), ('OST_StructuralFraming', u'beam'),
          ('OST_StructuralColumns', u'column'), ('OST_StructuralFoundation', u'foundation'),
          ('OST_Stairs', u'stairs'))


def _kind(DB, host):
    try:
        cat = host.Category.Id
    except Exception:
        return None
    from nosa_utils.revit_helpers import get_id_value
    for name, kind in _KINDS:
        if get_id_value(cat) == int(getattr(DB.BuiltInCategory, name)):
            return kind
    return None


def _text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def _xyz(p):
    return (p.X * _MM, p.Y * _MM, p.Z * _MM)


def _chain(DB, rebar, i):
    from Autodesk.Revit.DB.Structure import MultiplanarOption
    pts = []
    try:
        curves = rebar.GetTransformedCenterlineCurves(False, False, False,
                                                      MultiplanarOption.IncludeOnlyPlanarCurves, i)
    except Exception:
        return []
    segments = []
    for c in curves:
        if isinstance(c, DB.Line):
            segments.append((_xyz(c.GetEndPoint(0)), _xyz(c.GetEndPoint(1)), False))
        else:
            pts = [_xyz(p) for p in _fine_points(DB, c)]
            segments.extend((a, b, True) for a, b in zip(pts, pts[1:]))
    return segments


SAGITTA_MM = 1.0     # the chords an arc is checked by stray no further than this from it


def _fine_points(DB, curve):
    """
    Points along a curved bar close enough that no chord strays SAGITTA_MM from it: Revit's own tessellation of a
    curved beam's 3.5 m radius bars strays some 8 mm, which read as the bars clashing with their links.
    """
    if isinstance(curve, DB.Arc):
        r = curve.Radius * _MM
        sweep = abs(curve.GetEndParameter(1) - curve.GetEndParameter(0))
        if r > 0 and sweep > 0:
            step = 2.0 * math.acos(max(-1.0, 1.0 - SAGITTA_MM / r))
            n = max(2, min(int(math.ceil(sweep / step)), 400))
            return [curve.Evaluate(k / float(n), True) for k in range(n + 1)]
    return list(curve.Tessellate())


def _solid_faces(DB, host):
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    faces = []
    try:
        geo = host.get_Geometry(opts)
    except Exception:
        return faces
    stack = list(geo) if geo is not None else []
    while stack:
        g = stack.pop()
        if isinstance(g, DB.Solid) and g.Volume > 1e-6:
            faces.extend(list(g.Faces))
        elif isinstance(g, DB.GeometryInstance):
            stack.extend(list(g.GetInstanceGeometry()))
    return faces


def _solids(DB, host):
    opts = DB.Options()
    out, stack = [], []
    try:
        stack = list(host.get_Geometry(opts) or [])
    except Exception:
        return out
    while stack:
        g = stack.pop()
        if isinstance(g, DB.Solid) and g.Volume > 1e-6:
            out.append(g)
        elif isinstance(g, DB.GeometryInstance):
            stack.extend(list(g.GetInstanceGeometry()))
    return out


def _faces_not_crossed(DB, faces, chain):
    """
    The faces a bar has a cover to: not the plane faces it runs through (a beam's end face, where its bars go on
    into the column), whose distance falls to nothing where the bar crosses them.
    """
    pts = [a for a, _b, _bend in chain] + [chain[-1][1]]
    out = []
    for f in faces:
        if isinstance(f, DB.PlanarFace):
            n, o = f.FaceNormal, f.Origin
            sides = [(p[0] / _MM - o.X) * n.X + (p[1] / _MM - o.Y) * n.Y + (p[2] / _MM - o.Z) * n.Z for p in pts]
            if min(sides) < -1e-3 and max(sides) > 1e-3:
                continue
        out.append(f)
    return out


def _inside(DB, solids, point_mm):
    """
    The point lies in the member's own concrete: a bar's anchorage into a column lies in the beam's box but not in
    it, and has no cover to the beam's faces.
    """
    if not solids:
        return True
    p = DB.XYZ(point_mm[0] / _MM, point_mm[1] / _MM, point_mm[2] / _MM)
    for axis in (DB.XYZ.BasisX, DB.XYZ.BasisY, DB.XYZ.BasisZ):
        line = DB.Line.CreateBound(p - axis.Multiply(0.5 / _MM), p + axis.Multiply(0.5 / _MM))
        for solid in solids:
            try:
                if solid.IntersectWithCurve(line, DB.SolidCurveIntersectionOptions()).SegmentCount > 0:
                    return True
            except Exception:
                return True
    return False


def _cover_mm(DB, faces, box, point_mm, dia_mm):
    """Clear cover of a bar at a point inside the host's box: nearest face less the radius; None outside the box."""
    p = DB.XYZ(point_mm[0] / _MM, point_mm[1] / _MM, point_mm[2] / _MM)
    tol = 1.0 / _MM
    if not (box.Min.X - tol <= p.X <= box.Max.X + tol and box.Min.Y - tol <= p.Y <= box.Max.Y + tol and
            box.Min.Z - tol <= p.Z <= box.Max.Z + tol):
        return None
    best = None
    for f in faces:
        try:
            r = f.Project(p)
        except Exception:
            r = None
        if r is not None:
            d = r.Distance * _MM
            best = d if best is None else min(best, d)
    return best - dia_mm / 2.0 if best is not None else None


def _nominal_cover_mm(doc, DB, host):
    for bip in ('CLEAR_COVER_OTHER', 'CLEAR_COVER_BOTTOM', 'CLEAR_COVER_TOP'):
        try:
            p = host.get_Parameter(getattr(DB.BuiltInParameter, bip))
            el = doc.GetElement(p.AsElementId()) if p is not None else None
            if el is not None:
                return el.CoverDistance * _MM
        except Exception:
            continue
    return None


def _depth_mm(DB, host, kind, box):
    if kind == u'wall':
        try:
            return host.Width * _MM
        except Exception:
            pass
    if kind in (u'slab', u'foundation'):
        return (box.Max.Z - box.Min.Z) * _MM
    return min(box.Max.X - box.Min.X, box.Max.Y - box.Min.Y) * _MM


def _beam_axis(host):
    try:
        c = host.Location.Curve
        d = c.GetEndPoint(1) - c.GetEndPoint(0)
        return c, d.Normalize()
    except Exception:
        return None, None


def audit(doc, host_ids=None, fck_mpa=32.0, aggregate_mm=AGGREGATE_MM):
    """[Finding] for the rebar of the given hosts (ElementIds) or of the whole model. Read-only."""
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import Rebar
    from nosa_utils.revit_helpers import get_id_value, element_name
    from nosa_utils.revit_helpers import element_id_from_int
    wanted = set(get_id_value(i) for i in host_ids) if host_ids else None
    by_host = {}
    for r in DB.FilteredElementCollector(doc).OfClass(Rebar):
        by_host.setdefault(get_id_value(r.GetHostId()), []).append(r)
    hosts = dict((hid, doc.GetElement(element_id_from_int(hid))) for hid in by_host)
    hosts = dict((hid, h) for hid, h in hosts.items() if h is not None and h.get_BoundingBox(None) is not None)
    checked = set(hosts) if wanted is None else set(hosts) & wanted
    # T8.49: the members meeting the checked ones (a beam's columns, the slab on it) for the joint check
    tol = JOINT_REACH_MM / _MM
    around = set(checked)
    for hid in checked:
        a = hosts[hid].get_BoundingBox(None)
        for other, h in hosts.items():
            if other not in around and _touch(a, h.get_BoundingBox(None), tol):
                around.add(other)
    out, parts = [], {}
    for hid in sorted(around):
        found, samples, label = _audit_host(doc, DB, hosts[hid], by_host[hid], fck_mpa, aggregate_mm, element_name,
                                            get_id_value)
        if hid in checked:
            out.extend(found)
        parts[hid] = (samples, label)
    out.extend(_joint_pairs(hosts, parts, checked, aggregate_mm, get_id_value))
    for hid in sorted(checked):
        out.extend(_buildability_host(doc, DB, hosts[hid], by_host[hid], hosts, by_host, aggregate_mm,
                                      parts[hid][1] if hid in parts else u'', get_id_value))
        out.extend(_rule_added(hosts[hid], by_host[hid], parts[hid][1] if hid in parts else u''))
    return out


def _rule_added(host, rebars, label):
    """T9.15: the bar sets a detailing rule added to a member, to be confirmed with the design (not graded)."""
    from nosa_utils import rule_flags
    rules = {}
    for r in rebars:
        rule = rule_flags.rule_for(_text(r, u'NOSA_Rebar_Layer'))
        if rule:
            rules.setdefault(rule, []).append(_text(r, u'NOSA_Rebar_Mark') or u'?')
    return [Finding(u'', label, u', '.join(sorted(set(marks))), u'Rule-added bars', INFO,
                    u'{}: {}'.format(rule, rule_flags.CONFIRM), host.Id) for rule, marks in sorted(rules.items())]


STATIONS = (0.1, 0.5, 0.9)      # where a beam is checked for congestion, along its span
MAX_SECTION_BARS = 80


def _crossing(doc, DB, rebars, origin, normal, axes):
    """
    The bars crossing the plane through origin (mm) square to normal: [(coordinates along axes, dia)] mm, and the
    bend points (x, y, z) mm of bars lying within 100 mm of the plane (link corners, cross-tie hooks).
    """
    bars, bends = [], []
    for rebar in rebars:
        try:
            dia = doc.GetElement(rebar.GetTypeId()).BarModelDiameter * _MM
            n = rebar.NumberOfBarPositions
        except Exception:
            continue
        for i in range(min(n, MAX_SECTION_BARS)):
            for a, b, bend in _chain(DB, rebar, i):
                da, db = _dot(_sub(a, origin), normal), _dot(_sub(b, origin), normal)
                if bend:
                    if abs(da) < 100.0:
                        bends.append(a)
                    continue
                if da * db < 0.0:
                    t = da / (da - db)
                    q = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
                    bars.append(tuple(_dot(_sub(q, origin), ax) for ax in axes) + (dia,))
    return bars, bends


def _stations(DB, host, kind):
    """[(origin mm, normal, across, mid height above origin mm, label)] of the sections a member is checked at."""
    box = host.get_BoundingBox(None)
    if box is None:
        return []
    if kind == u'beam':
        curve, axis = _beam_axis(host)
        if curve is None or not isinstance(curve, DB.Line):
            return []
        n = math.sqrt(axis.X ** 2 + axis.Y ** 2) or 1.0
        u = (axis.X / n, axis.Y / n, 0.0)
        across = (-u[1], u[0], 0.0)
        out = []
        for f in STATIONS:
            p = _xyz(curve.Evaluate(f, True))
            out.append(((p[0], p[1], box.Min.Z * _MM), u, across, (box.Max.Z - box.Min.Z) * _MM / 2.0,
                        u'{:.0f}% of the span'.format(100.0 * f)))
        return out
    if kind == u'column':
        c = ((box.Min.X + box.Max.X) / 2.0 * _MM, (box.Min.Y + box.Max.Y) / 2.0 * _MM,
             (box.Min.Z + box.Max.Z) / 2.0 * _MM)
        return [(c, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.0, u'mid height')]
    return []


def congested_stations(doc, host, aggregate_mm=AGGREGATE_MM):
    """
    T9.8: [((x, y, z) ft, [issue])] of the stations of a beam (0.1, 0.5, 0.9 of its span) or a column (mid height)
    where its own bars congest the section: where a 1:10 section is drawn.
    """
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import RebarHostData
    try:
        rebars = list(RebarHostData.GetRebarHostData(host).GetRebarsInHost())
    except Exception:
        return []
    out = []
    for origin, normal, across, mid, _label in _stations(DB, host, _kind(DB, host)):
        if normal == (0.0, 0.0, 1.0):
            continue                       # a column's plan section is checked for restraint, not layers
        bars, _bends = _crossing(doc, DB, rebars, origin, normal, (across, (0.0, 0.0, 1.0)))
        issues = [t for _sev, t in congestion_issues(bars, mid, aggregate_mm)]
        if issues:
            out.append((tuple(c / _MM for c in origin), issues))
    return out


def _buildability_host(doc, DB, host, rebars, hosts, by_host, aggregate_mm, label, get_id_value):
    """T9.8-T9.10 findings of one member: congested sections, column bars no link holds, joint poker gaps."""
    out = []
    kind = _kind(DB, host)
    for origin, normal, across, mid, where in _stations(DB, host, kind):
        if kind == u'column':
            other = (-across[1], across[0], 0.0)
            bars, bends = _crossing(doc, DB, rebars, origin, normal, (across, other))
            restraints = [(_dot(_sub(p, origin), across), _dot(_sub(p, origin), other)) for p in bends]
            main = [b for b in bars if b[2] >= 12.0]
            loose = unrestrained_bars(main, restraints) if restraints and main else []
            if loose:
                out.append(Finding(u'', label, u'', u'Bar restraint', WARNING,
                                   u'{} main bar(s) neither in a link corner nor within 150 mm of one that is: add '
                                   u'a link or cross-tie (EC2 9.5.3(6), SMDSC 4th ed. 4.2.2)'.format(len(loose)),
                                   host.Id))
            continue
        bars, _bends = _crossing(doc, DB, rebars, origin, normal, (across, (0.0, 0.0, 1.0)))
        for _sev, text in congestion_issues(bars, mid, aggregate_mm):
            out.append(Finding(u'', label, u'', u'Congestion', WARNING, u'{} at {}'.format(text, where), host.Id))
    if kind == u'beam':
        out.extend(_joint_vibrator(doc, DB, host, rebars, hosts, by_host, label, get_id_value))
    return out


def _joint_vibrator(doc, DB, beam, rebars, hosts, by_host, label, get_id_value):
    """T9.9: each end of a beam over a column: its top bars and the column bars through the joint, across it."""
    out = []
    curve, axis = _beam_axis(beam)
    box = beam.get_BoundingBox(None)
    if curve is None or box is None or not isinstance(curve, DB.Line):
        return out
    n = math.sqrt(axis.X ** 2 + axis.Y ** 2) or 1.0
    u = (axis.X / n, axis.Y / n, 0.0)
    across = (-u[1], u[0], 0.0)
    up = (0.0, 0.0, 1.0)
    width = _depth_mm(DB, beam, u'beam', box)
    for end in (0, 1):
        p = _xyz(curve.GetEndPoint(end))
        for hid, col in hosts.items():
            if _kind(DB, col) != u'column':
                continue
            cb = col.get_BoundingBox(None)
            if not (cb.Min.X * _MM - 1.0 <= p[0] <= cb.Max.X * _MM + 1.0 and
                    cb.Min.Y * _MM - 1.0 <= p[1] <= cb.Max.Y * _MM + 1.0):
                continue
            # the poker goes in from the top: the beam's top layer over the column and the column bars through it
            inner = (p[0] + u[0] * (100.0 if end == 0 else -100.0), p[1] + u[1] * (100.0 if end == 0 else -100.0),
                     box.Max.Z * _MM - 60.0)
            beam_bars = [b for b in _crossing(doc, DB, rebars, inner, u, (across, up))[0] if b[1] > -80.0]
            col_bars = [b for b in _crossing(doc, DB, by_host.get(hid, []), inner, up, (across, u))[0]
                        if abs(b[0]) <= width / 2.0]
            bars = beam_bars + col_bars
            if len(bars) < 3:
                continue
            issue = joint_vibrator_issue(width, [b[0] for b in bars], [b[2] for b in bars])
            if issue:
                out.append(Finding(u'', label, u'', u'Vibrator gap', WARNING, u'{} (column {})'.format(
                    issue, get_id_value(col.Id)), beam.Id))
    return out


JOINT_REACH_MM = 50.0


def _touch(a, b, tol):
    """Two bounding boxes within tol (ft) of each other."""
    return (a.Min.X - tol <= b.Max.X and b.Min.X - tol <= a.Max.X and a.Min.Y - tol <= b.Max.Y and
            b.Min.Y - tol <= a.Max.Y and a.Min.Z - tol <= b.Max.Z and b.Min.Z - tol <= a.Max.Z)


JOINT_ADVICE = (u'keep the column bars where they are and either crank the beam bar inwards just before the '
                u'joint, take it to a second layer (check the reduced d) or use more, smaller bars (e.g. 4H25 for '
                u'2H32)')


def joint_advice(issue):
    """
    A joint clash with the way to resolve it (user decision 2026-10-11, SMDSC): never moved by the program, since
    an automatic shift cuts the lever arm d and the cover; the column's bars rule and the beam's bars give way.
    """
    if not issue or not issue.startswith(u'clash') or JOINT_ADVICE in issue:
        return issue
    return u'{} - {}'.format(issue, JOINT_ADVICE)


def _joint_pairs(hosts, parts, checked, aggregate_mm, get_id_value):
    """Bars of two members that meet (beam and column, slab and beam) clashing or crowding each other."""
    out = []
    ids = sorted(parts)
    tol = JOINT_REACH_MM / _MM
    for i, a in enumerate(ids):
        ba = hosts[a].get_BoundingBox(None)
        for b in ids[i + 1:]:
            if a not in checked and b not in checked:
                continue
            if not _touch(ba, hosts[b].get_BoundingBox(None), tol):
                continue
            owner = dict((get_id_value(r.Id), a) for r, _d, _c, _m in parts[a][0])
            owner.update((get_id_value(r.Id), b) for r, _d, _c, _m in parts[b][0])
            found = _pairs(parts[a][0] + parts[b][0], u'{} / {}'.format(parts[a][1], parts[b][1]), aggregate_mm,
                           get_id_value, owner)
            for f in found:
                f.Check = u'Joint ' + f.Check.lower()
                f.Issue = joint_advice(f.Issue)
            out.extend(found)
    return out


def _audit_host(doc, DB, host, rebars, fck_mpa, aggregate_mm, element_name, get_id_value):
    """([Finding], the bar samples for the clash checks, the host's label)."""
    out = []
    kind = _kind(DB, host)
    box = host.get_BoundingBox(None)
    if box is None:
        return out, [], u''
    try:
        label = u'{} {}'.format(element_name(doc.GetElement(host.GetTypeId())), get_id_value(host.Id))
    except Exception:
        label = u'{}'.format(get_id_value(host.Id))
    faces = _solid_faces(DB, host)
    solids = _solids(DB, host)
    nominal = _nominal_cover_mm(doc, DB, host)
    depth = _depth_mm(DB, host, kind, box)
    samples = []                      # (rebar, dia, segments, mark)
    layer_area = {}                   # slab / wall / base: area per m of each set in the plane
    vertical_area = 0.0
    axis_curve, axis = _beam_axis(host) if kind == u'beam' else (None, None)
    top_layer = []                    # beam: (position across, dia) of the top bars at mid span

    done = set()

    def add(rebar, mark, check, severity, issue):
        key = (get_id_value(rebar.Id), check)
        if key not in done:
            done.add(key)
            out.append(Finding(_text(rebar, u'NOSA_Rebar_Group'), label, mark, check, severity, issue, rebar.Id))

    for rebar in rebars:
        try:
            dia = doc.GetElement(rebar.GetTypeId()).BarModelDiameter * _MM
            n = rebar.NumberOfBarPositions
        except Exception:
            continue
        mark = _text(rebar, u'NOSA_Rebar_Mark') or _text(rebar, u'Schedule Mark')
        first = _chain(DB, rebar, 0)
        if not first:
            continue
        lengths = [sum(math.sqrt(_dot(_sub(b, a), _sub(b, a))) for a, b, _bend in _chain(DB, rebar, i))
                   for i in sorted(set((0, n - 1)))]
        if max(lengths) > STOCK_MM + 1.0:
            add(rebar, mark, u'Stock length', WARNING, u'bar {:.0f} mm over the {:.0f} mm stock length: lap or '
                u'split it (SMDSC 4.2.4)'.format(max(lengths), STOCK_MM))
        main = max(first, key=lambda s: _dot(_sub(s[1], s[0]), _sub(s[1], s[0])))
        mlen = math.sqrt(_dot(_sub(main[1], main[0]), _sub(main[1], main[0])))
        u = tuple(c / mlen for c in _sub(main[1], main[0])) if mlen > 1e-6 else (1.0, 0.0, 0.0)
        spacing = None
        if n > 1:
            second = _chain(DB, rebar, 1)
            if second:
                m0 = tuple((a + b) / 2.0 for a, b in zip(main[0], main[1]))
                main1 = max(second, key=lambda s: _dot(_sub(s[1], s[0]), _sub(s[1], s[0])))
                m1 = tuple((a + b) / 2.0 for a, b in zip(main1[0], main1[1]))
                off = _sub(m1, m0)
                along = _dot(off, u)
                spacing = math.sqrt(max(0.0, _dot(off, off) - along * along))
        if spacing:
            issue = spacing_issue(spacing, dia, aggregate_mm)
            if issue:
                add(rebar, mark, u'Clear spacing', WARNING, issue)
            most = max_pitch_mm(kind, depth)
            flat = abs(u[2]) < 0.3 if kind in (u'slab', u'foundation') else True
            if most and flat and spacing > most + 1.0:
                add(rebar, mark, u'Pitch', WARNING, u'pitch {:.0f} mm over the {:.0f} allowed (SMDSC 6.{})'.format(
                    spacing, most, {u'slab': 2, u'wall': 5, u'foundation': 7}[kind]))
            if kind in (u'slab', u'foundation') and flat or kind == u'wall' and abs(u[2]) > 0.7:
                key = (_text(rebar, u'NOSA_Rebar_Layer'), round(u[0], 1), round(u[1], 1), round(u[2], 1))
                layer_area[key] = max(layer_area.get(key, 0.0), area_per_m(dia, spacing))
        if kind == u'column' and abs(u[2]) > 0.9:
            vertical_area += n * math.pi * dia ** 2 / 4.0
        for i in sorted(set((0, n // 2, n - 1))):
            chain = first if i == 0 else _chain(DB, rebar, i)
            pts = [s[0] for s in chain] + [chain[-1][1]] + [tuple((a + b) / 2.0 for a, b in zip(s[0], s[1]))
                                                             for s in chain]
            closed = math.sqrt(_dot(_sub(chain[0][0], chain[-1][1]), _sub(chain[0][0], chain[-1][1]))) < 60.0
            if kind == u'column' and abs(u[2]) > 0.9 or kind == u'beam' and not closed:
                # a column bar's ends run on into the base or the lift above (starters, laps), a beam's main bars
                # into the columns they anchor in: not a cover to the member's own faces
                k = len(chain)
                pts = pts[1:k] + pts[k + 1:]          # inner vertices and midpoints, not the two ends
            own = _faces_not_crossed(DB, faces, chain)
            covers = [c for c in (_cover_mm(DB, own, box, p, dia) for p in pts if _inside(DB, solids, p))
                      if c is not None]
            if covers:
                for severity, issue in cover_issues(min(covers), dia, nominal, aggregate_mm):
                    add(rebar, mark, u'Cover', severity, issue)
                    break
        idx = range(n) if n <= 12 else sorted(set((0, 1, n // 2, n - 2, n - 1)))
        for i in idx:
            samples.append((rebar, dia, first if i == 0 else _chain(DB, rebar, i), mark))
        if axis is not None and abs(_dot(u, (axis.X, axis.Y, axis.Z))) > 0.99:
            # a longitudinal bar in the top quarter of the beam, crossing its mid span
            mid_mm = _xyz(axis_curve.Evaluate(0.5, True))
            top_band = 0.25 * (box.Max.Z - box.Min.Z) * _MM
            across = (-axis.Y, axis.X, 0.0)
            for i in range(n):
                for a, b, _bend in (first if i == 0 else _chain(DB, rebar, i)):
                    lo, hi = sorted((_dot(_sub(a, mid_mm), u), _dot(_sub(b, mid_mm), u)))
                    if lo <= 0.0 <= hi:
                        if box.Max.Z * _MM - (a[2] + b[2]) / 2.0 < top_band:
                            top_layer.append((_dot(_sub(a, mid_mm), across), dia))
                        break
    if layer_area and depth > 0.0 and kind == u'wall':
        ratio = sum(layer_area.values()) / (1000.0 * depth)        # vertical bars, both faces
        issue = ratio_issue(kind, ratio, fck_mpa)
        if issue:
            out.append(Finding(u'', label, u'', u'Steel ratio', WARNING, issue, host.Id))
    elif layer_area and depth > 0.0:
        d = max(depth - (nominal or 30.0), 1.0)
        for (layer, _x, _y, _z), area in sorted(layer_area.items()):
            issue = ratio_issue(kind, area / (1000.0 * d), fck_mpa)
            if issue:
                out.append(Finding(u'', label, layer, u'Steel ratio', WARNING, issue, host.Id))
    if kind == u'column' and vertical_area:
        ac = (box.Max.X - box.Min.X) * (box.Max.Y - box.Min.Y) * _MM * _MM
        issue = ratio_issue(kind, vertical_area / ac, fck_mpa)
        if issue:
            out.append(Finding(u'', label, u'', u'Steel ratio', WARNING, issue, host.Id))
    if kind == u'beam' and len(top_layer) > 2:
        issue = vibrator_issue(depth, gaps_clear([p for p, _d in top_layer], [d for _p, d in top_layer]))
        if issue:
            out.append(Finding(u'', label, u'', u'Vibrator gap', WARNING, issue, host.Id))
    out.extend(_pairs(samples, label, aggregate_mm, get_id_value))
    return out, samples, label


def _pairs(samples, label, aggregate_mm, get_id_value, owner=None):
    """
    Clashes and crowding between bars of different sets, one finding per pair of sets; owner {rebar id: host}:
    only pairs of bars of different members (a joint).
    """
    segs = []
    for rebar, dia, chain, mark in samples:
        for a, b, bend in chain:
            lo = tuple(min(a[k], b[k]) - dia for k in range(3))
            hi = tuple(max(a[k], b[k]) + dia for k in range(3))
            segs.append((get_id_value(rebar.Id), rebar, dia, a, b, lo, hi, mark, bend))
    if len(segs) > MAX_SEGMENTS:
        return [Finding(u'', label, u'', u'Clashes', WARNING, u'{} bar segments: too many to check clashes '
                        u'here, check this host on its own'.format(len(segs)))]
    out, seen = [], set()
    reach = 3.0 * min_clear_mm(40.0, aggregate_mm)
    for i in range(len(segs)):
        si = segs[i]
        for j in range(i + 1, len(segs)):
            sj = segs[j]
            if si[0] == sj[0] or owner is not None and owner.get(si[0]) == owner.get(sj[0]):
                continue
            pair = (min(si[0], sj[0]), max(si[0], sj[0]))
            if pair in seen:
                continue
            if any(si[5][k] - reach > sj[6][k] or sj[5][k] - reach > si[6][k] for k in range(3)):
                continue
            dist, cos, overlap, at = segment_distance(si[3], si[4], sj[3], sj[4])
            if is_lap(dist, cos, overlap, _length(si[3], si[4]), _length(sj[3], sj[4]), si[2], sj[2]):
                continue                  # two bars lapped: modelled on one line, in contact on site
            found = pair_issue(dist, cos, overlap, si[2], sj[2], aggregate_mm, si[8] or sj[8])
            if found:
                seen.add(pair)
                severity, issue = found
                issue += u' at ({:.0f}, {:.0f}, {:.0f})'.format(*at)
                out.append(Finding(u'', label, u'{} / {}'.format(si[7], sj[7]), u'Clash' if severity == ERROR
                                   else u'Congestion', severity, issue, si[1].Id))
    return out
