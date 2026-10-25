# -*- coding: utf-8 -*-
"""
Full-depth beams (user 2026-10-25) without cutting the slab: a beam the slab cuts is reinforced with the join
switched, then the join is put back. Do its bars stay where they were made? New unsaved project only, rolled back.
Scope: doc, EXT_ROOT, PYREVIT, OUT. Result: RESULT.
"""
import io
import json
import os
import re

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS
from System.Collections.Generic import List

if doc.PathName or not re.match(u'^Project[0-9]+$', doc.Title):
    raise RuntimeError(u'not the unsaved test project: ' + doc.Title)

_MM = 304.8


def f(mm):
    return mm / _MM


def name_of(e):
    return DB.Element.Name.GetValue(e)


def symbol(category, family, name):
    for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(category):
        if s.FamilyName == family and name_of(s) == name:
            if not s.IsActive:
                s.Activate()
            return s


def extents(beam):
    out = []
    hd = DBS.RebarHostData.GetRebarHostData(beam)
    for r in hd.GetRebarsInHost():
        bb = r.get_BoundingBox(None)
        layer = r.LookupParameter(u'NOSA_Rebar_Layer')
        out.append((layer.AsString() if layer else u'', round(bb.Min.Z * _MM, 1), round(bb.Max.Z * _MM, 1),
                    round(bb.Min.X * _MM, 1), round(bb.Max.X * _MM, 1)))
    return sorted(out)


_log = []
group = DB.TransactionGroup(doc, u'NOSA join restore probe')
group.Start()
try:
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    ground, first = levels[0], levels[1]
    sq = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Square', u'450x450mm')  # nosa-lint: disable=NOSA002 - harness script, runs inside Revit
    bt = symbol(DB.BuiltInCategory.OST_StructuralFraming, u'RC Beam', u'300x600mm')  # nosa-lint: disable=NOSA002 - harness script, runs inside Revit
    ftype = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.FloorType) if name_of(x).startswith(u'300mm RC')][0]
    X0 = 500000.0
    z = first.Elevation * _MM
    t = DB.Transaction(doc, u'probe model')
    t.Start()
    for x in (0.0, 6000.0):
        c = doc.Create.NewFamilyInstance(DB.XYZ(f(X0 + x), 0, ground.Elevation), sq, ground, DBS.StructuralType.Column)
        c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(first.Id)  # nosa-lint: disable=NOSA002 - harness script, runs inside Revit
    beam = doc.Create.NewFamilyInstance(DB.Line.CreateBound(DB.XYZ(f(X0), 0, f(z)), DB.XYZ(f(X0 + 6000), 0, f(z))), bt,
                                        first, DBS.StructuralType.Beam)
    cl = DB.CurveLoop()
    pts = [(-225, -3000), (6225, -3000), (6225, 3000), (-225, 3000)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        cl.Append(DB.Line.CreateBound(DB.XYZ(f(X0 + ax), f(ay), f(z)), DB.XYZ(f(X0 + bx), f(by), f(z))))
    floor = DB.Floor.Create(doc, List[DB.CurveLoop]([cl]), ftype.Id, first.Id)
    floor.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).Set(1)  # nosa-lint: disable=NOSA002 - harness script, runs inside Revit
    t.Commit()
    joined = DB.JoinGeometryUtils.AreElementsJoined(doc, floor, beam)
    _log.append(u'joined {} floor cuts beam {}'.format(
        joined, joined and DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, floor, beam)))
    bid = beam.Id.Value if hasattr(beam.Id, 'Value') else beam.Id.IntegerValue
    scope = {'doc': doc, 'MODE': 'beams', 'IDS': [bid], 'CONTROLS': u'{}', 'OVERRIDES': u'{}', 'EXT_ROOT': EXT_ROOT,
             'PYREVIT': PYREVIT, 'ROLLBACK': True, 'ASSIMILATE': True, '__name__': '__nosa_case__'}
    execfile(os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_harness.py'), scope)
    _log.append(u'beam cut by floor after the run: {}'.format(DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, floor, beam)))
    made = extents(beam)
    _log.append(u'made: ' + json.dumps(made))
    t = DB.Transaction(doc, u'probe restore join')
    t.Start()
    if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, floor, beam):
        DB.JoinGeometryUtils.SwitchJoinOrder(doc, floor, beam)
    t.Commit()
    after = extents(beam)
    _log.append(u'after restoring the join: ' + json.dumps(after))
    _log.append(u'SAME' if made == after else u'MOVED')
    _log.append(scope.get('RESULT', u'')[:1500])
except Exception:
    import traceback
    _log.append(traceback.format_exc())
finally:
    group.RollBack()
RESULT = u'\n'.join(_log)
with io.open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(RESULT)
