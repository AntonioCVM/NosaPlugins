# -*- coding: utf-8 -*-
from pyrevit import forms, revit, DB, script
import wpf
import sys
import os
import System
from System.Collections.ObjectModel import ObservableCollection

# Import Logic Modules (absolute — lib_path injected by script.py)
from logic_coords import CoordinateLogic
from logic_numbering import NumberingLogic
from logic_sheets import SheetLogic

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

class ScopeBoxItem:
    def __init__(self, sb, name):
        self.SB = sb
        self.Name = name
        self.IsSelected = False

class PileMasterWindow(forms.WPFWindow):
    def __init__(self):
        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        wpf.LoadComponent(self, xaml_file)
        
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
        
        # Load Initial Data AFTER UI is ready
        self.Loaded += self.OnWindowLoaded
    
    def OnWindowLoaded(self, sender, args):
        """Called when window is fully loaded and visible."""
        # Track current tab (0=Coords, 1=Numbering, 2=Visibility)
        self.current_tab = 0
        self.update_nav_selection()
        
        # Initial load
        self.load_numbering_data()
        self.load_zones()
    
    def NavButton_Click(self, sender, args):
        """Handle sidebar navigation clicks."""
        btn_name = sender.Name
        
        # Hide all tabs
        self.TabCoords.Visibility = System.Windows.Visibility.Collapsed
        self.TabNumbering.Visibility = System.Windows.Visibility.Collapsed
        self.TabVisibility.Visibility = System.Windows.Visibility.Collapsed
        
        # Show selected tab and update action button
        if btn_name == "BtnTabCoords":
            self.TabCoords.Visibility = System.Windows.Visibility.Visible
            self.current_tab = 0
            self.BtnAction.Content = "UPDATE COORDINATES"
        elif btn_name == "BtnTabNumbering":
            self.TabNumbering.Visibility = System.Windows.Visibility.Visible
            self.current_tab = 1
            self.BtnAction.Content = "RUN NUMBERING"
        elif btn_name == "BtnTabVisibility":
            self.TabVisibility.Visibility = System.Windows.Visibility.Visible
            self.current_tab = 2
            self.BtnAction.Content = "UPDATE VISIBILITY"
        
        self.update_nav_selection()
    
    def update_nav_selection(self):
        """Update the visual selection state of nav buttons."""
        self.BtnTabCoords.Tag = "Selected" if self.current_tab == 0 else None
        self.BtnTabNumbering.Tag = "Selected" if self.current_tab == 1 else None
        self.BtnTabVisibility.Tag = "Selected" if self.current_tab == 2 else None
    
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
            self.scope_box_items.Add(ScopeBoxItem(sb, sb.Name))
            
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

    def run_coordinates(self, elements):
        px = self.tbParamX.Text
        py = self.tbParamY.Text
        prot = self.tbParamRot.Text

        coord_mode = self._get_coord_mode_from_ui()

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
