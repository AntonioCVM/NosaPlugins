# -*- coding: utf-8 -*-
from pyrevit import forms, DB, revit
from pyrevit.forms import WPFWindow
import os
import sys
import System.Windows
from System.Windows.Data import CollectionViewSource
from System.ComponentModel import SortDescription
from System.Collections.ObjectModel import ObservableCollection
from System.Globalization import CultureInfo

import imp
_here = os.path.dirname(os.path.abspath(__file__))
_logic_mod = imp.load_source('tagall_logic', os.path.join(_here, 'logic.py'))
TagLogic = _logic_mod.TagLogic

def _ensure_extension_lib():
    extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    lib_path = os.path.join(extension_root, "lib")
    if lib_path not in sys.path:
        sys.path.append(lib_path)

_ensure_extension_lib()
from nosa_utils.theme import ThemeManager

class CategoryItem(object):
    def __init__(self, data):
        self.Name = data['name']
        self.BicName = data['bic_name']
        self.Bic = data['bic']
        self.Discipline = data['discipline']

class ViewItem(object):
    def __init__(self, data):
        self.Name = data['name']
        self.Element = data['element']
        self.Id = data['id']
        self.IsChecked = False # For mass selection

    def __repr__(self):
        return self.Name

class AssignmentItem(object):
    def __init__(self, cat_name, tag_name, tag_symbol, bic_name):
        self.CategoryName = cat_name
        self.TagName = tag_name
        self.TagSymbol = tag_symbol
        self.BicName = bic_name

