# -*- coding: utf-8 -*-
"""Bind NOSA_Material_Group to Materials and classify every material of the open model.
Scope: doc, EXT_ROOT, PYREVIT, OVERWRITE (bool). Result: RESULT."""
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
try:
    from nosa_utils import material_groups as mg
    from nosa_utils import transactions as nosa_tx
    report = mg.bind(doc)
    _log.append(u'bind: bound {} already {} errors {}'.format(report.get('bound'), report.get('already'),
                                                             report.get('errors')))
    t = DB.Transaction(doc, u'NOSA — Material groups')
    nosa_tx._install(t, nosa_tx.FailureCollector())
    t.Start()
    try:
        overwrite = OVERWRITE
    except NameError:
        overwrite = False
    out = mg.assign(doc, overwrite)
    _log.append(u'commit: {}'.format(t.Commit()))
    for group in sorted(out):
        _log.append(u'{} ({}): {}'.format(group, len(out[group]), u', '.join(sorted(out[group]))))
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
