# -*- coding: utf-8 -*-
"""
rebar_qa._pairs (sweep, 2026-10-25) against _pairs_reference (the double loop it replaced) on the reinforced
building: every member's own bars and every touching pair of members, same samples, findings compared one by one.
The reference is given a full collection between calls only so that it can finish (diagnostic). Scope (PROBE): doc,
ids, _log, _mem.
"""
import time

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
import System

from nosa_utils import rebar_qa as qa
from nosa_utils.revit_helpers import element_name, get_id_value


def key(findings):
    return [(f.Mark, f.Check, f.Severity, f.Issue) for f in findings]


by_host = {}
for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
    by_host.setdefault(get_id_value(r.GetHostId()), []).append(r)
hosts = dict((get_id_value(i), doc.GetElement(i)) for k in ('bases', 'columns', 'beams', 'slabs', 'walls', 'stairs')
             for i in ids[k])
parts = {}
for hid, h in hosts.items():
    _found, samples, label = qa._audit_host(doc, DB, h, by_host.get(hid, []), 32.0, qa.AGGREGATE_MM, element_name,
                                            get_id_value)
    parts[hid] = (samples, label)
jobs = [(u'member {}'.format(hid), parts[hid][0], None) for hid in sorted(parts)]
tol = qa.JOINT_REACH_MM / qa._MM
order = sorted(parts)
for i, a in enumerate(order):
    for b in order[i + 1:]:
        if qa._touch(hosts[a].get_BoundingBox(None), hosts[b].get_BoundingBox(None), tol):
            owner = dict((get_id_value(r.Id), a) for r, _d, _c, _m in parts[a][0])
            owner.update((get_id_value(r.Id), b) for r, _d, _c, _m in parts[b][0])
            jobs.append((u'joint {} / {}'.format(a, b), parts[a][0] + parts[b][0], owner))
same = differ = found_total = 0
t_new = t_old = 0.0
for name, samples, owner in jobs:
    t0 = time.time()
    new = qa._pairs(samples, u'X', qa.AGGREGATE_MM, get_id_value, owner)
    t_new += time.time() - t0
    t0 = time.time()
    old = qa._pairs_reference(samples, u'X', qa.AGGREGATE_MM, get_id_value, owner)
    t_old += time.time() - t0
    System.GC.Collect()
    System.GC.WaitForPendingFinalizers()
    found_total += len(new)
    if key(new) == key(old):
        same += 1
    else:
        differ += 1
        _log.append(u'  DIFFERENT {}: new {} old {}'.format(name, len(new), len(old)))
_log.append(u'== _pairs equivalence: {} checks ({} members, {} joints), {} same, {} different, {} findings; '
            u'new {:.0f} s, reference {:.0f} s'.format(len(jobs), len(parts), len(jobs) - len(parts), same, differ,
                                                        found_total, t_new, t_old))
