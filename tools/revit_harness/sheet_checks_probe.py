# -*- coding: utf-8 -*-
"""T8.12: run nosa_utils.sheet_checks on every sheet of the open model (read-only). Result: RESULT."""
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
try:
    from nosa_utils import sheet_checks
    sheets = sorted(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet), key=lambda s: s.SheetNumber)
    findings = sheet_checks.check_sheets(doc, sheets)
    for f in findings:
        _out.append(u'{:7} {:11} {} | {}'.format(f.Severity, f.Check, f.Sheet[:32], f.Message))
    _out.append(u'{} sheets, {} findings'.format(len(sheets), len(findings)))
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
