# -*- coding: utf-8 -*-
"""T7.1 probe: copy HOST (with its bars) COPIES times, plan + apply partitions, read the BBS; all rolled back.
Scope: doc, EXT_ROOT, PYREVIT, HOST, COPIES. Result: RESULT."""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication
from System.Collections.Generic import List

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
_out = []
group = None
try:
    if u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    from nosa_utils.revit_helpers import element_id_from_int, get_id_value
    from Autodesk.Revit.DB.Structure import RebarHostData
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel',
                       'RebarAutomate.pushbutton', 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    parts = load_module('rebar_partitions', os.path.join(lib, 'rebar_partitions.py'))
    sched = load_module('rebar_schedule', os.path.join(lib, 'rebar_schedule.py'))

    group = DB.TransactionGroup(doc, u'NOSA test - partitions')
    group.Start()
    host = doc.GetElement(element_id_from_int(HOST))
    ids = List[DB.ElementId]([host.Id] + [r.Id for r in RebarHostData.GetRebarHostData(host).GetRebarsInHost()])
    t = DB.Transaction(doc, u'copies')
    t.Start()
    for k in range(int(COPIES)):
        DB.ElementTransformUtils.CopyElements(doc, ids, DB.XYZ((k + 1) * 6000 / 304.8, 0, 0))
    t.Commit()

    hosts = parts.collect_hosts(doc)
    assignment = parts.plan(hosts)
    for h in sorted(hosts, key=lambda h: assignment[h['id']]['group']):
        a = assignment[h['id']]
        _out.append(u'host {} {} mark "{}" level {} bars {} -> {} grp {} rep {} mbrs {}'.format(
            h['id'], h['category'], h['mark'], h['level'], h['bars'], a['partition'], a['group'],
            a['representative'], a['members']))

    try:
        win_mod = load_module('partitions_window', os.path.join(lib, 'partitions_window.py'))
        win = win_mod.PartitionsWindow(doc, {})
        _out.append(u'dialog rows {} summary "{}"'.format(len(win.rows), win.TxtSummary.Text))
        win.Close()
    except Exception:
        _out.append(u'dialog FAILED ' + traceback.format_exc())

    t = DB.Transaction(doc, u'apply')
    t.Start()
    summary = parts.apply(doc, hosts, assignment, {})
    t.Commit()
    _out.append(u'apply {}'.format(summary))

    data = sched.generate_schedule_data(doc)
    for row in sched.bbs_rows(data):
        _out.append(u'BBS ' + u' | '.join(row[:8]))
    group.RollBack()
    group = None
except Exception:
    _out.append(traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
RESULT = u'\n'.join(_out)
