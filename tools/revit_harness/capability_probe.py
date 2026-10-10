# -*- coding: utf-8 -*-
"""
T8.55: what this Revit version's API gives the reinforcement tools - API flags by reflection and live probes in
transactions rolled back (test models only) - merged into the matrix at OUT (data/revit_capabilities.json).
Scope: doc, EXT_ROOT, OUT. Result: RESULT.
"""
import sys
import os
import io
import json
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

if os.path.join(EXT_ROOT, 'lib') not in sys.path:
    sys.path.insert(0, os.path.join(EXT_ROOT, 'lib'))
sys.modules.pop('nosa_utils.revit_capabilities', None)
from nosa_utils import revit_capabilities as rc

if doc.PathName or not (doc.Title == u'Project1' or u'template' in doc.Title):
    raise RuntimeError(u'not a test model: ' + doc.Title)
version = doc.Application.VersionNumber
flags = rc.api_flags(DB, DBS)
live = {}
_log = [u'Revit {}'.format(version)]


def probe(name, fn):
    t = DB.Transaction(doc, u'NOSA probe ' + name)
    t.Start()
    try:
        note = fn()
        live[name] = (u'ok', note or u'')
    except Exception as e:
        live[name] = (u'fail', u'{}'.format(e)[:200])
    finally:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()


def _a_set_in_a_view():
    for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        if view.IsTemplate:
            continue
        for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar):
            if r.NumberOfBarPositions > 2:
                return view, r
    return None, None


def p_select():
    view, r = _a_set_in_a_view()
    if r is None:
        raise RuntimeError(u'no rebar set in a plan view')
    r.SetPresentationMode(view, DBS.RebarPresentationMode.Select)
    for i in range(r.NumberOfBarPositions):
        r.SetBarHiddenStatus(view, i, i != 1)
    return u'a set in a plan'


def p_mra():
    view, r = _a_set_in_a_view()
    mra_type = DB.FilteredElementCollector(doc).OfClass(DB.MultiReferenceAnnotationType).FirstElement()
    if r is None or mra_type is None:
        raise RuntimeError(u'no set or no MRA type')
    from System.Collections.Generic import List
    opts = DB.MultiReferenceAnnotationOptions(mra_type)
    spread = r.GetShapeDrivenAccessor().Normal           # the set's own distribution direction
    opts.DimensionPlaneNormal = view.ViewDirection
    opts.DimensionLineDirection = spread
    opts.DimensionLineOrigin = view.Origin
    opts.TagHeadPosition = view.Origin
    ids = List[DB.ElementId]()
    ids.Add(r.Id)
    opts.SetElementsToDimension(ids)
    DB.MultiReferenceAnnotation.Create(doc, view.Id, opts)
    return u''


def p_fabric():
    floor = DB.FilteredElementCollector(doc).OfClass(DB.Floor).FirstElement()
    if floor is None:
        raise RuntimeError(u'no floor')
    sheet = DB.FilteredElementCollector(doc).OfClass(DBS.FabricSheetType).FirstElementId()
    if sheet == DB.ElementId.InvalidElementId:
        sheet = DBS.FabricSheetType.CreateDefaultFabricSheetType(doc)
    area_type = DB.FilteredElementCollector(doc).OfClass(DBS.FabricAreaType).FirstElementId()
    area = DBS.FabricArea.Create(doc, floor, DB.XYZ.BasisX, area_type, sheet)
    doc.Regenerate()
    return u'{} sheets'.format(area.GetFabricSheetElementIds().Count)


def p_couplers():
    col = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
        .WhereElementIsNotElementType().FirstElement()
    symbols = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(
        DB.BuiltInCategory.OST_Coupler) if s.FamilyName == u'NOSA Rebar Coupler' and DB.Element.Name.GetValue(s) == u'H20']
    bar_type = [b for b in DB.FilteredElementCollector(doc).OfClass(DBS.RebarBarType)
                if abs(b.BarNominalDiameter * 304.8 - 20.0) < 0.1]
    if col is None or not symbols or not bar_type:
        raise RuntimeError(u'no column, NOSA Rebar Coupler H20 or H20 bar type')
    bar_type = bar_type[0]
    for bip in (DB.BuiltInParameter.COUPLER_MAIN_BAR_SIZE, DB.BuiltInParameter.COUPLER_COUPLED_BAR_SIZE):
        symbols[0].get_Parameter(bip).Set(bar_type.Id)
    if not symbols[0].IsActive:
        symbols[0].Activate()
    box = col.get_BoundingBox(None)
    x, y = (box.Min.X + box.Max.X) / 2.0, (box.Min.Y + box.Max.Y) / 2.0
    z0, z1 = box.Min.Z + 0.3, box.Max.Z - 0.3
    zm = (z0 + z1) / 2.0
    from System.Collections.Generic import List

    def bar(a, b):
        curves = List[DB.Curve]()
        curves.Add(DB.Line.CreateBound(DB.XYZ(x, y, a), DB.XYZ(x, y, b)))
        return DBS.Rebar.CreateFromCurves(doc, DBS.RebarStyle.Standard, bar_type, None, None, col, DB.XYZ.BasisX,
                                          curves, DBS.RebarHookOrientation.Left, DBS.RebarHookOrientation.Left,
                                          True, True)
    r1, r2 = bar(z0, zm), bar(zm, z1)
    result = DBS.RebarCoupler.Create(doc, symbols[0].Id, DBS.RebarReinforcementData.Create(r1.Id, 1),
                                     DBS.RebarReinforcementData.Create(r2.Id, 0))
    coupler = result[0] if isinstance(result, tuple) else result
    if coupler is None:
        raise RuntimeError(u'{}'.format(result[1] if isinstance(result, tuple) else u'no coupler'))
    return u''


def p_varying():
    view, r = _a_set_in_a_view()
    if r is None:
        raise RuntimeError(u'no rebar set')
    r.DistributionType = DBS.DistributionType.VaryingLength
    return u''


for name, fn in ((u'presentation_select', p_select), (u'multi_rebar_annotation', p_mra), (u'fabric', p_fabric),
                 (u'couplers', p_couplers), (u'varying_length', p_varying)):
    if flags.get(name):
        probe(name, fn)

matrix = rc.merge(rc.load_matrix(OUT), version, flags, live)
with io.open(OUT, 'w', encoding='utf-8', newline='') as f:
    f.write(json.dumps(matrix, indent=2, ensure_ascii=False) + u'\n')
for name, _what, _where in rc.CAPABILITIES:
    _log.append(u'{}: api {} live {}'.format(name, flags.get(name), live.get(name)))
RESULT = u'\n'.join(_log)
