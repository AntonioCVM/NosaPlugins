# -*- coding: utf-8 -*-
"""Tag every rebar of HOST in VIEW_ID, count overlapping tag pairs before/after resolve_tag_overlaps.
Scope: doc, EXT_ROOT, PYREVIT, HOST, VIEW_ID, KEEP (bool: commit the tags). Result: RESULT."""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
_out = []
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils.revit_helpers import element_id_from_int
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    det = load_module('probe_rebar_detailing', os.path.join(lib, 'rebar_detailing.py'))
    view = doc.GetElement(element_id_from_int(VIEW_ID))
    host = doc.GetElement(element_id_from_int(HOST))
    from Autodesk.Revit.DB.Structure import RebarHostData
    rebars = list(RebarHostData.GetRebarHostData(host).GetRebarsInHost())
    try:
        rebars = rebars[:1] * int(REPEAT)     # forced stack: the same bar tagged REPEAT times
    except NameError:
        pass

    def overlaps(tags):
        right, up = view.RightDirection, view.UpDirection
        rects = [det._text_rect(t, det._view_rect(t, view, right, up)) for t in tags]
        rects = [r for r in rects if r is not None]
        n = 0
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    n += 1
        return n

    t = DB.Transaction(doc, u'NOSA test - tags')
    t.Start()
    tags, errors = det.create_rebar_tags(doc, view, rebars, tag_type_id=det.tag_type_for_view(doc, view))
    doc.Regenerate()
    before = overlaps(tags)
    moved = det.resolve_tag_overlaps(doc, view, tags)
    doc.Regenerate()
    after = overlaps(tags)
    _out.append(u'tags {} errors {} overlapping pairs before {} after {} moved {}'.format(
        len(tags), len(errors), before, after, moved))
    if KEEP:
        t.Commit()
    else:
        t.RollBack()
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
