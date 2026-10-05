# -*- coding: utf-8 -*-
"""Material Manager Replace material: concrete column + RC beam + RC wall, Concrete - Generic -> RC40/50 in
CATEGORY (default all), report the materials before/after; all rolled back. Scope: doc, EXT_ROOT, PYREVIT."""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import StructuralType

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []
_MM = 1.0 / 304.8


def mats(el):
    from nosa_utils.revit_helpers import element_name
    return u', '.join(sorted(set(element_name(doc.GetElement(i)) for i in el.GetMaterialIds(False))))


group = DB.TransactionGroup(doc, u'NOSA test - replace material')
group.Start()
try:
    from nosa_utils.bootstrap import load_module
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Structures.panel', 'Quantities.pulldown', 'MaterialManager.pushbutton', 'lib')
    logic = load_module('probe_mm_logic', os.path.join(lib, 'logic.py'))
    level = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)[1]
    from nosa_utils.revit_helpers import element_name
    syms = dict(((s.FamilyName, element_name(s)), s) for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol))
    t = DB.Transaction(doc, u'elements')
    t.Start()
    col_sym = [s for (f, n), s in syms.items() if f == u'Concrete Rectangular'][0]
    beam_sym = [s for (f, n), s in syms.items() if f == u'RC Beam'][0]
    for s in (col_sym, beam_sym):
        if not s.IsActive:
            s.Activate()
    col = doc.Create.NewFamilyInstance(DB.XYZ(0, 0, 0), col_sym, level, StructuralType.Column)
    z = level.Elevation
    beam = doc.Create.NewFamilyInstance(DB.Line.CreateBound(DB.XYZ(5, 0, z), DB.XYZ(25, 0, z)), beam_sym, level,
                                        StructuralType.Beam)
    wt = [w for w in DB.FilteredElementCollector(doc).OfClass(DB.WallType) if element_name(w) == u'300mm RC Wall'][0]
    wall = DB.Wall.Create(doc, DB.Line.CreateBound(DB.XYZ(0, 20, 0), DB.XYZ(20, 20, 0)), wt.Id, level.Id, 10, 0,
                          False, True)
    t.Commit()
    _log.append(u'before: column {} | beam {} | wall {}'.format(mats(col), mats(beam), mats(wall)))
    names = dict((element_name(m), m.Id) for m in DB.FilteredElementCollector(doc).OfClass(DB.Material))
    try:
        category = CATEGORY
    except NameError:
        category = logic.ALL_STRUCTURAL
    report = logic.replace_material(doc, names[u'Concrete - Generic'], names[u'Concrete - RC40/50'], category)
    _log.append(u'report: {}'.format(report))
    _log.append(u'after: column {} | beam {} | wall {}'.format(mats(col), mats(beam), mats(wall)))
except Exception:
    _log.append(traceback.format_exc())
finally:
    group.RollBack()
    _log.append(u'rolled back')
RESULT = u'\n'.join(_log)
