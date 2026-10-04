# -*- coding: utf-8 -*-
import clr
try:
    clr.AddReference('System.Drawing')
    clr.AddReference('System.Windows.Forms')
    clr.AddReference('PresentationCore')
    clr.AddReference('PresentationFramework')
except Exception:  # nosa-lint: disable=NOSA006 - assemblies usually already referenced; runs before nosa_utils is importable
    pass

import os
import re
import System
from System.Windows import MessageBox
from System.Windows.Controls import DataGridTextColumn, DataGridLength
from System.Windows.Data import Binding
from System.Windows.Media import Brushes, Color, SolidColorBrush
from System.Collections.Generic import Dictionary
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms

from nosa_utils.base_window import NOSAWindow
from nosa_utils.telemetry import log_swallowed
from nosa_utils.logging import Logger
from nosa_utils import sheet_protocol as _sp
_LOG = u'SheetExportHub/ui'

from managers import ViewSetManager, ExportPresetManager
from utils import Utils
from view_collector import ViewCollector
from exporters import ExportManager
from naming import NamingBuilder
from validation import ExportValidator
import column_presets
import param_editor

logger = Logger()


class SheetItem(object):
    """
    Wrapper for one sheet/view row. Params holds EVERY parameter value found
    on the element (string, via Utils.get_sheet_parameters / ViewCollector.
    get_view_parameters — both already cached), keyed by name. DataGrid
    columns bind to Params[Name] via an indexer path, so switching the active
    column preset only rebuilds column definitions, never reloads data.

    Sheets only: two corrections on top of the raw per-element parameter
    scan, since most sheets don't carry their own copy of these —
      - Project Number / Originator are project-scoped in the NOSA protocol;
        fall back to Project Information (nosa_utils.sheet_protocol) when
        the sheet-level value is blank.
      - Document Number (NOSA field 7) isn't its own shared parameter on the
        sheet at all — it's shown as the sheet's actual Sheet Number value.
    """
    def __init__(self, doc, element, is_view=False):
        self.Element = element
        self.Id = element.Id
        self.IsChecked = False
        self.HasPending = False

        if is_view:
            raw = ViewCollector.get_view_parameters(element)
            self.Number = raw.get('View Number') or str(getattr(element, 'ViewType', ''))
            self.Name = element.Name
        else:
            raw = Utils.get_sheet_parameters(element)
            self.Number = element.SheetNumber
            self.Name = element.Name

        self.Params = Dictionary[str, str]()
        for k, v in raw.items():
            self.Params[k] = v if v is not None else ''
        if 'Sheet Number' not in self.Params and not is_view:
            self.Params['Sheet Number'] = self.Number or ''
        if 'Sheet Name' not in self.Params:
            self.Params['Sheet Name'] = self.Name or ''

        if not is_view:
            if not self._val('Project Number'):
                self.Params['Project Number'] = _sp.read_project_number(doc, element) or ''
            if not self._val('Originator'):
                self.Params['Originator'] = _sp.read_originator(doc, element) or ''
            self.Params['Document Number'] = self.Number or ''

    def _val(self, name):
        return self.Params[name] if name in self.Params else ''


class ExportPresetItem(object):
    """Wrapper for ComboExportPreset items (DisplayMemberPath='Name')."""
    def __init__(self, name):
        self.Name = name

    def __str__(self):
        return self.Name


