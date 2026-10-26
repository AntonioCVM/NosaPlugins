# -*- coding: utf-8 -*-
"""
A/B probe (2026-10-26): rebar_presentation._seen_bars as it was before 1e243b9 (no clipping to the section's depth),
to tell whether that change moved the beam sections' calling-ups onto cut bars. Scope (building_test PROBE): _log.
"""
import rebar_presentation as rp
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS


def _seen_bars_old(view):
    out = []
    doc = view.Document
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar):
        for i in rp.shown_positions(r, view):
            try:
                curves = r.GetTransformedCenterlineCurves(False, False, False,
                                                          DBS.MultiplanarOption.IncludeOnlyPlanarCurves, i)
            except Exception:
                continue
            for c in curves:
                pts = [c.GetEndPoint(0), c.GetEndPoint(1)] if isinstance(c, DB.Line) else list(c.Tessellate())
                for p, q in zip(pts, pts[1:]):
                    a, b = rp._xy(view, p), rp._xy(view, q)
                    if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1.0:
                        out.append((a, b))
    return out


rp._seen_bars = _seen_bars_old
_log.append(u'== seen_bars: old (no depth clip)')
