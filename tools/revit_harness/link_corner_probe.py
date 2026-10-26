# -*- coding: utf-8 -*-
"""
The QA's column clashes between a vertical bar and a link (01 / 02, 'centrelines n mm apart'), measured exactly: the
link's own curves (lines and true arcs, centre and radius, not the QA's sampled points) against each vertical bar's
axis in plan, giving the real surface-to-surface gap (bar radius x 1.1 for the ribs, as rebar_qa.REAL_DIA). A
QA clash whose exact gap is >= 0 is a demonstrated false positive; one under 0 is a real interference. Scope
(building_test PROBE): doc, ids, _log, _mem. Columns of the first storey only.
"""
import math

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import MultiplanarOption, RebarHostData

from nosa_utils import rebar_qa as qa
from nosa_utils.revit_helpers import get_id_value

FT = 304.8


def layer(r):
    p = r.LookupParameter(u'NOSA_Rebar_Layer')
    return p.AsString() if p is not None else u''


def dia(r):
    return doc.GetElement(r.GetTypeId()).BarModelDiameter * FT


def plan_distance(curve, x, y):
    """Shortest plan distance (mm) from point (x, y) mm to a link curve (its z ignored), exact for lines and arcs."""
    if isinstance(curve, DB.Arc):
        c = curve.Center
        cx, cy, r = c.X * FT, c.Y * FT, curve.Radius * FT
        d = math.hypot(x - cx, y - cy)
        # the nearest point of the full circle lies on the arc when its direction is within the arc's sweep
        p = DB.XYZ((cx + (x - cx) * r / d) / FT, (cy + (y - cy) * r / d) / FT, c.Z) if d > 1e-9 else None
        if p is not None:
            res = curve.Project(p)
            if res is not None and res.Distance * FT < 0.5:
                return abs(d - r), u'arc r={:.1f}'.format(r)
        ends = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
        return min(math.hypot(x - e.X * FT, y - e.Y * FT) for e in ends), u'arc end'
    a, b = curve.GetEndPoint(0), curve.GetEndPoint(1)
    ax, ay, bx, by = a.X * FT, a.Y * FT, b.X * FT, b.Y * FT
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
    return math.hypot(x - ax - t * dx, y - ay - t * dy), u'line'


base_z = min(doc.GetElement(i).get_BoundingBox(None).Min.Z for i in ids['columns'])
first = [doc.GetElement(i) for i in ids['columns'] if abs(doc.GetElement(i).get_BoundingBox(None).Min.Z - base_z) < 0.1]
found = qa.audit(doc, [c.Id for c in first])
qa_pairs = [f for f in found if f.Check == u'Clash']
_log.append(u'== link corner probe: {} first-storey columns, {} QA clashes inside them'.format(len(first), len(qa_pairs)))
rows = []
for col in first:
    rebars = list(RebarHostData.GetRebarsInHost(RebarHostData.GetRebarHostData(col))) if False else \
        list(RebarHostData.GetRebarHostData(col).GetRebarsInHost())
    verticals = [r for r in rebars if layer(r) == u'vertical']
    links = [r for r in rebars if layer(r) in (u'stirrup', u'link')]
    if not links or not verticals:
        continue
    link = links[0]
    lcurves = list(link.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0))
    dl = dia(link)
    for v in verticals:
        dv = dia(v)
        for i in range(v.NumberOfBarPositions):
            curves = v.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i)
            upright = [c for c in curves if isinstance(c, DB.Line) and abs(c.Direction.Z) > 0.99]
            if not upright:
                continue
            c0 = max(upright, key=lambda c: c.Length)          # the bar's vertical run, not an L-bar's leg
            x, y = c0.GetEndPoint(0).X * FT, c0.GetEndPoint(0).Y * FT
            best = min((plan_distance(c, x, y) for c in lcurves), key=lambda t: t[0])
            gap = best[0] - qa.REAL_DIA * (dv + dl) / 2.0
            rows.append((get_id_value(col.Id), get_id_value(v.Id), i, round(x, 1), round(y, 1), round(best[0], 1),
                         best[1], round(gap, 1)))
