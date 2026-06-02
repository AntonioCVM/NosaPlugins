# -*- coding: utf-8 -*-
import io
import os, sys, csv, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)

_logic = imp.load_source('wtriage_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
classify_warnings       = _logic.classify_warnings
auto_fix_warning        = _logic.auto_fix_warning
get_fixable_description = _logic.get_fixable_description

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger
logger = Logger()


class WarningRow(object):
    def __init__(self, d):
        self.Index         = d.get('index', 0)
        self.Severity      = d.get('severity', 'Low')
        self.Description   = d.get('description', '')
        self.Action        = d.get('action', '')
        self.ElementIds    = d.get('element_ids', [])
        self.ElementsStr   = d.get('elements_str', '')
        self.CountElements = d.get('count_elements', 0)
        self.IsIgnored     = d.get('ignored', False)


class WarningsTriageWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'warnings_triage')
        self.doc       = doc
        self._all_rows = []
        self._rows     = ObservableCollection[WarningRow]()
        self._data     = None
        self.GridResults.ItemsSource = self._rows
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def _active_severities(self):
        s = set()
        if self.ChkHigh.IsChecked   == True: s.add('High')
        if self.ChkMedium.IsChecked == True: s.add('Medium')
        if self.ChkLow.IsChecked    == True: s.add('Low')
        return s

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Reading model warnings...')
        self._rows.Clear(); self._all_rows = []
        self.BtnExport.IsEnabled  = False
        self.BtnIgnore.IsEnabled  = False
        self.BtnAutoFix.IsEnabled = False
        try:
            self._data = classify_warnings(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert('Error: {}'.format(e)); return
        self._all_rows = [WarningRow(d) for d in self._data['warnings']]
        self._apply_filter()
        self.SetLoading(False)
        self.BtnExport.IsEnabled = True
        cfg = self.LoadConfig(); cfg['dark_mode'] = self.dark_mode; self.SaveConfig(cfg)

    def _apply_filter(self):
        sevs        = self._active_severities()
        show_ignored = self.ChkShowIgnored.IsChecked == True
        search       = self.TxtSearch.Text.lower() if hasattr(self, 'TxtSearch') else ''
        self._rows.Clear()
        h = m = l = 0
        for r in self._all_rows:
            if r.IsIgnored and not show_ignored: continue
            if r.Severity not in sevs: continue
            if search and search not in r.Description.lower() and search not in r.Action.lower(): continue
            self._rows.Add(r)
            if r.Severity == 'High':   h += 1
            elif r.Severity == 'Medium': m += 1
            else: l += 1
        self.TxtHigh.Text   = '{} High'.format(h)
        self.TxtMedium.Text = '{} Medium'.format(m)
        self.TxtLow.Text    = '{} Low'.format(l)
        self.TxtTotal.Text  = '{} total model warnings'.format(self._data['total'] if self._data else 0)

    def Filter_Changed(self, sender, args): self._apply_filter()
    def Search_Changed(self, sender, args): self._apply_filter()

    def Grid_SelectionChanged(self, sender, args):
        row = self.GridResults.SelectedItem
        has = row is not None
        self.BtnSelect.IsEnabled  = has
        self.BtnIgnore.IsEnabled  = has
        if has:
            fix_label = get_fixable_description(row.Description)
            self.BtnAutoFix.IsEnabled = fix_label is not None
            self.TxtAction.Text       = row.Action or '—'
            self.PanelAction.Visibility = System.Windows.Visibility.Visible
        else:
            self.BtnAutoFix.IsEnabled = False
            self.PanelAction.Visibility = System.Windows.Visibility.Collapsed

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row or not row.ElementIds: return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(i)) for i in row.ElementIds[:50]])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert('Could not select: {}'.format(e))

    def AutoFix_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row:
            return
        fix_label = get_fixable_description(row.Description)
        if fix_label is None:
            forms.alert('No automatic fix available for this warning.')
            return
        answer = forms.alert(
            "Apply fix '{}' to this warning?\n\n{}".format(fix_label, row.Description),
            yes=True, no=True
        )
        if not answer:
            return
        data = {'description': row.Description, 'element_ids': row.ElementIds}
        try:
            success, message = auto_fix_warning(self.doc, data)
        except Exception as e:
            forms.alert("Fix error: {}".format(e))
            return
        forms.alert(message)
        if success:
            self._apply_filter()

    def Ignore_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row: return
        row.IsIgnored = True
        self._apply_filter()

    def Export_Click(self, sender, args):
        if not self._data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['#','Severity','Warning','Elements','Count','Action'])
                for r in self._rows:
                    w.writerow([r.Index, r.Severity, r.Description, r.ElementsStr, r.CountElements, r.Action])
            forms.alert('Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert('Export failed: {}'.format(e))
