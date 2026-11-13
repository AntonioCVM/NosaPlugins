# -*- coding: utf-8 -*-
"""T8.48: run nosa_utils.rebar_qa.audit (read-only) on the hosts in IDS. Scope: doc, EXT_ROOT, IDS. Result: RESULT."""
import sys
import os
import time
import clr
clr.AddReference("RevitAPI")
for p in (os.path.join(EXT_ROOT, 'lib'),):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.modules.pop('nosa_utils.rebar_qa', None)
from nosa_utils import rebar_qa
from nosa_utils.revit_helpers import element_id_from_int

_log = []
try:
    t0 = time.time()
    found = rebar_qa.audit(doc, [element_id_from_int(i) for i in IDS] if IDS else None)
    _log.append(u'{} finding(s) in {:.1f} s'.format(len(found), time.time() - t0))
    for f in found:
        _log.append(u'{} | {} | {} | {} | {} | {}'.format(f.Drawing, f.Host, f.Mark, f.Check, f.Severity, f.Issue))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
