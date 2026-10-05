# -*- coding: utf-8 -*-
"""
0900 sections: hide HIDE (list of keys), export the view, show everything again and check that every
element is back where it was; all rolled back. Scope: doc, EXT_ROOT, PYREVIT, HIDE, HIDE2 (optional second
selection), IMAGE. Result: RESULT.
"""
import sys
import os
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []


def run():
    from System.Collections.Generic import List
    from nosa_utils import general_notes as gn
    from nosa_utils import general_notes_sections as gs
    from nosa_utils import transactions as nosa_tx
    view = gn.find_view(doc)
    _log.append(u'sections: {}'.format([(k, p) for k, _l, p in gs.sections_in_view(doc, view)]))
    headings, items = gs._layout(doc, view)
    members = gs.assign(headings, items)
    _log.append(u'members: {}'.format(dict((k, len(v)) for k, v in members.items())))
    before = dict((i[0], (round(i[1], 3), round(i[3], 3))) for i in items)
    group = DB.TransactionGroup(doc, u'NOSA test - 0900 sections')
    group.Start()
    try:
        report = gn.bind(doc)
        _log.append(u'bind: {}'.format(report))
        t = DB.Transaction(doc, u'hide')
        nosa_tx._install(t, nosa_tx.FailureCollector())
        t.Start()
        n, moved = gs.apply(doc, view, list(HIDE))
        t.Commit()
        _log.append(u'hidden {} moved {} state {}'.format(n, moved, gs.read_state(doc)))
        if IMAGE:
            opts = DB.ImageExportOptions()
            opts.ExportRange = DB.ExportRange.SetOfViews
            opts.SetViewsAndSheets(List[DB.ElementId]([view.Id]))
            opts.FilePath = IMAGE
            opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
            opts.ZoomType = DB.ZoomFitType.FitToPage
            opts.PixelSize = 4000
            doc.ExportImage(opts)
        try:
            second = list(HIDE2)
        except NameError:
            second = None
        if second is not None:
            t = DB.Transaction(doc, u'hide 2')
            nosa_tx._install(t, nosa_tx.FailureCollector())
            t.Start()
            n, moved = gs.apply(doc, view, second)
            t.Commit()
            _log.append(u'second pass hidden {} moved {} state {}'.format(n, moved, gs.read_state(doc)))
        t = DB.Transaction(doc, u'show')
        nosa_tx._install(t, nosa_tx.FailureCollector())
        t.Start()
        gs.apply(doc, view, [])
        t.Commit()
        _h, after_items = gs._layout(doc, view)
        after = dict((i[0], (round(i[1], 3), round(i[3], 3))) for i in after_items)
        off = [k for k in before if k in after and (abs(before[k][0] - after[k][0]) > 0.01 or
                                                     abs(before[k][1] - after[k][1]) > 0.01)]
        still_hidden = [e for e in DB.FilteredElementCollector(doc).OwnedByView(view.Id).WhereElementIsNotElementType()
                        if e.Category is not None and e.IsHidden(view)]
        missing = [k for k in before if k not in after]
        _log.append(u'restored: {} elements off their place, {} not visible again, {} hidden in the view, state {}'.format(
            len(off), len(missing), len(still_hidden), gs.read_state(doc)))
    finally:
        group.RollBack()
        _log.append(u'rolled back')


try:
    run()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
