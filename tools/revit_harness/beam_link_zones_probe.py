# -*- coding: utf-8 -*-
"""
Where each beam's link sets lie along it, once reinforced (2026-10-26: refit_loops took B1-B2's zones back to where
they were first made). Per beam set: bars, pitch, first and last bar from the beam's start (mm), and whether any bar
stands inside a column (a zone across a support). Scope (building_test PROBE): doc, ids, _log.
"""
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import MultiplanarOption, RebarHostData

from nosa_utils.revit_helpers import get_id_value

FT = 304.8


def layer(r):
    p = r.LookupParameter(u'NOSA_Rebar_Layer')
    return p.AsString() if p is not None else u''


columns = [doc.GetElement(i) for i in ids['columns']]
col_boxes = [c.get_BoundingBox(None) for c in columns]
inside_total, sets_total = 0, 0
for bid in ids['beams'][:8]:
    beam = doc.GetElement(bid)
    line = beam.Location.Curve
    a, d = line.GetEndPoint(0), line.Direction.Normalize()
    rows = []
    for r in RebarHostData.GetRebarHostData(beam).GetRebarsInHost():
        if not layer(r).startswith(u'stirrup'):
            continue
        n = r.NumberOfBarPositions
        stations, inside = [], 0
        for i in range(n):
            c = list(r.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i))
            p = c[0].GetEndPoint(0)
            stations.append((p - a).DotProduct(d) * FT)
            q = c[0].Evaluate(0.5, True)
            if any(b.Min.X < q.X < b.Max.X and b.Min.Y < q.Y < b.Max.Y and b.Min.Z < q.Z < b.Max.Z for b in col_boxes):
                inside += 1
        sets_total += 1
        inside_total += 1 if inside else 0
        rows.append(u'{}x {:.0f}..{:.0f}{}'.format(n, min(stations), max(stations),
                                                  u' IN COLUMN x{}'.format(inside) if inside else u''))
    _log.append(u'  beam {} ({:.0f} mm): {}'.format(get_id_value(bid), line.Length * FT, u'; '.join(sorted(rows))))
_log.append(u'== beam link zones: {} sets, {} with bars inside a column'.format(sets_total, inside_total))

# the columns' link sets up their height: from the column's base, every bar inside it
outside = 0
for col in columns[:9]:
    bb = col.get_BoundingBox(None)
    for r in RebarHostData.GetRebarHostData(col).GetRebarsInHost():
        if layer(r) not in (u'stirrup', u'link'):
            continue
        zs = [list(r.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves,
                                                    i))[0].GetEndPoint(0).Z for i in range(r.NumberOfBarPositions)]
        out = sum(1 for z in zs if z < bb.Min.Z or z > bb.Max.Z)
        outside += 1 if out else 0
        _log.append(u'  column {} links {}x {:.0f}..{:.0f} above its base ({:.0f} high){}'.format(
            get_id_value(col.Id), len(zs), (min(zs) - bb.Min.Z) * FT, (max(zs) - bb.Min.Z) * FT,
            (bb.Max.Z - bb.Min.Z) * FT, u' OUTSIDE x{}'.format(out) if out else u''))
_log.append(u'== column link sets outside their column: {}'.format(outside))
