# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import forms, revit
import os
import sys
import System.Windows
import imp
_here = os.path.dirname(os.path.abspath(__file__))
_logic_mod = imp.load_source('copyvtemplates_logic', os.path.join(_here, 'logic.py'))
CopyTemplateLogic = _logic_mod.CopyTemplateLogic

def _ensure_extension_lib():
    extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    lib_path = os.path.join(extension_root, "lib")
    if lib_path not in sys.path:
        sys.path.append(lib_path)

_ensure_extension_lib()
from nosa_utils.base_window import NOSAWindow

class ViewItem(object):
    def __init__(self, element, name=None):
        self.Element = element
        self.Name = name if name else element.Name
        self.ViewType = str(element.ViewType)
        self.IsChecked = False
        
    def __repr__(self):
        return self.Name

class CopyTemplatesWindow(NOSAWindow):
    def __init__(self, doc):
        self.doc = doc
        self.logic = CopyTemplateLogic(doc)

        self.all_views = []
        self.visible_views1 = []
        self.visible_views2 = []

        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml_file, 'copy_view_templates')
        self.ChkDarkMode.IsChecked = self.dark_mode

        # Load Data AFTER XAML is loaded
        self.LoadTemplates()
        self.LoadViews()

        # Subscribe to Events AFTER everything is initialized
        self.ComboTemplates.SelectionChanged += self.OnComboTemplateChanged
        self.TxtFilterViews1.TextChanged += self.FilterViews1_Changed
        self.MainTabs.SelectionChanged += self.OnTabChanged

    def LoadTemplates(self):
        templates = self.logic.get_all_templates()
        self.ComboTemplates.ItemsSource = templates
        if templates:
            self.ComboTemplates.SelectedIndex = 0

    def LoadViews(self):
        raw_views = self.logic.get_all_non_template_views()
        self.all_views = [ViewItem(v) for v in raw_views]
        
        # Bind to both lists initially
        self.visible_views1 = list(self.all_views)
        self.visible_views2 = list(self.all_views)
        
        self.ListViews1.ItemsSource = self.visible_views1
        self.ListViews2.ItemsSource = self.visible_views2
        
        # Also Populate ComboSourceViews for Tab 2
        self.ComboSourceViews.ItemsSource = raw_views
        if raw_views:
             self.ComboSourceViews.SelectedIndex = 0

    def OnComboTemplateChanged(self, sender, args):
        # Guard against early initialization calls
        if not hasattr(self, 'logic'):
            return
            
        tmpl = self.ComboTemplates.SelectedItem
        if tmpl:
            info = self.logic.get_template_info(tmpl)
            self.TxtInfoScale.Text = "Scale: " + info['scale']
            self.TxtInfoFilters.Text = "Filters: {}".format(len(info['filters']))
            self.PanelTemplateInfo.Visibility = System.Windows.Visibility.Visible

    def OnTabChanged(self, sender, args):
        """Handle tab switching to show/hide appropriate controls."""
        if self.MainTabs.SelectedIndex == 0:
            # Tab 1: Apply Template
            self.ListViews1.Visibility = System.Windows.Visibility.Visible
            self.ListViews2.Visibility = System.Windows.Visibility.Collapsed
            self.ChkCheckAll1.Visibility = System.Windows.Visibility.Visible
            self.ChkCheckAll2.Visibility = System.Windows.Visibility.Collapsed
            self.TxtCount1.Visibility = System.Windows.Visibility.Visible
            self.TxtCount2.Visibility = System.Windows.Visibility.Collapsed
        else:
            # Tab 2: Copy Overrides
            self.ListViews1.Visibility = System.Windows.Visibility.Collapsed
            self.ListViews2.Visibility = System.Windows.Visibility.Visible
            self.ChkCheckAll1.Visibility = System.Windows.Visibility.Collapsed
            self.ChkCheckAll2.Visibility = System.Windows.Visibility.Visible
            self.TxtCount1.Visibility = System.Windows.Visibility.Collapsed
            self.TxtCount2.Visibility = System.Windows.Visibility.Visible

    def FilterViews1_Changed(self, sender, args):
        text = self.TxtFilterViews1.Text.lower()
        if not text:
            self.visible_views1 = list(self.all_views)
        else:
            self.visible_views1 = [v for v in self.all_views if text in v.Name.lower()]
        self.ListViews1.ItemsSource = self.visible_views1
        self.ListViews2.ItemsSource = self.visible_views1  # Same filter for both tabs
        
    def CheckAll1_Checked(self, sender, args):
        for v in self.visible_views1: v.IsChecked = True
        self.ListViews1.Items.Refresh()
    
    def CheckAll1_Unchecked(self, sender, args):
        for v in self.visible_views1: v.IsChecked = False
        self.ListViews1.Items.Refresh()

    def CheckAll2_Checked(self, sender, args):
        for v in self.visible_views1: v.IsChecked = True  # Use same list
        self.ListViews2.Items.Refresh()

    def CheckAll2_Unchecked(self, sender, args):
        for v in self.visible_views1: v.IsChecked = False  # Use same list
        self.ListViews2.Items.Refresh()

    def ApplyTemplate_Click(self, sender, args):
        tmpl = self.ComboTemplates.SelectedItem
        if not tmpl:
            forms.alert("Please select a source template.")
            return

        targets = [v for v in self.ListViews1.ItemsSource if v.IsChecked]
        if not targets:
            forms.alert("Please check at least one target view.")
            return
            
        self.OverlayProgress.Visibility = System.Windows.Visibility.Visible
        System.Windows.Forms.Application.DoEvents()
        
        count = 0
        with revit.Transaction("Apply Template"):
            for v_item in targets:
                success, err = self.logic.copy_template_to_view(tmpl, v_item.Element)
                if success: count += 1
                
        self.OverlayProgress.Visibility = System.Windows.Visibility.Collapsed
        forms.alert("Applied '{}' to {} views.".format(tmpl.Name, count))
        self.Close()

    def CopyOverrides_Click(self, sender, args):
        src = self.ComboSourceViews.SelectedItem
        if not src:
            forms.alert("Please select a source view.")
            return
            
        targets = [v for v in self.ListViews2.ItemsSource if v.IsChecked]
        if not targets:
             forms.alert("Please check at least one target view.")
             return
             
        # Filter out self
        targets = [v for v in targets if v.Element.Id != src.Id]
        
        self.OverlayProgress.Visibility = System.Windows.Visibility.Visible
        System.Windows.Forms.Application.DoEvents()
        
        count = 0 
        with revit.Transaction("Copy Overrides"):
             for v_item in targets:
                 success, res = self.logic.copy_overrides_to_view(src, v_item.Element)
                 if success: count += 1
                 
        self.OverlayProgress.Visibility = System.Windows.Visibility.Collapsed
        forms.alert("Copied overrides to {} views.".format(count))
        self.Close()


