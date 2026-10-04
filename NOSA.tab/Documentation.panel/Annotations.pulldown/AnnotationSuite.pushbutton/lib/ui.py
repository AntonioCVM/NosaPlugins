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
from nosa_utils import tag_rules, tag_engine

_VIS = System.Windows.Visibility.Visible
_COL = System.Windows.Visibility.Collapsed


from nosa_utils.bootstrap import load_module as _load_module
_anno = _load_module('suite_anno', os.path.join(os.path.dirname(__file__), 'logic_annotation_batch.py'))
_gbb  = _load_module('suite_gbb', os.path.join(os.path.dirname(__file__), 'logic_grid_bubbles.py'))


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
        """One row per Tag All category: a tick box and its tag type ('(NOSA default)' first)."""
        import System.Windows.Controls as SWC
        self._tag_rows = {}
        panel = self.PanelTagCategories
        panel.Children.Clear()
        for key, label, _bic, _geometry in tag_rules.CATEGORIES:
            row = SWC.Grid()
            row.Margin = System.Windows.Thickness(0, 3, 0, 3)
            for width in (180.0, 1.0):
                col = SWC.ColumnDefinition()
                col.Width = System.Windows.GridLength(width, System.Windows.GridUnitType.Pixel if width > 1 else
                                                      System.Windows.GridUnitType.Star)
                row.ColumnDefinitions.Add(col)
            check = SWC.CheckBox()
            check.Content = label
            check.IsChecked = True
            check.VerticalAlignment = System.Windows.VerticalAlignment.Center
            combo = SWC.ComboBox()
            combo.Height = 24
            combo.FontSize = 11
            combo.Items.Add(u'(NOSA default)')
            types = []
            try:
                types = tag_engine.tag_types(self.doc, key)
            except Exception:
                log_swallowed(_LOG, u'AnnotationSuiteWindow._load_tag_families')
            for name, _type_id in types:
                combo.Items.Add(name)
            combo.SelectedIndex = 0
            if not types:
                check.IsChecked = False
                check.IsEnabled = False
                check.ToolTip = u'No tag family of this category is loaded in the project.'
            SWC.Grid.SetColumn(combo, 1)
            row.Children.Add(check)
            row.Children.Add(combo)
            panel.Children.Add(row)
            self._tag_rows[key] = (check, combo, types)

    def _tag_choice(self):
        """({key: type id or None}, [ticked keys])."""
        type_ids, keys = {}, []
        for key, (check, combo, types) in self._tag_rows.items():
            if check.IsChecked == True:
                keys.append(key)
            idx = combo.SelectedIndex
            type_ids[key] = types[idx - 1][1] if 0 < idx <= len(types) else None
        return type_ids, keys

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
        type_ids, ticked = self._tag_choice()
        recommended = self.ChkTagRecommended.IsChecked == True
        total = {'created': 0, 'rearranged': 0, 'leaders': 0, 'failed': 0}
        lines, errors = [], []
        self.SetLoading(True, u'Tagging...')
        try:
            for view in views:
                keys = ticked
                if recommended:
                    template = self.doc.GetElement(view.ViewTemplateId)
                    wanted = tag_rules.recommend(view.ViewType, element_name(template) if template else u'',
                                                 view.Name, rebar_visible=bool(tag_engine.elements(self.doc, view, 'rebar')))
                    keys = [k for k in ticked if k in wanted]
                if not keys:
                    lines.append(u'{}: nothing to tag for this view type.'.format(view.Name))
                    continue
                r = tag_engine.tag_view(self.doc, view, keys, type_ids,
                                        rearrange=self.ChkTagRearrange.IsChecked == True)
                for k in total:
                    total[k] += r[k]
                errors.extend(r['errors'])
                lines.append(u'{}: {} new, {} moved, {} leaders'.format(
                    view.Name, r['created'], r['rearranged'], r['leaders']))
        except Exception as e:
            forms.alert(u'Tag All failed: {}'.format(e))
            return
        finally:
            self.SetLoading(False)
        text = (u'Tags — New: {created}  |  Moved: {rearranged}  |  Leaders: {leaders}  |  '
                u'Failed: {failed}'.format(**total))
        self.SuiteTxtResult.Text = text + u'\n' + u'\n'.join(lines + errors[:6])

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
