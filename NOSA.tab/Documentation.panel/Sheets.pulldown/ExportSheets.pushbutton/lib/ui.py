# -*- coding: utf-8 -*-
import clr
try:
    clr.AddReference('System.Drawing')
    clr.AddReference('System.Windows.Forms')
    clr.AddReference('PresentationCore')
    clr.AddReference('PresentationFramework')
except Exception:
    pass

import os
import re
import System
from System.Windows import MessageBox, Window, Application
from System.Windows.Controls import CheckBox, UserControl, Orientation
from System.Windows.Input import Keyboard, ModifierKeys
from System.Collections.ObjectModel import ObservableCollection

from pyrevit import revit, DB, UI, forms
from pyrevit.forms import WPFWindow

from managers import ViewSetManager, NamingProfileManager, LanguageManager
from utils import Utils
from view_collector import ViewCollector
from exporters import ExportManager
from naming import NamingBuilder
from nosa_utils.logging import Logger
from nosa_utils.theme import ThemeManager
from nosa_utils.i18n import Localization
from config import Config

logger = Logger()

class SheetItem(object):
    """Wrapper for sheet/view item in ListView"""
    def __init__(self, element):
        self.Element = element
        self.Id = element.Id
        self.IsChecked = False
        
        # Display properties
        if hasattr(element, 'SheetNumber'):
            self.Number = element.SheetNumber
            self.Name = element.Name
            
            # Revision
            try:
                p = element.LookupParameter("Current Revision")
                self.Revision = p.AsString() if p else "-"
            except Exception:
                self.Revision = "-"
        else:
            # It's a view
            self.Number = str(element.ViewType)
            self.Name = element.Name
            self.Revision = "-"

class NamingProfileItem(object):
    """Wrapper for combo box item"""
    def __init__(self, name):
        self.Name = name
    
    def __str__(self):
        return self.Name

