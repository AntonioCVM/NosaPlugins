# -*- coding: utf-8 -*-
import os, sys
import System.Windows
import System.Windows.Controls as WpfCtrl
import System.Windows.Forms   as WinForms
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.loader     import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('excelsync_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_MATCH_BY_UID  = 'UniqueId'
_MATCH_BY_MARK = 'Mark'


class ExcelSyncWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'excel_sync')
        self.doc = doc

        self._csv_path   = None
        self._headers    = []
        self._rows       = []
        self._matched    = []
        self._map_boxes  = []   # list of (csv_col, TextBox)

        self.CboKeyCol.ItemsSource   = []
        self.TxtFilePath.Text        = 'No file selected'
        self.TxtPreview.Text         = ''

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ── file browse ───────────────────────────────────────────────────────────

    def Browse_Click(self, sender, args):
        dlg = WinForms.OpenFileDialog()
        dlg.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        dlg.Title  = "Select CSV File"
        if dlg.ShowDialog() == WinForms.DialogResult.OK:
            self._csv_path   = dlg.FileName
            self.TxtFilePath.Text = dlg.FileName
            self._clear_state()

    def _clear_state(self):
        self._headers   = []
        self._rows      = []
        self._matched   = []
        self._map_boxes = []
        self.TxtPreview.Text = ''
        self.MappingPanel.Children.Clear()
        self.BtnApply.IsEnabled = False
        self.TxtStatus.Text = ''

    # ── load CSV ──────────────────────────────────────────────────────────────

    def Load_Click(self, sender, args):
        if not self._csv_path:
            forms.alert("Select a CSV file first.")
            return

        self.SetLoading(True, "Reading CSV...")
        try:
            headers, rows = _logic.load_csv(self._csv_path)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Failed to read CSV:\n{}".format(e))
            return
        self.SetLoading(False)

        self._headers = headers
        self._rows    = rows

        # Key column combo
        self.CboKeyCol.ItemsSource   = headers
        self.CboKeyCol.SelectedIndex = 0 if headers else -1

        # CSV preview
        self.TxtPreview.Text = _logic.format_preview(headers, rows)

        # Build mapping panel (skip the key column at first, rebuild on key change)
        self._build_mapping()
        self.BtnApply.IsEnabled = len(rows) > 0

    def _build_mapping(self):
        self.MappingPanel.Children.Clear()
        self._map_boxes = []

        key_col = self.CboKeyCol.SelectedItem
        non_key = [h for h in self._headers if h != key_col]

        if not non_key:
            lbl = WpfCtrl.TextBlock()
            lbl.Text = "(no other columns to map)"
            lbl.Opacity = 0.5
            self.MappingPanel.Children.Add(lbl)
            return

        for col in non_key:
            g = WpfCtrl.Grid()
            c0 = WpfCtrl.ColumnDefinition()
            c0.Width = System.Windows.GridLength(180)
            c1 = WpfCtrl.ColumnDefinition()
            c1.Width = System.Windows.GridLength(1, System.Windows.GridUnitType.Star)
            g.ColumnDefinitions.Add(c0)
            g.ColumnDefinitions.Add(c1)
            g.Margin = System.Windows.Thickness(0, 0, 0, 6)

            lbl = WpfCtrl.TextBlock()
            lbl.Text               = col
            lbl.VerticalAlignment  = System.Windows.VerticalAlignment.Center
            lbl.FontSize           = 12
            WpfCtrl.Grid.SetColumn(lbl, 0)
            g.Children.Add(lbl)

            tb = WpfCtrl.TextBox()
            tb.Height    = 26
            tb.FontSize  = 12
            tb.Padding   = System.Windows.Thickness(4, 2, 4, 2)
            tb.ToolTip   = "Revit parameter name for column '{}'".format(col)
            WpfCtrl.Grid.SetColumn(tb, 1)
            g.Children.Add(tb)

            self.MappingPanel.Children.Add(g)
            self._map_boxes.append((col, tb))

    def KeyCol_Changed(self, sender, args):
        if self._headers:
            self._build_mapping()

    # ── apply ─────────────────────────────────────────────────────────────────

    def Apply_Click(self, sender, args):
        if not self._rows:
            forms.alert("Load a CSV file first.")
            return

        key_col  = self.CboKeyCol.SelectedItem
        match_by = _MATCH_BY_UID if self.RdoUniqueId.IsChecked == True else _MATCH_BY_MARK

        if not key_col:
            forms.alert("Select a key column.")
            return

        mapping = [(col, tb.Text.strip()) for col, tb in self._map_boxes]
        active  = [(c, p) for c, p in mapping if p]
        if not active:
            forms.alert("Enter at least one Revit parameter name in the mapping.")
            return

        self.SetLoading(True, "Matching elements...")
        try:
            matched = _logic.match_elements(self.doc, self._rows, key_col, match_by)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Match failed: {}".format(e))
            return

        matched_count = sum(1 for m in matched if m['matched'])
        unmatched     = len(matched) - matched_count
        multi         = sum(1 for m in matched if m.get('multiple'))

        if matched_count == 0:
            self.SetLoading(False)
            msg = "No elements matched.\nCheck that the key column '{}' values exist as {} in the model.".format(
                key_col, match_by)
            forms.alert(msg)
            return

        info = "Matched {} / {} rows.".format(matched_count, len(matched))
        if unmatched:
            info += "\n{} rows had no matching element.".format(unmatched)
        if multi:
            info += "\n{} keys matched multiple elements (first used).".format(multi)
        info += "\n\nApply {} column mapping(s) to {} element(s)?".format(len(active), matched_count)

        if not forms.alert(info, yes=True, no=True):
            self.SetLoading(False)
            return

        self.SetLoading(True, "Applying parameters...")
        try:
            ok, failed, skipped = _logic.apply_mapping(self.doc, matched, mapping)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Apply failed: {}".format(e))
            return
        self.SetLoading(False)

        result = "Done.\n  OK: {}  |  Failed: {}  |  Skipped (no match): {}".format(
            ok, failed, skipped)
        self.TxtStatus.Text = result
        forms.alert(result, title="Excel Sync")
