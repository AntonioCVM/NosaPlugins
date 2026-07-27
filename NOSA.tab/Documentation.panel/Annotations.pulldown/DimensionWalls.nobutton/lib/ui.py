# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import forms, revit
import os
import sys
import System.Windows
import imp
_here = os.path.dirname(os.path.abspath(__file__))
_logic_mod = imp.load_source('dimensionwalls_logic', os.path.join(_here, 'logic.py'))
DimensionLogic = _logic_mod.DimensionLogic

def _ensure_extension_lib():
    extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    lib_path = os.path.join(extension_root, "lib")
    if lib_path not in sys.path:
        sys.path.append(lib_path)

_ensure_extension_lib()
from nosa_utils.base_window import NOSAWindow

class ViewItem(object):
    def __init__(self, element):
        self.Element = element
        self.Name = element.Name
        self.IsChecked = False
        
    def __repr__(self):
        return self.Name

class DimensionWallsWindow(NOSAWindow):
    def __init__(self, doc):
        self.doc = doc
        self.logic = DimensionLogic(doc)

        self.all_views = []
        self.visible_views = []

        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml_file, 'dimension_walls')
        self.ChkDarkMode.IsChecked = self.dark_mode

        # Load Data
        self.LoadDimensionTypes()
        self.LoadViews()

        # Events
        self.TxtFilterViews.TextChanged += self.FilterViews_Changed

    def LoadDimensionTypes(self):
        types = self.logic.get_dimension_types()
        self.ComboDimTypes.ItemsSource = types
        if types:
            self.ComboDimTypes.SelectedIndex = 0

    def LoadViews(self):
        # Only floor/structural plans
        collector = DB.FilteredElementCollector(self.doc)\
            .OfClass(DB.View)\
            .WhereElementIsNotElementType()
            
        views = []
        for v in collector:
            if v.IsTemplate: continue
            if v.ViewType in [DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan]:
                views.append(v)
                
        sorted_views = sorted(views, key=lambda x: x.Name)
        
        self.all_views = [ViewItem(v) for v in sorted_views]
        self.visible_views = list(self.all_views)
        self.ListViews.ItemsSource = self.visible_views
        
        # Pre-select active view if finding it
        active_id = self.doc.ActiveView.Id
        for v in self.all_views:
            if v.Element.Id == active_id:
                v.IsChecked = True

    def FilterViews_Changed(self, sender, args):
        text = self.TxtFilterViews.Text.lower()
        if not text:
            self.visible_views = list(self.all_views)
        else:
            self.visible_views = [v for v in self.all_views if text in v.Name.lower()]
        self.ListViews.ItemsSource = self.visible_views
        self.TxtCount.Text = "{} items".format(len(self.visible_views))

    def CheckAll_Checked(self, sender, args):
        for v in self.visible_views: v.IsChecked = True
        self.ListViews.Items.Refresh()

    def CheckAll_Unchecked(self, sender, args):
        for v in self.visible_views: v.IsChecked = False
        self.ListViews.Items.Refresh()

    def Run_Click(self, sender, args):
        dim_type = self.ComboDimTypes.SelectedItem
        if not dim_type:
            forms.alert("Please select a Dimension Type.")
            return

        offset_str = self.TxtOffset.Text
        try:
            offset_mm = float(offset_str)
        except ValueError:
             forms.alert("Invalid offset value.")
             return

        selected_views = [v.Element for v in self.all_views if v.IsChecked]
        if not selected_views:
             forms.alert("Please select at least one View.")
             return
             
        do_straight = self.ChkStraight.IsChecked
        do_curved = self.ChkCurved.IsChecked
        
        if not do_straight and not do_curved:
             forms.alert("Please select at least one Wall Type (Straight or Curved).")
             return

        self.OverlayProgress.Visibility = System.Windows.Visibility.Visible
        try:
            import clr
            clr.AddReference('System.Windows.Forms')
            import System.Windows.Forms as _WinForms
            _WinForms.Application.DoEvents()
        except Exception:
            pass
        
        total_created = 0
        total_failed = 0
        
        with revit.Transaction("Dimension Walls"):
            for view in selected_views:
                walls = self.logic.get_valid_walls_in_view(view)
                
                for wall in walls:
                    geo = self.logic.get_wall_curve_data(wall)
                    is_arc = geo['is_arc']
                    
                    if is_arc and do_curved:
                        results = self.logic.create_arc_dimensions(wall, view, dim_type, offset_mm)
                        if results:
                            total_created += len(results)
                        else:
                            # Not strictly failed, maybe geometry issue
                            pass
                            
                    elif not is_arc and do_straight:
                        dim = self.logic.create_linear_dimension(wall, view, dim_type, offset_mm)
                        if dim:
                            total_created += 1
                        else:
                            total_failed += 1
                            
        self.OverlayProgress.Visibility = System.Windows.Visibility.Collapsed
        forms.alert("Created {} dimensions.\n(Failed/Skipped: {})".format(total_created, total_failed))
        self.Close()


