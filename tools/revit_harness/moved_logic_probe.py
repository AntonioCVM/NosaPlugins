# -*- coding: utf-8 -*-
"""T8.3: the logic moved out of the retired hidden modules loads and runs (read-only). Result: RESULT."""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml'):
    clr.AddReference(_asm)
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
from nosa_utils.bootstrap import load_module

TAB = os.path.join(EXT_ROOT, 'NOSA.tab')
_out = []


def step(label, fn):
    try:
        _out.append(u'OK   {}: {}'.format(label, fn()))
    except Exception:
        _out.append(u'FAIL {}: {}'.format(label, traceback.format_exc().strip().splitlines()[-1]))


def lib(*parts):
    path = os.path.join(TAB, *parts)
    if os.path.dirname(path) not in sys.path:
        sys.path.insert(0, os.path.dirname(path))
    return path


iw = lib('Documentation.panel', 'IssueWorkflowHub.pushbutton', 'lib', 'x')
gate = load_module('probe_gate', os.path.join(os.path.dirname(iw), 'logic_issue_gate.py'))
pc = load_module('probe_pc', os.path.join(os.path.dirname(iw), 'logic_protocol_checker.py'))
step('issue gate -> DPC protocol check', lambda: len(gate.check_protocol(doc) or []))
step('protocol checker -> nosa_utils.sheet_namer', lambda: len(pc._sheet_namer().F6_CODES))
sh = lib('Documentation.panel', 'Sheets.pulldown', 'SheetHub.pushbutton', 'lib', 'ui.py')
shm = load_module('probe_sheethub', sh)
step('SheetHub -> drawing_index / sheet_namer / SheetGen', lambda: [m.__name__ for m in shm._hub_logics()])
dt = lib('Data.panel', 'DataToolsHub.pushbutton', 'lib', 'ui.py')
dtm = load_module('probe_dth', dt)
step('DataToolsHub -> link change monitor', lambda: os.path.basename(dtm._lm_lcm_logic().__file__))
vt = lib('Documentation.panel', 'Views.pulldown', 'ViewTemplateManager.pushbutton', 'lib', 'logic_template_guard.py')
vtm = load_module('probe_tg', vt)
step('TemplateGuard rules file found', lambda: (os.path.isfile(vtm._RULES_FILE), sorted(vtm.load_rules())[:4]))
qa = lib('Structures.panel', 'StructuralQA.pushbutton', 'lib', 'logic_drawing_checker.py')
qam = load_module('probe_qa_dc', qa)
step('StructuralQA drawing checker -> template guard', lambda: os.path.basename(qam._templateguard_logic().__file__))
RESULT = u'\n'.join(_out)
