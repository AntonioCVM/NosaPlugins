# -*- coding: utf-8 -*-
import imp
import json
import os
import sys

from System.Collections.ObjectModel import ObservableCollection

from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('paramdrift_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


class ParamItem(object):
    def __init__(self, name):
        self.Name      = name
        self.IsChecked = False


class DriftRow(object):
    def __init__(self, d):
        self.Element   = d.get('key', u'')
        self.Parameter = d.get('param', u'')
        self.Change    = d.get('change', u'')
        self.Baseline  = d.get('baseline', u'')
        self.Current   = d.get('current', u'')


class ParameterDriftWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'parameter_drift_monitor')
        self.doc      = doc
        self._params  = ObservableCollection[object]()
        self._rows    = ObservableCollection[object]()
        self._baseline = {}

        self.ParamList.ItemsSource  = self._params
        self.DriftGrid.ItemsSource  = self._rows

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._saved_params = cfg.get('watched_params', [])
        self._baseline     = cfg.get('baseline', {})
        self._load_params()

        if self._baseline:
            self.TxtBaselineInfo.Text = u'Baseline saved — {} elements tracked'.format(
                len(self._baseline))
        else:
            self.TxtBaselineInfo.Text = u'No baseline saved yet.'

    def _load_params(self):
        self._params.Clear()
        for name in _logic.get_shared_param_names(self.doc):
            item = ParamItem(name)
            item.IsChecked = name in self._saved_params
            self._params.Add(item)
        self.TxtStatus.Text = u'{} shared parameters found.'.format(len(self._params))

    def _selected_param_names(self):
        return [p.Name for p in self._params if p.IsChecked]

    # ── handlers ──────────────────────────────────────────────────────────────

    def SaveBaseline_Click(self, sender, args):
        names = self._selected_param_names()
        if not names:
            forms.alert(u'Select at least one parameter to monitor.', title=u'Parameter Drift Monitor')
            return
        self.SetLoading(True, u'Scanning model…')
        try:
            self._baseline = _logic.snapshot_model(self.doc, names)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error scanning model:\n{}'.format(e), title=u'Parameter Drift Monitor')
            return
        self.SetLoading(False)
        self._save_cfg()
        self.TxtBaselineInfo.Text = u'Baseline saved — {} elements tracked'.format(
            len(self._baseline))
        self.TxtStatus.Text = u'Baseline saved ({} elements, {} params).'.format(
            len(self._baseline), len(names))
        self._rows.Clear()

    def Compare_Click(self, sender, args):
        if not self._baseline:
            forms.alert(u'Save a baseline first.', title=u'Parameter Drift Monitor')
            return
        names = self._selected_param_names()
        if not names:
            forms.alert(u'Select at least one parameter to compare.', title=u'Parameter Drift Monitor')
            return
        self.SetLoading(True, u'Comparing…')
        try:
            current = _logic.snapshot_model(self.doc, names)
            diffs   = _logic.compare_snapshots(self._baseline, current)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error comparing:\n{}'.format(e), title=u'Parameter Drift Monitor')
            return
        self._rows.Clear()
        for d in diffs:
            self._rows.Add(DriftRow(d))
        self.SetLoading(False)
        if diffs:
            self.TxtStatus.Text = u'{} drift{} detected.'.format(
                len(diffs), u's' if len(diffs) != 1 else u'')
        else:
            self.TxtStatus.Text = u'No drift detected — model matches baseline.'

    def ImportExcel_Click(self, sender, args):
        path = forms.pick_file(file_ext='xlsx', title=u'Select Reference Excel')
        if not path:
            return
        try:
            self._baseline = _logic.import_from_excel(path)
            self._save_cfg()
            self.TxtBaselineInfo.Text = u'Excel baseline loaded — {} elements'.format(
                len(self._baseline))
        except Exception as e:
            forms.alert(u'Could not read Excel:\n{}'.format(e), title=u'Parameter Drift Monitor')

    def ExportCSV_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv', title=u'Save Drift Report')
        if not path:
            return
        diffs = [{'key': r.Element, 'param': r.Parameter, 'change': r.Change,
                  'baseline': r.Baseline, 'current': r.Current} for r in self._rows]
        try:
            _logic.export_diffs_csv(diffs, path)
            self.TxtStatus.Text = u'Exported to {}'.format(os.path.basename(path))
        except Exception as e:
            forms.alert(u'Export failed:\n{}'.format(e), title=u'Parameter Drift Monitor')

    def SelectInModel_Click(self, sender, args):
        rows = list(self.DriftGrid.SelectedItems or [])
        if not rows:
            rows = list(self._rows)
        keys = set(r.Element for r in rows if r.Element)
        if not keys:
            self.TxtStatus.Text = u'No drift rows to select — run a comparison first.'
            return
        self.SetLoading(True, u'Resolving elements…')
        try:
            ids = _logic.resolve_key_elements(self.doc, keys)
        finally:
            self.SetLoading(False)
        if not ids:
            self.TxtStatus.Text = u'No matching elements found in the model.'
            return
        try:
            from pyrevit import revit
            from Autodesk.Revit import DB as _DB
            from System.Collections.Generic import List as _List
            net_ids = _List[_DB.ElementId]()
            for i in ids:
                net_ids.Add(i)
            revit.uidoc.Selection.SetElementIds(net_ids)
            self.TxtStatus.Text = u'Selected {} element(s) in the model.'.format(net_ids.Count)
        except Exception as e:
            self.TxtStatus.Text = u'Selection failed: {}'.format(e)

    def SelectAll_Click(self, sender, args):
        for p in self._params:
            p.IsChecked = True
        self.ParamList.Items.Refresh()

    def ClearAll_Click(self, sender, args):
        for p in self._params:
            p.IsChecked = False
        self.ParamList.Items.Refresh()

    def _save_cfg(self):
        self.SaveConfig({
            'dark_mode':     bool(self.ChkDarkMode.IsChecked),
            'watched_params': self._selected_param_names(),
            'baseline':      self._baseline,
        })

    def Close_Click(self, sender, args):
        self._save_cfg()
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