arcs = [c for c in lcurves if isinstance(c, DB.Arc)]
_log.append(u'  link of the last column: {} curves, {} arcs, radius {}'.format(
    len(lcurves), len(arcs), sorted(set(round(a.Radius * FT, 1) for a in arcs))))
neg = [r for r in rows if r[7] < -0.05]
_log.append(u'  vertical bar positions checked {}, exact gap < 0 (real overlap) {}, min gap {} mm'.format(
    len(rows), len(neg), min(r[7] for r in rows) if rows else None))
for r in sorted(rows, key=lambda r: r[7])[:12]:
    _log.append(u'    column {} bar {}#{} at ({}, {}): centreline to link {} mm ({}), surface gap {} mm'.format(*r))
for f in qa_pairs[:6]:
    _log.append(u'    QA: {} | {} | {}'.format(f.Host, f.Mark, f.Issue[:110]))


# the first column's link and corner bar, in full, to check the arithmetic by hand
col = first[0]
rebars = list(RebarHostData.GetRebarHostData(col).GetRebarsInHost())
lk = [r for r in rebars if layer(r) in (u'stirrup', u'link')][0]
bb = col.get_BoundingBox(None)
_log.append(u'  column {} box x {:.1f}..{:.1f} y {:.1f}..{:.1f}; link {} dia {:.0f}, shape {}'.format(
    get_id_value(col.Id), bb.Min.X * FT, bb.Max.X * FT, bb.Min.Y * FT, bb.Max.Y * FT, get_id_value(lk.Id), dia(lk),
    lk.LookupParameter(u'NOSA_Rebar_Shape_Code').AsString() if lk.LookupParameter(u'NOSA_Rebar_Shape_Code') else u''))
for c in lk.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0):
    if isinstance(c, DB.Arc):
        _log.append(u'    arc centre ({:.1f}, {:.1f}) r {:.1f} from ({:.1f}, {:.1f}) to ({:.1f}, {:.1f})'.format(
            c.Center.X * FT, c.Center.Y * FT, c.Radius * FT, c.GetEndPoint(0).X * FT, c.GetEndPoint(0).Y * FT,
            c.GetEndPoint(1).X * FT, c.GetEndPoint(1).Y * FT))
    else:
        _log.append(u'    line ({:.1f}, {:.1f}) to ({:.1f}, {:.1f})'.format(
            c.GetEndPoint(0).X * FT, c.GetEndPoint(0).Y * FT, c.GetEndPoint(1).X * FT, c.GetEndPoint(1).Y * FT))


# every first-storey column's link extents against its own centre (did the fit reach all of them?)
for col in first:
    rebars = list(RebarHostData.GetRebarHostData(col).GetRebarsInHost())
    for lk in [r for r in rebars if layer(r) in (u'stirrup', u'link')]:
        bb = col.get_BoundingBox(None)
        cx, cy = (bb.Min.X + bb.Max.X) / 2.0 * FT, (bb.Min.Y + bb.Max.Y) / 2.0 * FT
        pts = [p for c in lk.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, 0)
               if isinstance(c, DB.Line) for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
        xs, ys = [p.X * FT - cx for p in pts], [p.Y * FT - cy for p in pts]
        acc = lk.GetShapeDrivenAccessor()
        _log.append(u'    column {} link {} n{} normal ({:.0f},{:.0f},{:.0f}) x {:.1f}..{:.1f} y {:.1f}..{:.1f}'.format(
            get_id_value(col.Id), get_id_value(lk.Id), lk.NumberOfBarPositions, acc.Normal.X, acc.Normal.Y,
            acc.Normal.Z, min(xs), max(xs), min(ys), max(ys)))
