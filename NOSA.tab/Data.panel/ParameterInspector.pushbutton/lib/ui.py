# -*- coding: utf-8 -*-
import io
import os, sys, csv

import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.loader import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('paraminspector_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_SEARCH_PLACEHOLDER = "Search parameters..."


class ParamRow(object):
    def __init__(self, row_data, element_count):
        self.Name    = row_data['name']
        self.Group   = row_data['group']
        self.Storage = row_data['storage']
        self.RW      = "R" if row_data['readonly'] else "RW"
        self.HasDiff = not row_data['consistent'] and element_count > 1
        self._params = row_data['params']
        self._readonly = row_data['readonly']

        values = row_data['values']
        if element_count <= 1:
            self.ValueStr = values[0] if values else ''
        else:
            unique = list(dict.fromkeys(v for v in values if v is not None))
            if len(unique) == 1:
                self.ValueStr = unique[0]
            else:
                self.ValueStr = " | ".join(str(v) for v in unique[:4])
                if len(unique) > 4:
                    self.ValueStr += " ..."


class ParameterInspectorWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'parameter_inspector')
        self.doc        = doc
        self._elements  = []
        self._all_rows  = []
        self._rows      = ObservableCollection[ParamRow]()
        self.GridParams.ItemsSource = self._rows
        self._search_active = False

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ── load ────────────────────────────────────────────────────────────────

    def Load_Click(self, sender, args):
        sel = revit.get_selection()
        elements = list(sel.elements) if hasattr(sel, 'elements') else list(sel)
        if not elements:
            forms.alert("No elements selected. Select elements in Revit first.")
            return

        self._elements = elements
        self.TxtElementCount.Text = "{} element(s)".format(len(elements))
        self.SetLoading(True, "Reading parameters...")

        try:
            self._all_rows = _logic.collect_params(self.doc, elements)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error collecting parameters: {}".format(e))
            return

        self._apply_filters()
        self.SetLoading(False)
        self.BtnExport.IsEnabled   = True
        self.BtnCopyFrom.IsEnabled = len(elements) > 1

    # ── filters ──────────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filters()

    def _apply_filters(self):
        show_builtin  = self.ChkShowBuiltin.IsChecked  == True
        show_shared   = self.ChkShowShared.IsChecked   == True
        show_project  = self.ChkShowProject.IsChecked  == True
        only_diffs    = self.ChkOnlyDiffs.IsChecked    == True
        only_writable = self.ChkOnlyWritable.IsChecked == True
        search_text   = (self.TxtSearch.Text or '').strip().lower()
        if search_text == _SEARCH_PLACEHOLDER.lower():
            search_text = ''

        visible = []
        for rd in self._all_rows:
            if rd['builtin'] and not show_builtin:
                continue
            if rd['shared'] and not show_shared:
                continue
            if not rd['builtin'] and not rd['shared'] and not show_project:
                continue
            if only_diffs and rd['consistent']:
                continue
            if only_writable and rd['readonly']:
                continue
            if search_text and search_text not in rd['name'].lower():
                continue
            visible.append(rd)

        n_elem = len(self._elements)
        self._rows.Clear()
        diffs = 0
        for rd in visible:
            row = ParamRow(rd, n_elem)
            if row.HasDiff:
                diffs += 1
            self._rows.Add(row)

        self.TxtTotalParams.Text = "{} params".format(len(visible))
        self.TxtDiffParams.Text  = "{} diffs".format(diffs)

    # ── search ───────────────────────────────────────────────────────────────

    def Search_GotFocus(self, sender, args):
        if self.TxtSearch.Text == _SEARCH_PLACEHOLDER:
            self.TxtSearch.Text = ''
            self.TxtSearch.Foreground = System.Windows.Media.Brushes.Black
            self._search_active = True

    def Search_LostFocus(self, sender, args):
        if not self.TxtSearch.Text.strip():
            self.TxtSearch.Text = _SEARCH_PLACEHOLDER
            self.TxtSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._search_active = False

    def Search_Changed(self, sender, args):
        if self._search_active or self.TxtSearch.Text != _SEARCH_PLACEHOLDER:
            self._apply_filters()

    # ── grid ────────────────────────────────────────────────────────────────

    def Grid_SelectionChanged(self, sender, args):
        row = self.GridParams.SelectedItem
        self.BtnApply.IsEnabled = (
            row is not None and not row._readonly and bool(self._elements)
        )

    # ── bulk edit ────────────────────────────────────────────────────────────

    def Apply_Click(self, sender, args):
        row = self.GridParams.SelectedItem
        if row is None or row._readonly:
            return
        new_val = self.TxtNewValue.Text
        params  = [p for p in row._params if p is not None]
        if not params:
            forms.alert("No editable parameters found for this row.")
            return
        ok, fail = _logic.set_param_value(self.doc, params, new_val)
        forms.alert("Set: {}  |  Failed: {}".format(ok, fail), title="Bulk Edit")
        self.Load_Click(None, None)

    # ── copy from source ─────────────────────────────────────────────────────

    def CopyFrom_Click(self, sender, args):
        if len(self._elements) < 2:
            return
        source  = self._elements[0]
        targets = self._elements[1:]
        name = getattr(source, 'Name', str(source.Id))
        if not forms.alert(
            "Copy all writable parameters from:\n{}\n\nTo {} elements?".format(name, len(targets)),
            yes=True, no=True
        ):
            return
        copied, skipped = _logic.copy_params_from_source(self.doc, source, targets)
        forms.alert("Copied: {}  |  Skipped: {}".format(copied, skipped))
        self.Load_Click(None, None)

    # ── export ───────────────────────────────────────────────────────────────

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                header = ['Group', 'Parameter', 'Type', 'R/W', 'Consistent?']
                for i in range(len(self._elements)):
                    header.append('Element {}'.format(i + 1))
                w.writerow(header)
                for rd in self._all_rows:
                    row = [
                        rd['group'], rd['name'], rd['storage'],
                        'R' if rd['readonly'] else 'RW',
                        'Yes' if rd['consistent'] else 'No',
                    ] + rd['values']
                    w.writerow(row)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
