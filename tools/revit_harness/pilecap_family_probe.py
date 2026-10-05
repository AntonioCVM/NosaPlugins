# -*- coding: utf-8 -*-
"""Create Pilecap mixed model: regular grids -> family types, others -> slab + piles. Reports what was
created and where the piles are; all rolled back. Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT."""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []
_FT = 304.8
group = DB.TransactionGroup(doc, u'NOSA test - pile caps')
group.Start()
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils.revit_helpers import element_name
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Foundations.panel', 'PileTools.pulldown', 'CreatePilecapType.pushbutton', 'lib')
    logic = load_module('probe_createpilecap_logic', os.path.join(lib, 'logic.py'))
    level = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)[0]
    piles = dict((n, i) for i, n in logic.get_pile_types(doc))
    caps = logic.get_cap_types(doc)
    square = piles[u'Pile Square piling : 300x300mm']
    tube = piles[u'Pile-Steel Pipe Circular : 300mm Diameter']
    cases = [(2, 2, square, 900.0, 450.0), (3, 2, square, 900.0, 450.0), (2, 4, tube, 1050.0, 375.0),
             (3, 4, square, 900.0, 450.0)]
    x = 0.0
    for n_h, n_v, pile_id, spc, clr in cases:
        before = set(e.Id.IntegerValue for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType())
        cfg = {'n_h': n_h, 'n_v': n_v, 'spacing_mm': spc, 'clearance_mm': clr, 'cutoff_mm': 75.0,
               'cap_type_id': caps[0][0], 'pile_type_id': pile_id, 'level_id': level.Id}
        created, errors = logic.create_pilecap(doc, cfg, DB.XYZ(x, 0, level.Elevation))
        new = [e for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
               if e.Id.IntegerValue not in before and isinstance(e, (DB.FamilyInstance, DB.Floor, DB.Group))]
        lines = []
        for e in new:
            if isinstance(e, DB.FamilyInstance) and e.SuperComponent is None:
                bb = e.get_BoundingBox(None)
                subs = [doc.GetElement(i) for i in e.GetSubComponentIds()]
                pts = sorted((round((s.Location.Point.X - x) * _FT), round(s.Location.Point.Y * _FT)) for s in subs)
                lines.append(u'{} : {} | {:.0f} x {:.0f} | piles {} {} {}'.format(
                    e.Symbol.FamilyName, element_name(e.Symbol), (bb.Max.X - bb.Min.X) * _FT,
                    (bb.Max.Y - bb.Min.Y) * _FT, len(subs),
                    sorted(set(u'{}:{}'.format(s.Symbol.FamilyName, element_name(s.Symbol)) for s in subs)), pts))
            elif isinstance(e, DB.Group):
                lines.append(u'group {} ({} members)'.format(element_name(e.GroupType), len(list(e.GetMemberIds()))))
        _log.append(u'{} x {} -> created {} errors {} | {}'.format(n_h, n_v, created, errors, u' ; '.join(lines)))
        x += 30.0
except Exception:
    _log.append(traceback.format_exc())
finally:
    group.RollBack()
    _log.append(u'rolled back')
RESULT = u'\n'.join(_log)
