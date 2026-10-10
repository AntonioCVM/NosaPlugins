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

ERROR, WARNING = u'Error', u'Warning'


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
    """[(severity, text)]: the cover to a bar under its size or the aggregate, or under the nominal less the deviation."""
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


def gaps_clear(positions_mm, dias_mm):
    """Clear gaps (real size) between neighbouring bars of one layer, positions across the member."""
    pairs = sorted(zip(positions_mm, dias_mm))
    return [b[0] - a[0] - REAL_DIA * (a[1] + b[1]) / 2.0 for a, b in zip(pairs, pairs[1:])]


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
            pts = [_xyz(p) for p in c.Tessellate()]
            segments.extend((a, b, True) for a, b in zip(pts, pts[1:]))
    return segments


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
    wanted = set(get_id_value(i) for i in host_ids) if host_ids else None
    by_host = {}
    for r in DB.FilteredElementCollector(doc).OfClass(Rebar):
        hid = get_id_value(r.GetHostId())
        if wanted is None or hid in wanted:
            by_host.setdefault(hid, []).append(r)
    out = []
    for hid, rebars in sorted(by_host.items()):
        from nosa_utils.revit_helpers import element_id_from_int
        host = doc.GetElement(element_id_from_int(hid))
        if host is None:
            continue
        out.extend(_audit_host(doc, DB, host, rebars, fck_mpa, aggregate_mm, element_name, get_id_value))
    return out


def _audit_host(doc, DB, host, rebars, fck_mpa, aggregate_mm, element_name, get_id_value):
    out = []
    kind = _kind(DB, host)
    box = host.get_BoundingBox(None)
    if box is None:
        return out
    try:
        label = u'{} {}'.format(element_name(doc.GetElement(host.GetTypeId())), get_id_value(host.Id))
    except Exception:
        label = u'{}'.format(get_id_value(host.Id))
    faces = _solid_faces(DB, host)
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
            covers = [c for c in (_cover_mm(DB, faces, box, p, dia) for p in pts) if c is not None]
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
    return out


def _pairs(samples, label, aggregate_mm, get_id_value):
    """Clashes and crowding between bars of different sets of one host, one finding per pair of sets."""
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
            if si[0] == sj[0]:
                continue
            pair = (min(si[0], sj[0]), max(si[0], sj[0]))
            if pair in seen:
                continue
            if any(si[5][k] - reach > sj[6][k] or sj[5][k] - reach > si[6][k] for k in range(3)):
                continue
            dist, cos, overlap, at = segment_distance(si[3], si[4], sj[3], sj[4])
            found = pair_issue(dist, cos, overlap, si[2], sj[2], aggregate_mm, si[8] or sj[8])
            if found:
                seen.add(pair)
                severity, issue = found
                issue += u' at ({:.0f}, {:.0f}, {:.0f})'.format(*at)
                out.append(Finding(u'', label, u'{} / {}'.format(si[7], sj[7]), u'Clash' if severity == ERROR
                                   else u'Congestion', severity, issue, si[1].Id))
    return out