class SheetExportHubWindow(NOSAWindow):
    """Sheet Export Hub — two-panel batch export UI with configurable
    columns and inline/batch sheet parameter editing."""

    def __init__(self, doc):
        self._is_initializing = True
        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml_file, 'sheet_export_hub')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.ComboDiscipline.SelectionChanged += self.Discipline_Changed
        self.ComboColumnPreset.SelectionChanged += self.ColumnPreset_Changed
        self.ComboExportPreset.SelectionChanged += self.ExportPreset_Selected
        self.ComboQualityPreset.SelectionChanged += self.QualityPreset_Changed
        self.ComboDwgSetup.SelectionChanged += self.DwgSetup_Changed
        self.doc = doc
        # NOSAWindow.ApplyTheme() applies colors but doesn't touch this
        # checkbox itself (each subclass is expected to sync it, same as
        # Drawing Index does).
        self.ChkDarkMode.IsChecked = self.dark_mode

        self.naming_builder = NamingBuilder()
        self.output_folder = ""
        self.subfolder = ""
        self.quality_preset = "Standard"
        self.is_exporting_views = False
        # None = use the fixed NOSA quality preset; otherwise the name of a
        # DWG Export Setup already saved in this document.
        self.dwg_setup_name = None
        self.combined_pdf_name = "Combined Export"
        # Sheets and Views need different columns (Sheet Number / Project
        # Number / Originator etc. don't apply to views) — tracked
        # separately per mode, active_column_preset is just whichever of
        # the two applies right now (kept in sync by _sync_active_preset).
        self.sheet_column_preset = column_presets.DEFAULT_PRESET_NAME
        self.view_column_preset = column_presets.DEFAULT_VIEW_PRESET_NAME
        self.active_column_preset = self.sheet_column_preset
        self._pending_changes = {}   # {sheet_number: {param_name: new_value}}
        self._suspend_status_update = False

        self.sheet_items = ObservableCollection[SheetItem]()
        self.project_params = {}
        self.GridSheets.ItemsSource = self.sheet_items

        # Row selection highlight, painted directly on the row containers
        # rather than via a Style/ControlTemplate trigger. WPF's built-in
        # DataGridRow template paints IsSelected through its own theme
        # VisualStates, which sit above a Style.Trigger in dependency-
        # property precedence, so a styled Background never actually showed
        # even though IsSelected really was True (SelectedItems/"Check
        # Highlighted" always worked correctly). A LOCAL value set here
        # beats that theme visual outright, in any WPF host. LoadingRow
        # re-applies it to containers recycled by virtualisation (scrolling,
        # or the grid swapping ItemsSource when the search box filters).
        self.GridSheets.SelectionChanged += self.GridSheets_SelectionChanged
        self.GridSheets.LoadingRow += self.GridSheets_LoadingRow

        self.sub_tabs = {
            "BtnSubNaming": self.SubNaming,
            "BtnSubPdf": self.SubPdf,
            "BtnSubFormats": self.SubFormats,
        }

        self._load_quality_presets()
        self._load_dwg_setups()
        self._load_export_presets()
        self._load_sheet_sets()

        self._apply_config(self.LoadConfig())
        self._sync_active_preset()

        self.LoadData()
        self._load_discipline_filter()
        self._apply_filters()
        self._load_column_presets()
        self.RebuildColumns()

        self.SwitchTab("BtnSubNaming", self.sub_tabs)
        self.UpdatePreview()
        self.UpdateStatus()

        self._is_initializing = False

    # =========================================================================
    # DATA LOADING
    # =========================================================================

    def LoadData(self):
        self.sheet_items.Clear()
        if self.is_exporting_views:
            elements = ViewCollector.get_all_views(self.doc)
        else:
            elements = ViewCollector.get_all_sheets(self.doc)
        for el in elements:
            self.sheet_items.Add(SheetItem(self.doc, el, is_view=self.is_exporting_views))
        self.LoadProjectParameters()
        self.LoadParameters()

    def LoadProjectParameters(self):
        """Extracts all parameters from Project Information."""
        self.project_params = {}
        try:
            if self.doc.ProjectInformation:
                p_info = self.doc.ProjectInformation
                if p_info.Name:
                    self.project_params['Project Name'] = p_info.Name
                if hasattr(p_info, 'Number') and p_info.Number:
                    self.project_params['Project Number'] = p_info.Number
                if hasattr(p_info, 'Status') and p_info.Status:
                    self.project_params['Project Status'] = p_info.Status
                if hasattr(p_info, 'ClientName') and p_info.ClientName:
                    self.project_params['Client Name'] = p_info.ClientName
                if hasattr(p_info, 'Address') and p_info.Address:
                    self.project_params['Project Address'] = p_info.Address
                for param in p_info.Parameters:
                    try:
                        if param.Definition:
                            name = param.Definition.Name
                            if param.StorageType == DB.StorageType.String:
                                val = param.AsString()
                            else:
                                val = param.AsValueString()
                            if val:
                                self.project_params[name] = val
                    except Exception:
                        log_swallowed(_LOG, u'LoadProjectParameters')
        except Exception as e:
            logger.error("Error loading project parameters", e)

    def LoadParameters(self):
        """Populates the Naming tab's Available Parameters list."""
        self.ListParams.Items.Clear()
        names = column_presets.ColumnPresetManager.get_available_columns(
            list(self.sheet_items), self.project_params)
        for n in names:
            self.ListParams.Items.Add(n)

    # =========================================================================
    # MODE / SEARCH / DISCIPLINE FILTER
    # =========================================================================

    def Mode_Changed(self, sender, args):
        if self._is_initializing:
            return
        self.is_exporting_views = (self.RbViews.IsChecked == True)
        self._pending_changes.clear()
        self._sync_active_preset()
        self.LoadData()
        self._load_discipline_filter()
        self._apply_filters()
        self._load_column_presets()
        self.RebuildColumns()
        self.UpdatePreview()
        self.UpdateStatus()
        self.SaveLastConfig()

    def _sync_active_preset(self):
        """active_column_preset always mirrors whichever mode is active."""
        self.active_column_preset = (
            self.view_column_preset if self.is_exporting_views else self.sheet_column_preset
        )

    def Search_Changed(self, sender, args):
        if self._is_initializing:
            return
        self._apply_filters()
        self.SaveLastConfig()

    def Discipline_Changed(self, sender, args):
        if self._is_initializing:
            return
        self._apply_filters()

    def _load_discipline_filter(self):
        self.ComboDiscipline.Items.Clear()
        self.ComboDiscipline.Items.Add("All disciplines")
        values = set()
        for item in self.sheet_items:
            try:
                v = item.Params["Discipline"] if "Discipline" in item.Params else ""
            except Exception:
                v = ""
            if v:
                values.add(v)
        for v in sorted(values):
            self.ComboDiscipline.Items.Add(v)
        self.ComboDiscipline.SelectedIndex = 0

    def _apply_filters(self):
        search_txt = (self.TxtSearch.Text or '').lower() if hasattr(self, 'TxtSearch') else ''
        disc_filter = None
        if hasattr(self, 'ComboDiscipline') and self.ComboDiscipline.SelectedItem:
            sel = str(self.ComboDiscipline.SelectedItem)
            if sel != "All disciplines":
                disc_filter = sel

        def matches(item):
            if search_txt:
                if search_txt not in (item.Number or '').lower() and search_txt not in (item.Name or '').lower():
                    return False
            if disc_filter:
                try:
                    v = item.Params["Discipline"] if "Discipline" in item.Params else ""
                except Exception:
                    v = ""
                if v != disc_filter:
                    return False
            return True

        if search_txt or disc_filter:
            self.GridSheets.ItemsSource = [i for i in self.sheet_items if matches(i)]
        else:
            self.GridSheets.ItemsSource = self.sheet_items

    # =========================================================================
    # COLUMN PRESETS
    # =========================================================================

    def _load_column_presets(self):
        self.ComboColumnPreset.Items.Clear()
        for name in column_presets.ColumnPresetManager.get_all_preset_names():
            self.ComboColumnPreset.Items.Add(name)
        items = list(self.ComboColumnPreset.Items)
        idx = items.index(self.active_column_preset) if self.active_column_preset in items else 0
        self.ComboColumnPreset.SelectedIndex = idx

    def ColumnPreset_Changed(self, sender, args):
        if self._is_initializing:
            return
        if self.ComboColumnPreset.SelectedItem:
            name = str(self.ComboColumnPreset.SelectedItem)
            self.active_column_preset = name
            if self.is_exporting_views:
                self.view_column_preset = name
            else:
                self.sheet_column_preset = name
            self.RebuildColumns()
            self.SaveLastConfig()

    def RebuildColumns(self):
        """Rebuild the DataGrid's dynamic columns (everything after the fixed
        checkbox column) from the active column preset."""
        while self.GridSheets.Columns.Count > 1:
            self.GridSheets.Columns.RemoveAt(1)
        names = column_presets.ColumnPresetManager.load_preset(self.active_column_preset) or []
        for name in names:
            col = DataGridTextColumn()
            col.Header = name
            col.Binding = Binding("Params[{}]".format(name))
            col.IsReadOnly = not param_editor.is_editable(name)
            col.Width = DataGridLength(130)
            self.GridSheets.Columns.Add(col)

    def ManageColumns_Click(self, sender, args):
        from column_chooser_dialog import ColumnChooserDialog
        available = column_presets.ColumnPresetManager.get_available_columns(
            list(self.sheet_items), self.project_params)
        dlg = ColumnChooserDialog(self.active_column_preset, available)
        dlg.Owner = self
        if dlg.ShowDialog():
            self._load_column_presets()
            if dlg.result_preset_name:
                self.active_column_preset = dlg.result_preset_name
                if self.is_exporting_views:
                    self.view_column_preset = dlg.result_preset_name
                else:
                    self.sheet_column_preset = dlg.result_preset_name
                items = list(self.ComboColumnPreset.Items)
                if self.active_column_preset in items:
                    self.ComboColumnPreset.SelectedIndex = items.index(self.active_column_preset)
            self.RebuildColumns()
            self.SaveLastConfig()

    # =========================================================================
    # SELECTION
    # =========================================================================

    def Sheet_Checked(self, sender, args):
        # Write the new state back to the row explicitly instead of trusting
        # the XAML TwoWay binding to do it — in this DataGrid/pythonnet
        # combination the checkbox can visually toggle without the bound
        # SheetItem.IsChecked actually being updated, which left
        # UpdateStatus() reading stale (unchecked) state. No range-select or
        # Items.Refresh() here: a refresh-driven IsChecked change fires this
        # same Checked/Unchecked event again, so anything here that mutates
        # other rows and refreshes can cascade. Numeric range selection is
        # covered by the "Range..." button instead.
        if self._suspend_status_update:
            return
        item = getattr(sender, 'DataContext', None)
        if item is not None:
            item.IsChecked = (sender.IsChecked == True)
        self.UpdateStatus()
        self.SaveLastConfig()

    def SelectAll_Click(self, sender, args):
        self._suspend_status_update = True
        try:
            for item in self.GridSheets.ItemsSource:
                item.IsChecked = True
            self.GridSheets.Items.Refresh()
        finally:
            self._suspend_status_update = False
        self.UpdateStatus()
        self.SaveLastConfig()

    def SelectNone_Click(self, sender, args):
        self._suspend_status_update = True
        try:
            for item in self.GridSheets.ItemsSource:
                item.IsChecked = False
            self.GridSheets.Items.Refresh()
        finally:
            self._suspend_status_update = False
        self.UpdateStatus()
        self.SaveLastConfig()

    def InvertChecks_Click(self, sender, args):
        self._suspend_status_update = True
        try:
            for item in self.GridSheets.ItemsSource:
                item.IsChecked = not (item.IsChecked == True)
            self.GridSheets.Items.Refresh()
        finally:
            self._suspend_status_update = False
        self.UpdateStatus()
        self.SaveLastConfig()

    def SelectRange_Click(self, sender, args):
        from pyrevit.forms import ask_for_string
        range_text = ask_for_string(
            prompt="Enter range (examples: A101-A110 or 101-110):",
            title="Select Range",
        )
        if not range_text:
            return
        range_text = range_text.strip()
        parts = range_text.split("-")
        if len(parts) != 2:
            MessageBox.Show("Invalid range format. Use START-END.")
            return
        start_raw, end_raw = parts[0].strip(), parts[1].strip()

        # Resolve which matching strategy applies and the bounds up front —
        # no grid mutation yet, so an early return here can't leave the
        # suspend flag stuck.
        m_start = re.match(r"^([A-Za-z\-]*)(\d+)$", start_raw)
        m_end = re.match(r"^([A-Za-z\-]*)(\d+)$", end_raw)
        use_prefix = bool(m_start and m_end and m_start.group(1).lower() == m_end.group(1).lower())

        if use_prefix:
            prefix = m_start.group(1).lower()
            low, high = sorted((int(m_start.group(2)), int(m_end.group(2))))
        else:
            n1 = self._extract_first_number(start_raw)
            n2 = self._extract_first_number(end_raw)
            if n1 is None or n2 is None:
                MessageBox.Show("Could not parse numeric range.")
                return
            low, high = sorted((n1, n2))

        matched = 0
        self._suspend_status_update = True
        try:
            for item in self.sheet_items:
                if use_prefix:
                    item_match = re.match(r"^([A-Za-z\-]*)(\d+)$", (item.Number or "").strip().lower())
                    in_range = bool(item_match and item_match.group(1) == prefix
                                     and low <= int(item_match.group(2)) <= high)
                else:
                    current_num = self._extract_first_number(item.Number or "")
                    in_range = current_num is not None and low <= current_num <= high
                if in_range:
                    item.IsChecked = True
                    matched += 1
            self.GridSheets.Items.Refresh()
        finally:
            self._suspend_status_update = False

        self.UpdateStatus()
        self.SaveLastConfig()
        MessageBox.Show("Checked {} items in range.".format(matched))

    def CheckHighlighted_Click(self, sender, args):
        """Check the export checkbox for every row currently row-selected
        (highlighted) in the grid — Ctrl/Shift-click to highlight several
        rows with the mouse, then use this to check them all at once."""
        highlighted = list(self.GridSheets.SelectedItems)
        if not highlighted:
            MessageBox.Show("Highlight one or more rows first (click, or Ctrl/Shift-click for several).")
            return
        self._suspend_status_update = True
        try:
            for item in highlighted:
                item.IsChecked = True
            self.GridSheets.Items.Refresh()
        finally:
            self._suspend_status_update = False
        self.UpdateStatus()
        self.SaveLastConfig()

    # =========================================================================
    # ROW SELECTION HIGHLIGHT (painted in code — see comment in __init__)
    # =========================================================================

    def _selection_brush(self):
        # Fresh brush each call: WPF Freezable brushes can only be shared
        # safely once frozen, and there's no need to cache one instance here.
        return SolidColorBrush(Color.FromArgb(0x40, 0xFF, 0x5F, 0x00))

    def _paint_row(self, row, is_selected):
        if row is None:
            return
        try:
            row.Background = self._selection_brush() if is_selected else Brushes.Transparent
        except Exception:  # nosa-lint: disable=NOSA006 - row repaint, called for every row on LoadingRow/SelectionChanged
            pass

    def GridSheets_SelectionChanged(self, sender, args):
        try:
            for item in args.RemovedItems:
                self._paint_row(self.GridSheets.ItemContainerGenerator.ContainerFromItem(item), False)
            for item in args.AddedItems:
                self._paint_row(self.GridSheets.ItemContainerGenerator.ContainerFromItem(item), True)
        except Exception:  # nosa-lint: disable=NOSA006 - SelectionChanged handler, fires on every click; cosmetic repaint only
            pass

    def GridSheets_LoadingRow(self, sender, args):
        """A row container that's just been realised (initial load, scroll
        virtualisation, or the grid rebuilding its ItemsSource when the
        search box filters) doesn't know about a pre-existing selection —
        repaint it here so the highlight survives all of that."""
        try:
            is_selected = args.Row.Item in list(self.GridSheets.SelectedItems)
            self._paint_row(args.Row, is_selected)
        except Exception:  # nosa-lint: disable=NOSA006 - LoadingRow handler, fires per realised row; cosmetic repaint only
            pass

    # =========================================================================
    # SHEET SETS
    # =========================================================================

    def _load_sheet_sets(self):
        try:
            self.ComboSheetSets.Items.Clear()
            self.ComboSheetSets.Items.Add("")
            for name in ViewSetManager.get_all_sets():
                self.ComboSheetSets.Items.Add(name)
            self.ComboSheetSets.SelectedIndex = 0
        except Exception:
            log_swallowed(_LOG, u'_load_sheet_sets')

    def LoadSet_Click(self, sender, args):
        name = self.ComboSheetSets.SelectedItem
        if not name or str(name) == "":
            MessageBox.Show("Select a sheet set first.")
            return
        ids = ViewSetManager.load_set(str(name))
        if not ids:
            MessageBox.Show("Could not load set '{}'. It may be empty or missing.".format(name))
            return
        id_values = set(Utils._get_element_id_value(eid) for eid in ids)
        self._suspend_status_update = True
        try:
            for item in self.sheet_items:
                item.IsChecked = Utils._get_element_id_value(item.Id) in id_values
            self.GridSheets.Items.Refresh()
        finally:
            self._suspend_status_update = False
        self.UpdateStatus()

    def SaveSet_Click(self, sender, args):
        selected_ids = [item.Id for item in self.sheet_items if item.IsChecked]
        if not selected_ids:
            MessageBox.Show("Select at least one sheet before saving a set.")
            return
        from pyrevit.forms import ask_for_string
        name = ask_for_string(prompt="Enter a name for this sheet set:", title="Save Sheet Set")
        if not name:
            return
        ok = ViewSetManager.save_set(name.strip(), selected_ids)
        if ok:
            self._load_sheet_sets()
            MessageBox.Show("Saved set '{}' with {} sheets.".format(name, len(selected_ids)))
        else:
            MessageBox.Show("Failed to save set.")

    def DeleteSet_Click(self, sender, args):
        name = self.ComboSheetSets.SelectedItem
        if not name or str(name) == "":
            MessageBox.Show("Select a sheet set to delete.")
            return
        res = MessageBox.Show(
            "Delete sheet set '{}'?".format(name),
            "Confirm Delete",
            System.Windows.MessageBoxButton.YesNo
        )
        if str(res) == "Yes":
            ViewSetManager.delete_set(str(name))
            self._load_sheet_sets()

    # =========================================================================
    # PARAMETER EDITING (inline + batch)
    # =========================================================================

    def Grid_CellEditEnding(self, sender, args):
        if self._is_initializing:
            return
        try:
            row = args.Row.Item
            if row is None or not hasattr(row, 'Element'):
                return
            col = args.Column
            if not hasattr(col, 'Header') or not col.Header:
                return
            param_name = str(col.Header)
            if not param_editor.is_editable(param_name):
                return
            try:
                new_val = args.EditingElement.Text or ''
            except Exception:
                new_val = ''

            number = row.Number
            if number not in self._pending_changes:
                self._pending_changes[number] = {}
            self._pending_changes[number][param_name] = new_val
            try:
                row.Params[param_name] = new_val
            except Exception:
                log_swallowed(_LOG, u'Grid_CellEditEnding')
            row.HasPending = True
            self.BtnApplyEdits.IsEnabled = True
            self._refresh_grid_async()
        except Exception as e:
            forms.alert("Could not track edit: {}".format(e))

    def _refresh_grid_async(self):
        try:
            import System.Windows.Threading as _swt
            def _do_refresh():
                try:
                    self.GridSheets.Items.Refresh()
                except Exception:
                    log_swallowed(_LOG, u'_do_refresh')
            self.GridSheets.Dispatcher.BeginInvoke(
                _swt.DispatcherPriority.Background, System.Action(_do_refresh))
        except Exception:
            log_swallowed(_LOG, u'_refresh_grid_async')

    def ApplyParamEdits_Click(self, sender, args):
        if not self._pending_changes:
            return
        elements_by_number = {item.Number: item.Element for item in self.sheet_items}
        ok, fail = param_editor.apply_changes(self.doc, elements_by_number, self._pending_changes)
        for item in self.sheet_items:
            if item.Number in self._pending_changes:
                item.HasPending = False
        self._pending_changes.clear()
        self.BtnApplyEdits.IsEnabled = False
        self.GridSheets.Items.Refresh()
        forms.alert("Applied: {}   /   Failed: {}".format(ok, fail))

    def EditParameters_Click(self, sender, args):
        checked = [item for item in self.sheet_items if item.IsChecked]
        if not checked:
            MessageBox.Show("Check one or more sheets/views first.")
            return
        from edit_parameters_dialog import EditParametersDialog
        editable_fields = [n for n in _sp.NOSA_PARAM_ORDER if param_editor.is_editable(n)]
        dlg = EditParametersDialog(editable_fields, len(checked))
        dlg.Owner = self
        if dlg.ShowDialog() and dlg.result_values:
            elements_by_number = {item.Number: item.Element for item in checked}
            changes = {item.Number: dict(dlg.result_values) for item in checked}
            ok, fail = param_editor.apply_changes(self.doc, elements_by_number, changes)
            for item in checked:
                for k, v in dlg.result_values.items():
                    item.Params[k] = v
                pending = self._pending_changes.get(item.Number)
                if pending:
                    for k in dlg.result_values.keys():
                        pending.pop(k, None)
                    if not pending:
                        del self._pending_changes[item.Number]
                        item.HasPending = False
            self.BtnApplyEdits.IsEnabled = len(self._pending_changes) > 0
            self.GridSheets.Items.Refresh()
            forms.alert("Applied: {}   /   Failed: {}".format(ok, fail))

    # =========================================================================
    # NAMING
    # =========================================================================

    def Param_DoubleClick(self, sender, args):
        selected_param = self.ListParams.SelectedItem
        if selected_param:
            self.naming_builder.add_parameter(selected_param)
            self.UpdateTemplateList()

    def Template_DoubleClick(self, sender, args):
        selected_item = self.ListTemplate.SelectedItem
        if selected_item:
            self.naming_builder.remove_parameter(str(selected_item))
            self.UpdateTemplateList()

    def Separator_Changed(self, sender, args):
        if self._is_initializing:
            return
        self.naming_builder.separator = self.TxtSeparator.Text
        self.UpdatePreview()
        self.UpdateStatus()
        self.SaveLastConfig()

    def UpdateTemplateList(self):
        self.ListTemplate.Items.Clear()
        for p in self.naming_builder.template:
            self.ListTemplate.Items.Add(str(p))
        self.UpdatePreview()
        self.UpdateStatus()
        self.SaveLastConfig()

    def UpdatePreview(self):
        if not self.sheet_items or len(self.sheet_items) == 0:
            self.TxtPreview.Text = "No sheets available"
            return
        first_item = self.sheet_items[0]
        try:
            name = self.naming_builder.build_filename(
                first_item.Element, project_params=self.project_params, is_view=self.is_exporting_views
            )
            self.TxtPreview.Text = name + ".pdf"
        except Exception as e:
            self.TxtPreview.Text = "Error: " + str(e)

    # =========================================================================
    # SUB-TABS / FORMATS
    # =========================================================================

    def SubTab_Click(self, sender, args):
        self.SwitchTab(sender.Name, self.sub_tabs)
        self.SaveLastConfig()

    def ColorMode_Changed(self, sender, args):
        if self._is_initializing:
            return
        self.SaveLastConfig()

    def _force_black(self):
        return hasattr(self, 'RbForceBlack') and self.RbForceBlack.IsChecked == True

    def Format_Changed(self, sender, args):
        if self._is_initializing:
            return
        self.UpdateStatus()
        self.SaveLastConfig()

    def _load_quality_presets(self):
        self.ComboQualityPreset.Items.Clear()
        for name in ["Quick", "Standard", "Print"]:
            self.ComboQualityPreset.Items.Add(name)
        self.ComboQualityPreset.SelectedItem = self.quality_preset

    def QualityPreset_Changed(self, sender, args):
        if self._is_initializing:
            return
        if self.ComboQualityPreset.SelectedItem:
            self.quality_preset = str(self.ComboQualityPreset.SelectedItem)
            self.SaveLastConfig()

    _DWG_SETUP_DEFAULT_LABEL = "Default (NOSA presets)"

    def _load_dwg_setups(self):
        """Populate ComboDwgSetup with the DWG Export Setups already saved
        in this document (Manage tab > Export Setups > DWG), plus the
        plugin's own fixed preset as the default option."""
        self.ComboDwgSetup.Items.Clear()
        self.ComboDwgSetup.Items.Add(self._DWG_SETUP_DEFAULT_LABEL)
        try:
            for name in DB.DWGExportOptions.GetPredefinedSetupNames(self.doc):
                self.ComboDwgSetup.Items.Add(name)
        except Exception as e:
            logger.warning("Could not read DWG export setups", e)
        self.ComboDwgSetup.SelectedIndex = 0

    def DwgSetup_Changed(self, sender, args):
        if self._is_initializing:
            return
        sel = self.ComboDwgSetup.SelectedItem
        self.dwg_setup_name = None if (not sel or str(sel) == self._DWG_SETUP_DEFAULT_LABEL) else str(sel)
        self.SaveLastConfig()

    def CombinedPdfName_Changed(self, sender, args):
        if self._is_initializing:
            return
        self.combined_pdf_name = self.TxtCombinedPdfName.Text or "Combined Export"
        self.SaveLastConfig()

    def _pre_export_check(self, elements):
        if not (hasattr(self, 'ChkPreExportCheck') and self.ChkPreExportCheck.IsChecked == True):
            return []
        flagged = []
        for el in elements:
            try:
                if hasattr(el, 'IsTemporaryHideIsolateActive') and el.IsTemporaryHideIsolateActive():
                    flagged.append(getattr(el, 'Name', str(el.Id)))
            except Exception:
                log_swallowed(_LOG, u'_pre_export_check')
        return flagged

    # =========================================================================
    # DESTINATION
    # =========================================================================

    def Browse_Click(self, sender, args):
        path = forms.pick_folder()
        if path:
            self.output_folder = path
            self.TxtFolder.Text = path
            self.UpdateStatus()
            self.SaveLastConfig()

    def Subfolder_Changed(self, sender, args):
        if self._is_initializing:
            return
        self.subfolder = self.TxtSubfolder.Text or ""
        self.UpdateStatus()
        self.SaveLastConfig()

    def _effective_output_folder(self):
        base = self.output_folder or ""
        if not base:
            return ""
        try:
            base = Utils.expand_path_variables(base, self.doc)
        except Exception:
            log_swallowed(_LOG, u'_effective_output_folder')
        if self.subfolder:
            return os.path.join(base, self.subfolder.strip().strip('\\/'))
        return base

    # =========================================================================
    # EXPORT PRESETS
    # =========================================================================

    def _load_export_presets(self):
        self.ComboExportPreset.ItemsSource = None
        items = [ExportPresetItem(n) for n in ExportPresetManager.get_all_presets()]
        self.ComboExportPreset.ItemsSource = items

    def ExportPreset_Selected(self, sender, args):
        if self._is_initializing:
            return
        if not self.ComboExportPreset.SelectedItem:
            return
        name = self.ComboExportPreset.SelectedItem.Name
        data = ExportPresetManager.load_preset(name)
        if not data:
            return

        naming = data.get('naming')
        if naming:
            self.naming_builder.from_dict(naming)
            self.TxtSeparator.Text = self.naming_builder.separator
            self.UpdateTemplateList()

        self.output_folder = data.get('output_folder', '')
        self.TxtFolder.Text = self.output_folder
        self.subfolder = data.get('subfolder', '')
        self.TxtSubfolder.Text = self.subfolder

        formats = data.get('export_formats', {})
        self.ChkPDF.IsChecked = formats.get('pdf', True)
        self.ChkDWG.IsChecked = formats.get('dwg', False)
        self.ChkDXF.IsChecked = formats.get('dxf', False)
        self.ChkCombinePdf.IsChecked = formats.get('pdf_combine', False)

        if data.get('force_black'):
            self.RbForceBlack.IsChecked = True
        else:
            self.RbUseModelColors.IsChecked = True

        self.dwg_setup_name = data.get('dwg_setup_name')
        items = list(self.ComboDwgSetup.Items)
        target = self.dwg_setup_name if self.dwg_setup_name in items else self._DWG_SETUP_DEFAULT_LABEL
        if target in items:
            self.ComboDwgSetup.SelectedIndex = items.index(target)

        self.combined_pdf_name = data.get('combined_pdf_name') or "Combined Export"
        self.TxtCombinedPdfName.Text = self.combined_pdf_name

        self.UpdateStatus()
        self.SaveLastConfig()

    def SaveExportPreset_Click(self, sender, args):
        from pyrevit.forms import ask_for_string
        name = ask_for_string(prompt="Enter a name for this export preset:", title="Save Export Preset")
        if not name:
            return
        export_formats = {
            'pdf': self.ChkPDF.IsChecked == True,
            'dwg': self.ChkDWG.IsChecked == True,
            'dxf': self.ChkDXF.IsChecked == True,
            'pdf_combine': self.ChkCombinePdf.IsChecked == True,
        }
        ok = ExportPresetManager.save_preset(
            name.strip(), self.naming_builder, self.output_folder, self.subfolder,
            export_formats, self._force_black(),
            dwg_setup_name=self.dwg_setup_name, combined_pdf_name=self.combined_pdf_name
        )
        if ok:
            self._load_export_presets()
            MessageBox.Show("Saved preset '{}'.".format(name))
        else:
            MessageBox.Show("Failed to save preset.")

    def DeleteExportPreset_Click(self, sender, args):
        if not self.ComboExportPreset.SelectedItem:
            MessageBox.Show("Select a preset to delete.")
            return
        name = self.ComboExportPreset.SelectedItem.Name
        res = MessageBox.Show(
            "Delete export preset '{}'?".format(name), "Confirm Delete",
            System.Windows.MessageBoxButton.YesNo
        )
        if str(res) == "Yes":
            ExportPresetManager.delete_preset(name)
            self._load_export_presets()

    # =========================================================================
    # LIVE STATUS STRIP
    # =========================================================================

    def UpdateStatus(self):
        checked = [item for item in self.sheet_items if item.IsChecked]
        if hasattr(self, 'BtnEditParams'):
            self.BtnEditParams.IsEnabled = len(checked) > 0
        if hasattr(self, 'BtnApplyEdits'):
            self.BtnApplyEdits.IsEnabled = len(self._pending_changes) > 0

        export_formats = {
            'pdf': self.ChkPDF.IsChecked == True,
            'dwg': self.ChkDWG.IsChecked == True,
            'dxf': self.ChkDXF.IsChecked == True,
            'pdf_combine': self.ChkCombinePdf.IsChecked == True,
            'force_black': self._force_black(),
        }
        elements = [item.Element for item in checked]
        output_folder = self._effective_output_folder()

        validator = ExportValidator()
        status = validator.quick_status(
            elements, self.naming_builder, output_folder, export_formats,
            is_views=self.is_exporting_views, project_params=self.project_params
        )

        self._set_dot(self.DotSelection, self.TxtStatusSelection, status['selection'])
        self._set_dot(self.DotNaming, self.TxtStatusNaming, status['naming'])
        self._set_dot(self.DotCollisions, self.TxtStatusCollisions, status['collisions'])
        self._set_dot(self.DotDestination, self.TxtStatusDestination, status['destination'])

        has_format = (export_formats['pdf'] or export_formats['dwg'] or export_formats['dxf']
                      or export_formats['pdf_combine'])
        all_ok = (status['selection'][0] and status['naming'][0] and status['collisions'][0]
                  and status['destination'][0] and has_format)
        self.BtnExport.IsEnabled = all_ok
        self.BtnExport.Content = "Export {} item{}".format(
            len(checked), "" if len(checked) == 1 else "s") if checked else "Export"

    def _set_dot(self, dot, label, status_tuple):
        ok, msg = status_tuple
        dot.Fill = self.Resources["StatusOkColor"] if ok else self.Resources["StatusPendingColor"]
        label.Text = msg

    # =========================================================================
    # EXPORT
    # =========================================================================

    def Export_Click(self, sender, args):
        selected_elements = [item.Element for item in self.sheet_items if item.IsChecked]
        if not selected_elements:
            MessageBox.Show("Please select sheets/views first.")
            return

        output_folder = self._effective_output_folder()
        if not output_folder:
            MessageBox.Show("Please select a destination folder.")
            return

        self.LoadProjectParameters()

        export_formats = {
            'pdf': self.ChkPDF.IsChecked == True,
            'dwg': self.ChkDWG.IsChecked == True,
            'dxf': self.ChkDXF.IsChecked == True,
            'pdf_combine': self.ChkCombinePdf.IsChecked == True,
            'force_black': self._force_black(),
        }

        # Create the destination folder before validating/confirming, so the
        # confirm dialog's disk checks (existence, permissions, space) see
        # its final state instead of flagging a folder that's about to be
        # created anyway.
        if not os.path.exists(output_folder):
            try:
                os.makedirs(output_folder)
            except Exception as e:
                MessageBox.Show("Could not create destination folder: {}".format(e))
                return

        selected_elements = self._drawing_check_gate(selected_elements)
        if not selected_elements:
            return

        from confirm_export_dialog import ConfirmExportDialog
        dlg = ConfirmExportDialog(
            selected_elements, self.naming_builder, export_formats,
            output_folder, self.project_params, self.is_exporting_views
        )
        dlg.Owner = self
        if not dlg.ShowDialog():
            return

        flagged = self._pre_export_check(selected_elements)
        if flagged:
            names = "\n".join(flagged[:10])
            if len(flagged) > 10:
                names += "\n... and {} more".format(len(flagged) - 10)
            res = MessageBox.Show(
                "Warning: {} view(s) have temporary Hide/Isolate or overrides active.\n\n{}\n\n"
                "These may affect export colours.\n\nContinue anyway?".format(len(flagged), names),
                "Pre-export Warning",
                System.Windows.MessageBoxButton.YesNo
            )
            if str(res) != 'Yes':
                return

        try:
            self.ExpLog.IsExpanded = True
        except Exception:
            log_swallowed(_LOG, u'Export_Click')
        self.TxtLog.Text = "Starting export...\n"
        total_count = len(selected_elements)
        self._set_export_progress(0, total_count)

        mgr = ExportManager(
            self.doc, selected_elements, self.naming_builder, output_folder,
            export_formats, self.quality_preset, self.project_params, self.is_exporting_views,
            dwg_setup_name=self.dwg_setup_name, combined_pdf_name=self.combined_pdf_name
        )

        progress_re = re.compile(r'^PROCESSING (\d+)/(\d+)')

        def progress(msg):
            self.TxtLog.AppendText(msg + "\n")
            self.TxtLog.ScrollToEnd()
            match = progress_re.match(msg.strip())
            if match:
                self._set_export_progress(int(match.group(1)), int(match.group(2)))
            else:
                self._pump_ui()

        try:
            success, msg = mgr.export_all(progress)
            if success:
                self.TxtLog.AppendText("EXPORT COMPLETED SUCCESSFULLY.\n")
                self._set_export_progress(total_count, total_count)
                self.SaveLastConfig()
                Utils.open_folder(output_folder)
            else:
                self.TxtLog.AppendText("EXPORT FAILED: {}\n".format(msg))
        except Exception as e:
            self.TxtLog.AppendText("ERROR: " + str(e) + "\n")
            logger.error("Export failed", e)

    # =========================================================================
    # DRAWING CHECK (T8.12)
    # =========================================================================

    def _drawing_findings(self, elements):
        from nosa_utils import sheet_checks
        sheets = [e for e in elements if isinstance(e, DB.ViewSheet)]
        labels = [u'{} - {}'.format(s.SheetNumber, s.Name) for s in sheets]
        return sheets, labels, sheet_checks.check_sheets(self.doc, sheets)

    def _drawing_check_gate(self, elements):
        """NOSA protocol + content check before exporting sheets: export all, compliant only, or cancel."""
        if self.is_exporting_views:
            return elements
        try:
            sheets, labels, findings = self._drawing_findings(elements)
        except Exception as e:
            logger.error("Drawing check failed", e)
            return elements
        if not findings:
            return elements
        from protocol_report_dialog import ProtocolReportDialog, ALL, COMPLIANT
        dlg = ProtocolReportDialog(findings, labels, for_export=True)
        dlg.Owner = self
        dlg.ShowDialog()
        if dlg.choice == ALL:
            return elements
        if dlg.choice == COMPLIANT:
            keep = set(dlg.compliant_labels)
            return [e for e in elements if not isinstance(e, DB.ViewSheet) or
                    u'{} - {}'.format(e.SheetNumber, e.Name) in keep]
        return []

    def CheckDrawings_Click(self, sender, args):
        selected = [item.Element for item in self.sheet_items if item.IsChecked]
        sheets = [e for e in selected if isinstance(e, DB.ViewSheet)]
        if not sheets:
            MessageBox.Show("Select the sheets to check first.")
            return
        _s, labels, findings = self._drawing_findings(sheets)
        if not findings:
            MessageBox.Show("{} sheet(s) checked: no issues found.".format(len(labels)))
            return
        from protocol_report_dialog import ProtocolReportDialog
        dlg = ProtocolReportDialog(findings, labels, for_export=False)
        dlg.Owner = self
        dlg.ShowDialog()

    def _pump_ui(self):
        """Give the WPF Dispatcher a beat to process pending layout/render
        work between synchronous Revit API calls. exporters.py's own
        Application.DoEvents() pumps the WinForms message loop, which does
        nothing for a WPF window — this is the real equivalent, and it's
        what actually keeps the log/progress bar visibly updating instead
        of appearing frozen until export_all() returns. The export loop
        itself still runs on the UI thread (Revit's API can't be called
        from a background thread), so this smooths the feedback — it can't
        make Revit itself not busy while exporting."""
        try:
            import System.Windows.Threading as _swt
            self.Dispatcher.Invoke(System.Action(lambda: None), _swt.DispatcherPriority.Background)
        except Exception:  # nosa-lint: disable=NOSA006 - UI message pump during export, called per sheet; failure is harmless
            pass

    def _set_export_progress(self, current, total):
        try:
            self.ExportProgress.IsIndeterminate = False
            self.ExportProgress.Minimum = 0
            self.ExportProgress.Maximum = max(1, total)
            self.ExportProgress.Value = min(current, total)
        except Exception:
            log_swallowed(_LOG, u'_set_export_progress')
        self._pump_ui()

    # =========================================================================
    # CONFIG PERSISTENCE (NOSAWindow.SaveConfig/LoadConfig — single JSON file)
    # =========================================================================

    def SaveLastConfig(self):
        if self._is_initializing:
            return
        try:
            cfg = self.LoadConfig()
            cfg.update({
                'output_folder': self.output_folder,
                'subfolder': self.subfolder,
                'is_exporting_views': self.is_exporting_views,
                'search_text': self.TxtSearch.Text if hasattr(self, 'TxtSearch') else '',
                'format_pdf': self.ChkPDF.IsChecked == True,
                'format_dwg': self.ChkDWG.IsChecked == True,
                'format_dxf': self.ChkDXF.IsChecked == True,
                'format_pdf_combine': self.ChkCombinePdf.IsChecked == True,
                'force_black': self._force_black(),
                'quality_preset': self.quality_preset,
                'sheet_column_preset': self.sheet_column_preset,
                'view_column_preset': self.view_column_preset,
                'dwg_setup_name': self.dwg_setup_name,
                'combined_pdf_name': self.combined_pdf_name,
            })
            self.SaveConfig(cfg)
        except Exception:
            log_swallowed(_LOG, u'SaveLastConfig')

    def _apply_config(self, cfg):
        """Restore persisted UI state (no data reload — LoadData() runs
        separately right after this, in __init__)."""
        if not cfg:
            return

        self.output_folder = cfg.get('output_folder', '')
        self.TxtFolder.Text = self.output_folder
        self.subfolder = cfg.get('subfolder', '')
        self.TxtSubfolder.Text = self.subfolder

        self.is_exporting_views = cfg.get('is_exporting_views', False)
        self.RbViews.IsChecked = self.is_exporting_views
        self.RbSheets.IsChecked = not self.is_exporting_views

        self.ChkPDF.IsChecked = cfg.get('format_pdf', True)
        self.ChkDWG.IsChecked = cfg.get('format_dwg', False)
        self.ChkDXF.IsChecked = cfg.get('format_dxf', False)
        self.ChkCombinePdf.IsChecked = cfg.get('format_pdf_combine', False)
        if cfg.get('force_black'):
            self.RbForceBlack.IsChecked = True
        else:
            self.RbUseModelColors.IsChecked = True

        self.quality_preset = cfg.get('quality_preset', 'Standard')
        self.ComboQualityPreset.SelectedItem = self.quality_preset

        self.dwg_setup_name = cfg.get('dwg_setup_name')
        items = list(self.ComboDwgSetup.Items)
        target = self.dwg_setup_name if self.dwg_setup_name in items else self._DWG_SETUP_DEFAULT_LABEL
        if target in items:
            self.ComboDwgSetup.SelectedIndex = items.index(target)

        self.combined_pdf_name = cfg.get('combined_pdf_name') or "Combined Export"
        self.TxtCombinedPdfName.Text = self.combined_pdf_name

        self.sheet_column_preset = cfg.get('sheet_column_preset', column_presets.DEFAULT_PRESET_NAME)
        self.view_column_preset = cfg.get('view_column_preset', column_presets.DEFAULT_VIEW_PRESET_NAME)

        self.TxtSearch.Text = cfg.get('search_text', '')

    # =========================================================================
    # SMALL HELPERS
    # =========================================================================

    def _extract_first_number(self, value):
        match = re.search(r"\d+", str(value))
        if not match:
            return None
        try:
            return int(match.group(0))
        except Exception:
            return None
