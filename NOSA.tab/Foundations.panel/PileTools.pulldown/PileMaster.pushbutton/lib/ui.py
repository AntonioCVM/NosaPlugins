# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import forms, revit, script
import sys
import os
import System
from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.telemetry import log_swallowed
_LOG = u'pilemaster'

_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)
from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import element_id_from_int

# Import Logic Modules (absolute — lib_path injected by script.py)
from logic_coords    import CoordinateLogic
from logic_numbering import NumberingLogic
from logic_sheets    import SheetLogic
from logic_dmu       import read_config as _dmu_read_config, write_config as _dmu_write_config
from logic_report    import collect_report, get_levels, export_xlsx as _report_xlsx, export_csv as _report_csv
from logic_schedule  import list_pile_schedules, create_or_open_schedule
from System          import Int64
from System.Collections.Generic import List
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs

class PrefixItem(object):
    """Simple data class for WPF DataGrid binding.
    Uses plain attributes instead of @property for WPF compatibility.
    """
    def __init__(self, key, family, typename, prefix, suffix, count):
        self.Key = key
        self.FamilyName = family
        self.TypeName = typename
        self.Prefix = prefix
        self.Suffix = suffix
        self.Count = count

class _ReportRowWrapper(object):
    """Adds sequential 'no_str' to a PileReportRow for DataGrid binding."""
    def __init__(self, row, index):
        self._row  = row
        self._no   = index
        # proxy all properties
        self.el_id          = row.el_id
        self.mark_str       = row.mark_str
        self.family_str     = row.family_str
        self.type_str       = row.type_str
        self.level_str      = row.level_str
        self.x_str          = row.x_str
        self.y_str          = row.y_str
        self.z_head_str     = row.z_head_str
        self.z_toe_str      = row.z_toe_str
        self.length_str     = row.length_str
        self.diam_str       = row.diam_str
        self.incl_str       = row.incl_str
        self.load_str       = row.load_str
        self.comments_str   = row.comments_str

    @property
    def no_str(self):
        return str(self._no)


class ScopeBoxItem:
    def __init__(self, sb, name):
        self.SB = sb
        self.Name = name
        self.IsSelected = False

