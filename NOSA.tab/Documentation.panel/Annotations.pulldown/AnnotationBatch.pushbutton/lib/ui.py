# -*- coding: utf-8 -*-
import os, sys, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)

_logic = imp.load_source('annobatch_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
get_structural_views = _logic.get_structural_views
batch_tag_elements   = _logic.batch_tag_elements
batch_grid_bubbles   = _logic.batch_grid_bubbles
get_tag_families     = _logic.get_tag_families

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger
from pyrevit import DB
logger = Logger()


class ViewItem(object):
    def __init__(self, view):
        self.View      = view
        self.Name      = "{} ({})".format(view.Name, str(view.ViewType).split('.')[-1])
        self.IsChecked = False


class AnnotationBatchWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'annotation_batch')
        self.doc   = doc
        self._tabs = {'BtnTabTags': self.TabTags, 'BtnTabGrids': self.TabGrids}
        self._view_items = ObservableCollection[ViewItem]()
        self.ListViews.ItemsSource = self._view_items
        self._tag_lists = {}   # combo_name -> list of tag dicts (replaces combo.Tag)
        self._load_views()
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def _load_views(self):
        self._all_view_items = [ViewItem(v) for v in get_structural_views(self.doc)]
        # Build set of view IDs placed on sheets
        self._sheet_view_ids = set()
        try:
            for s in __import__('pyrevit').DB.FilteredElementCollector(self.doc)\
                        .OfClass(__import__('pyrevit').DB.ViewSheet).ToElements():
                for vpid in s.GetAllViewports():
                    try:
                        vp = self.doc.GetElement(vpid)
                        sid = vp.ViewId.IntegerValue if hasattr(vp.ViewId,'IntegerValue') else int(str(vp.ViewId))
                        self._sheet_view_ids.add(sid)
                    except Exception:
                        pass
        except Exception:
            pass
        self._apply_view_filter()
        self._load_tag_families()

    def _load_tag_families(self):
        """Populate tag ComboBoxes with available tag families."""
        try:
            for bic, combo_name in [
                (DB.BuiltInCategory.OST_StructuralColumns,    'CmbTagColumns'),
                (DB.BuiltInCategory.OST_StructuralFraming,    'CmbTagFraming'),
                (DB.BuiltInCategory.OST_StructuralFoundation, 'CmbTagFound'),
            ]:
                if not hasattr(self, combo_name): continue
                combo = getattr(self, combo_name)
                tags = get_tag_families(self.doc, bic)
                combo.Items.Clear()
                combo.Items.Add('(first available)')
                for t in tags:
                    combo.Items.Add(t['name'])
                combo.SelectedIndex = 0
                self._tag_lists[combo_name] = tags
        except Exception:
            pass

    def _get_tag_id(self, combo_name):
        """Return ElementId of selected tag, or InvalidElementId."""
        try:
            combo = getattr(self, combo_name)
            idx   = combo.SelectedIndex
            tags  = self._tag_lists.get(combo_name, [])
            if tags and idx > 0 and idx <= len(tags):
                return tags[idx - 1]['id']
        except Exception:
            pass
        return DB.ElementId.InvalidElementId

    def _apply_view_filter(self):
        search = ''
        only_sheets = False
        try:
            search = self.TxtSearchViews.Text.lower()
        except Exception:
            pass
        try:
            only_sheets = self.ChkOnlyOnSheetsAnno.IsChecked == True
        except Exception:
            pass
        self._view_items.Clear()
        for vi in self._all_view_items:
            if search and search not in vi.Name.lower():
                continue
            if only_sheets:
                vid = vi.View.Id.IntegerValue if hasattr(vi.View.Id,'IntegerValue') else int(str(vi.View.Id))
                if vid not in self._sheet_view_ids:
                    continue
            self._view_items.Add(vi)

    def SearchViews_Changed(self, sender, args):
        self._apply_view_filter()

    def FilterViews_Changed(self, sender, args):
        self._apply_view_filter()

    def NavButton_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)

    def SelectAllViews_Click(self, sender, args):
        for vi in self._view_items: vi.IsChecked = True
        self.ListViews.Items.Refresh()

    def _selected_views(self):
        return [vi.View for vi in self._view_items if vi.IsChecked]

    def Run_Click(self, sender, args):
        views = self._selected_views()
        if not views:
            forms.alert("Select at least one view.")
            return

        active_tab = next((k for k, g in self._tabs.items()
                           if g.Visibility == System.Windows.Visibility.Visible), 'BtnTabTags')

        result_text = ""
        try:
            with revit.Transaction("NOSA — Annotation Batch"):
                if active_tab == 'BtnTabTags':
                    total = {'created': 0, 'skipped': 0, 'failed': 0}
                    use_leader = self.ChkLeader.IsChecked == True
                    for bic, chk, combo_name in [
                        (DB.BuiltInCategory.OST_StructuralColumns,    self.ChkTagColumns, 'CmbTagColumns'),
                        (DB.BuiltInCategory.OST_StructuralFraming,     self.ChkTagFraming, 'CmbTagFraming'),
                        (DB.BuiltInCategory.OST_StructuralFoundation,  self.ChkTagFound,   'CmbTagFound'),
                    ]:
                        if chk.IsChecked != True: continue
                        tag_id = self._get_tag_id(combo_name)
                        r = batch_tag_elements(self.doc, views, bic, tag_id, use_leader)
                        for k in total: total[k] += r[k]
                    result_text = "Tags — Created: {created} | Skipped: {skipped} | Failed: {failed}".format(**total)

                elif active_tab == 'BtnTabGrids':
                    show = self.RbShowBubbles.IsChecked == True
                    r = batch_grid_bubbles(self.doc, views, show)
                    result_text = "Grid bubbles {} — Updated: {} | Failed: {}".format(
                        "shown" if show else "hidden", r['updated'], r['failed'])

        except Exception as e:
            result_text = "Error: {}".format(e)

        self.TxtResult.Text = result_text
        self.PanelResult.Visibility = System.Windows.Visibility.Visible
        cfg = self.LoadConfig(); cfg['dark_mode'] = self.dark_mode; self.SaveConfig(cfg)
