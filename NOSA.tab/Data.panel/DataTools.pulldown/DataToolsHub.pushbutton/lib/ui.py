# -*- coding: utf-8 -*-
"""
DataToolsHubWindow — sidebar-navigation hub consolidating 5 formerly
standalone plugins: Excel Sync (ES_), Workset Health (WH_), Model Cleanup
(MC_), Link Manager (LM_) and Type Renamer (TR_).

Each absorbed tool's controls/handlers carry a short unique prefix so they
can coexist in a single WPF Window/class without x:Name or method-name
collisions. Business logic (logic_*.py) is untouched — only relocated and
loaded via imp.load_source() with a globally-unique module alias, which is
the established fix for the sys.modules collision bug that hit this
extension when two plugins shipped a same-named logic.py/managers.py.

Shared/reserved (unprefixed) controls used by every absorbed tool exactly
as before the merge: ChkDarkMode, TxtStatus, LoadingPanel, ProcessBar.
These are the fixed names NOSAWindow.SetLoading()/Theme_Toggled() always
target, so every self.TxtStatus.Text = ... / self.SetLoading(...) call
copied verbatim from the original tools keeps working unchanged — it now
writes to the ONE shared hub footer / overlay instead of a per-tool one,
which is exactly the "shared footer written by whichever tab is active"
pattern used by the FootingDesigner pilot merge.
"""
import imp
import io
import os
import sys
import csv
import System.Windows
import System.Windows.Controls as WpfCtrl
import System.Windows.Forms   as WinForms
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_here = os.path.dirname(os.path.abspath(__file__))
_es_logic = imp.load_source('dth_es_logic', os.path.join(_here, 'logic_excel_sync.py'))
_wh_logic = imp.load_source('dth_wh_logic', os.path.join(_here, 'logic_workset_health.py'))
_mc_logic = imp.load_source('dth_mc_logic', os.path.join(_here, 'logic_model_cleanup.py'))
_lm_logic = imp.load_source('dth_lm_logic', os.path.join(_here, 'logic_link_manager.py'))
_tr_logic = imp.load_source('dth_tr_logic', os.path.join(_here, 'logic_type_renamer.py'))

_MATCH_BY_UID  = 'UniqueId'
_MATCH_BY_MARK = 'Mark'
_VIS = System.Windows.Visibility.Visible
_COL = System.Windows.Visibility.Collapsed

_lm_lcm = None


def _lm_lcm_logic():
    """Lazy-load LinkChangeMonitor logic (lives under Structures/Coordination)."""
    global _lm_lcm
    if _lm_lcm is None:
        ext_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..', '..'))
        for suffix in ('nobutton', 'pushbutton'):
            path = os.path.join(ext_root, 'NOSA.tab', 'Structures.panel',
                                'Coordination.pulldown',
                                'LinkChangeMonitor.{}'.format(suffix),
                                'lib', 'logic.py')
            if os.path.isfile(path):
                _lm_lcm = imp.load_source('dth_lm_lcm_logic', path)
                break
        if _lm_lcm is None:
            raise ImportError(u'LinkChangeMonitor logic not found.')
    return _lm_lcm


# ══════════════════════════════════════════════════════════════════════
# Row / item classes (module-level; no naming collisions across tools)
# ══════════════════════════════════════════════════════════════════════

class _WH_WorksetRow(object):
    def __init__(self, rec):
        self.Name     = rec['name']
        self.Count    = str(rec['count'])
        self.Owner    = rec['owner'] or u'—'
        self.Editable = u'Yes' if rec['editable'] else u'No'
        self.Open     = u'Yes' if rec['open'] else u'No'
        self.Visible  = u'Yes' if rec['visible'] else u'No'
        self._id      = rec['id']


class MC_OrphanRow(object):
    def __init__(self, d):
        self.VType = d['type']; self.Name = d['name']; self.Id = d['id']
        self.IsChecked = False


class MC_FamilyRow(object):
    def __init__(self, d):
        self.Category = d['category']; self.Family = d['family']
        self.TypeName = d['type']; self.Id = d['id']
        self.IsChecked = False


class MC_TplRow(object):
    def __init__(self, d):
        self.Name = d['name']; self.Id = d['id']
        self.IsChecked = False


class MC_WarnRow(object):
    def __init__(self, d):
        self.Description = d['description'][:120]; self.ElementCount = d['elements']


class MC_CadRow(object):
    def __init__(self, d):
        self.Name = d['name']; self.View = d['view']
        self.Kind = 'Link' if d['is_linked'] else 'Import'
        self.Id = d['id']; self.IsChecked = False


class MC_RoomRow(object):
    def __init__(self, d):
        self.Number = d['number']; self.Name = d['name']
        self.Level = d['level']; self.Id = d['id']
        self.IsChecked = False


class _LM_LinkRow(object):
    def __init__(self, rec):
        self.LinkName = rec['name']
        self.Kind     = rec['kind']
        self.Status   = rec['status']
        self.LinkPath = rec['path']
        self._rec     = rec


class _TR_TypeRow(object):
    def __init__(self, rec, new_name=u''):
        self.Name    = rec['name']
        self.NewName = new_name if new_name != rec['name'] else u''
        self._rec    = rec


class DataToolsHubWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'data_tools_hub')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._tabs = {
            'NavBtnExcelSync':     self.PanelExcelSync,
            'NavBtnWorksetHealth': self.PanelWorksetHealth,
            'NavBtnModelCleanup':  self.PanelModelCleanup,
            'NavBtnLinkManager':   self.PanelLinkManager,
            'NavBtnTypeRenamer':   self.PanelTypeRenamer,
        }

        self._es_init()
        self._wh_init()
        self._mc_init()
        self._lm_init()
        self._tr_init()

        self.SwitchTab('NavBtnExcelSync', self._tabs)

    def HubNav_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)

    # ══════════════════════════════════════════════════════════════════
    # EXCEL SYNC  (ES_)
    # ══════════════════════════════════════════════════════════════════

    def _es_init(self):
        self._es_csv_path      = None
        self._es_headers       = []
        self._es_rows          = []
        self._es_matched       = []
        self._es_map_boxes     = []
        self._es_mode          = 'params'
        self._es_tbl_path      = None
        self._es_tbl_sheet     = None
        self._es_tbl_headers   = []
        self._es_tbl_rows      = []
        self._es_tbl_map_boxes = []

        self.ES_CboKeyCol.ItemsSource = []
        self.ES_TxtFilePath.Text      = 'No file selected'
        self.ES_TxtPreview.Text       = ''

        self._es_show_mode('params')

    def _es_show_mode(self, mode):
        self._es_mode = mode
        Vis = System.Windows.Visibility
        is_params = mode == 'params'
        self.ES_PanelModeParams.Visibility = Vis.Visible if is_params else Vis.Collapsed
        self.ES_PanelModeTable.Visibility  = Vis.Visible if not is_params else Vis.Collapsed
        if is_params:
            self.ES_TxtPreviewHeader.Text = u'CSV Preview'
            self.ES_TxtMappingHeader.Text  = u'Column Mapping  (CSV column → Revit parameter name)'
        else:
            self.ES_TxtPreviewHeader.Text = u'Table Preview'
            self.ES_TxtMappingHeader.Text  = u'Column Mapping  (worksheet column → Revit parameter name)'

    def ES_Mode_Click(self, sender, args):
        mode = str(sender.Tag)
        self._es_show_mode('params' if mode == 'Params' else 'table')
        if mode == 'Table':
            self._es_build_tbl_mapping()
        else:
            self._es_build_mapping()

    # ── file browse ───────────────────────────────────────────────────────────

    def ES_Browse_Click(self, sender, args):
        dlg = WinForms.OpenFileDialog()
        dlg.Filter = (
            "Spreadsheet files (*.xlsx;*.csv)|*.xlsx;*.csv"
            "|Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm"
            "|CSV (*.csv)|*.csv"
            "|All files (*.*)|*.*"
        )
        dlg.Title  = "Select Excel or CSV File"
        if dlg.ShowDialog() == WinForms.DialogResult.OK:
            self._es_csv_path   = dlg.FileName
            self.ES_TxtFilePath.Text = dlg.FileName
            self._es_clear_state()

    def _es_clear_state(self):
        self._es_headers   = []
        self._es_rows      = []
        self._es_matched   = []
        self._es_map_boxes = []
        self.ES_TxtPreview.Text = ''
        self.ES_MappingPanel.Children.Clear()
        self.ES_BtnApply.IsEnabled = False
        self.TxtStatus.Text = ''

    # ── load CSV ──────────────────────────────────────────────────────────────

    def ES_Load_Click(self, sender, args):
        if not self._es_csv_path:
            forms.alert("Select a CSV file first.")
            return

        self.SetLoading(True, "Reading file...")
        try:
            headers, rows = _es_logic.load_file(self._es_csv_path)
        except ImportError:
            self.SetLoading(False)
            forms.alert(
                "openpyxl is required to read .xlsx files.\n"
                "It should be available in your pyRevit environment.\n\n"
                "Alternatively, save the file as CSV and use that instead."
            )
            return
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Failed to read file:\n{}".format(e))
            return
        self.SetLoading(False)

        self._es_headers = headers
        self._es_rows    = rows

        # Key column combo
        self.ES_CboKeyCol.ItemsSource   = headers
        self.ES_CboKeyCol.SelectedIndex = 0 if headers else -1

        # CSV preview
        self.ES_TxtPreview.Text = _es_logic.format_preview(headers, rows)

        # Build mapping panel (skip the key column at first, rebuild on key change)
        self._es_build_mapping()
        self.ES_BtnApply.IsEnabled = len(rows) > 0

    def _es_build_mapping(self):
        self.ES_MappingPanel.Children.Clear()
        self._es_map_boxes = []

        key_col = self.ES_CboKeyCol.SelectedItem
        non_key = [h for h in self._es_headers if h != key_col]

        if not non_key:
            lbl = WpfCtrl.TextBlock()
            lbl.Text = "(no other columns to map)"
            lbl.Opacity = 0.5
            self.ES_MappingPanel.Children.Add(lbl)
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

            self.ES_MappingPanel.Children.Add(g)
            self._es_map_boxes.append((col, tb))

    def ES_KeyCol_Changed(self, sender, args):
        if self._es_headers:
            self._es_build_mapping()

    # ── apply ─────────────────────────────────────────────────────────────────

    def ES_Apply_Click(self, sender, args):
        if not self._es_rows:
            forms.alert("Load a CSV file first.")
            return

        key_col  = self.ES_CboKeyCol.SelectedItem
        match_by = _MATCH_BY_UID if self.ES_RdoUniqueId.IsChecked == True else _MATCH_BY_MARK

        if not key_col:
            forms.alert("Select a key column.")
            return

        mapping = [(col, tb.Text.strip()) for col, tb in self._es_map_boxes]
        active  = [(c, p) for c, p in mapping if p]
        if not active:
            forms.alert("Enter at least one Revit parameter name in the mapping.")
            return

        self.SetLoading(True, "Matching elements...")
        try:
            matched = _es_logic.match_elements(self.doc, self._es_rows, key_col, match_by)
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
            ok, failed, skipped = _es_logic.apply_mapping(self.doc, matched, mapping)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Apply failed: {}".format(e))
            return
        self.SetLoading(False)

        result = "Done.\n  OK: {}  |  Failed: {}  |  Skipped (no match): {}".format(
            ok, failed, skipped)
        self.TxtStatus.Text = result
        forms.alert(result, title="Excel Sync")

    # ── export Revit → CSV ────────────────────────────────────────────────────

    def ES_Export_Click(self, sender, args):
        raw = self.ES_TxtExportParams.Text or ''
        param_names = [p.strip() for p in raw.splitlines() if p.strip()]
        if not param_names:
            forms.alert("Enter at least one parameter name in the export list.")
            return

        match_by = _MATCH_BY_UID if self.ES_RdoUniqueId.IsChecked == True else _MATCH_BY_MARK

        dlg = WinForms.SaveFileDialog()
        dlg.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        dlg.Title  = "Save exported parameters as CSV"
        dlg.FileName = "revit_export.csv"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return

        self.SetLoading(True, "Exporting parameters...")
        try:
            row_count, missing = _es_logic.export_to_csv(
                self.doc, param_names, match_by, dlg.FileName)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Export failed:\n{}".format(e))
            return
        self.SetLoading(False)

        msg = u"Exported {} elements to:\n{}".format(row_count, dlg.FileName)
        if missing:
            msg += u"\n\nParameters not found on any element:\n  {}".format(
                u"\n  ".join(missing))
        self.TxtStatus.Text = u"Exported {} rows.".format(row_count)
        forms.alert(msg, title="Export Complete")

    # ── Import Table mode ─────────────────────────────────────────────────────

    def ES_TblBrowse_Click(self, sender, args):
        dlg = WinForms.OpenFileDialog()
        dlg.Filter = "Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|All files (*.*)|*.*"
        dlg.Title  = "Select Excel Workbook"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        self._es_tbl_path = dlg.FileName
        self.ES_TxtTblFilePath.Text = dlg.FileName
        self._es_tbl_headers = []
        self._es_tbl_rows = []
        self._es_tbl_map_boxes = []
        self.ES_TxtPreview.Text = ''
        self.ES_BtnTblApply.IsEnabled = False
        try:
            sheets = _es_logic.list_workbook_sheets(self._es_tbl_path)
        except ImportError:
            forms.alert("openpyxl is required to read Excel workbooks.")
            return
        except Exception as e:
            forms.alert("Failed to read workbook:\n{}".format(e))
            return
        self.ES_CboTblSheet.ItemsSource = sheets
        self.ES_CboTblSheet.SelectedIndex = 0 if sheets else -1

    def ES_TblSheet_Changed(self, sender, args):
        if not self._es_tbl_path or self.ES_CboTblSheet.SelectedItem is None:
            return
        self._es_tbl_sheet = str(self.ES_CboTblSheet.SelectedItem)
        self._es_clear_tbl_state(keep_path=True)

    def _es_clear_tbl_state(self, keep_path=False):
        self._es_tbl_headers = []
        self._es_tbl_rows = []
        self._es_tbl_map_boxes = []
        if not keep_path:
            self._es_tbl_path = None
            self.ES_TxtTblFilePath.Text = 'No file selected'
        self.ES_TxtPreview.Text = ''
        self.ES_MappingPanel.Children.Clear()
        self.ES_BtnTblApply.IsEnabled = False
        self.ES_TxtTblStatus.Text = ''

    def ES_TblLoad_Click(self, sender, args):
        if not self._es_tbl_path or not self._es_tbl_sheet:
            forms.alert("Select an Excel file and worksheet first.")
            return
        self.SetLoading(True, "Reading worksheet...")
        try:
            headers, rows = _es_logic.load_xlsx_sheet(self._es_tbl_path, self._es_tbl_sheet)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Failed to read worksheet:\n{}".format(e))
            return
        self.SetLoading(False)
        self._es_tbl_headers = headers
        self._es_tbl_rows = rows
        self.ES_CboTblKeyCol.ItemsSource = headers
        self.ES_CboTblKeyCol.SelectedIndex = 0 if headers else -1
        self.ES_TxtPreview.Text = _es_logic.format_preview(headers, rows)
        self._es_build_tbl_mapping()
        self.ES_BtnTblApply.IsEnabled = len(rows) > 0

    def _es_build_tbl_mapping(self):
        self.ES_MappingPanel.Children.Clear()
        self._es_tbl_map_boxes = []
        key_col = self.ES_CboTblKeyCol.SelectedItem
        headers = self._es_tbl_headers if self._es_mode == 'table' else self._es_headers
        non_key = [h for h in headers if h != key_col]
        if not non_key:
            lbl = WpfCtrl.TextBlock()
            lbl.Text = "(no other columns to map)"
            lbl.Opacity = 0.5
            self.ES_MappingPanel.Children.Add(lbl)
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
            lbl.Text = col
            lbl.VerticalAlignment = System.Windows.VerticalAlignment.Center
            lbl.FontSize = 12
            WpfCtrl.Grid.SetColumn(lbl, 0)
            g.Children.Add(lbl)
            tb = WpfCtrl.TextBox()
            tb.Height = 26
            tb.FontSize = 12
            tb.Padding = System.Windows.Thickness(4, 2, 4, 2)
            WpfCtrl.Grid.SetColumn(tb, 1)
            g.Children.Add(tb)
            self.ES_MappingPanel.Children.Add(g)
            self._es_tbl_map_boxes.append((col, tb))

    def ES_TblKeyCol_Changed(self, sender, args):
        if self._es_tbl_headers:
            self._es_build_tbl_mapping()

    def ES_TblApply_Click(self, sender, args):
        if not self._es_tbl_rows:
            forms.alert("Load a worksheet first.")
            return
        key_col = self.ES_CboTblKeyCol.SelectedItem
        match_by = _MATCH_BY_UID if self.ES_RdoTblUniqueId.IsChecked == True else _MATCH_BY_MARK
        if not key_col:
            forms.alert("Select a key column.")
            return
        mapping = [(col, tb.Text.strip()) for col, tb in self._es_tbl_map_boxes]
        active = [(c, p) for c, p in mapping if p]
        if not active:
            forms.alert("Enter at least one Revit parameter name in the mapping.")
            return
        self.SetLoading(True, "Matching elements...")
        try:
            matched = _es_logic.match_elements(self.doc, self._es_tbl_rows, key_col, match_by)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Match failed: {}".format(e))
            return
        matched_count = sum(1 for m in matched if m['matched'])
        if matched_count == 0:
            self.SetLoading(False)
            forms.alert("No elements matched. Check key column values in the model.")
            return
        info = "Apply {} mapping(s) to {} element(s) from worksheet '{}'?".format(
            len(active), matched_count, self._es_tbl_sheet)
        if not forms.alert(info, yes=True, no=True):
            self.SetLoading(False)
            return
        self.SetLoading(True, "Applying parameters...")
        try:
            ok, failed, skipped = _es_logic.apply_mapping(self.doc, matched, mapping)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Apply failed: {}".format(e))
            return
        self.SetLoading(False)
        result = "Done.\n  OK: {}  |  Failed: {}  |  Skipped: {}".format(ok, failed, skipped)
        self.ES_TxtTblStatus.Text = result
        forms.alert(result, title="Import Table")

    # ══════════════════════════════════════════════════════════════════
    # WORKSET HEALTH  (WH_)
    # ══════════════════════════════════════════════════════════════════

    def _wh_init(self):
        self._wh_stats = []
        if not _wh_logic.is_workshared(self.doc):
            self.TxtStatus.Text = u'This model is not workshared. Worksets are not available.'
            self.WH_TxtSubtitle.Text = u'(not workshared)'
        else:
            self._wh_load()

    def _wh_load(self):
        self._wh_stats = _wh_logic.get_workset_stats(self.doc)
        self._wh_rows  = [_WH_WorksetRow(s) for s in self._wh_stats]
        self._wh_apply_search()

        self.WH_CboTargetWorkset.Items.Clear()
        for s in self._wh_stats:
            self.WH_CboTargetWorkset.Items.Add(s)
        if self.WH_CboTargetWorkset.Items.Count > 0:
            self.WH_CboTargetWorkset.SelectedIndex = 0

        total_el = sum(s['count'] for s in self._wh_stats)
        self.WH_TxtSubtitle.Text = u'{} worksets · {} elements total'.format(
            len(self._wh_stats), total_el)
        self.TxtStatus.Text = u'Ready.'

    def _wh_apply_search(self):
        try:
            text = (self.WH_TxtSearch.Text or u'').strip().lower()
        except Exception:
            text = u''
        rows = getattr(self, '_wh_rows', [])
        if text:
            rows = [r for r in rows
                    if text in r.Name.lower() or text in r.Owner.lower()]
        self.WH_GridWorksets.ItemsSource = rows

    def WH_Search_Changed(self, sender, args):
        self._wh_apply_search()

    def WH_Grid_SelectionChanged(self, sender, args):
        pass

    def WH_MoveElements_Click(self, sender, args):
        selected_rows = list(self.WH_GridWorksets.SelectedItems)
        if not selected_rows:
            self.TxtStatus.Text = u'Select a source workset row first.'
            return
        target = self.WH_CboTargetWorkset.SelectedItem
        if target is None:
            self.TxtStatus.Text = u'Select a target workset.'
            return

        source_ids = {row._id for row in selected_rows}
        if target['id'] in source_ids:
            self.TxtStatus.Text = u'Source and target worksets must differ.'
            return

        els = _wh_logic.get_elements_on_worksets(self.doc, source_ids)

        if not els:
            self.TxtStatus.Text = u'No elements on selected workset(s).'
            return

        el_ids = [el.Id for el in els]
        self.SetLoading(True, u'Moving elements…')
        try:
            moved, failed = _wh_logic.move_elements_to_workset(
                self.doc, el_ids, target['id'])
        finally:
            self.SetLoading(False)

        self.TxtStatus.Text = u'Moved {} elements to "{}". {} could not be moved.'.format(
            moved, target['name'], failed)
        self._wh_load()

    def WH_Refresh_Click(self, sender, args):
        self._wh_load()

    def WH_Close_Click(self, sender, args):
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # MODEL CLEANUP  (MC_)
    # ══════════════════════════════════════════════════════════════════

    def _mc_init(self):
        self.doc_mc = self.doc
        self._mc_data = None

        self._mc_tabs = {
            'MC_BtnTabOrphans':   self.MC_TabOrphans,
            'MC_BtnTabFamilies':  self.MC_TabFamilies,
            'MC_BtnTabTemplates': self.MC_TabTemplates,
            'MC_BtnTabCAD':       self.MC_TabCAD,
            'MC_BtnTabRooms':     self.MC_TabRooms,
            'MC_BtnTabWarnings':  self.MC_TabWarnings,
        }

        self._mc_orphan_rows   = ObservableCollection[MC_OrphanRow]()
        self._mc_family_rows   = ObservableCollection[MC_FamilyRow]()
        self._mc_template_rows = ObservableCollection[MC_TplRow]()
        self._mc_warn_rows     = ObservableCollection[MC_WarnRow]()
        self._mc_cad_rows      = ObservableCollection[MC_CadRow]()
        self._mc_room_rows     = ObservableCollection[MC_RoomRow]()

        self.MC_TabOrphans.ItemsSource   = self._mc_orphan_rows
        self.MC_TabFamilies.ItemsSource  = self._mc_family_rows
        self.MC_TabTemplates.ItemsSource = self._mc_template_rows
        self.MC_TabWarnings.ItemsSource  = self._mc_warn_rows
        self.MC_TabCAD.ItemsSource       = self._mc_cad_rows
        self.MC_TabRooms.ItemsSource     = self._mc_room_rows

    # ── navigation ────────────────────────────────────────────────────────────

    def MC_NavButton_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._mc_tabs)
        self._mc_update_actions()

    # ── scan ─────────────────────────────────────────────────────────────────

    def MC_Scan_Click(self, sender, args):
        self.SetLoading(True, 'Scanning model...')
        for col in (self._mc_orphan_rows, self._mc_family_rows, self._mc_template_rows,
                    self._mc_warn_rows, self._mc_cad_rows, self._mc_room_rows):
            col.Clear()
        self.MC_BtnExport.IsEnabled = self.MC_BtnPurge.IsEnabled = False

        try:
            self._mc_data = _mc_logic.run_all(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error: {}".format(e))
            return

        s = self._mc_data['summary']
        self.MC_TxtOrphans.Text   = "{} orphan views".format(s['orphan_views'])
        self.MC_TxtFamilies.Text  = "{} unused types".format(s['unused_families'])
        self.MC_TxtTemplates.Text = "{} unused templates".format(s['unused_templates'])
        self.MC_TxtWarnings.Text  = "{} trivial warnings".format(s['trivial_warnings'])
        self.MC_TxtCAD.Text       = "{} CAD imports".format(s['cad_imports'])
        self.MC_TxtRooms.Text     = "{} unplaced rooms".format(s['unplaced_rooms'])

        for r in self._mc_data['orphan_views']:    self._mc_orphan_rows.Add(MC_OrphanRow(r))
        for r in self._mc_data['unused_families']: self._mc_family_rows.Add(MC_FamilyRow(r))
        for r in self._mc_data['unused_templates']:self._mc_template_rows.Add(MC_TplRow(r))
        for r in self._mc_data['trivial_warnings']:self._mc_warn_rows.Add(MC_WarnRow(r))
        for r in self._mc_data['cad_imports']:     self._mc_cad_rows.Add(MC_CadRow(r))
        for r in self._mc_data['unplaced_rooms']:  self._mc_room_rows.Add(MC_RoomRow(r))

        self.SetLoading(False)
        self.MC_BtnExport.IsEnabled = True
        self._mc_update_actions()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _mc_active_tab_name(self):
        for name, grid in self._mc_tabs.items():
            if grid.Visibility == System.Windows.Visibility.Visible:
                return name
        return ''

    def _mc_update_actions(self):
        tab = self._mc_active_tab_name()
        can_select = tab == 'MC_BtnTabOrphans' and self.MC_TabOrphans.SelectedItem is not None
        self.MC_BtnSelect.IsEnabled = can_select
        purgeable_tabs = ('MC_BtnTabOrphans', 'MC_BtnTabFamilies', 'MC_BtnTabTemplates',
                          'MC_BtnTabCAD', 'MC_BtnTabRooms')
        tab_grid_map = {
            'MC_BtnTabOrphans':   self.MC_TabOrphans,
            'MC_BtnTabFamilies':  self.MC_TabFamilies,
            'MC_BtnTabTemplates': self.MC_TabTemplates,
            'MC_BtnTabCAD':       self.MC_TabCAD,
            'MC_BtnTabRooms':     self.MC_TabRooms,
        }
        if tab in purgeable_tabs and self._mc_data is not None:
            grid = tab_grid_map.get(tab)
            has_selection = grid is not None and grid.SelectedItems and len(list(grid.SelectedItems)) > 0
            self.MC_BtnPurge.IsEnabled = has_selection
        else:
            self.MC_BtnPurge.IsEnabled = False

    def MC_Grid_SelectionChanged(self, sender, args):
        self._mc_update_actions()

    # ── select ────────────────────────────────────────────────────────────────

    def MC_Select_Click(self, sender, args):
        row = self.MC_TabOrphans.SelectedItem
        if not row or not hasattr(row, 'Id'): return
        try:
            from Autodesk.Revit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    # ── purge ─────────────────────────────────────────────────────────────────

    def MC_Purge_Click(self, sender, args):
        tab = self._mc_active_tab_name()
        if tab == 'MC_BtnTabOrphans':
            self._mc_purge_orphans()
        elif tab == 'MC_BtnTabFamilies':
            self._mc_purge_families()
        elif tab == 'MC_BtnTabTemplates':
            self._mc_purge_templates()
        elif tab == 'MC_BtnTabCAD':
            self._mc_purge_cad()
        elif tab == 'MC_BtnTabRooms':
            self._mc_purge_rooms()

    def _mc_selected_rows(self, grid):
        return list(grid.SelectedItems) if grid.SelectedItems else []

    @property
    def _mc_dry_run(self):
        try:
            return bool(self.MC_ChkDryRun.IsChecked)
        except Exception:
            return False

    def _mc_confirm_purge(self, label, rows):
        n = len(rows)
        if n == 0:
            forms.alert("Select rows to delete first (Ctrl+click or Shift+click for multiple).")
            return False
        if self._mc_dry_run:
            forms.alert(
                u"DRY RUN — {} {} would be deleted.\n"
                u"No changes have been made to the model.\n\n"
                u"Uncheck 'Dry Run' to perform the actual deletion.".format(n, label),
                title="Dry Run Preview"
            )
            return False
        return forms.alert(
            "Permanently delete {} {}?\nThis cannot be undone.".format(n, label),
            yes=True, no=True
        )

    def _mc_purge_orphans(self):
        rows = self._mc_selected_rows(self.MC_TabOrphans)
        if not self._mc_confirm_purge("orphan view(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting orphan views...")
        deleted, failed = _mc_logic.purge_orphan_views(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Views")
        self.MC_Scan_Click(None, None)

    def _mc_purge_families(self):
        rows = self._mc_selected_rows(self.MC_TabFamilies)
        if not self._mc_confirm_purge("unused family type(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting unused families...")
        deleted, failed = _mc_logic.purge_unused_families(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Families")
        self.MC_Scan_Click(None, None)

    def _mc_purge_templates(self):
        rows = self._mc_selected_rows(self.MC_TabTemplates)
        if not self._mc_confirm_purge("unused template(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting unused templates...")
        deleted, failed = _mc_logic.purge_unused_templates(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Templates")
        self.MC_Scan_Click(None, None)

    def _mc_purge_cad(self):
        rows = [r for r in self._mc_selected_rows(self.MC_TabCAD) if r.Kind == 'Import']
        if not self._mc_confirm_purge("CAD import(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting CAD imports...")
        deleted, failed = _mc_logic.purge_cad_imports(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {} (links are skipped)".format(deleted, failed),
                    title="Delete CAD Imports")
        self.MC_Scan_Click(None, None)

    def _mc_purge_rooms(self):
        rows = self._mc_selected_rows(self.MC_TabRooms)
        if not self._mc_confirm_purge("unplaced room(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting unplaced rooms...")
        deleted, failed = _mc_logic.purge_unplaced_rooms(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Rooms")
        self.MC_Scan_Click(None, None)

    # ── quick purge ───────────────────────────────────────────────────────────

    def MC_QuickPurgeAll_Click(self, sender, args):
        if not forms.alert(
            u'Quick Purge All will scan the model and permanently delete:\n'
            u'  • All orphan views\n'
            u'  • All unused family types\n'
            u'  • All unused view templates\n'
            u'  • All CAD imports (not links)\n'
            u'  • All unplaced rooms\n\n'
            u'This cannot be undone. Continue?',
            yes=True, no=True, title=u'Quick Purge All'
        ):
            return
        self.SetLoading(True, u'Scanning model...')
        try:
            data = _mc_logic.run_all(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Scan failed: {}'.format(e))
            return

        results = []
        cats = [
            ('orphan views',       data['orphan_views'],    _mc_logic.purge_orphan_views,    'id'),
            ('unused family types', data['unused_families'], _mc_logic.purge_unused_families, 'id'),
            ('unused templates',    data['unused_templates'],_mc_logic.purge_unused_templates,'id'),
            ('CAD imports',         [r for r in data['cad_imports'] if not r.get('is_linked')],
                                                             _mc_logic.purge_cad_imports,     'id'),
            ('unplaced rooms',      data['unplaced_rooms'], _mc_logic.purge_unplaced_rooms,  'id'),
        ]
        for label, items, purge_fn, id_key in cats:
            if not items:
                results.append(u'  {} — none found'.format(label))
                continue
            ids = [r[id_key] for r in items]
            self.SetLoading(True, u'Purging {}...'.format(label))
            try:
                deleted, failed = purge_fn(self.doc, ids)
                results.append(u'  {} — deleted {}, failed {}'.format(label, deleted, failed))
            except Exception as e:
                results.append(u'  {} — ERROR: {}'.format(label, e))

        self.SetLoading(False)
        forms.alert(u'Quick Purge Complete:\n' + u'\n'.join(results), title=u'Quick Purge Results')
        self.MC_Scan_Click(None, None)

    # ── export ────────────────────────────────────────────────────────────────

    def MC_Export_Click(self, sender, args):
        if not self._mc_data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['=== ORPHAN VIEWS ==='])
                w.writerow(['Type', 'Name', 'ID'])
                for r in self._mc_orphan_rows: w.writerow([r.VType, r.Name, r.Id])
                w.writerow([])
                w.writerow(['=== UNUSED FAMILY TYPES ==='])
                w.writerow(['Category', 'Family', 'Type', 'ID'])
                for r in self._mc_family_rows: w.writerow([r.Category, r.Family, r.TypeName, r.Id])
                w.writerow([])
                w.writerow(['=== UNUSED TEMPLATES ==='])
                w.writerow(['Name', 'ID'])
                for r in self._mc_template_rows: w.writerow([r.Name, r.Id])
                w.writerow([])
                w.writerow(['=== CAD IMPORTS ==='])
                w.writerow(['Name', 'View', 'Kind', 'ID'])
                for r in self._mc_cad_rows: w.writerow([r.Name, r.View, r.Kind, r.Id])
                w.writerow([])
                w.writerow(['=== UNPLACED ROOMS ==='])
                w.writerow(['Number', 'Name', 'Level', 'ID'])
                for r in self._mc_room_rows: w.writerow([r.Number, r.Name, r.Level, r.Id])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    # ══════════════════════════════════════════════════════════════════
    # LINK MANAGER  (LM_)
    # ══════════════════════════════════════════════════════════════════

    def _lm_init(self):
        self._lm_data = []
        self._lm_load()

    def _lm_load(self):
        self._lm_data = _lm_logic.collect_all(self.doc)
        self._lm_rows = [_LM_LinkRow(r) for r in self._lm_data]
        self._lm_apply_search()
        rvt     = sum(1 for r in self._lm_data if r['kind'] == u'RVT Link')
        cad     = sum(1 for r in self._lm_data if u'CAD' in r['kind'])
        missing = sum(1 for r in self._lm_data if r['status'] == u'Missing')
        try:
            self.LM_TxtSummary.Text = u'{} RVT · {} CAD · {} missing'.format(rvt, cad, missing)
        except Exception:
            pass
        try:
            self.TxtStatus.Text = u'{} links found.'.format(len(self._lm_data))
        except Exception:
            pass

    def _lm_apply_search(self):
        try:
            text = (self.LM_TxtSearch.Text or u'').strip().lower()
        except Exception:
            text = u''
        rows = getattr(self, '_lm_rows', [])
        if text:
            rows = [r for r in rows
                    if text in r.LinkName.lower()
                    or text in r.Kind.lower()
                    or text in r.Status.lower()
                    or text in r.LinkPath.lower()]
        self.LM_GridLinks.ItemsSource = rows

    def LM_Search_Changed(self, sender, args):
        self._lm_apply_search()

    def _lm_selected_rows(self):
        return list(self.LM_GridLinks.SelectedItems)

    def LM_Reload_Click(self, sender, args):
        rows = self._lm_selected_rows()
        if not rows:
            self.TxtStatus.Text = u'Select links to reload.'
            return
        self.SetLoading(True, u'Reloading…')
        ok = fail = 0
        try:
            for row in rows:
                if row._rec['kind'] != u'RVT Link':
                    continue
                try:
                    _lm_logic.reload_link(self.doc, row._rec['element'])
                    ok += 1
                except Exception as ex:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Reloaded {}. Failed: {}.'.format(ok, fail)
        self._lm_load()

    def LM_Unload_Click(self, sender, args):
        rows = self._lm_selected_rows()
        if not rows:
            self.TxtStatus.Text = u'Select links to unload.'
            return
        self.SetLoading(True, u'Unloading…')
        ok = fail = 0
        try:
            for row in rows:
                if row._rec['kind'] != u'RVT Link':
                    continue
                try:
                    _lm_logic.unload_link(self.doc, row._rec['element'])
                    ok += 1
                except Exception as ex:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Unloaded {}. Failed: {}.'.format(ok, fail)
        self._lm_load()

    def LM_Remove_Click(self, sender, args):
        rows = self._lm_selected_rows()
        if not rows:
            self.TxtStatus.Text = u'Select links to remove.'
            return
        try:
            from pyrevit import forms as _forms
            if not _forms.alert(
                    u'Remove {} link(s) from the model?'.format(len(rows)),
                    title=u'Confirm Remove', yes=True, no=True):
                return
        except Exception:
            pass
        ok = fail = 0
        self.SetLoading(True, u'Removing…')
        try:
            for row in rows:
                try:
                    _lm_logic.remove_link(self.doc, row._rec['id'])
                    ok += 1
                except Exception:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Removed {}. Failed: {}.'.format(ok, fail)
        self._lm_load()

    def LM_ReloadAllMissing_Click(self, sender, args):
        missing = [r for r in self._lm_data if r['status'] == u'Missing' and r['kind'] == u'RVT Link']
        if not missing:
            self.TxtStatus.Text = u'No missing RVT links found.'
            return
        ok = fail = 0
        self.SetLoading(True, u'Reloading missing links…')
        try:
            for rec in missing:
                try:
                    _lm_logic.reload_link(self.doc, rec['element'])
                    ok += 1
                except Exception:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Reload attempted on {} missing links. OK: {}  Failed: {}.'.format(
            len(missing), ok, fail)
        self._lm_load()

    def LM_Refresh_Click(self, sender, args):
        self._lm_load()

    def LM_Snapshot_Click(self, sender, args):
        try:
            lcm = _lm_lcm_logic()
            links = lcm.get_links(self.doc)
        except Exception as e:
            self.TxtStatus.Text = u'Change monitor unavailable: {}'.format(e)
            return
        if not links:
            self.TxtStatus.Text = u'No loaded RVT link instances to snapshot.'
            return
        self.SetLoading(True, u'Taking snapshots…')
        ok = fail = 0
        try:
            for link in links:
                try:
                    lcm.take_snapshot(self.doc, link)
                    ok += 1
                except Exception:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = (u'Baseline snapshot saved for {} link(s). '
                               u'Failed: {}.'.format(ok, fail))

    def LM_Changes_Click(self, sender, args):
        try:
            lcm = _lm_lcm_logic()
            links = lcm.get_links(self.doc)
        except Exception as e:
            self.TxtStatus.Text = u'Change monitor unavailable: {}'.format(e)
            return
        if not links:
            self.TxtStatus.Text = u'No loaded RVT link instances to compare.'
            return
        self.SetLoading(True, u'Comparing against snapshots…')
        lines = []
        total = 0
        try:
            for link in links:
                try:
                    name = link.Name
                except Exception:
                    name = u'(link)'
                try:
                    changes = lcm.compare_link(self.doc, link)
                except Exception as e:
                    changes = [type('X', (object,), {
                        'category': u'Error', 'detail': u'{}'.format(e),
                        'severity': 'red'})()]
                lines.append(u'')
                lines.append(u'=== {} — {} change(s) ==='.format(name, len(changes)))
                for c in changes:
                    total += 1
                    lines.append(u'  [{}] {}: {}'.format(
                        c.severity.upper(), c.category, c.detail))
        finally:
            self.SetLoading(False)

        from pyrevit import forms as _forms
        report = u'\n'.join(lines).strip()
        if len(lines) <= 28:
            _forms.alert(report or u'No changes detected.',
                         title=u'Link Changes')
        else:
            import tempfile, io as _io, datetime as _dt
            path = os.path.join(
                tempfile.gettempdir(),
                'nosa_link_changes_{}.txt'.format(_dt.datetime.now().strftime('%H%M%S')))
            with _io.open(path, 'w', encoding='utf-8-sig') as f:
                f.write(report)
            try:
                os.startfile(path)
            except Exception:
                _forms.alert(u'Report saved to:\n{}'.format(path),
                             title=u'Link Changes')
        self.TxtStatus.Text = u'{} change(s) across {} link(s).'.format(total, len(links))

    def LM_Close_Click(self, sender, args):
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # TYPE RENAMER  (TR_)
    # ══════════════════════════════════════════════════════════════════

    def _tr_init(self):
        self._tr_type_data = []

        for cat in _tr_logic.category_names():
            self.TR_CboCategory.Items.Add(cat)
        if self.TR_CboCategory.Items.Count > 0:
            self.TR_CboCategory.SelectedIndex = 0

        self.TR_RbFindReplace.IsChecked = True
        self.TR_PnlFindReplace.Visibility  = _VIS
        self.TR_PnlPrefixSuffix.Visibility = _COL
        self.TxtStatus.Text = u'Select a category to load types.'

    def _tr_get_mode(self):
        return u'find_replace' if self.TR_RbFindReplace.IsChecked else u'prefix_suffix'

    def _tr_rebuild_preview(self):
        mode    = self._tr_get_mode()
        find    = self.TR_TxtFind.Text
        replace = self.TR_TxtReplace.Text
        prefix  = self.TR_TxtPrefix.Text
        suffix  = self.TR_TxtSuffix.Text

        pairs = _tr_logic.preview_rename(
            [r['name'] for r in self._tr_type_data],
            mode, find, replace, prefix, suffix)

        rows = []
        for i, (old, new) in enumerate(pairs):
            rows.append(_TR_TypeRow(self._tr_type_data[i], new))

        try:
            search = (self.TR_TxtSearch.Text or u'').strip().lower()
        except Exception:
            search = u''
        if search:
            rows = [r for r in rows
                    if search in r.Name.lower() or search in r.NewName.lower()]
        self.TR_GridTypes.ItemsSource = rows

    def TR_Category_Changed(self, sender, args):
        cat = self.TR_CboCategory.SelectedItem
        if not cat:
            return
        self._tr_type_data = _tr_logic.get_types_for_category(self.doc, cat)
        self._tr_rebuild_preview()
        self.TxtStatus.Text = u'{} types loaded.'.format(len(self._tr_type_data))

    def TR_Mode_Changed(self, sender, args):
        is_fr = bool(self.TR_RbFindReplace.IsChecked)
        self.TR_PnlFindReplace.Visibility  = _VIS if is_fr else _COL
        self.TR_PnlPrefixSuffix.Visibility = _COL if is_fr else _VIS
        self._tr_rebuild_preview()

    def TR_Rule_Changed(self, sender, args):
        self._tr_rebuild_preview()

    def TR_Search_Changed(self, sender, args):
        self._tr_rebuild_preview()

    def TR_Grid_SelectionChanged(self, sender, args):
        n = self.TR_GridTypes.SelectedItems.Count
        if n:
            self.TxtStatus.Text = u'{} type{} selected.'.format(n, u's' if n != 1 else u'')
        else:
            self.TxtStatus.Text = u'{} types loaded.'.format(len(self._tr_type_data))

    def TR_SelectAll_Click(self, sender, args):
        self.TR_GridTypes.SelectAll()

    def TR_ApplyRename_Click(self, sender, args):
        selected = list(self.TR_GridTypes.SelectedItems)
        if not selected:
            self.TR_TxtFormStatus.Text = u'Select at least one type to rename.'
            return

        pairs = []
        for row in selected:
            new = row.NewName
            if new and new != row.Name:
                pairs.append((row._rec['element'], new))

        if not pairs:
            self.TR_TxtFormStatus.Text = u'No name changes detected — check find/prefix settings.'
            return

        self.SetLoading(True, u'Renaming types…')
        try:
            renamed, failed, errors = _tr_logic.apply_renames(self.doc, pairs)
        finally:
            self.SetLoading(False)

        msg = u'Renamed {}. Failed: {}.'.format(renamed, failed)
        if errors:
            msg += u'  ' + u'; '.join(errors[:3])
        self.TR_TxtFormStatus.Text = msg
        self.TR_Category_Changed(None, None)

    def TR_Close_Click(self, sender, args):
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
