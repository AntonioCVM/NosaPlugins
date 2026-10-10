# -*- coding: utf-8 -*-
"""T8.50: nosa_utils.ties.check_floor (read-only) on the floors in IDS. Scope: doc, EXT_ROOT, IDS. Result: RESULT."""
import sys
import os
import clr
clr.AddReference("RevitAPI")
if os.path.join(EXT_ROOT, 'lib') not in sys.path:
    sys.path.insert(0, os.path.join(EXT_ROOT, 'lib'))
sys.modules.pop('nosa_utils.ties', None)
from nosa_utils import ties
from nosa_utils.revit_helpers import element_id_from_int

_log = []
try:
    for i in IDS:
        for check, ok, text in ties.check_floor(doc, doc.GetElement(element_id_from_int(i)), 4, 8.5, 7.5):
            _log.append(u'{} {} {}: {}'.format(i, check, u'OK' if ok else u'MISSING', text))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
