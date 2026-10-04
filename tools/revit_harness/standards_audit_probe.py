# -*- coding: utf-8 -*-
"""T8.14: run nosa_utils.standards_audit on the open model (read-only); full list to a file. Result: RESULT."""
import sys
import os
import io
import tempfile
import traceback

import clr
clr.AddReference('RevitAPI')
for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_out = []
try:
    from nosa_utils import standards_audit
    findings = standards_audit.audit(doc)
    path = os.path.join(tempfile.gettempdir(), 'nosa_standards_audit.tsv')
    with io.open(path, 'w', encoding='utf-8') as f:
        for x in findings:
            f.write(u'{}\t{}\t{}\t{}\t{}\n'.format(x.Area, x.Item, x.Issue, x.Unused, x.element_id))
    counts = {}
    for x in findings:
        counts[x.Area] = counts.get(x.Area, 0) + 1
    _out.append(u'{} findings -> {} | {}'.format(len(findings), path, counts))
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
