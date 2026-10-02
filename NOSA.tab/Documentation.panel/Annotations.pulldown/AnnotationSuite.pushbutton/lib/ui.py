# -*- coding: utf-8 -*-
import os
import sys

import System.Windows
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms
from nosa_utils.telemetry import log_swallowed
_LOG = u'annotationsuite'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value, element_name

_VIS = System.Windows.Visibility.Visible
_COL = System.Windows.Visibility.Collapsed


def _load_sibling_logic(name, module_name):
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    for suffix in ('pushbutton', 'nobutton'):
        path = os.path.join(base, '{}.{}'.format(name, suffix), 'lib', 'logic.py')
        if os.path.exists(path):
            from nosa_utils.bootstrap import load_module
            return load_module(module_name, path)
    raise ImportError('Cannot find logic for: ' + name)


_anno = _load_sibling_logic('AnnotationBatch', 'suite_anno')
_gbb  = _load_sibling_logic('GridBubbleBatch', 'suite_gbb')


class ViewItem(object):
    def __init__(self, view):
        self.View      = view
        self.Name      = u'{} ({})'.format(view.Name, str(view.ViewType).split(u'.')[-1])
        self.IsChecked = False


class AnnotationSuiteWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'annotation_suite')
        self.doc = doc
        self._view_items     = ObservableCollection[ViewItem]()
        self._all_view_items = []
        self._tag_lists      = {}
        self._spot_types     = []
        self._sheet_view_ids = set()

        self.SuiteListViews.ItemsSource = self._view_items

        try:
            self._build_sheet_view_ids()
            self._load_views()
            self._load_tag_families()
            self._load_spot_types()
            cfg = self.LoadConfig()
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        except Exception as e:
            forms.alert(u'Annotation Suite init error:\n{}'.format(e), title=u'Error')

    def _build_sheet_view_ids(self):
        try:
            for s in DB.FilteredElementCollector(self.doc)\
                        .OfClass(DB.ViewSheet).ToElements():
                for vpid in s.GetAllViewports():
                    try:
                        vp = self.doc.GetElement(vpid)
                        self._sheet_view_ids.add(get_id_value(vp.ViewId))
                    except Exception:
                        log_swallowed(_LOG, u'AnnotationSuiteWindow._build_sheet_view_ids')
        except Exception:
            log_swallowed(_LOG, u'AnnotationSuiteWindow._build_sheet_view_ids')

    def _load_views(self):
        self._all_view_items = [ViewItem(v) for v in _anno.get_structural_views(self.doc)]
        self._apply_view_filter()

    def _apply_view_filter(self):
        try:
            search = (self.SuiteTxtSearch.Text or u'').lower()
        except Exception:
            search = u''
        try:
            only_sheets = self.SuiteChkOnlySheets.IsChecked == True
        except Exception:
            only_sheets = False
        self._view_items.Clear()
        for vi in self._all_view_items:
            if search and search not in vi.Name.lower():
                continue
            if only_sheets and get_id_value(vi.View.Id) not in self._sheet_view_ids:
                continue
            self._view_items.Add(vi)

    def _load_tag_families(self):
        for bic, combo_name in [
            (DB.BuiltInCategory.OST_StructuralColumns,    u'CmbTagColumns'),
            (DB.BuiltInCategory.OST_StructuralFraming,    u'CmbTagFraming'),
            (DB.BuiltInCategory.OST_StructuralFoundation, u'CmbTagFound'),
        ]:
            try:
                combo = getattr(self, combo_name)
                tags  = _anno.get_tag_families(self.doc, bic)
                combo.Items.Clear()
                combo.Items.Add(u'(first available)')
                for t in tags:
                    combo.Items.Add(t['name'])
                combo.SelectedIndex = 0
                self._tag_lists[combo_name] = tags
            except Exception:
                log_swallowed(_LOG, u'AnnotationSuiteWindow._load_tag_families')

    def _load_spot_types(self):
        try:
            self._spot_types = list(_anno.get_spot_elevation_types(self.doc))
            self.CboSpotType.Items.Clear()
            self.CboSpotType.Items.Add(u'(default style)')
            for st in self._spot_types:
                self.CboSpotType.Items.Add(element_name(st) or str(st.Id))
            self.CboSpotType.SelectedIndex = 0
        except Exception:
            self._spot_types = []

    def _get_tag_id(self, combo_name):
        try:
            combo = getattr(self, combo_name)
            idx   = combo.SelectedIndex
            tags  = self._tag_lists.get(combo_name, [])
            if tags and idx > 0 and idx <= len(tags):
                return tags[idx - 1]['id']
        except Exception:
            log_swallowed(_LOG, u'AnnotationSuiteWindow._get_tag_id')
        return DB.ElementId.InvalidElementId

    def _selected_views(self):
        return [vi.View for vi in self._view_items if vi.IsChecked]

    # ── view selection ────────────────────────────────────────────────────────

    def Suite_SearchViews_Changed(self, sender, args):
        self._apply_view_filter()

    def Suite_FilterViews_Changed(self, sender, args):
        self._apply_view_filter()

    def Suite_SelectAll_Click(self, sender, args):
        for vi in self._view_items:
            vi.IsChecked = True
        self.SuiteListViews.Items.Refresh()

    # ── tab 0: structural tags ────────────────────────────────────────────────

    def RunTags_Click(self, sender, args):
        views = self._selected_views()
        if not views:
            forms.alert(u'Select at least one view.')
            return
        use_leader = self.ChkLeader.IsChecked == True
        total = {'created': 0, 'skipped': 0, 'failed': 0}
        self.SetLoading(True, u'Applying tags...')
        try:
            for bic, chk, combo_name in [
                (DB.BuiltInCategory.OST_StructuralColumns,    self.ChkTagColumns, u'CmbTagColumns'),
                (DB.BuiltInCategory.OST_StructuralFraming,    self.ChkTagFraming, u'CmbTagFraming'),
                (DB.BuiltInCategory.OST_StructuralFoundation, self.ChkTagFound,   u'CmbTagFound'),
            ]:
                if chk.IsChecked != True:
                    continue
                tag_id = self._get_tag_id(combo_name)
                r = _anno.batch_tag_elements(self.doc, views, bic, tag_id, use_leader)
                for k in total:
                    total[k] += r[k]
        except Exception as e:
            forms.alert(u'Tag failed: {}'.format(e))
            return
        finally:
            self.SetLoading(False)
        self.SuiteTxtResult.Text = (
            u'Tags — Created: {created}  |  Skipped: {skipped}  |  Failed: {failed}'.format(**total))

    # ── tab 1: grid bubbles ───────────────────────────────────────────────────

    def RunGbb_Click(self, sender, args):
        views = self._selected_views()
        if not views:
            forms.alert(u'Select at least one view.')
            return
        if self.GbbRbShow.IsChecked:        action = u'show'
        elif self.GbbRbHide.IsChecked:      action = u'hide'
        else:                               action = u'standardise'
        both = self.GbbChkBothEnds.IsChecked == True
        self.SetLoading(True, u'Updating grid bubbles...')
        try:
            r = _gbb.apply_bubble_action(self.doc, views, action, both)
            self.GbbTxtStatus.Text = (
                u'Updated {} bubble ends across {} views ({} skipped, {} failed).'.format(
                    r['updated'], r['views'], r['skipped'], r['failed']))
        except Exception as e:
            forms.alert(u'Grid bubble error: {}'.format(e))
        finally:
            self.SetLoading(False)

    # ── tab 2: spot elevations ────────────────────────────────────────────────

    def RunSpotElevs_Click(self, sender, args):
        views = self._selected_views()
        if not views:
            forms.alert(u'Select at least one view.')
            return
        try:
            idx     = self.CboSpotType.SelectedIndex
            type_id = (self._spot_types[idx - 1].Id
                       if self._spot_types and idx > 0 else DB.ElementId.InvalidElementId)
        except Exception:
            type_id = DB.ElementId.InvalidElementId
        self.SetLoading(True, u'Placing spot elevations...')
        try:
            r = _anno.batch_spot_elevations(self.doc, views, type_id)
            self.SuiteTxtResult.Text = (
                u'Spot elevations — Created: {}  |  Failed: {}'.format(r['created'], r['failed']))
        except Exception as e:
            forms.alert(u'Spot elevation error: {}'.format(e))
        finally:
            self.SetLoading(False)
