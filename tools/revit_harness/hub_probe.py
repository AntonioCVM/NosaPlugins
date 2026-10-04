# -*- coding: utf-8 -*-
"""
T8.6–T8.11: build a TabbedHub of existing tools (never shown), open every tab, check the moved
content keeps its named controls and theme brushes. Scope: doc, EXT_ROOT, PYREVIT, TOOLS (JSON list
of [header, path to ui.py relative to NOSA.tab, class name]). Result: RESULT.
"""
import sys
import os
import json
import inspect
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml', 'System.Windows.Forms'):
    clr.AddReference(_asm)
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_uiapp = UIApplication(doc.Application)
__builtin__.__revit__ = _uiapp

from nosa_utils.bootstrap import load_module
from nosa_utils.tabbed_hub import TabbedHub
from pyrevit import forms
forms.alert = lambda *a, **k: True

_out = []
TAB = os.path.join(EXT_ROOT, 'NOSA.tab')
pool = {'doc': doc, 'uidoc': _uiapp.ActiveUIDocument}


def factory(path, cls_name):
    def make():
        lib = os.path.dirname(os.path.join(TAB, path))
        if lib not in sys.path:
            sys.path.insert(0, lib)
        mod = load_module('hubprobe_' + cls_name, os.path.join(TAB, path))
        cls = getattr(mod, cls_name)
        args = inspect.getargspec(cls.__init__)[0][1:]
        return cls(*[pool.get(a) for a in args])
    return make


try:
    tools = json.loads(TOOLS)
    hub = TabbedHub(u'Probe hub', u'hub_probe', [(h, factory(p, c)) for h, p, c in tools])
    for i in range(len(tools)):
        hub.HubTabs.SelectedIndex = i
        tool = hub.tool(i)
        named = [n for n in dir(tool) if n[:3] in ('Txt', 'Btn', 'Chk', 'Cmb', 'Grd', 'Tab', 'Lst', 'Dg_') or
                 n.split('_')[0] in ('HS', 'WT', 'CR', 'FA', 'RC', 'QQ')]
        reachable = 0
        for n in named[:40]:
            try:
                getattr(tool, n)
                reachable += 1
            except Exception:  # nosa-lint: disable=NOSA006 - counted as unreachable
                pass
        content = hub.HubTabs.Items[i].Content
        _out.append(u'tab {} "{}": content {} | named controls reachable {}/{} | BgColor in tab resources {} | '
                    u'Close delegated {}'.format(i, tools[i][0], content.GetType().Name, reachable, min(len(named), 40),
                                                 content.Resources.Contains('BgColor'), tool.Close == hub.Close))
    hub.ApplyTheme(True)
    tool0 = hub.tool(0)
    _out.append(u'dark theme: hub bg {} | tool0 brush {}'.format(hub.Resources['BgColor'].Color,
                                                                 hub.HubTabs.Items[0].Content.Resources['BgColor'].Color))
    tool0.ApplyTheme(True)
    _out.append(u'tool0.ApplyTheme(dark): tab brush {}'.format(hub.HubTabs.Items[0].Content.Resources['BgColor'].Color))
    hub.ApplyTheme(False)
    tool0.ApplyTheme(False)
    hub.Close()
except Exception:
    _out.append(u'EXCEPTION:\n' + traceback.format_exc())
RESULT = u'\n'.join(_out)
