# -*- coding: utf-8 -*-
"""T8.13: bind NOSA_GN_*, seed from 0900, change values, apply, check differences. Rolled back."""
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
_out = []
group = None
try:
    from nosa_utils import general_notes as gn
    from nosa_utils import transactions as nosa_tx
    group = DB.TransactionGroup(doc, u'NOSA test - general notes')
    group.Start()
    report = gn.bind(doc)
    _out.append(u'bind: {} bound, {} already, errors {}'.format(len(report['bound']), len(report['already']),
                                                                report['errors'][:3]))
    seed = gn.sheet_values(doc)
    _out.append(u'values found on 0900: {} of {} — missing {}'.format(
        len(seed), len(gn.FIELDS), sorted(set(f[0] for f in gn.FIELDS) - set(seed))))
    t = nosa_tx.guard(DB.Transaction(doc, u'NOSA test - seed'))
    t.Start()
    gn.write_project_values(doc, seed)
    t.Commit()
    _out.append(u'differences after seeding: {}'.format(gn.differences(doc)))
    new = {u'Concrete_Grade': u'C32/40', u'Cover_Typical': u'45mm', u'Fire_Resistance': u'90',
           u'Wind_Speed': u'30 m/s', u'Steel_Grade': u'S355', u'Anchorage_Concrete': u'C32/40'}
    t = nosa_tx.guard(DB.Transaction(doc, u'NOSA test - apply'))
    t.Start()
    gn.write_project_values(doc, new)
    _out.append(u'differences before apply: {}'.format(gn.differences(doc)))
    changed, missing = gn.apply(doc, gn.project_values(doc))
    t.Commit()
    _out.append(u'applied: {} cells changed, missing {}'.format(changed, missing))
    _out.append(u'differences after apply: {}'.format(gn.differences(doc)))
    after = gn.sheet_values(doc)
    _out.append(u'sheet now: {}'.format(dict((k, after.get(k)) for k in new)))
    view = gn.find_view(doc)
    for n in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote):
        txt = n.Text
        if txt.strip().startswith(u'16\r') or txt.strip().startswith(u'40Ø'):
            _out.append(u'table note: ' + txt.replace(u'\r', u' | ')[:120])
    group.RollBack()
    group = None
    _out.append(u'rolled back')
except Exception:
    _out.append(traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
RESULT = u'\n'.join(_out)
