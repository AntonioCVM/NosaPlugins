# -*- coding: utf-8 -*-
"""
T8.2 smoke test of every visible plugin, inside Revit (test models only): import every module of
each pushbutton's lib/ and build (never show) each NOSAWindow it defines, with alerts captured.
Nothing is written to the model. Scope: doc, EXT_ROOT, PYREVIT, optional ONLY (substring filter).
Result: RESULT.
"""
import sys
import os
import inspect
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml', 'System.Windows.Forms'):
    clr.AddReference(_asm)
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_uiapp = UIApplication(doc.Application)
__builtin__.__revit__ = _uiapp

from io import StringIO
_console = StringIO()
_old = sys.stdout
sys.stdout = _console

from nosa_utils.bootstrap import load_module
from nosa_utils.base_window import NOSAWindow
from pyrevit import forms

_out = []
_alerts = []
forms.alert = lambda msg, *a, **k: _alerts.append(unicode(msg)[:100]) or True
forms.ask_for_string = lambda *a, **k: None
for _name in ('SelectFromList', 'CommandSwitchWindow'):
    _cls = getattr(forms, _name, None)
    if _cls is not None:
        _cls.show = staticmethod(lambda *a, **k: None)
TAB = os.path.join(EXT_ROOT, 'NOSA.tab')
try:
    only = ONLY
except NameError:
    only = u''


class _Output(object):
    def print_md(self, text):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def _plugins():
    for dp, dns, fns in os.walk(TAB):
        dns.sort()
        if dp.endswith('.pushbutton') and os.path.isdir(os.path.join(dp, 'lib')):
            yield dp


group = None
ok = fail = 0
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    group = DB.TransactionGroup(doc, u'NOSA smoke (rolled back)')
    group.Start()
    pool = {'doc': doc, 'uidoc': _uiapp.ActiveUIDocument, 'uiapp': _uiapp, 'output': _Output(),
            'revit_doc': doc, 'document': doc}
    for plugin in _plugins():
        rel = os.path.relpath(plugin, TAB).replace('\\', '/')
        if only and only not in rel:
            continue
        lib = os.path.join(plugin, 'lib')
        if lib not in sys.path:
            sys.path.insert(0, lib)
        key = os.path.basename(plugin).split('.')[0]
        problems, windows = [], []
        modules = {}
        # _*subprocess*.py run under CPython in their own process, not in Revit
        names = sorted(f for f in os.listdir(lib) if f.endswith('.py') and f != '__init__.py'
                       and 'subprocess' not in f)
        # ui.py last: it usually loads the others
        names.sort(key=lambda f: f == 'ui.py')
        for f in names:
            try:
                modules[f] = load_module('smoke_{}_{}'.format(key, f[:-3]), os.path.join(lib, f))
            except Exception:
                problems.append(u'import {}: {}'.format(f, traceback.format_exc().strip().splitlines()[-1]))
        for f, mod in sorted(modules.items()):
            for attr in dir(mod):
                cls = getattr(mod, attr)
                if not (inspect.isclass(cls) and issubclass(cls, NOSAWindow) and cls is not NOSAWindow):
                    continue
                if getattr(cls, '__module__', None) != mod.__name__:
                    continue
                try:
                    try:
                        args = inspect.getargspec(cls.__init__)[0][1:]
                    except TypeError:
                        args = ['doc']
                    if any(a not in pool for a in args):
                        windows.append(attr + u' (needs data, skipped)')
                        continue
                    win = cls(*[pool.get(a) for a in args])
                    try:
                        win.Close()
                    except Exception:  # nosa-lint: disable=NOSA006 - already closed by itself
                        pass
                    windows.append(attr)
                except Exception:
                    problems.append(u'window {}.{}: {}'.format(f, attr, traceback.format_exc().strip().splitlines()[-1]))
        hub_path = os.path.join(lib, 'hub.py')
        if os.path.isfile(hub_path):
            try:
                from nosa_utils.tabbed_hub import TabbedHub
                hub_mod = modules.get('hub.py') or load_module('smoke_{}_hub'.format(key), hub_path)
                hub = TabbedHub(key, 'smoke_' + key, hub_mod.tools(doc, _uiapp.ActiveUIDocument))
                tabs = []
                for i in range(hub.HubTabs.Items.Count):
                    hub.HubTabs.SelectedIndex = i
                    tool = hub.tool(i)
                    tabs.append(u'{}={}'.format(hub.HubTabs.Items[i].Header, type(tool).__name__))
                hub.Close()
                windows.append(u'hub[{}]'.format(u', '.join(tabs)))
            except Exception:
                problems.append(u'hub: {}'.format(traceback.format_exc().strip().splitlines()[-1]))
        if problems:
            fail += 1
            _out.append(u'FAIL {} | windows {} | {}'.format(rel, windows, u' || '.join(problems)))
        else:
            ok += 1
            _out.append(u'OK   {} | modules {} | windows {}'.format(rel, len(modules), windows))
except Exception:
    _out.append(u'EXCEPTION:\n' + traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
    sys.stdout = _old

_out.append(u'{} ok, {} failing | alerts raised while building: {}'.format(ok, fail, len(_alerts)))
RESULT = u'\n'.join(_out)
