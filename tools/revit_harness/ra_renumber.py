# -*- coding: utf-8 -*-
"""Harness: renumber a partition of the test model (scope: doc, EXT_ROOT, PARTITION)."""
import os
import sys
import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
_rb = os.path.join(EXT_ROOT, 'NOSA.tab', 'Structures.panel', 'Quantities.pulldown',
                   'RebarAutomate.pushbutton', 'lib')
for p in (os.path.join(EXT_ROOT, 'lib'), _rb):
    if p not in sys.path:
        sys.path.insert(0, p)
_log = []
try:
    import rebar_marking
    t = DB.Transaction(doc, u'NOSA test — Renumber Partition')
    t.Start()
    summary = rebar_marking.renumber_partition(doc, {'standard': None, 'mark_prefix': PARTITION})
    t.Commit()
    _log.append(u'{}'.format(summary))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
