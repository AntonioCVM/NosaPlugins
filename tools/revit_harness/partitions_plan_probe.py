# -*- coding: utf-8 -*-
"""Read-only: the partitions RebarAutomate would give the reinforced hosts, and why hosts differ.
Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT."""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib'),
           os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []
try:
    import rebar_partitions as rp
    hosts = rp.collect_hosts(doc)
    plan = rp.plan(hosts)
    for h in sorted(hosts, key=lambda x: x['id']):
        e = plan[h['id']]
        _log.append(u'{} {} {} -> {} rep={} members={} bars={}'.format(
            h['id'], h['category'], h['type'], e['partition'], e['representative'], e['members'], h['bars']))
    by_type = {}
    for h in hosts:
        by_type.setdefault((h['category'], h['type']), []).append(h)
    for key, group in by_type.items():
        if len(group) < 2:
            continue
        ref = set(group[0]['fingerprint'][2])
        for h in group[1:]:
            other = set(h['fingerprint'][2])
            if other != ref:
                _log.append(u'DIFF {} vs {}: only in first {} | only in second {}'.format(
                    group[0]['id'], h['id'], sorted(ref - other), sorted(other - ref)))
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
