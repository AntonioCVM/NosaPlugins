# -*- coding: utf-8 -*-
"""Build (never show) the windows of the hubs moved by the 2026-10-03 ribbon reorganisation.
Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT."""
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
_uiapp = UIApplication(doc.Application)
__builtin__.__revit__ = _uiapp
from nosa_utils.bootstrap import load_module

_out = []
TAB = os.path.join(EXT_ROOT, 'NOSA.tab')
HUBS = (
    (('Reinforcement.panel', 'RebarAutomate.pushbutton'), 'RebarAutomateWindow', False),
    (('Reinforcement.panel', 'RebarHub.pushbutton'), 'RebarHubWindow', True),
    (('Structures.panel', 'StructuralQA.pushbutton'), 'StructuralQAWindow', False),
    (('Foundations.panel', 'SurveyExport.pushbutton'), 'SurveyExportWindow', False),
    (('Data.panel', 'ElementCommentsHub.pushbutton'), 'ElementCommentsHubWindow', True),
)
for parts, cls, needs_uidoc in HUBS:
    try:
        folder = os.path.join(TAB, *parts)
        lib = os.path.join(folder, 'lib')
        if lib not in sys.path:
            sys.path.insert(0, lib)
        mod = load_module('smoke_' + parts[-1].split('.')[0].lower(), os.path.join(lib, 'ui.py'))
        args = (doc, _uiapp.ActiveUIDocument) if needs_uidoc else (doc,)
        win = getattr(mod, cls)(*args)
        _out.append(u'OK   {} built'.format(cls))
        win.Close()
    except Exception:
        _out.append(u'FAIL {}\n{}'.format(cls, traceback.format_exc()))
RESULT = u'\n'.join(_out)
