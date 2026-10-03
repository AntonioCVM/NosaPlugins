# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — modification tools on bars already in the model (T7.7): split straight bars
to the commercial stock length with staggered laps, delete the bars of a host, show bars as solids.
"""
import os

from Autodesk.Revit import DB

_HERE = os.path.dirname(os.path.abspath(__file__))
_MM_PER_FT = 304.8
_engine = None
_wall = None


def _modules():
    global _engine, _wall
    if _engine is None:
        from nosa_utils.bootstrap import load_module
        _engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
        _wall = load_module('wall_rebar', os.path.join(_HERE, 'wall_rebar.py'))
    return _engine, _wall


def bar_diameter_mm(doc, rebar):
    bar_type = doc.GetElement(rebar.GetTypeId())
    for name in ('BarModelDiameter', 'BarNominalDiameter', 'BarDiameter'):
        try:
            return getattr(bar_type, name) * _MM_PER_FT
        except Exception:  # nosa-lint: disable=NOSA006 - next API name for this Revit year
            continue
    p = bar_type.get_Parameter(DB.BuiltInParameter.REBAR_BAR_DIAMETER)
    return p.AsDouble() * _MM_PER_FT if p else None


def straight_set_geometry(rebar):
    """{line, normal, spacing_mm, count} of a shape-driven set of straight bars, or None."""
    from Autodesk.Revit.DB.Structure import MultiplanarOption
    try:
        if not rebar.IsRebarShapeDriven():
            return None
        count = rebar.NumberOfBarPositions
        first = list(rebar.GetTransformedCenterlineCurves(
            False, True, True, MultiplanarOption.IncludeOnlyPlanarCurves, 0))
    except Exception:
        return None
    if len(first) != 1 or not isinstance(first[0], DB.Line):
        return None
    line = first[0]
    if count > 1:
        last = list(rebar.GetTransformedCenterlineCurves(
            False, True, True, MultiplanarOption.IncludeOnlyPlanarCurves, count - 1))[0]
        step = last.GetEndPoint(0) - line.GetEndPoint(0)
        array_ft = step.GetLength()
        if array_ft < 1e-6:
            return None
        return {'line': line, 'normal': step.Normalize(), 'count': count,
                'spacing_mm': array_ft * _MM_PER_FT / (count - 1)}
    return {'line': line, 'normal': rebar.GetShapeDrivenAccessor().Normal, 'count': 1, 'spacing_mm': 0.0}


def split_specs(geometry, stock_length_mm, lap_length_mm):
    """New sets for one straight set: alternate bars staggered as on slabs and walls (T7.6)."""
    engine, wall = _modules()
    count, spacing = geometry['count'], geometry['spacing_mm']
    layouts = wall.parity_layouts(count, spacing) if count > 1 else [(0.0, 1, 0.0)]
    staggered = len(layouts) > 1
    specs = []
    for parity, (offset_mm, n, array_mm) in enumerate(layouts):
        line = geometry['line']
        if offset_mm:
            line = line.CreateTransformed(DB.Transform.CreateTranslation(
                geometry['normal'].Multiply(offset_mm / _MM_PER_FT)))
        first = wall.stagger_first_mm(stock_length_mm, lap_length_mm) if parity else None
        for seg in engine.split_rebar_by_stock_length(line, stock_length_mm, lap_length_mm,
                                                      first_length_mm=first):
            specs.append({'curves': [seg.curve], 'normal': geometry['normal'], 'count': n,
                          'array_length_mm': array_mm,
                          # a hair over the true step, so Revit never lays out one bar too many
                          'spacing_mm': (2.0 * spacing if staggered else spacing) + 0.01})
    return specs


def host_rebars(doc, hosts):
    """Free Rebar elements of the hosts (bars inside an Area/Path system are left alone)."""
    from Autodesk.Revit.DB.Structure import Rebar, RebarHostData
    out = []
    for host in hosts:
        data = RebarHostData.GetRebarHostData(host)
        if data is None:
            continue
        out.extend(r for r in data.GetRebarsInHost() if isinstance(r, Rebar))
    return out


def view_rebars(doc, view):
    from Autodesk.Revit.DB.Structure import Rebar
    return [r for r in DB.FilteredElementCollector(doc, view.Id).OfClass(Rebar)]


def toggle_solids(view, rebars):
    """Solid + unobscured on every bar, or back to normal when they all already are. -> new state.

    Revit 2023+ dropped Rebar.SetSolidInView: bars draw as solids in a 3D view at Fine detail level.
    """
    show = not all(r.IsUnobscuredInView(view) for r in rebars)
    for r in rebars:
        r.SetUnobscuredInView(view, show)
        if hasattr(r, 'SetSolidInView'):
            r.SetSolidInView(view, show)
    if show and view.DetailLevel != DB.ViewDetailLevel.Fine:
        view.DetailLevel = DB.ViewDetailLevel.Fine
    return show