class ExportSheetsProForm(WPFWindow):
    """Modern WPF UI for Export Sheets Pro v4.2"""
    
    def __init__(self, doc):
        self.doc = doc
        
        # Determine XAML path
        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        WPFWindow.__init__(self, xaml_file)
        
        # Managers
        self.naming_builder = NamingBuilder()
        self.output_folder = ""
        self.current_preset = "Standard"
        self.is_exporting_views = False
        self._last_checked_index = -1
        self._loaded_config = {}
        self._is_initializing = True
        
        # Data
        self.all_sheets = []
        self.sheet_items = ObservableCollection[SheetItem]()
        self.project_params = {}  # Store project parameters
        
        # Setup UI
        self.ListSheets.ItemsSource = self.sheet_items
        
        # Theme
        self.dark_mode = ThemeManager.load_theme()
        self.ApplyTheme(self.dark_mode)
        
        # Setup Tabs (Sidebar Navigation)
        self.tabs = {
            "BtnTabSheets": self.TabSheets,
            "BtnTabNaming": self.TabNaming,
            "BtnTabFormats": self.TabFormats,
            "BtnTabConfig": self.TabConfig,
            "BtnTabLog": self.TabLog
        }
        
        # Initial Load
        self.LoadLastConfig()
        self.LoadData()
        self.LoadNamingProfiles()  # Load Profiles
        self.ApplyLoadedConfig()
        self.UpdateStatus()
        self._is_initializing = False
        self._load_sheet_sets()

    # =========================================================================
    # THEME & UI HELPERS
    # =========================================================================
    
    def ApplyTheme(self, dark_mode):
        self.dark_mode = dark_mode
        self.ChkDarkMode.IsChecked = dark_mode
        colors = ThemeManager.get_colors(dark_mode)
        
        # Apply colors to Dynamic Resources
        try:
            self.Resources["BgColor"].Color = colors['bg']
            self.Resources["PanelColor"].Color = colors['panel']
            self.Resources["TextColor"].Color = colors['text']
            self.Resources["AccentColor"].Color = colors['accent']
            self.Resources["BorderColor"].Color = colors['border']
        except Exception as e:
            logger.debug("Failed to apply dynamic resource theme: " + str(e))
            
    def Theme_Toggled(self, sender, args):
        new_mode = self.ChkDarkMode.IsChecked
        if new_mode != self.dark_mode:
            ThemeManager.save_theme(new_mode)
            self.ApplyTheme(new_mode)
            self.SaveLastConfig()
            
    def NavButton_Click(self, sender, args):
        btn_name = sender.Name
        self.SwitchTab(btn_name)
        
    def SwitchTab(self, btn_name):
        # Update Content Visibility
        if btn_name in self.tabs:
            target_grid = self.tabs[btn_name]
            
            # Hide all
            for grid in self.tabs.values():
                grid.Visibility = System.Windows.Visibility.Collapsed
            
            # Show target
            target_grid.Visibility = System.Windows.Visibility.Visible
            
        # Update Buttons Visual State
        for name in self.tabs.keys():
            btn = getattr(self, name)
            if name == btn_name:
                btn.Tag = "Selected"
            else:
                btn.Tag = ""
        self.SaveLastConfig()

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
            self.sheet_items.Add(SheetItem(el))
            
        # Load Parameters
        self.LoadProjectParameters()  # Load Project Info params
        self.LoadParameters()         # Load Available Params List

    def LoadProjectParameters(self):
        """Extracts all parameters from Project Information"""
        self.project_params = {}
        try:
            if self.doc.ProjectInformation:
                p_info = self.doc.ProjectInformation
                
                # Built-in properties
                if p_info.Name: self.project_params['Project Name'] = p_info.Name
                if hasattr(p_info, 'Number') and p_info.Number: self.project_params['Project Number'] = p_info.Number
                if hasattr(p_info, 'Status') and p_info.Status: self.project_params['Project Status'] = p_info.Status
                if hasattr(p_info, 'ClientName') and p_info.ClientName: self.project_params['Client Name'] = p_info.ClientName
                if hasattr(p_info, 'Address') and p_info.Address: self.project_params['Project Address'] = p_info.Address
                
                # Scan all parameters
                for param in p_info.Parameters:
                    try:
                        if param.Definition:
                             name = param.Definition.Name
                             # Get value based on storage type
                             val = None
                             if param.StorageType == DB.StorageType.String:
                                 val = param.AsString()
                             else:
                                 val = param.AsValueString()
                             
                             if val:
                                 self.project_params[name] = val
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Error loading project parameters", e)

    def LoadParameters(self):
        self.ListParams.Items.Clear()
        parameters = set()

        # 1. Project Info Parameters (from our loaded dict)
        for k in self.project_params.keys():
            parameters.add(k)
        
        # Also ensure definition names from ProjectInfo are there even if empty?
        # User wants to select them.
        try:
            if self.doc.ProjectInformation:
                for p in self.doc.ProjectInformation.Parameters:
                    if p.Definition:
                        parameters.add(p.Definition.Name)
        except Exception:
            pass
            
        # 2. Sheet/View Parameters (from first available element)
        if self.sheet_items and len(self.sheet_items) > 0:
            first_element = self.sheet_items[0].Element
            for p in first_element.Parameters:
                 if p.Definition:
                        parameters.add(p.Definition.Name)
                        
        # Ensure Criticals exist
        defaults = ["Sheet Number", "Sheet Name", "Current Revision", "Project Number", "Project Name"]
        for d in defaults:
            parameters.add(d)
            
        # Sort and Add
        for p in sorted(list(parameters)):
            self.ListParams.Items.Add(p)

    # =========================================================================
    # TAB 1: SHEETS
    # =========================================================================

    def Mode_Changed(self, sender, args):
        if self.RbViews.IsChecked == True:
            self.is_exporting_views = True
        else:
            self.is_exporting_views = False
        self.LoadData()
        self.UpdateStatus()
        self.SaveLastConfig()
        
    def Search_Changed(self, sender, args):
        search_txt = self.TxtSearch.Text.lower()
        if not search_txt:
            self.ListSheets.ItemsSource = self.sheet_items
            self.SaveLastConfig()
            return
            
        filtered = [item for item in self.sheet_items 
                   if search_txt in item.Number.lower() or search_txt in item.Name.lower()]
        self.ListSheets.ItemsSource = filtered
        self.SaveLastConfig()

    def Sheet_Checked(self, sender, args):
        current_item = getattr(sender, "DataContext", None)
        if current_item is not None:
            current_source = list(self.ListSheets.ItemsSource)
            current_index = self._get_item_index(current_source, current_item)
            modifiers = Keyboard.Modifiers

            if current_index >= 0 and (modifiers & ModifierKeys.Shift) and self._last_checked_index >= 0:
                start = min(self._last_checked_index, current_index)
                end = max(self._last_checked_index, current_index)
                target_state = sender.IsChecked == True
                for idx in range(start, end + 1):
                    current_source[idx].IsChecked = target_state
                self.ListSheets.Items.Refresh()

            if current_index >= 0:
                self._last_checked_index = current_index

        self.UpdateStatus()
        self.SaveLastConfig()
    
    def SelectAll_Click(self, sender, args):
        for item in self.ListSheets.ItemsSource:
            item.IsChecked = True
        self.ListSheets.Items.Refresh()
        self.UpdateStatus()
        self.SaveLastConfig()

    def SelectNone_Click(self, sender, args):
        for item in self.ListSheets.ItemsSource:
            item.IsChecked = False
        self.ListSheets.Items.Refresh()
        self.UpdateStatus()
        self.SaveLastConfig()

    def CheckSelectedRows_Click(self, sender, args):
        """Marks as checked all currently selected rows in the list."""
        selected_rows = list(self.ListSheets.SelectedItems)
        if not selected_rows:
            MessageBox.Show("Select one or more rows first.")
            return

        for item in selected_rows:
            item.IsChecked = True

        self.ListSheets.Items.Refresh()
        self.UpdateStatus()
        self.SaveLastConfig()

    def InvertChecks_Click(self, sender, args):
        """Invert current checked state for visible rows."""
        for item in self.ListSheets.ItemsSource:
            item.IsChecked = not (item.IsChecked == True)
        self.ListSheets.Items.Refresh()
        self.UpdateStatus()
        self.SaveLastConfig()

    # =========================================================================
    # SHEET SETS
    # =========================================================================

    def _load_sheet_sets(self):
        """Populate ComboSheetSets with saved sets."""
        try:
            self.ComboSheetSets.Items.Clear()
            self.ComboSheetSets.Items.Add("")
            for name in ViewSetManager.get_all_sets():
                self.ComboSheetSets.Items.Add(name)
            self.ComboSheetSets.SelectedIndex = 0
        except Exception:
            pass

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
        for item in self.sheet_items:
            item.IsChecked = Utils._get_element_id_value(item.Id) in id_values
        self.ListSheets.Items.Refresh()
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

    def SelectRange_Click(self, sender, args):
        """Select/check a numeric range of sheet numbers (e.g. A101-A110 or 101-110)."""
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

        start_raw = parts[0].strip()
        end_raw = parts[1].strip()

        matched = 0
        # Strategy 1: same prefix and numeric suffix, e.g. A101-A110
        m_start = re.match(r"^([A-Za-z\-]*)(\d+)$", start_raw)
        m_end = re.match(r"^([A-Za-z\-]*)(\d+)$", end_raw)
        if m_start and m_end and m_start.group(1).lower() == m_end.group(1).lower():
            prefix = m_start.group(1).lower()
            n1 = int(m_start.group(2))
            n2 = int(m_end.group(2))
            low = min(n1, n2)
            high = max(n1, n2)
            for item in self.sheet_items:
                number = (item.Number or "").strip().lower()
                item_match = re.match(r"^([A-Za-z\-]*)(\d+)$", number)
                if item_match and item_match.group(1) == prefix:
                    current_num = int(item_match.group(2))
                    if low <= current_num <= high:
                        item.IsChecked = True
                        matched += 1
        else:
            # Strategy 2: numeric fallback using first number found in the sheet number
            n1 = self._extract_first_number(start_raw)
            n2 = self._extract_first_number(end_raw)
            if n1 is None or n2 is None:
                MessageBox.Show("Could not parse numeric range.")
                return
            low = min(n1, n2)
            high = max(n1, n2)
            for item in self.sheet_items:
                current_num = self._extract_first_number(item.Number or "")
                if current_num is not None and low <= current_num <= high:
                    item.IsChecked = True
                    matched += 1

        self.ListSheets.Items.Refresh()
        self.UpdateStatus()
        self.SaveLastConfig()
        MessageBox.Show("Checked {} items in range.".format(matched))

    # =========================================================================
    # TAB 2: NAMING & PROFILES
    # =========================================================================

    def LoadNamingProfiles(self):
        """Populate ComboBox with profiles"""
        self.ComboNamingProfiles.ItemsSource = None
        profiles = NamingProfileManager.get_all_profiles()
        
        items = []
        for p in profiles:
            items.append(NamingProfileItem(p))
            
        self.ComboNamingProfiles.ItemsSource = items
        # If we already loaded a persisted profile name, select it now.
        self._select_naming_profile(self._loaded_config.get('naming_profile'))

    def NamingProfile_Selected(self, sender, args):
        if self.ComboNamingProfiles.SelectedItem:
            profile_name = self.ComboNamingProfiles.SelectedItem.Name
            
            # Load Profile Data
            data = NamingProfileManager.load_profile(profile_name)
            if data:
                if isinstance(data, dict):
                    self.naming_builder.from_dict(data)
                else:
                    self.naming_builder.template = data if isinstance(data, list) else []
                
                self.UpdateTemplateList()
                self.SaveLastConfig()

    def SaveProfile_Click(self, sender, args):
        if not self.naming_builder.template:
             MessageBox.Show("Template is empty. Please add parameters first.")
             return
             
        # Ask for name
        from pyrevit.forms import ask_for_string
        name = ask_for_string(prompt="Enter Profile Name:", title="Save Naming Profile")
        
        if name:
            NamingProfileManager.save_profile(name, self.naming_builder)
            self.LoadNamingProfiles() # Refresh
            MessageBox.Show("Profile '{}' saved.".format(name))
            
    def DeleteProfile_Click(self, sender, args):
        if self.ComboNamingProfiles.SelectedItem:
            name = self.ComboNamingProfiles.SelectedItem.Name
            res = MessageBox.Show("Delete profile '{}'?".format(name), "Confirm", MessageBox.MessageBoxButton.YesNo)
            if res == MessageBox.MessageBoxResult.Yes:
                NamingProfileManager.delete_profile(name)
                self.LoadNamingProfiles()

    def Param_DoubleClick(self, sender, args):
        selected_param = self.ListParams.SelectedItem
        if selected_param:
            self.naming_builder.add_parameter(selected_param)
            self.UpdateTemplateList()

    def Template_DoubleClick(self, sender, args):
        selected_item = self.ListTemplate.SelectedItem
        if selected_item:
            param_name = str(selected_item)
            self.naming_builder.remove_parameter(param_name)
            self.UpdateTemplateList()
            
    def Separator_Changed(self, sender, args):
        self.naming_builder.separator = self.TxtSeparator.Text
        self.UpdatePreview()
        self.SaveLastConfig()
        
    def UpdateTemplateList(self):
        self.ListTemplate.Items.Clear()
        for p in self.naming_builder.template:
            self.ListTemplate.Items.Add(str(p))
        self.UpdatePreview()
        
    def UpdatePreview(self):
        if not self.sheet_items:
            self.TxtPreview.Text = "No sheets available"
            return
        
        # Use first sheet for preview
        first_item = self.sheet_items[0]
        try:
            # PASS PROJECT PARAMS HERE
            name = self.naming_builder.build_filename(
                first_item.Element, 
                project_params=self.project_params, 
                is_view=self.is_exporting_views
            )
            self.TxtPreview.Text = name + ".pdf"
        except Exception as e:
            self.TxtPreview.Text = "Error: " + str(e)

    # =========================================================================
    # TAB 3 & 4: CONFIG & STATUS
    # =========================================================================

    def ColorMode_Changed(self, sender, args):
        self.SaveLastConfig()

    def Format_Changed(self, sender, args):
        self.UpdateStatus()
        self.SaveLastConfig()

    def _force_black(self):
        return hasattr(self, 'RbForceBlack') and self.RbForceBlack.IsChecked == True

    def _pre_export_check(self, elements):
        """Return list of sheet/view names that have temporary state active."""
        if not (hasattr(self, 'ChkPreExportCheck') and self.ChkPreExportCheck.IsChecked == True):
            return []
        flagged = []
        for el in elements:
            try:
                v = el if hasattr(el, 'IsTemporaryHideIsolateActive') else None
                if v is None:
                    continue
                if v.IsTemporaryHideIsolateActive():
                    flagged.append(getattr(el, 'Name', str(el.Id)))
            except Exception:
                pass
        return flagged
        
    def Browse_Click(self, sender, args):
        path = forms.pick_folder()
        if path:
            self.output_folder = path
            self.TxtFolder.Text = path
            self.SaveLastConfig()

    def UpdateStatus(self):
        # Selection
        count = 0
        for item in self.sheet_items:
            if item.IsChecked: count += 1
        self.LblStatusSelection.Text = "{} Sheets Selected".format(count)
        
        # Formats
        formats = []
        if self.ChkPDF.IsChecked: formats.append("PDF")
        if self.ChkDWG.IsChecked: formats.append("DWG")
        if self.ChkDXF.IsChecked: formats.append("DXF")
        self.LblStatusFormats.Text = ", ".join(formats) if formats else "None"

    # =========================================================================
    # EXPORT LOGIC
    # =========================================================================

    def Export_Click(self, sender, args):
        # 1. Gather Selection
        selected_elements = [item.Element for item in self.sheet_items if item.IsChecked]
        
        if not selected_elements:
            MessageBox.Show("Please select sheets/views first.")
            return
            
        if not self.output_folder:
            MessageBox.Show("Please select an output folder in Configuration.")
            self.SwitchTab("BtnTabConfig")
            return

        # 1b. Pre-export check: temporary overrides/isolations
        flagged = self._pre_export_check(selected_elements)
        if flagged:
            names = "\n".join(flagged[:10])
            if len(flagged) > 10:
                names += "\n... and {} more".format(len(flagged) - 10)
            res = MessageBox.Show(
                "Warning: {} view(s) have temporary Hide/Isolate or overrides active.\n\n{}\n\nThese may affect export colours.\n\nContinue anyway?".format(len(flagged), names),
                "Pre-export Warning",
                System.Windows.MessageBoxButton.YesNo
            )
            if str(res) != 'Yes':
                return

        # 2. Switch to Log Tab
        self.SwitchTab("BtnTabLog")
        self.ExportProgress.IsIndeterminate = True
        self.TxtLog.Text = "Starting Export...\n"
        
        # 3. Formats
        export_formats = {
            'pdf': self.ChkPDF.IsChecked == True,
            'dwg': self.ChkDWG.IsChecked == True,
            'dxf': self.ChkDXF.IsChecked == True,
            'force_black': self._force_black(),
        }

        self.TxtLog.AppendText("Colour mode: {}\n".format(
            "Force black" if export_formats['force_black'] else "Model colours"
        ))
        self.TxtLog.AppendText("Formats: PDF={}, DWG={}, DXF={}\n".format(
            export_formats['pdf'], export_formats['dwg'], export_formats['dxf']
        ))
        
        # Use pre-loaded + potentially refreshed project params
        self.LoadProjectParameters()
        
        mgr = ExportManager(
            self.doc,
            selected_elements,
            self.naming_builder,
            self.output_folder,
            export_formats,
            self.current_preset,
            self.project_params,
            self.is_exporting_views
        )
        
        # Define progress callback
        def progress(msg):
             self.TxtLog.AppendText(msg + "\n")
             self.TxtLog.ScrollToEnd()
             self.TxtLog.Dispatcher.Invoke(lambda: None, System.Windows.Threading.DispatcherPriority.Background)

        self.TxtLog.AppendText("Processing {} elements...\n".format(len(selected_elements)))
        
        # Execute
        try:
            success, msg = mgr.export_all(progress)
            
            if success:
                self.TxtLog.AppendText("EXPORT COMPLETED SUCCESSFULLY.\n")
                self.ExportProgress.IsIndeterminate = False
                self.ExportProgress.Value = 100
                self.SaveLastConfig()
            else:
                self.TxtLog.AppendText("EXPORT FAILED: {}\n".format(msg))
                self.ExportProgress.IsIndeterminate = False
            
        except Exception as e:
            self.TxtLog.AppendText("ERROR: " + str(e) + "\n")
            logger.error("Export failed", e)

    # =========================================================================
    # CONFIG PERSISTENCE
    # =========================================================================

    def SaveLastConfig(self):
        if self._is_initializing:
            return
        try:
            profile_name = self.ComboNamingProfiles.SelectedItem.Name if self.ComboNamingProfiles.SelectedItem else None
            config_data = {
                'output_folder': self.output_folder,
                'naming_profile': profile_name,
                'is_exporting_views': self.is_exporting_views,
                'search_text': self.TxtSearch.Text if hasattr(self, "TxtSearch") else "",
                'format_pdf': self.ChkPDF.IsChecked == True,
                'format_dwg': self.ChkDWG.IsChecked == True,
                'format_dxf': self.ChkDXF.IsChecked == True,
                'dark_mode': self.dark_mode,
                'active_tab': self._get_active_tab_name()
            }
            import json
            with open(Config.LAST_CONFIG_FILE, 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception:
            pass
            
    def LoadLastConfig(self):
        try:
            import json
            if os.path.exists(Config.LAST_CONFIG_FILE):
                with open(Config.LAST_CONFIG_FILE, 'r') as f:
                    self._loaded_config = json.load(f)
                    self._set_output_folder(self._loaded_config.get('output_folder', ''))
        except Exception:
            pass

    def ApplyLoadedConfig(self):
        """Apply persisted session options after controls are initialized."""
        if not self._loaded_config:
            return

        data = self._loaded_config

        self.dark_mode = data.get('dark_mode', self.dark_mode)
        self.ApplyTheme(self.dark_mode)

        self.RbViews.IsChecked = data.get('is_exporting_views', False)
        self.RbSheets.IsChecked = not self.RbViews.IsChecked
        self.is_exporting_views = self.RbViews.IsChecked == True

        self.ChkPDF.IsChecked = data.get('format_pdf', True)
        self.ChkDWG.IsChecked = data.get('format_dwg', False)
        self.ChkDXF.IsChecked = data.get('format_dxf', False)
        self.TxtSearch.Text = data.get('search_text', '')

        # Reapply mode-dependent data and filtered list
        self.LoadData()
        self.Search_Changed(self.TxtSearch, None)

        self._select_naming_profile(data.get('naming_profile'))

        self.SwitchTab(data.get('active_tab', "BtnTabSheets"))

    def _get_active_tab_name(self):
        for name, grid in self.tabs.items():
            if grid.Visibility == System.Windows.Visibility.Visible:
                return name
        return "BtnTabSheets"

    def _get_item_index(self, items, target):
        for idx, item in enumerate(items):
            if item == target:
                return idx
        return -1

    def _extract_first_number(self, value):
        match = re.search(r"\d+", str(value))
        if not match:
            return None
        try:
            return int(match.group(0))
        except Exception:
            return None

    def _set_output_folder(self, folder_path):
        path = folder_path or ""
        self.output_folder = path
        self.TxtFolder.Text = path

    def _select_naming_profile(self, profile_name):
        if not profile_name:
            return False
        for item in self.ComboNamingProfiles.ItemsSource or []:
            if item.Name == profile_name:
                self.ComboNamingProfiles.SelectedItem = item
                return True
        return False
