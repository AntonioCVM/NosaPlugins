# -*- coding: utf-8 -*-
"""T8.54: bind, update and the column/base schedules, in a rolled-back group. Scope: doc, EXT_ROOT. Result: RESULT."""
import sys
import os
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit import DB
LIB = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
for p in (LIB, os.path.join(EXT_ROOT, 'lib')):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.modules.pop('tabular_schedules', None)
import tabular_schedules

_log = []
group = DB.TransactionGroup(doc, u'NOSA test T8.54')
group.Start()
try:
    _log.append(u'bind: {}'.format(tabular_schedules.bind(doc)))
    t = DB.Transaction(doc, u'NOSA test tabular')
    t.Start()
    _log.append(u'update: columns {} bases {} groups {}'.format(*tabular_schedules.update(doc)))
    for v in tabular_schedules.ensure_schedules(doc):
        t.Commit() if t.HasStarted() and not t.HasEnded() else None
        body = v.GetTableData().GetSectionData(DB.SectionType.Body)
        _log.append(u'== ' + v.Name)
        for r in range(body.NumberOfRows):
            _log.append(u' | '.join(v.GetCellText(DB.SectionType.Body, r, c) for c in range(body.NumberOfColumns)))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
finally:
    group.RollBack()
RESULT = u'\n'.join(_log)
