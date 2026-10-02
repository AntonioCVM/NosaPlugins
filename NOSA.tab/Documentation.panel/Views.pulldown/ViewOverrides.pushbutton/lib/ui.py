# -*- coding: utf-8 -*-
import os, sys
import System.Windows
import System.Windows.Media
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_here      = os.path.dirname(os.path.abspath(__file__))
from nosa_utils.bootstrap import load_module
_vf_logic  = load_module('vo_vf_logic', os.path.join(_here, 'logic_view_filter_batch.py'))
_cbp_logic = load_module('vo_cbp_logic', os.path.join(_here, 'logic_colour_by_param.py'))

_ALL_TYPES  = u'All Types'
_SEARCH_VP  = u'Search views...'
_SEARCH_FP  = u'Search filters...'


class _FilterItem(object):
    def __init__(self, info):
        self.Id         = info['id']
        self.Name       = info['name']
        self.Categories = u', '.join(info['categories']) if info['categories'] else u'—'
        self.IsChecked  = False


class _ViewRow(object):
    def __init__(self, view, filter_ids=None):
        self.View        = view
        self.Name        = view.Name
        self.ViewType    = str(view.ViewType)
        self.IsChecked   = False
        self.FilterCount = len(filter_ids or [])


class _ColorRow(object):
    def __init__(self, value, count, rgb):
        self.Value     = value
        self.Count     = str(count)
        r, g, b        = rgb
        self.SwatchHex = u'#{:02X}{:02X}{:02X}'.format(r, g, b)
        self.HexStr    = self.SwatchHex
        self._rgb      = rgb


class ViewOverridesWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_overrides')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.VF_CboSourceView.SelectionChanged += self.VF_SourceView_Changed
        self.VF_LstFilters.SelectionChanged += self.VF_FilterList_SelectionChanged
        self.VF_CboViewType.SelectionChanged += self.VF_ViewType_Changed
        self.VF_GridViews.SelectionChanged += self.VF_ViewGrid_SelectionChanged
        self.CP_CmbCategory.SelectionChanged += self.CP_Category_Changed
        self.CP_CmbParam.SelectionChanged += self.CP_Param_Changed
        self.doc   = doc
        self.uidoc = revit.uidoc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._vf_init()
        self._cp_init(cfg)

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: VIEW FILTER BATCH
    # ══════════════════════════════════════════════════════════════════

    def _vf_init(self):
        self._vf_all_filter_items = []
        self._vf_vis_filter_items = ObservableCollection[_FilterItem]()
        self._vf_filter_search_on = False
        self._vf_all_view_rows    = []
        self._vf_vis_view_rows    = ObservableCollection[_ViewRow]()
        self._vf_view_search_on   = False
        self._vf_mode             = 'copy'

        filters = _vf_logic.get_all_project_filters(self.doc)
        self._vf_all_filter_items = [_FilterItem(f) for f in filters]
        self._vf_refresh_filter_list()

        views = _vf_logic.get_applicable_views(self.doc)
        for v in views:
            try:
                fids = list(v.GetFilters())
            except Exception:
                fids = []
            self._vf_all_view_rows.append(_ViewRow(v, fids))

        self.VF_GridViews.ItemsSource   = self._vf_vis_view_rows
        self.VF_LstFilters.ItemsSource  = self._vf_vis_filter_items
        self.VF_CboSourceView.ItemsSource      = views
        self.VF_CboApplySourceView.ItemsSource = views
        if views:
            self.VF_CboSourceView.SelectedIndex      = 0
            self.VF_CboApplySourceView.SelectedIndex = 0

        types = sorted(set(r.ViewType for r in self._vf_all_view_rows))
        self.VF_CboViewType.ItemsSource   = [_ALL_TYPES] + types
        self.VF_CboViewType.SelectedIndex = 0

        self._vf_refresh_view_list()
        self._vf_update_pills()
        self._vf_update_mode_panels()

    def _vf_update_mode_panels(self):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        m = self._vf_mode
        self.VF_PanelCopyOptions.Visibility   = V if m == 'copy'   else C
        self.VF_PanelFilterOptions.Visibility = C if m == 'copy'   else V
        self.VF_PanelToggleOpts.Visibility    = V if m == 'toggle' else C
        self.VF_PanelApplyOpts.Visibility     = V if m == 'apply'  else C
        labels = {'copy': u'COPY FILTERS', 'apply': u'APPLY FILTERS',
                  'toggle': u'TOGGLE FILTERS', 'remove': u'REMOVE FILTERS'}
        self.VF_BtnExecute.Content = labels.get(m, u'EXECUTE')

    def VF_Mode_Changed(self, sender, args):
        if self.VF_RbCopy.IsChecked:    self._vf_mode = 'copy'
        elif self.VF_RbApply.IsChecked: self._vf_mode = 'apply'
        elif self.VF_RbToggle.IsChecked:self._vf_mode = 'toggle'
        else:                            self._vf_mode = 'remove'
        self._vf_update_mode_panels()

    def VF_SourceView_Changed(self, sender, args):
        pass

    def VF_ApplyFromView_Changed(self, sender, args):
        self.VF_CboApplySourceView.IsEnabled = self.VF_ChkApplyFromView.IsChecked == True

    def VF_FilterSearch_GotFocus(self, sender, args):
        if self.VF_TxtFilterSearch.Text == _SEARCH_FP:
            self.VF_TxtFilterSearch.Text       = u''
            self.VF_TxtFilterSearch.Foreground = System.Windows.Media.Brushes.Black
            self._vf_filter_search_on          = True

    def VF_FilterSearch_LostFocus(self, sender, args):
        if not self.VF_TxtFilterSearch.Text.strip():
            self.VF_TxtFilterSearch.Text       = _SEARCH_FP
            self.VF_TxtFilterSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._vf_filter_search_on          = False

    def VF_FilterSearch_Changed(self, sender, args):
        if self._vf_filter_search_on or self.VF_TxtFilterSearch.Text != _SEARCH_FP:
            self._vf_refresh_filter_list()

    def _vf_refresh_filter_list(self):
        txt = (self.VF_TxtFilterSearch.Text or u'').strip().lower()
        if txt == _SEARCH_FP.lower():
            txt = u''
        self._vf_vis_filter_items.Clear()
        for fi in self._vf_all_filter_items:
            if txt and txt not in fi.Name.lower():
                continue
            self._vf_vis_filter_items.Add(fi)

    def VF_FilterList_SelectionChanged(self, sender, args):
        self._vf_update_pills()

    def VF_FilterCheck_Click(self, sender, args):
        self._vf_update_pills()

    def VF_FilterSelectAll_Click(self, sender, args):
        for fi in self._vf_vis_filter_items:
            fi.IsChecked = True
        self.VF_LstFilters.Items.Refresh()
        self._vf_update_pills()

    def VF_FilterSelectNone_Click(self, sender, args):
        for fi in self._vf_vis_filter_items:
            fi.IsChecked = False
        self.VF_LstFilters.Items.Refresh()
        self._vf_update_pills()

    def VF_ViewSearch_GotFocus(self, sender, args):
        if self.VF_TxtViewSearch.Text == _SEARCH_VP:
            self.VF_TxtViewSearch.Text       = u''
            self.VF_TxtViewSearch.Foreground = System.Windows.Media.Brushes.Black
            self._vf_view_search_on          = True

    def VF_ViewSearch_LostFocus(self, sender, args):
        if not self.VF_TxtViewSearch.Text.strip():
            self.VF_TxtViewSearch.Text       = _SEARCH_VP
            self.VF_TxtViewSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._vf_view_search_on          = False

    def VF_ViewSearch_Changed(self, sender, args):
        if self._vf_view_search_on or self.VF_TxtViewSearch.Text != _SEARCH_VP:
            self._vf_refresh_view_list()

    def VF_ViewType_Changed(self, sender, args):
        self._vf_refresh_view_list()

    def _vf_refresh_view_list(self):
        txt   = (self.VF_TxtViewSearch.Text or u'').strip().lower()
        if txt == _SEARCH_VP.lower():
            txt = u''
        vtype = self.VF_CboViewType.SelectedItem
        if vtype == _ALL_TYPES or vtype is None:
            vtype = None
        self._vf_vis_view_rows.Clear()
        for vr in self._vf_all_view_rows:
            if txt and txt not in vr.Name.lower():
                continue
            if vtype and vr.ViewType != vtype:
                continue
            self._vf_vis_view_rows.Add(vr)
        self._vf_update_pills()

    def VF_ViewGrid_SelectionChanged(self, sender, args):
        self._vf_update_pills()

    def VF_ViewCheck_Click(self, sender, args):
        self._vf_update_pills()

    def VF_SelectAllViews_Click(self, sender, args):
        for vr in self._vf_vis_view_rows:
            vr.IsChecked = True
        self.VF_GridViews.Items.Refresh()
        self._vf_update_pills()

    def VF_SelectNoneViews_Click(self, sender, args):
        for vr in self._vf_vis_view_rows:
            vr.IsChecked = False
        self.VF_GridViews.Items.Refresh()
        self._vf_update_pills()

    def VF_InvertViews_Click(self, sender, args):
        for vr in self._vf_vis_view_rows:
            vr.IsChecked = not vr.IsChecked
        self.VF_GridViews.Items.Refresh()
        self._vf_update_pills()

    def _vf_update_pills(self):
        self.VF_TxtPillViews.Text    = u'{} views'.format(len(self._vf_vis_view_rows))
        self.VF_TxtPillFilters.Text  = u'{} filters'.format(len(self._vf_vis_filter_items))
        self.VF_TxtPillSelected.Text = u'{} selected'.format(
            sum(1 for vr in self._vf_vis_view_rows if vr.IsChecked))

    def VF_Execute_Click(self, sender, args):
        target_views = [vr.View for vr in self._vf_vis_view_rows if vr.IsChecked]
        if not target_views:
            forms.alert(u'No views selected.')
            return
        self.SetLoading(True, u'Applying changes...')
        try:
            if self._vf_mode == 'copy':
                self._vf_exec_copy(target_views)
            elif self._vf_mode == 'apply':
                self._vf_exec_apply(target_views)
            elif self._vf_mode == 'toggle':
                self._vf_exec_toggle(target_views)
            elif self._vf_mode == 'remove':
                self._vf_exec_remove(target_views)
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))
        finally:
            self.SetLoading(False)
            self._vf_reload_counts()

    def _vf_exec_copy(self, targets):
        src = self.VF_CboSourceView.SelectedItem
        if src is None:
            forms.alert(u'Select a source view.'); return
        inc_ov = self.VF_ChkIncludeOverrides.IsChecked == True
        copied, skipped, _ = _vf_logic.copy_filters_from_view(
            self.doc, src, targets, include_overrides=inc_ov)
        msg = u'Copied: {}  |  Skipped: {}  |  Views: {}'.format(copied, skipped, len(targets))
        self.VF_TxtLastResult.Text = msg
        forms.alert(msg, title=u'Copy Filters')

    def _vf_exec_apply(self, targets):
        checked = [fi for fi in self._vf_vis_filter_items if fi.IsChecked]
        if not checked:
            forms.alert(u'No filters selected.'); return
        src_view = self.VF_CboApplySourceView.SelectedItem \
                   if self.VF_ChkApplyFromView.IsChecked == True else None
        finfos = [{'id': fi.Id, 'name': fi.Name, 'categories': []} for fi in checked]
        applied, skipped, _ = _vf_logic.apply_filters_to_views(
            self.doc, finfos, targets, source_view=src_view)
        msg = u'Applied: {}  |  Skipped: {}  |  Views: {}'.format(applied, skipped, len(targets))
        self.VF_TxtLastResult.Text = msg
        forms.alert(msg, title=u'Apply Filters')

    def _vf_exec_toggle(self, targets):
        checked = [fi for fi in self._vf_vis_filter_items if fi.IsChecked]
        if not checked:
            forms.alert(u'No filters selected.'); return
        enable = self.VF_RbEnable.IsChecked == True
        finfos = [{'id': fi.Id, 'name': fi.Name, 'categories': []} for fi in checked]
        toggled, skipped = _vf_logic.toggle_filters_in_views(self.doc, finfos, targets, enable)
        action = u'Enabled' if enable else u'Disabled'
        msg = u'{}: {}  |  Skipped: {}'.format(action, toggled, skipped)
        self.VF_TxtLastResult.Text = msg
        forms.alert(msg, title=u'Toggle Filters')

    def _vf_exec_remove(self, targets):
        checked = [fi for fi in self._vf_vis_filter_items if fi.IsChecked]
        if not checked:
            forms.alert(u'No filters selected.'); return
        names = u', '.join(fi.Name for fi in checked[:5])
        if len(checked) > 5:
            names += u' ...'
        if not forms.alert(
            u'Remove {} filter(s) from {} view(s)?\n\nFilters: {}'.format(
                len(checked), len(targets), names),
            yes=True, no=True
        ):
            return
        finfos = [{'id': fi.Id, 'name': fi.Name, 'categories': []} for fi in checked]
        removed, skipped = _vf_logic.remove_filters_from_views(self.doc, finfos, targets)
        msg = u'Removed: {}  |  Skipped: {}'.format(removed, skipped)
        self.VF_TxtLastResult.Text = msg
        forms.alert(msg, title=u'Remove Filters')

    def _vf_reload_counts(self):
        for vr in self._vf_all_view_rows:
            try:
                vr.FilterCount = len(list(vr.View.GetFilters()))
            except Exception:
                pass
        self.VF_GridViews.Items.Refresh()

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: COLOUR BY PARAMETER
    # ══════════════════════════════════════════════════════════════════

    def _cp_init(self, cfg):
        self._cp_color_rows   = ObservableCollection[_ColorRow]()
        self._cp_value_map    = {}
        self._cp_color_assign = {}
        self._cp_cats_data    = []
        self.CP_GridColors.ItemsSource = self._cp_color_rows

        last_param = cfg.get('cp_last_param', u'')
        self._cp_last_param = last_param
        self._cp_populate_categories()

    def _cp_active_view(self):
        return self.uidoc.ActiveView

    def _cp_populate_categories(self):
        view = self._cp_active_view()
        if view is None:
            self.CP_TxtStatus.Text = u'No active view.'
            return
        cats = _cbp_logic.get_categories_in_view(self.doc, view)
        self.CP_CmbCategory.Items.Clear()
        for cid, cname in cats:
            self.CP_CmbCategory.Items.Add(cname)
        self._cp_cats_data = cats
        if cats:
            self.CP_CmbCategory.SelectedIndex = 0

    def _cp_populate_params(self):
        idx = self.CP_CmbCategory.SelectedIndex
        if idx < 0 or idx >= len(self._cp_cats_data):
            return
        cid, _ = self._cp_cats_data[idx]
        view   = self._cp_active_view()
        if view is None:
            return
        params = _cbp_logic.get_instance_params_for_category(self.doc, view, cid)
        self.CP_CmbParam.Items.Clear()
        for p in params:
            self.CP_CmbParam.Items.Add(p)
        if self._cp_last_param in params:
            self.CP_CmbParam.SelectedIndex = params.index(self._cp_last_param)
        elif params:
            self.CP_CmbParam.SelectedIndex = 0

    def _cp_collect_values(self):
        idx = self.CP_CmbCategory.SelectedIndex
        if idx < 0 or idx >= len(self._cp_cats_data):
            return
        cid, _     = self._cp_cats_data[idx]
        param_name = self.CP_CmbParam.SelectedItem
        if not param_name:
            return
        view = self._cp_active_view()
        if view is None:
            return
        self._cp_value_map    = _cbp_logic.collect_values_for_param(
            self.doc, view, cid, str(param_name))
        self._cp_color_assign = _cbp_logic.assign_colors(list(self._cp_value_map.keys()))
        self._cp_color_rows.Clear()
        for val_str, ids in sorted(self._cp_value_map.items()):
            rgb = self._cp_color_assign.get(val_str, (180, 180, 180))
            self._cp_color_rows.Add(_ColorRow(val_str, len(ids), rgb))
        self.CP_TxtStatus.Text = u'{} unique values across {} elements'.format(
            len(self._cp_value_map),
            sum(len(v) for v in self._cp_value_map.values()))

    def CP_Refresh_Click(self, sender, args):
        self._cp_populate_categories()
        self._cp_populate_params()
        self._cp_collect_values()

    def CP_Category_Changed(self, sender, args):
        self._cp_populate_params()
        self._cp_collect_values()

    def CP_Param_Changed(self, sender, args):
        pname = self.CP_CmbParam.SelectedItem
        if pname:
            self._cp_last_param = str(pname)
            cfg = self.LoadConfig()
            cfg['cp_last_param'] = self._cp_last_param
            self.SaveConfig(cfg)
        self._cp_collect_values()

    def CP_Apply_Click(self, sender, args):
        view = self._cp_active_view()
        if view is None or not self._cp_value_map:
            self.CP_TxtStatus.Text = u'Nothing to apply.'
            return
        ca = {}
        for row in self._cp_color_rows:
            r = int(row.SwatchHex[1:3], 16)
            g = int(row.SwatchHex[3:5], 16)
            b = int(row.SwatchHex[5:7], 16)
            ca[row.Value] = (r, g, b)
        with DB.Transaction(self.doc, u'NOSA — Colour by Parameter') as t:
            t.Start()
            n = _cbp_logic.apply_overrides(self.doc, view, self._cp_value_map, ca)
            t.Commit()
        self.CP_TxtStatus.Text = u'Applied overrides to {} elements.'.format(n)

    def CP_Clear_Click(self, sender, args):
        view = self._cp_active_view()
        if view is None or not self._cp_value_map:
            return
        with DB.Transaction(self.doc, u'NOSA — Clear Colour Overrides') as t:
            t.Start()
            _cbp_logic.clear_overrides(self.doc, view, self._cp_value_map)
            t.Commit()
        self.CP_TxtStatus.Text = u'Overrides cleared.'

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