class TagAllWindow(WPFWindow):
    def __init__(self, doc):
        self.doc = doc
        self.logic = TagLogic(doc)
        
        # DIAGNOSTIC RUN (Removed for performance)
        # try:
        #      self.logic.diagnose_tags_in_project()
        # (diagnostic block removed)
        
        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        WPFWindow.__init__(self, xaml_file)

        # Collections
        self.all_categories = []
        self.all_views = [] 
        self.assignments = ObservableCollection[AssignmentItem]()
        self.GridAssignments.ItemsSource = self.assignments
        
        # Internal Map
        self.current_tag_map = {} 
        
        # Load Data
        self.LoadCategories()
        self.LoadViews()
        
        # Events
        self.ListCategories.SelectionChanged += self.OnCategorySelectionChanged

        # Theme
        self._dark_mode = ThemeManager.load_theme()
        self.ChkDarkMode.IsChecked = self._dark_mode
        self.ApplyTheme()

    def ApplyTheme(self):
        colors = ThemeManager.get_colors(self._dark_mode)
        try:
            self.Resources["BgColor"].Color = colors['bg']
            self.Resources["PanelColor"].Color = colors['panel']
            self.Resources["TextColor"].Color = colors['text']
            self.Resources["AccentColor"].Color = colors['accent']
            self.Resources["BorderColor"].Color = colors['border']
        except Exception:
            pass

    def Theme_Toggled(self, sender, args):
        self._dark_mode = bool(self.ChkDarkMode.IsChecked)
        ThemeManager.save_theme(self._dark_mode)
        self.ApplyTheme()

    def LoadCategories(self):
        cats = self.logic.get_categories()
        # Create CollectionView for Grouping
        cat_items = [CategoryItem(c) for c in cats]
        view_source = CollectionViewSource()
        view_source.Source = cat_items
        view_source.GroupDescriptions.Add(System.Windows.Data.PropertyGroupDescription("Discipline"))
        self.ListCategories.ItemsSource = view_source.View

    def LoadViews(self):
        views = self.logic.get_taggable_views()
        self.all_views = [ViewItem(v) for v in views]
        self._populate_level_filter()
        self._apply_view_filter()

    def _populate_level_filter(self):
        """Fill ComboFilterLevel with distinct levels found in views."""
        try:
            levels = sorted(set(
                v.Element.GenLevel.Name
                for v in self.all_views
                if hasattr(v.Element, 'GenLevel') and v.Element.GenLevel
            ))
            if hasattr(self, 'ComboFilterLevel'):
                self.ComboFilterLevel.Items.Clear()
                self.ComboFilterLevel.Items.Add("All levels")
                for l in levels:
                    self.ComboFilterLevel.Items.Add(l)
                self.ComboFilterLevel.SelectedIndex = 0
        except Exception:
            pass

    def _apply_view_filter(self):
        text   = self.TxtFilterViews.Text.lower() if hasattr(self, 'TxtFilterViews') else ''
        level  = ''
        try:
            sel = self.ComboFilterLevel.SelectedItem
            if sel and str(sel) != 'All levels':
                level = str(sel)
        except Exception:
            pass

        filtered = []
        for v in self.all_views:
            if text and text not in v.Name.lower():
                continue
            if level:
                try:
                    if not hasattr(v.Element, 'GenLevel') or not v.Element.GenLevel:
                        continue
                    if v.Element.GenLevel.Name != level:
                        continue
                except Exception:
                    continue
            filtered.append(v)
        self.ListViews.ItemsSource = filtered

    def FilterViews_TextChanged(self, sender, args):
        self._apply_view_filter()

    def FilterLevel_Changed(self, sender, args):
        self._apply_view_filter()

    def OnCategorySelectionChanged(self, sender, args):
        selected = self.ListCategories.SelectedItems
        if not selected or len(selected) == 0:
            self.PanelTagConfig.Visibility = System.Windows.Visibility.Collapsed
            self.TxtConfigInfo.Visibility = System.Windows.Visibility.Visible
            return

        # Use the first selected item to populate list
        primary = selected[0]
        self.TxtCurrentCat.Text = "Configure: " + primary.Name
        if len(selected) > 1:
            self.TxtCurrentCat.Text += " (+{} others)".format(len(selected)-1)
            
        tags = self.logic.get_tag_family_symbols(primary.BicName)
        
        if not tags:
             # Only show alert if truly needed, silent otherwise
             forms.alert(
                "No tags found for '{}'.".format(primary.Name),
                title="No Tags Found"
             )
             self.ComboTagTypes.Items.Clear()
             return

        # Store in map
        self.current_tag_map = {}
        tag_names = []
        for t in tags:
            self.current_tag_map[t['name']] = t
            tag_names.append(t['name'])
            
        # Bind SIMPLE STRINGS to the ComboBox
        self.ComboTagTypes.ItemsSource = None
        self.ComboTagTypes.Items.Clear()
        
        for name in tag_names:
            self.ComboTagTypes.Items.Add(name)
        
        if tag_names:
             self.ComboTagTypes.SelectedIndex = 0
            
        self.PanelTagConfig.Visibility = System.Windows.Visibility.Visible
        self.TxtConfigInfo.Visibility = System.Windows.Visibility.Collapsed

    def ApplyTagInfo_Click(self, sender, args):
        selected_cat_items = self.ListCategories.SelectedItems
        selected_tag_name = self.ComboTagTypes.SelectedItem
        
        if not selected_cat_items: return
        if not selected_tag_name: 
            forms.alert("No tag type selected.")
            return
            
        # Lookup symbol object
        tag_data = self.current_tag_map.get(selected_tag_name)
        if not tag_data:
            forms.alert("Error retrieving selected tag data.")
            return
            
        # Update assignments
        for cat_item in selected_cat_items:
            # Remove existing assignment for this category if any
            to_remove = [x for x in self.assignments if x.BicName == cat_item.BicName]
            for x in to_remove:
                self.assignments.Remove(x)
                
            # Add new
            self.assignments.Add(AssignmentItem(
                cat_item.Name,
                tag_data['name'],
                tag_data['symbol'],
                cat_item.BicName
            ))

    def Run_Click(self, sender, args):
        if self.assignments.Count == 0:
            forms.alert("Please configure tag types for at least one category.")
            return

        selected_views = [v for v in self.ListViews.ItemsSource if v.IsChecked]
        
        if not selected_views:
            forms.alert("Please select at least one target view.")
            return
            
        # Options
        use_leader = self.ChkLeader.IsChecked
        skip_dupes = self.ChkSkipDuplicates.IsChecked
        
        # Run
        self.PanelProgress.Visibility = System.Windows.Visibility.Visible
        count_tagged = 0
        count_skipped = 0
        count_failed  = 0
        total_views   = len(selected_views)

        try:
             with revit.Transaction("Batch Tag"):
                 for v_idx, view_item in enumerate(selected_views):
                     view = view_item.Element

                     # Real per-view progress
                     try:
                         self.TxtStatus.Text = "View {}/{}: {}".format(v_idx + 1, total_views, view.Name[:40])
                         pct = int((v_idx / float(total_views)) * 100)
                         self.ProgressBar.Value = pct
                         import System.Windows.Forms as WinForms
                         WinForms.Application.DoEvents()
                     except Exception:
                         pass
                     
                     existing_tags = set()
                     if skip_dupes:
                         existing_tags = self.logic.get_existing_tagged_ids(view)

                     for assignment in self.assignments:
                         bic      = self.logic.safe_get_builtincategory(assignment.BicName)
                         elements = self.logic.get_elements_in_view(view, bic)
                         
                         if not assignment.TagSymbol.IsActive:
                             assignment.TagSymbol.Activate()
                             self.doc.Regenerate()
                             
                         for elem in elements:
                             eid = self.logic.get_id_value(elem.Id)
                             if skip_dupes and eid in existing_tags:
                                 count_skipped += 1
                                 continue
                             loc = self.logic.get_element_center(elem)
                             if not loc:
                                 count_skipped += 1
                                 continue
                             try:
                                 tag = DB.IndependentTag.Create(
                                     self.doc, view.Id, DB.Reference(elem),
                                     use_leader, DB.TagMode.TM_ADDBY_CATEGORY,
                                     DB.TagOrientation.Horizontal, loc
                                 )
                                 tag.ChangeTypeId(assignment.TagSymbol.Id)
                                 count_tagged += 1
                                 existing_tags.add(eid)
                             except Exception:
                                 count_failed += 1
        except Exception as e:
            forms.alert("Error during tagging: " + str(e))

        try:
            self.ProgressBar.Value = 100
            self.TxtStatus.Text = "Done"
        except Exception:
            pass

        forms.alert("Done!\nTagged: {}\nSkipped: {}\nFailed: {}".format(
            count_tagged, count_skipped, count_failed))
        self.Close()
