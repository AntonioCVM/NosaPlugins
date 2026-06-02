# -*- coding: utf-8 -*-
import os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.loader import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('viewfilterbatch_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_SEARCH_VIEW_PH    = "Search views..."
_SEARCH_FILTER_PH  = "Search filters..."
_ALL_TYPES_LABEL   = "All Types"


class FilterItem(object):
    def __init__(self, info):
        self.Id         = info['id']
        self.Name       = info['name']
        self.Categories = ', '.join(info['categories']) if info['categories'] else '—'
        self.IsChecked  = False


class ViewRow(object):
    def __init__(self, view, filter_ids=None):
        self.View        = view
        self.Name        = view.Name
        self.ViewType    = str(view.ViewType)
        self.IsChecked   = False
        applied = filter_ids or []
        self.FilterCount = len(applied)


class ViewFilterBatchWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'viewfilter_batch')
        self.doc = doc

        self._all_filter_items  = []
        self._vis_filter_items  = ObservableCollection[FilterItem]()
        self._filter_search_on  = False

        self._all_view_rows     = []
        self._vis_view_rows     = ObservableCollection[ViewRow]()
        self._view_search_on    = False

        self._mode = 'copy'   # copy | apply | toggle | remove

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self._load_data()
        self._update_mode_panels()

    # ── data loading ────────────────────────────────────────────────────────

    def _load_data(self):
        # Filters
        filters = _logic.get_all_project_filters(self.doc)
        self._all_filter_items = [FilterItem(f) for f in filters]
        self._refresh_filter_list()

        # Views
        views = _logic.get_applicable_views(self.doc)
        self._all_view_rows = []
        for v in views:
            try:
                fids = list(v.GetFilters())
            except Exception:
                fids = []
            self._all_view_rows.append(ViewRow(v, fids))

        self.GridViews.ItemsSource = self._vis_view_rows
        self.LstFilters.ItemsSource = self._vis_filter_items

        # Populate source view combos
        self.CboSourceView.ItemsSource      = views
        self.CboApplySourceView.ItemsSource = views
        if views:
            self.CboSourceView.SelectedIndex      = 0
            self.CboApplySourceView.SelectedIndex = 0

        # Populate view-type combo
        types = sorted(set(r.ViewType for r in self._all_view_rows))
        type_list = [_ALL_TYPES_LABEL] + types
        self.CboViewType.ItemsSource  = type_list
        self.CboViewType.SelectedIndex = 0

        self._refresh_view_list()
        self._update_pills()

    # ── mode switching ───────────────────────────────────────────────────────

    def Mode_Changed(self, sender, args):
        if self.RbCopy.IsChecked:
            self._mode = 'copy'
        elif self.RbApply.IsChecked:
            self._mode = 'apply'
        elif self.RbToggle.IsChecked:
            self._mode = 'toggle'
        else:
            self._mode = 'remove'
        self._update_mode_panels()

    def _update_mode_panels(self):
        is_copy = self._mode == 'copy'
        vis_copy   = System.Windows.Visibility.Visible
        vis_hidden = System.Windows.Visibility.Collapsed

        self.PanelCopyOptions.Visibility   = vis_copy   if is_copy else vis_hidden
        self.PanelFilterOptions.Visibility = vis_hidden if is_copy else vis_copy
        self.PanelToggleOpts.Visibility    = vis_copy   if self._mode == 'toggle' else vis_hidden
        self.PanelApplyOpts.Visibility     = vis_copy   if self._mode == 'apply'  else vis_hidden

        labels = {
            'copy':   'COPY FILTERS',
            'apply':  'APPLY FILTERS',
            'toggle': 'TOGGLE FILTERS',
            'remove': 'REMOVE FILTERS',
        }
        self.BtnExecute.Content = labels.get(self._mode, 'EXECUTE')

    # ── source view change ───────────────────────────────────────────────────

    def SourceView_Changed(self, sender, args):
        pass   # nothing extra needed; view is read at Execute time

    def ApplyFromView_Changed(self, sender, args):
        self.CboApplySourceView.IsEnabled = self.ChkApplyFromView.IsChecked == True

    # ── filter list ─────────────────────────────────────────────────────────

    def FilterSearch_GotFocus(self, sender, args):
        if self.TxtFilterSearch.Text == _SEARCH_FILTER_PH:
            self.TxtFilterSearch.Text = ''
            self.TxtFilterSearch.Foreground = System.Windows.Media.Brushes.Black
            self._filter_search_on = True

    def FilterSearch_LostFocus(self, sender, args):
        if not self.TxtFilterSearch.Text.strip():
            self.TxtFilterSearch.Text = _SEARCH_FILTER_PH
            self.TxtFilterSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._filter_search_on = False

    def FilterSearch_Changed(self, sender, args):
        if self._filter_search_on or self.TxtFilterSearch.Text != _SEARCH_FILTER_PH:
            self._refresh_filter_list()

    def _refresh_filter_list(self):
        txt = (self.TxtFilterSearch.Text or '').strip().lower()
        if txt == _SEARCH_FILTER_PH.lower():
            txt = ''
        self._vis_filter_items.Clear()
        for fi in self._all_filter_items:
            if txt and txt not in fi.Name.lower():
                continue
            self._vis_filter_items.Add(fi)

    def FilterList_SelectionChanged(self, sender, args):
        self._update_pills()

    def FilterCheck_Click(self, sender, args):
        self._update_pills()

    def FilterSelectAll_Click(self, sender, args):
        for fi in self._vis_filter_items:
            fi.IsChecked = True
        self.LstFilters.Items.Refresh()
        self._update_pills()

    def FilterSelectNone_Click(self, sender, args):
        for fi in self._vis_filter_items:
            fi.IsChecked = False
        self.LstFilters.Items.Refresh()
        self._update_pills()

    # ── view list ────────────────────────────────────────────────────────────

    def ViewSearch_GotFocus(self, sender, args):
        if self.TxtViewSearch.Text == _SEARCH_VIEW_PH:
            self.TxtViewSearch.Text = ''
            self.TxtViewSearch.Foreground = System.Windows.Media.Brushes.Black
            self._view_search_on = True

    def ViewSearch_LostFocus(self, sender, args):
        if not self.TxtViewSearch.Text.strip():
            self.TxtViewSearch.Text = _SEARCH_VIEW_PH
            self.TxtViewSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._view_search_on = False

    def ViewSearch_Changed(self, sender, args):
        if self._view_search_on or self.TxtViewSearch.Text != _SEARCH_VIEW_PH:
            self._refresh_view_list()

    def ViewType_Changed(self, sender, args):
        self._refresh_view_list()

    def _refresh_view_list(self):
        txt = (self.TxtViewSearch.Text or '').strip().lower()
        if txt == _SEARCH_VIEW_PH.lower():
            txt = ''
        vtype = self.CboViewType.SelectedItem
        if vtype == _ALL_TYPES_LABEL or vtype is None:
            vtype = None

        self._vis_view_rows.Clear()
        for vr in self._all_view_rows:
            if txt and txt not in vr.Name.lower():
                continue
            if vtype and vr.ViewType != vtype:
                continue
            self._vis_view_rows.Add(vr)

        self._update_pills()

    def ViewGrid_SelectionChanged(self, sender, args):
        self._update_pills()

    def ViewCheck_Click(self, sender, args):
        self._update_pills()

    def SelectAllViews_Click(self, sender, args):
        for vr in self._vis_view_rows:
            vr.IsChecked = True
        self.GridViews.Items.Refresh()
        self._update_pills()

    def SelectNoneViews_Click(self, sender, args):
        for vr in self._vis_view_rows:
            vr.IsChecked = False
        self.GridViews.Items.Refresh()
        self._update_pills()

    def InvertViews_Click(self, sender, args):
        for vr in self._vis_view_rows:
            vr.IsChecked = not vr.IsChecked
        self.GridViews.Items.Refresh()
        self._update_pills()

    # ── pills ────────────────────────────────────────────────────────────────

    def _update_pills(self):
        total_views    = len(self._vis_view_rows)
        selected_views = sum(1 for vr in self._vis_view_rows if vr.IsChecked)
        total_filters  = len(self._vis_filter_items)
        checked_filters = sum(1 for fi in self._vis_filter_items if fi.IsChecked)

        self.TxtPillViews.Text    = "{} views".format(total_views)
        self.TxtPillFilters.Text  = "{} filters".format(total_filters)
        self.TxtPillSelected.Text = "{} selected".format(selected_views)

    # ── execute ──────────────────────────────────────────────────────────────

    def Execute_Click(self, sender, args):
        target_views = [vr.View for vr in self._vis_view_rows if vr.IsChecked]
        if not target_views:
            forms.alert("No views selected. Check at least one view in the list.")
            return

        self.SetLoading(True, "Applying changes...")

        try:
            if self._mode == 'copy':
                self._exec_copy(target_views)
            elif self._mode == 'apply':
                self._exec_apply(target_views)
            elif self._mode == 'toggle':
                self._exec_toggle(target_views)
            elif self._mode == 'remove':
                self._exec_remove(target_views)
        except Exception as e:
            forms.alert("Error: {}".format(e))
        finally:
            self.SetLoading(False)
            # Refresh filter counts
            self._reload_view_filter_counts()

    def _exec_copy(self, target_views):
        src = self.CboSourceView.SelectedItem
        if src is None:
            forms.alert("Select a source view.")
            return
        inc_ov = self.ChkIncludeOverrides.IsChecked == True
        copied, skipped, results = _logic.copy_filters_from_view(
            self.doc, src, target_views, include_overrides=inc_ov
        )
        msg = "Copied: {}  |  Skipped: {}  |  Views: {}".format(
            copied, skipped, len(results))
        self.TxtLastResult.Text = msg
        forms.alert(msg, title="Copy Filters")

    def _exec_apply(self, target_views):
        checked = [fi for fi in self._vis_filter_items if fi.IsChecked]
        if not checked:
            forms.alert("No filters selected. Check at least one filter.")
            return
        src_view = None
        if self.ChkApplyFromView.IsChecked == True:
            src_view = self.CboApplySourceView.SelectedItem
        filter_infos = [{'id': fi.Id, 'name': fi.Name, 'categories': []} for fi in checked]
        applied, skipped, results = _logic.apply_filters_to_views(
            self.doc, filter_infos, target_views, source_view=src_view
        )
        msg = "Applied: {}  |  Skipped: {}  |  Views: {}".format(
            applied, skipped, len(results))
        self.TxtLastResult.Text = msg
        forms.alert(msg, title="Apply Filters")

    def _exec_toggle(self, target_views):
        checked = [fi for fi in self._vis_filter_items if fi.IsChecked]
        if not checked:
            forms.alert("No filters selected.")
            return
        enable = self.RbEnable.IsChecked == True
        filter_infos = [{'id': fi.Id, 'name': fi.Name, 'categories': []} for fi in checked]
        toggled, skipped = _logic.toggle_filters_in_views(
            self.doc, filter_infos, target_views, enable
        )
        action = "Enabled" if enable else "Disabled"
        msg = "{}: {}  |  Skipped: {}".format(action, toggled, skipped)
        self.TxtLastResult.Text = msg
        forms.alert(msg, title="Toggle Filters")

    def _exec_remove(self, target_views):
        checked = [fi for fi in self._vis_filter_items if fi.IsChecked]
        if not checked:
            forms.alert("No filters selected.")
            return
        names = ', '.join(fi.Name for fi in checked[:5])
        if len(checked) > 5:
            names += ' ...'
        if not forms.alert(
            "Remove {} filter(s) from {} view(s)?\n\nFilters: {}".format(
                len(checked), len(target_views), names),
            yes=True, no=True
        ):
            return
        filter_infos = [{'id': fi.Id, 'name': fi.Name, 'categories': []} for fi in checked]
        removed, skipped = _logic.remove_filters_from_views(
            self.doc, filter_infos, target_views
        )
        msg = "Removed: {}  |  Skipped: {}".format(removed, skipped)
        self.TxtLastResult.Text = msg
        forms.alert(msg, title="Remove Filters")

    def _reload_view_filter_counts(self):
        for vr in self._all_view_rows:
            try:
                vr.FilterCount = len(list(vr.View.GetFilters()))
            except Exception:
                pass
        self.GridViews.Items.Refresh()
