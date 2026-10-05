# -*- coding: utf-8 -*-
"""Create Pilecap preview: pick each pile type, report the shapes and sizes drawn (window never shown).
Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT."""
import os
import sys
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
_log = []
try:
    from nosa_utils.bootstrap import load_module
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Foundations.panel', 'PileTools.pulldown', 'CreatePilecapType.pushbutton', 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    ui = load_module('probe_createpilecap_ui', os.path.join(lib, 'ui.py'))
    win = ui.CreatePilecapWindow(doc)
    items = list(win.CboPileType.ItemsSource)
    for i, item in enumerate(items):
        win.CboPileType.SelectedIndex = i
        kinds = [c.GetType().Name for c in win.PileCanvas.Children]
        piles = [c for c in win.PileCanvas.Children if c.GetType().Name in ('Rectangle', 'Ellipse')][1:]
        size = round(piles[0].Width, 1) if piles else None
        _log.append(u'{} -> {} | {} pile shapes ({}) of {} px'.format(
            item.Name, win.TxtInfoPiles.Text, len(piles), sorted(set(c.GetType().Name for c in piles)), size))
    win.Close()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