class PileMasterWindow(NOSAWindow):
    def __init__(self):
        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml_file, 'pile_master')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.cmbScope.SelectedIndex = 2
        self.cmbCoordType.SelectedIndex = 0
        self.GridReport.SelectionChanged += self.ReportGrid_SelectionChanged
        
        self.doc = revit.doc
        self.uidoc = revit.uidoc
        
        # Initialize Logic
        self.logic_coords = CoordinateLogic(self.doc)
        self.logic_num = NumberingLogic(self.doc)
        self.logic_sheets = SheetLogic(self.doc)
        
        # Initialize data containers (empty at first)
        self.prefix_data = ObservableCollection[object]()
        self.scope_box_items = ObservableCollection[object]()
        
        # Wire up events BEFORE loading data
        self.cmbScope.SelectionChanged += self.OnScopeChanged
        
        # Report state
        self._report_rows      = []
        self._report_level_map = {}

        # Load Initial Data AFTER UI is ready
        self.Loaded += self.OnWindowLoaded

        # Restore live-coords toggle state from config
        self._restore_live_state()
    
    def OnWindowLoaded(self, sender, args):
        """Called when window is fully loaded and visible."""
        # Track current tab (0=Coords … 4=Schedule)
        self.current_tab = 0
        self._schedule_items = []
        self.update_nav_selection()

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        # Initial load
        self.load_numbering_data()
        self.load_zones()

        # Populate report level filter
        self.CboReportLevel.Items.Add(u'— All levels —')
        for name, lvid in get_levels(self.doc):
            self.CboReportLevel.Items.Add(name)
            self._report_level_map[name] = lvid
        self.CboReportLevel.SelectedIndex = 0
    
    def NavButton_Click(self, sender, args):
        """Handle sidebar navigation clicks."""
        btn_name = sender.Name
        
        # Hide all tabs
        Coll = System.Windows.Visibility.Collapsed
        Vis  = System.Windows.Visibility.Visible
        self.TabCoords.Visibility    = Coll
        self.TabNumbering.Visibility = Coll
        self.TabVisibility.Visibility= Coll
        self.TabReport.Visibility    = Coll
        self.TabSchedule.Visibility  = Coll

        # Show selected tab and update action button
        if btn_name == "BtnTabCoords":
            self.TabCoords.Visibility = Vis
            self.current_tab = 0
            self.BtnAction.Content  = "UPDATE COORDINATES"
            self.ActionBar.Visibility = Vis
        elif btn_name == "BtnTabNumbering":
            self.TabNumbering.Visibility = Vis
            self.current_tab = 1
            self.BtnAction.Content  = "RUN NUMBERING"
            self.ActionBar.Visibility = Vis
        elif btn_name == "BtnTabVisibility":
            self.TabVisibility.Visibility = Vis
            self.current_tab = 2
            self.BtnAction.Content  = "UPDATE VISIBILITY"
            self.ActionBar.Visibility = Vis
        elif btn_name == "BtnTabReport":
            self.TabReport.Visibility = Vis
            self.current_tab = 3
            self.ActionBar.Visibility = Coll   # Report has its own controls
        elif btn_name == "BtnTabSchedule":
            self.TabSchedule.Visibility = Vis
            self.current_tab = 4
            self.ActionBar.Visibility = Coll
            self._refresh_schedule_list()

        self.update_nav_selection()
    
    def update_nav_selection(self):
        """Update the visual selection state of nav buttons."""
        self.BtnTabCoords.Tag    = "Selected" if self.current_tab == 0 else None
        self.BtnTabNumbering.Tag = "Selected" if self.current_tab == 1 else None
        self.BtnTabVisibility.Tag= "Selected" if self.current_tab == 2 else None
        self.BtnTabReport.Tag    = "Selected" if self.current_tab == 3 else None
        self.BtnTabSchedule.Tag  = "Selected" if self.current_tab == 4 else None
    
    def ActionButton_Click(self, sender, args):
        """Route action button click to the appropriate handler."""
        elements = self.get_elements()
        if self.current_tab == 0:
            self.run_coordinates(elements)
        elif self.current_tab == 1:
            self.run_numbering(elements)
        elif self.current_tab == 2:
            self.run_sheets(elements)
    
    def OnScopeChanged(self, sender, args):
        """Refresh numbering data when scope changes."""
        self.load_numbering_data()

    def RefreshData_Click(self, sender, args):
        """Manual refresh of all data."""
        self.load_numbering_data()
        self.load_zones()

    # ==========================
    # DATA LOADING
    # ==========================
    def get_elements(self):
        """Get elements based on selected scope."""
        scope = self.cmbScope.SelectedIndex
        # 0: Active View, 1: Selection, 2: Project
        
        if scope == 1:
            # Selection
            ids = self.uidoc.Selection.GetElementIds()
            if not ids: return []
            return [self.doc.GetElement(id) for id in ids if self.doc.GetElement(id)]
        
        # For Active View or Project
        if scope == 0:
            # Active View - pass view ID to constructor
            collector = DB.FilteredElementCollector(self.doc, self.doc.ActiveView.Id)
        else:
            # Entire project
            collector = DB.FilteredElementCollector(self.doc)
             
        collector = collector.OfCategory(DB.BuiltInCategory.OST_StructuralFoundation).WhereElementIsNotElementType()
        
        return list(collector.ToElements())

    def load_numbering_data(self):
        """Populate the Prefix Grid with validation."""
        from pyrevit import script
        output = script.get_output()
        
        # Clear existing data
        if not hasattr(self, "prefix_data") or self.prefix_data is None:
             self.prefix_data = ObservableCollection[object]()
             self.dgPrefixes.ItemsSource = self.prefix_data
        
        self.prefix_data.Clear()
        
        # Get elements
        # output.print_md("## Debug: Loading Numbering Data")
        # output.print_md("- **Scope Index**: {}".format(self.cmbScope.SelectedIndex))
        
        elems = self.get_elements()
        # output.print_md("- **Elements Found**: {}".format(len(elems) if elems else 0))
        
        # VALIDATION 1: Check if we got elements
        if not elems:
            scope_name = ["Active View", "Selection", "Project"][max(0, self.cmbScope.SelectedIndex)]
            info_item = PrefixItem(
                key="NO_ELEMENTS",
                family="── No Structural Foundations found ──",
                typename="Scope: {} | Try changing scope or check model".format(scope_name),
                prefix="",
                suffix="",
                count=0
            )
            self.prefix_data.Add(info_item)
            # output.print_md("**⚠ NO ELEMENTS FOUND**")
            return
        
        # Group by type (now groups by Family Name only)
        grouped = self.logic_num.group_by_type(elems)
        # output.print_md("- **Grouped Families**: {}".format(len(grouped) if grouped else 0))
        
        if grouped:
            pass
            # for key in list(grouped.keys())[:5]:  # Show first 5
            #     output.print_md("  - `{}`: {} elements".format(key, len(grouped[key])))
        
        # VALIDATION 2: Check if grouping succeeded
        if not grouped:
            info_item = PrefixItem(
                key="NO_TYPES",
                family="── Grouping Failed ──",
                typename="Elements found: {} | But grouping returned empty".format(len(elems)),
                prefix="",
                suffix="",
                count=0
            )
            self.prefix_data.Add(info_item)
            # output.print_md("**⚠ GROUPING FAILED**")
            return
        
        # SUCCESS: Populate grid
        # output.print_md("**✓ Populating Grid with {} families**".format(len(grouped)))
        
        for key in sorted(grouped.keys()):
            # key is now just "FamilyName"
            fam = key
            typename = ""  # No type name anymore
            
            # Default prefix based on family type
            prefix = "P-"
            if self.logic_num.is_pilecap(fam):
                prefix = "PC-"
            suffix = ""
            
            count = len(grouped[key])
            item = PrefixItem(key, fam, typename, prefix, suffix, count)
            # output.print_md("  - Adding: `{}` (Prefix: `{}`, Count: {})".format(key, prefix, count))
            self.prefix_data.Add(item)
        
        self.dgPrefixes.ItemsSource = self.prefix_data
        # output.print_md("**✓ Grid Populated - Total Items: {}**".format(self.prefix_data.Count))

    def load_zones(self):
        """Load scope boxes into multi-select list."""
        sbs = self.logic_sheets.get_scope_boxes()
        self.scope_box_items = ObservableCollection[object]()
        
        for sb in sbs:
            self.scope_box_items.Add(ScopeBoxItem(sb, getattr(sb, 'Name', None) or str(sb.Id)))
            
        self.lbScopeBoxes.ItemsSource = self.scope_box_items
    
    def OnScopeCheck(self, sender, args):
        """Handle check events."""
        sel = [i.Name for i in self.scope_box_items if i.IsSelected]
        self.tbZoneInfo.Text = "Selected {} zones: {}".format(len(sel), ", ".join(sel))

    # ==========================
    # ACTIONS
    # ==========================
    def RunCoordinates_Click(self, sender, args):
        """Run Coordinates Logic."""
        elements = self.get_elements()
        self.run_coordinates(elements)

    def RunNumbering_Click(self, sender, args):
        """Run Numbering Logic."""
        elements = self.get_elements()
        self.run_numbering(elements)

    def RunSheets_Click(self, sender, args):
        """Run Sheets Logic."""
        elements = self.get_elements()
        self.run_sheets(elements)

    # ==========================
    # LOGIC WRAPPERS
    # ==========================
    def _get_coord_mode_from_ui(self):
        """Map coord combo to logic_coords coord_mode string."""
        if not hasattr(self, "cmbCoordType") or self.cmbCoordType is None:
            return "coordination"
        idx = self.cmbCoordType.SelectedIndex
        modes = ("coordination", "survey", "project_base")
        if 0 <= idx < len(modes):
            return modes[idx]
        return "coordination"

    # ==========================
    # LIVE COORDINATES
    # ==========================

    def _restore_live_state(self):
        """Set toggle and indicator to match the saved config on window open."""
        try:
            cfg = _dmu_read_config()
            is_active = cfg.get('active', False)
            self._apply_live_ui(is_active)
            # Also restore saved param names
            self.tbParamX.Text   = cfg.get('param_x',   'X coordinate')
            self.tbParamY.Text   = cfg.get('param_y',   'Y coordinate')
            self.tbParamRot.Text = cfg.get('param_rot', 'Rotation angle')
            modes = ('coordination', 'survey', 'project_base')
            mode  = cfg.get('coord_mode', 'coordination')
            if mode in modes:
                self.cmbCoordType.SelectedIndex = modes.index(mode)
        except Exception:
            log_swallowed(_LOG, u'PileMasterWindow._restore_live_state')

    def _apply_live_ui(self, is_active):
        """Update toggle button, dot colour and status text."""
        try:
            import System.Windows.Media as Media
            self.TglLiveCoords.IsChecked = is_active
            self.TglLiveCoords.Content   = 'DISABLE' if is_active else 'ENABLE'
            if is_active:
                self.LiveDot.Fill    = Media.Brushes.LimeGreen
                self.TxtLiveStatus.Text = (
                    u'Active — coordinates update automatically when piles move or are created.'
                )
            else:
                self.LiveDot.Fill    = Media.Brushes.LightGray
                self.TxtLiveStatus.Text = (
                    u'Inactive — enable to auto-update coords when piles move or are created.'
                )
        except Exception:
            log_swallowed(_LOG, u'PileMasterWindow._apply_live_ui')

    def _current_config_from_ui(self):
        """Build a config dict from the current UI state."""
        modes = ('coordination', 'survey', 'project_base')
        idx   = max(0, min(self.cmbCoordType.SelectedIndex, 2))
        return {
            'active':          bool(self.TglLiveCoords.IsChecked),
            'param_x':         (self.tbParamX.Text   or 'X coordinate').strip(),
            'param_y':         (self.tbParamY.Text   or 'Y coordinate').strip(),
            'param_rot':       (self.tbParamRot.Text or 'Rotation angle').strip(),
            'coord_mode':      modes[idx],
            'update_rotation': True,
        }

    def ToggleLiveCoords_Click(self, sender, args):
        """Enable or disable live coordinate tracking."""
        try:
            is_active = (self.TglLiveCoords.IsChecked == True)  # noqa: E712
            cfg = self._current_config_from_ui()
            cfg['active'] = is_active
            _dmu_write_config(cfg)
            self._apply_live_ui(is_active)
        except Exception as e:
            forms.alert(u'Live Coordinates error: {}'.format(e), title='Error')

    def run_coordinates(self, elements):
        px = self.tbParamX.Text
        py = self.tbParamY.Text
        prot = self.tbParamRot.Text

        coord_mode = self._get_coord_mode_from_ui()

        # Save current config so the DMU picks up any param name changes
        _dmu_write_config(self._current_config_from_ui())

        s, f = self.logic_coords.update_coordinates(
            elements,
            px,
            py,
            prot,
            update_rotation=True,
            coord_mode=coord_mode,
        )
        forms.alert(
            "Coordinates Updated!\n\nSuccess: {}\nFailed: {}".format(s, f),
            title="Coordinates Report"
        )

    def run_numbering(self, elements):
        modes = []
        if self.chkPile.IsChecked: modes.append("Pile")
        if self.chkPileCap.IsChecked: modes.append("Pilecap")
        
        if not modes:
            forms.alert("Please select at least one numbering mode (Piles or Pilecaps).")
            return

        # Get "only empty" checkbox value
        only_empty = self.chkOnlyEmpty.IsChecked if hasattr(self, 'chkOnlyEmpty') else False

        # Gather configuration from UI
        # Key: "FamilyName" -> Value: (Prefix, Suffix)
        config_map = {}
        for item in self.prefix_data:
            if item.Key not in ["NO_ELEMENTS", "NO_TYPES", "INFO"]:
                config_map[item.Key] = (item.Prefix, item.Suffix)
        
        # DEBUG: Print to pyRevit console
        from pyrevit import script
        output = script.get_output()
        output.print_md("## DEBUG: Configuration Map from UI")
        output.print_md("Number of items in config_map: **{}**".format(len(config_map)))
        for k, v in config_map.items():
            output.print_md("- Family: `{}` -> Prefix: `{}`, Suffix: `{}`".format(k, v[0], v[1]))
            
        if not elements:
            forms.alert("No Structural Foundations found in the selected scope.\n\nCheck 'Selection Scope' (Active View vs Project).", title="Empty Selection")
            return

        # Pass all elements as a dummy group
        dummy_group = {"All": elements}
        
        count, piles_count, caps_count = self.logic_num.apply_numbering(dummy_group, config_map, modes, only_empty)
        
        msg = "Numbering Complete!\n\nElements Processed: {}\n(Piles: {}, Caps: {})".format(count, piles_count, caps_count)
        if count == 0:
            msg += "\n\nWARNING: No elements were numbered.\nPossible reasons:\n- Elements don't match family keywords\n- All elements already have numbers (if 'Only empty' is checked)"
            
        forms.alert(msg, title="Numbering Report")

    def run_sheets(self, elements):
        # Get selected scope boxes
        selected_items = [i for i in self.scope_box_items if i.IsSelected]

        if not selected_items:
            forms.alert("Please select at least one Scope Box.", title="No Selection")
            return

        mapping = {item.Name: item.SB for item in selected_items}

        forms.alert("Processing... This may take a moment if creating parameters.", title="Processing")

        updated, outside, (created_count, err) = self.logic_sheets.update_visibility(elements, mapping)

        msg = "Visibility Updated Successfully!\n\nIndices Updated: {}\nElements Outside All Zones: {}".format(updated, outside)

        if created_count > 0:
            msg += "\n\n(Auto-created {} missing 'Show_in_X' parameters)".format(created_count)

        if err:
            msg += "\n\nWARNING: Parameter creation failed:\n{}".format(err)

        forms.alert(msg, title="Visibility Report")

    # ── Report tab ────────────────────────────────────────────────────────────

    def GenerateReport_Click(self, sender, args):
        lv_sel = self.CboReportLevel.SelectedItem
        lv_id  = self._report_level_map.get(lv_sel) if lv_sel and lv_sel != u'— All levels —' else None

        sort_idx = self.CboReportSort.SelectedIndex
        sort_by  = ['mark', 'level', 'x', 'y'][sort_idx] if 0 <= sort_idx < 4 else 'mark'

        opts = {'filter_level_id': lv_id, 'sort_by': sort_by}

        try:
            raw_rows = collect_report(self.doc, opts)
        except Exception as e:
            forms.alert(u'Error collecting piles:\n{}'.format(e))
            return

        self._report_rows = raw_rows

        src = ObservableCollection[object]()
        for i, r in enumerate(raw_rows, 1):
            src.Add(_ReportRowWrapper(r, i))
        self.GridReport.ItemsSource = src

        self.TxtReportStatus.Text = u'{} piles found.'.format(len(raw_rows))
        has_rows = len(raw_rows) > 0
        self.BtnReportXlsx.IsEnabled = has_rows
        self.BtnReportCsv.IsEnabled  = has_rows

    def ReportGrid_SelectionChanged(self, sender, args):
        selected = list(self.GridReport.SelectedItems)
        if not selected:
            return
        try:
            ids = [DB.ElementId(Int64(int(w.el_id))) for w in selected if w.el_id is not None]
            if ids:
                self.uidoc.Selection.SetElementIds(List[DB.ElementId](ids))
        except Exception:
            log_swallowed(_LOG, u'PileMasterWindow.ReportGrid_SelectionChanged')

    def ReportXlsx_Click(self, sender, args):
        if not self._report_rows:
            return
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            proj = ''
            try:
                proj = self.doc.ProjectInformation.Name or ''
            except Exception:
                log_swallowed(_LOG, u'PileMasterWindow.ReportXlsx_Click')
            _report_xlsx(self._report_rows, path, proj)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use Export CSV instead.')
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def ReportCsv_Click(self, sender, args):
        if not self._report_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _report_csv(self._report_rows, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def _refresh_schedule_list(self):
        try:
            items = list_pile_schedules(self.doc)
            self._schedule_items = items
            self.LstSchedules.ItemsSource = [u'{}  (id {})'.format(n, i) for n, i in items]
            self.TxtSchedStatus.Text = u'{} foundation schedule(s) found.'.format(len(items))
        except Exception as e:
            self._schedule_items = []
            self.TxtSchedStatus.Text = u'Error: {}'.format(e)

    def ScheduleRefresh_Click(self, sender, args):
        self._refresh_schedule_list()

    def ScheduleCreate_Click(self, sender, args):
        try:
            with nosa_tx.guard(DB.Transaction(self.doc, u'NOSA — Pile Schedule')) as t:
                t.Start()
                _sched, _created, msg = create_or_open_schedule(self.doc, self.uidoc)
                t.Commit()
            self._refresh_schedule_list()
            forms.alert(msg, title=u'Pile Schedule')
        except Exception as e:
            forms.alert(u'Could not create schedule:\n{}'.format(e))

    def ScheduleOpen_Click(self, sender, args):
        idx = self.LstSchedules.SelectedIndex
        if idx < 0 or not getattr(self, '_schedule_items', None):
            return
        if idx >= len(self._schedule_items):
            return
        _name, eid = self._schedule_items[idx]
        try:
            sched = self.doc.GetElement(element_id_from_int(eid))
            if sched:
                self.uidoc.ActiveView = sched
                self.TxtSchedStatus.Text = u'Opened: {}'.format(sched.Name)
        except Exception as e:
            forms.alert(u'Could not open schedule:\n{}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)


