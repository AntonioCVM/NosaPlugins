# -*- coding: utf-8 -*-
"""
Closed links as asked and as Revit made them (2026-10-26: a column link came out 355 x 355 for 360 x 360): wraps
rebar_engine.realign_closed_loop to log, per loop, the plan size of the curves asked, of the bar created and of the
bar after the realignment, before the reinforcement runs. Scope: given by building_test's PRE hook (module objects).
"""
import io
import time

FT = 304.8


def _box(curves):
    xs = [p.X for c in curves for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
    ys = [p.Y for c in curves for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
    return u'x {:.1f}..{:.1f} y {:.1f}..{:.1f}'.format(min(xs) * FT, max(xs) * FT, min(ys) * FT, max(ys) * FT)


def _size(curves):
    xs = [p.X for c in curves for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
    ys = [p.Y for c in curves for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
    zs = [p.Z for c in curves for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
    return (round((max(xs) - min(xs)) * FT, 1), round((max(ys) - min(ys)) * FT, 1), round((max(zs) - min(zs)) * FT, 1))


def install(rebar_engine, out_path):
    from Autodesk.Revit.DB.Structure import MultiplanarOption
    original = rebar_engine.realign_closed_loop

    def traced(doc, rebar, curves, tol_mm=0.05):
        try:
            doc.Regenerate()
            made = _box(list(rebar.GetTransformedCenterlineCurves(False, False, False,
                                                                  MultiplanarOption.IncludeOnlyPlanarCurves, 0)))
        except Exception as e:
            made = u'({})'.format(e)
        original(doc, rebar, curves, tol_mm)
        try:
            doc.Regenerate()
            after = _box(list(rebar.GetTransformedCenterlineCurves(False, False, False,
                                                                   MultiplanarOption.IncludeOnlyPlanarCurves, 0)))
        except Exception as e:
            after = u'({})'.format(e)
        layer = rebar.LookupParameter(u'NOSA_Rebar_Layer') if rebar is not None else None
        with io.open(out_path, 'a', encoding='utf-8') as fh:
            fh.write(u'{} loop {} asked {} made {} after {}\n'.format(
                time.strftime('%H:%M:%S'), rebar.Id if rebar is not None else None, _box(curves), made, after))
    rebar_engine.realign_closed_loop = traced


def install_fit(rebar_engine, out_path):
    """The same, then the loop fitted to the asked box with ScaleToBox (an experiment: is the box the centreline?)."""
    from Autodesk.Revit import DB
    from Autodesk.Revit.DB.Structure import MultiplanarOption
    original = rebar_engine.realign_closed_loop

    def fitted(doc, rebar, curves, tol_mm=0.05):
        original(doc, rebar, curves, tol_mm)
        if rebar is None or not curves or curves[0].GetEndPoint(0).DistanceTo(curves[-1].GetEndPoint(1)) > 1e-6:
            return
        acc = rebar.GetShapeDrivenAccessor()
        n = acc.Normal.Normalize()
        u = curves[0].Direction.Normalize() if isinstance(curves[0], DB.Line) else None
        if u is None:
            return
        v = n.CrossProduct(u).Normalize()
        pts = [p for c in curves for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
        us, vs = [p.DotProduct(u) for p in pts], [p.DotProduct(v) for p in pts]
        w0 = pts[0].DotProduct(n)
        origin = u.Multiply(min(us)) + v.Multiply(min(vs)) + n.Multiply(w0)
        def placed_extents():
            doc.Regenerate()
            got = [p for c in rebar.GetTransformedCenterlineCurves(False, False, False,
                                                                     MultiplanarOption.IncludeOnlyPlanarCurves, 0)
                   for p in (c.GetEndPoint(0), c.GetEndPoint(1))]
            gu, gv = [p.DotProduct(u) for p in got], [p.DotProduct(v) for p in got]
            return min(gu), max(gu), min(gv), max(gv)
        want = (min(us), max(us), min(vs), max(vs))
        msg = u''
        try:
            bu0, bu1, bv0, bv1 = want
            for k in range(3):
                acc.ScaleToBox(u.Multiply(bu0) + v.Multiply(bv0) + n.Multiply(w0), u.Multiply(bu1 - bu0),
                               v.Multiply(bv1 - bv0))
                g = placed_extents()
                # the box grown or shrunk by what each side missed, then the next try
                bu0, bu1 = bu0 - (g[0] - want[0]), bu1 + (want[1] - g[1])
                bv0, bv1 = bv0 - (g[2] - want[2]), bv1 + (want[3] - g[3])
                msg += u' try{} size {:.1f} x {:.1f} off {:+.1f} {:+.1f} {:+.1f} {:+.1f};'.format(
                    k + 1, (g[1] - g[0]) * FT, (g[3] - g[2]) * FT, (g[0] - want[0]) * FT, (g[1] - want[1]) * FT,
                    (g[2] - want[2]) * FT, (g[3] - want[3]) * FT)
        except Exception as e:
            msg += u' ScaleToBox failed: {}'.format(e)
        with io.open(out_path, 'a', encoding='utf-8') as fh:
            fh.write(u'{} loop {} asked {} {}\n'.format(time.strftime('%H:%M:%S'), rebar.Id, _size(curves), msg))
    rebar_engine.realign_closed_loop = fitted
