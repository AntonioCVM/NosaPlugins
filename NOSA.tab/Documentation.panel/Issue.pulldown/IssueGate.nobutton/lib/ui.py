# -*- coding: utf-8 -*-
import imp
import os
import sys

import System.Windows.Media as WM
from System.Collections.ObjectModel import ObservableCollection

from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('issuegate_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_CHECK_DEFS = [
    ('protocol',   u'Sheet Protocol'),
    ('revisions',  u'Revision Completeness'),
    ('titleblock', u'Title Block Parameters'),
    ('duplicates', u'Duplicate Sheet Numbers'),
]

_SUFFIXES = {
    'protocol':   'Protocol',
    'revisions':  'Revisions',
    'titleblock': 'Titleblock',
    'duplicates': 'Duplicates',
}

_STATUS_ICONS = {
    'pass':    u'✓',
    'warn':    u'⚠',
    'fail':    u'✗',
    'error':   u'!',
    'pending': u'○',
}

_STATUS_LABELS = {
    'pass':    u'Pass',
    'warn':    u'Warning',
    'fail':    u'Fail',
    'error':   u'Error',
    'pending': u'Not checked',
}


def _make_brush(status):
    if status == 'pass':   return WM.SolidColorBrush(WM.Color.FromRgb(39,  174, 96))
    if status == 'warn':   return WM.SolidColorBrush(WM.Color.FromRgb(243, 156, 18))
    if status == 'fail':   return WM.SolidColorBrush(WM.Color.FromRgb(231, 76,  60))
    if status == 'error':  return WM.SolidColorBrush(WM.Color.FromRgb(120, 120, 120))
    return WM.SolidColorBrush(WM.Color.FromRgb(200, 200, 200))


class DetailRow(object):
    def __init__(self, item):
        self.SheetNumber = item.get('number', u'')
        self.SheetName   = item.get('name', u'')
        self.Severity    = item.get('severity', u'')
        self.Issue       = item.get('issue', u'')


class IssueGateWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'issue_gate')
        self.doc               = doc
        self.proceed_to_export = False
        self._results          = {}
        self._detail_rows      = ObservableCollection[object]()

        self.DetailGrid.ItemsSource = self._detail_rows

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._reset_cards()
        self.BtnExport.IsEnabled = False

    # ── card helpers ──────────────────────────────────────────────────────────

    def _reset_cards(self):
        pending_brush = _make_brush('pending')
        for key, _ in _CHECK_DEFS:
            suffix = _SUFFIXES[key]
            getattr(self, 'CardAccent' + suffix).BorderBrush = pending_brush
            getattr(self, 'TxtIcon'    + suffix).Text        = u'○'
            getattr(self, 'TxtIcon'    + suffix).Foreground  = pending_brush
            getattr(self, 'TxtStatus'  + suffix).Text        = u'Not checked'
            getattr(self, 'TxtStatus'  + suffix).Foreground  = pending_brush
            getattr(self, 'TxtCount'   + suffix).Text        = u''

    def _update_card(self, key, result):
        suffix = _SUFFIXES[key]
        st     = result.get('status', 'pending')
        cnt    = result.get('count', 0)
        err    = result.get('error', u'')
        brush  = _make_brush(st)

        getattr(self, 'CardAccent' + suffix).BorderBrush = brush

        icon_el = getattr(self, 'TxtIcon' + suffix)
        icon_el.Text       = _STATUS_ICONS.get(st, u'○')
        icon_el.Foreground = brush

        status_el = getattr(self, 'TxtStatus' + suffix)
        status_el.Text       = err if err else _STATUS_LABELS.get(st, st)
        status_el.Foreground = brush

        count_el = getattr(self, 'TxtCount' + suffix)
        if err:
            count_el.Text = u''
        elif cnt > 0:
            count_el.Text = u'{} issue{}'.format(cnt, u's' if cnt != 1 else u'')
        else:
            count_el.Text = u'No issues' if st == 'pass' else u''

    # ── detail panel ──────────────────────────────────────────────────────────

    def _show_details(self, key):
        self._detail_rows.Clear()
        result = self._results.get(key, {})
        label  = dict(_CHECK_DEFS).get(key, key)
        cnt    = result.get('count', 0)
        err    = result.get('error', u'')

        for item in result.get('items', []):
            self._detail_rows.Add(DetailRow(item))

        if err:
            self.TxtDetailTitle.Text = u'{} — Error: {}'.format(label, err)
        elif cnt == 0:
            self.TxtDetailTitle.Text = u'{} — No issues found'.format(label)
        else:
            self.TxtDetailTitle.Text = u'{} — {} issue{}'.format(
                label, cnt, u's' if cnt != 1 else u'')

    # ── overall status ────────────────────────────────────────────────────────

    def _update_status_bar(self):
        if not self._results:
            self.TxtGateStatus.Text  = u'Run checks to validate the model before issue.'
            self.BtnExport.IsEnabled = False
            return
        statuses = [r.get('status') for r in self._results.values()]
        if 'fail' in statuses:
            self.TxtGateStatus.Text  = u'FAIL — Critical issues found. Resolve before issuing.'
            self.BtnExport.IsEnabled = False
        elif 'error' in statuses:
            self.TxtGateStatus.Text  = u'ERROR — One or more checks could not run.'
            self.BtnExport.IsEnabled = False
        elif 'warn' in statuses:
            self.TxtGateStatus.Text  = u'WARN — Non-critical items need attention. Proceed with caution.'
            self.BtnExport.IsEnabled = True
        else:
            self.TxtGateStatus.Text  = u'PASS — All checks passed. Ready to export.'
            self.BtnExport.IsEnabled = True

    # ── event handlers ────────────────────────────────────────────────────────

    def RunChecks_Click(self, sender, args):
        self.SetLoading(True, u'Running pre-flight checks…')
        try:
            self._results = _logic.run_all(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks:\n{}'.format(e), title=u'Issue Gate')
            return

        for key, _ in _CHECK_DEFS:
            self._update_card(key, self._results.get(key, {'status': 'error', 'count': 0, 'items': []}))

        self._update_status_bar()
        self.SetLoading(False)

        for key, _ in _CHECK_DEFS:
            r = self._results.get(key, {})
            if r.get('count', 0) > 0:
                self._show_details(key)
                return
        self._show_details('protocol')

    def Card_Click(self, sender, args):
        key = str(sender.Tag) if sender.Tag else None
        if key:
            self._show_details(key)

    def SelectSheets_Click(self, sender, args):
        rows = list(self.DetailGrid.SelectedItems or [])
        if not rows:
            rows = list(self._detail_rows)
        numbers = set(r.SheetNumber for r in rows if r.SheetNumber)
        if not numbers:
            self.TxtGateStatus.Text = u'No sheets to select — run checks first.'
            return
        try:
            from pyrevit import revit
            from Autodesk.Revit import DB as _DB
            from System.Collections.Generic import List as _List
            ids = _List[_DB.ElementId]()
            for sheet in (_DB.FilteredElementCollector(self.doc)
                          .OfClass(_DB.ViewSheet).ToElements()):
                try:
                    if sheet.SheetNumber in numbers:
                        ids.Add(sheet.Id)
                except Exception:
                    pass
            revit.uidoc.Selection.SetElementIds(ids)
            self.TxtGateStatus.Text = u'Selected {} sheet(s) in the model.'.format(ids.Count)
        except Exception as e:
            self.TxtGateStatus.Text = u'Selection failed: {}'.format(e)

    def Export_Click(self, sender, args):
        self.SaveConfig({'dark_mode': bool(self.ChkDarkMode.IsChecked)})
        self.proceed_to_export = True
        self.Close()

    def Close_Click(self, sender, args):
        self.SaveConfig({'dark_mode': bool(self.ChkDarkMode.IsChecked)})
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
