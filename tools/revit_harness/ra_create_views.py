# -*- coding: utf-8 -*-
"""
The 'CREATE VIEWS FOR SELECTION' button of RebarAutomate, run headless on a test model (never saved): the old RC
drawings, their views and bar schedules cleared first (CLEAR), every reinforced member selected, the window's own
_create_views. Scope: doc, EXT_ROOT, PYREVIT, CLEAR, OUT (optional), KINDS (optional), MODE (optional: 'update' or
'regenerate' when the drawings exist, T12.9).
Only the test models below are accepted.
"""
import sys
import os
import re
import io
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
import __builtin__
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

TEST_MODELS = (u'Rebar test 2024', u'Rebar test 2026',
               u'Rebar test 2025 (copia de 2024)', u'Rebar test 2027 (copia de 2026)', u'Rebar test 2024 (copia)')  # T10.11 copies
if doc.Title not in TEST_MODELS:
    raise RuntimeError(u'not a test model')
for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'), os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
_log = []
OWN_VIEW = re.compile(u'^(Beam|Column|Slab|Wall|Foundation|Stair)s? .* - ')

if CLEAR:
    t = DB.Transaction(doc, u'NOSA test - clear RC drawings')
    t.Start()
    gone = 0
    for s in list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)):
        try:
            n = int(s.SheetNumber)
        except ValueError:
            continue
        if 4501 <= n <= 4999 or 5500 <= n <= 5999:
            doc.Delete(s.Id)
            gone += 1
    for v in list(DB.FilteredElementCollector(doc).OfClass(DB.View)):
        if not v.IsTemplate and OWN_VIEW.match(v.Name or u''):
            try:
                doc.Delete(v.Id)
                gone += 1
            except Exception:
                pass
    t.Commit()
    _log.append(u'cleared {} sheets / views'.format(gone))

from nosa_utils.bootstrap import load_module
from nosa_utils import transactions as _transactions
_revit_transaction = _transactions.revit_transaction


def _on_doc(name=None, doc_=None, **kwargs):
    return _revit_transaction(name, doc_ or doc, **kwargs)


_transactions.revit_transaction = _on_doc
ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))


def _alert(msg, *args, **kwargs):
    _log.append(u'ALERT: ' + unicode(msg))
    return True


ui.forms.alert = _alert
from pyrevit import forms as _forms
_forms.alert = _alert
import rebar_views
_build = rebar_views.build_drawings


def _logged(*a, **k):
    rep = _build(*a, **k)
    _log.append(u'ALL ERRORS ({}):\n'.format(len(rep.get('errors', []))) + u'\n'.join(rep.get('errors', [])))
    for i in (rep.get('review') or {}).get('issues', []):
        _log.append(u'ISSUE {} {} | {} | {} | {}'.format(i.get('category'), i.get('sheet'), i.get('view'),
                                                       i.get('element'), i.get('problem')))
    return rep


rebar_views.build_drawings = _logged
hosts = []
for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
    try:
        if rebar_views.host_kind(e) and rebar_views.host_rebars(e) and \
                ('KINDS' not in dir() or rebar_views.host_kind(e) in KINDS):
            hosts.append(e.Id)
    except Exception:
        continue


class _Selection(object):
    def GetElementIds(self):
        return list(hosts)


class _UIDoc(object):
    Document = doc
    Selection = _Selection()


win = ui.RebarAutomateWindow(doc)
win.Show = lambda: None
win._is_loaded = True
win.uidoc = _UIDoc()
win.ChkViewsSheets.IsChecked = True
win.ChkViewsTags.IsChecked = True
win.SetLoading = lambda *a, **k: None
win.drawing_mode = MODE if 'MODE' in dir() else 'regenerate'
try:
    win._create_views()
except Exception:
    import traceback
    _log.append(traceback.format_exc())
_log.append(u'STATUS: ' + unicode(win.TxtDetailingStatus.Text or u''))
sheets = sorted((s.SheetNumber, s.Name) for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                if s.SheetNumber.startswith(u'4') or s.SheetNumber.startswith(u'55'))
_log.append(u'SHEETS: ' + u'; '.join(u'{} {}'.format(n, m) for n, m in sheets))
RESULT = u'\n'.join(_log)
if 'OUT' in dir():
    with io.open(OUT, 'w', encoding='utf-8') as f:
        f.write(RESULT)
