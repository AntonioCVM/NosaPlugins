# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import forms, revit
import os
import sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

import imp
_here = os.path.dirname(os.path.abspath(__file__))
_logic_mod = imp.load_source('alignviewtitles_logic', os.path.join(_here, 'logic.py'))
AlignLogic = _logic_mod.AlignLogic

def _ensure_extension_lib():
    extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    lib_path = os.path.join(extension_root, "lib")
    if lib_path not in sys.path:
        sys.path.append(lib_path)

_ensure_extension_lib()
from nosa_utils.base_window import NOSAWindow

class ViewportItem(object):
    def __init__(self, data):
        self.SheetNumber = data['sheet_num']
        self.ViewName = data['view_name']
        self.Viewport = data['viewport']
        self.View = data['view']
        self.Data = data

class SheetSetItem(object):
    def __init__(self, name):
        self.Name = name
        self.IsChecked = False
    
    def __repr__(self):
        return self.Name

class AlignTitlesWindow(NOSAWindow):
    def __init__(self, doc):
        self.doc = doc
        self.uidoc = revit.uidoc
        self.logic = AlignLogic(doc)

        xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml_file, 'align_view_titles')
        self.ChkDarkMode.IsChecked = self.dark_mode

        # State
        self.ref_vp = None
        self.ref_view = None
        self.ref_offset = None
        self.matching_items = []

        # UI Collections
        self.preview_items = ObservableCollection[ViewportItem]()
        self.GridPreview.ItemsSource = self.preview_items

        self.sheet_sets = ObservableCollection[SheetSetItem]()
        self.ListSheetSets.ItemsSource = self.sheet_sets

        # Load Sets
        self.LoadSheetSets()

    def LoadSheetSets(self):
        sets = self.logic.get_sheet_sets()
        for s in sets:
            self.sheet_sets.Add(SheetSetItem(s))

    def Filter_Toggled(self, sender, args):
        vis = System.Windows.Visibility.Visible if self.ChkFilterSheets.IsChecked else System.Windows.Visibility.Collapsed
        self.ListSheetSets.Visibility = vis

    def PickRef_Click(self, sender, args):
        self.Hide()
        try:
            ref_pick = self.uidoc.Selection.PickObject(ObjectType.Element, "Select reference viewport")
            elem = self.doc.GetElement(ref_pick.ElementId)
            
            if isinstance(elem, DB.Viewport):
                self.ref_vp = elem
                self.ref_view = self.doc.GetElement(elem.ViewId)
                try:
                    self.ref_offset = self.ref_vp.LabelOffset
                except Exception as ex:
                    forms.alert(
                        u"Cannot read LabelOffset from this viewport.\n"
                        u"The viewport type may have 'Show Title' disabled.\n\n"
                        u"Detail: {}".format(ex))
                    self.ref_vp = None
                    self.ref_view = None
                    return

                ox = round(self.ref_offset.X * 304.8, 1)
                oy = round(self.ref_offset.Y * 304.8, 1)
                offset_note = u"  Offset: ({} mm, {} mm)".format(ox, oy)
                if ox == 0.0 and oy == 0.0:
                    offset_note += u"  ⚠ default — drag the title first!"

                self.TxtRefView.Text = self.ref_view.Name
                self.TxtRefScale.Text = u"Scale 1:{}{}".format(
                    self.ref_view.Scale, offset_note)
                self.PanelRefInfo.Visibility = System.Windows.Visibility.Visible
            else:
                forms.alert("Not a viewport.")
        except OperationCanceledException:
            pass
        except Exception as e:
            forms.alert("Could not pick reference viewport: {}".format(str(e)))
        finally:
            self.Show()

    def Preview_Click(self, sender, args):
        if not self.ref_vp:
            forms.alert("Please pick a reference viewport first.")
            return
            
        # Get filter
        filter_sets = None
        if self.ChkFilterSheets.IsChecked:
            selected = [item.Name for item in self.ListSheetSets.SelectedItems]
            if selected:
                filter_sets = selected
        
        # Search
        self.matching_items, debug_report = self.logic.get_matching_viewports(
            self.ref_view,
            filter_sets
        )
        
        self.preview_items.Clear()
        for m in self.matching_items:
            self.preview_items.Add(ViewportItem(m))
            
        self.TxtCount.Text = "{} found".format(len(self.matching_items))
        
        if not self.matching_items:
            forms.alert(
                "No matching viewports found.\n(Matches must have SAME Scale and Compatible View Type)\n\n" + debug_report,
                title="Search Diagnosis",
                warn_icon=True
            )

    def Apply_Click(self, sender, args):
        if not self.matching_items:
            forms.alert("Run preview first.")
            return

        mode = self.ComboMode.Text
        vertical = bool(self.ChkVertical.IsChecked)

        count = 0
        errors = []
        with revit.Transaction("Align Titles"):
            for item in self.matching_items:
                try:
                    target_vp = item['viewport']
                    new_offset = self.logic.calculate_aligned_offset(
                        self.ref_offset,
                        self.ref_vp,
                        target_vp,
                        mode,
                        vertical
                    )
                    target_vp.LabelOffset = new_offset
                    count += 1
                except Exception as ex:
                    err_msg = u'{}: {}'.format(item.get('view_name', '?'), ex)
                    errors.append(err_msg)

        msg = u'Aligned: {}'.format(count)
        if errors:
            msg += u'\nFailed: {}\n\nFirst error:\n{}'.format(
                len(errors), errors[0])
        forms.alert(msg)
        if count > 0:
            self.Close()


