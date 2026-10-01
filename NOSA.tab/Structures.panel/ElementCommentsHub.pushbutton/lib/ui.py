# -*- coding: utf-8 -*-
import os
import sys

import System
from Autodesk.Revit import DB
from pyrevit import forms, revit
from System.Collections.ObjectModel import ObservableCollection

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_here = os.path.dirname(os.path.abspath(__file__))
from nosa_utils.bootstrap import load_module
_logic = load_module('elc_logic', os.path.join(_here, 'logic.py'))
_dmu = load_module('elc_logic_dmu', os.path.join(_here, 'logic_dmu.py'))


class GroupRow(object):
    """One row = one exact (Category, Family, Type). Plain attributes only
    (WPF DataGrid binding, matching PileMaster's PrefixItem convention)."""
    def __init__(self, grp, prefix, suffix):
        self.Key      = grp.key
        self.Category = grp.category_label
        self.Family   = grp.family_name
        self.Type     = grp.type_name
        self.Count    = len(grp.elements)
        self.Current  = grp.current_comment or u''
        self.Prefix   = prefix
        self.Suffix   = suffix
        self.Preview  = u''


class CategoryItem(object):
    def __init__(self, key, label, checked=True):
        self.Key = key
        self.Label = label
        self.IsChecked = checked


class ElementCommentsHubWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'element_comments_hub')
        self.doc = doc
        self.uidoc = uidoc
        self._tabs = {
            'BtnTabManual': self.TabManual,
            'BtnTabAuto':   self.TabAuto,
        }
        self._tlogic = _logic.TypeCommentsLogic(doc)
        self._groups = {}
        self._rows = ObservableCollection[object]()
        self.GridGroups.ItemsSource = self._rows

        self._cat_items = ObservableCollection[object]()
        for key, label, _bic in _logic.CATEGORY_CHOICES:
            self._cat_items.Add(CategoryItem(key, label, True))
        self.ListCategories.ItemsSource = self._cat_items

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self.AutoInit()
        self._restore_auto_state()
        self._load_groups()

    # ── tabs ──────────────────────────────────────────────────────────────

    def Tab_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)

    # ── scope / categories ───────────────────────────────────────────────

    def _scope(self):
        if self.RbScopeSelection.IsChecked:
            return 'selection'
        if self.RbScopeProject.IsChecked:
            return 'project'
        return 'active_view'

    def _checked_categories(self):
        return [c.Key for c in self._cat_items if c.IsChecked]

    def CategoryCheck_Changed(self, sender, args):
        self._load_groups()

    def Scope_Changed(self, sender, args):
        self._load_groups()

    # ── manual grid ───────────────────────────────────────────────────────

    def _load_groups(self):
        self.SetLoading(True, u'Loading elements…')
        try:
            cat_keys = self._checked_categories()
            pairs = self._tlogic.get_elements(self._scope(), cat_keys, self.uidoc)
            self._groups = self._tlogic.group_by_type(pairs)
        finally:
            self.SetLoading(False)

        self._rows.Clear()
        if not self._groups:
            scope_label = {'active_view': u'active view', 'selection': u'selection',
                           'project': u'entire project'}.get(self._scope(), self._scope())
            self.TxtGroupCount.Text = (
                u'No elements found in the {} for the ticked categories. '
                u'Try "Entire project" or tick more categories.'.format(scope_label))
            return

        for key in sorted(self._groups.keys(), key=lambda k: (k[0], k[1], k[2])):
            grp = self._groups[key]
            prefix = _logic.default_prefix_for(grp.category_key, grp.family_name, grp.type_name)
            self._rows.Add(GroupRow(grp, prefix, u''))
        self._refresh_preview()
        self.TxtGroupCount.Text = u'{} type(s) · {} element(s)'.format(
            len(self._rows), sum(r.Count for r in self._rows))

    def _refresh_preview(self):
        """Uses the exact same compute_group_values() that Apply calls,
        so the preview can never disagree with what actually gets written."""
        only_empty = bool(self.ChkOnlyEmpty.IsChecked)
        config_map = {row.Key: (row.Prefix or u'', row.Suffix or u'') for row in self._rows}
        values = _logic.compute_group_values(self._groups, config_map, only_empty=only_empty)
        for row in self._rows:
            val = values.get(row.Key, u'')
            if only_empty and row.Current:
                row.Preview = u'(kept: {})'.format(row.Current)
            else:
                row.Preview = val
        self.GridGroups.Items.Refresh()

    def Groups_CellEdit(self, sender, args):
        try:
            header = str(getattr(args.Column, 'Header', ''))
            if header not in ('Prefix', 'Suffix'):
                return
            row = args.Row.Item
            txt = args.EditingElement.Text if hasattr(args.EditingElement, 'Text') else u''
            if header == 'Prefix':
                row.Prefix = u'{}'.format(txt)
            else:
                row.Suffix = u'{}'.format(txt)
            import System.Windows.Threading as _swt
            def _do_refresh():
                try:
                    self._refresh_preview()
                except Exception:
                    pass
            self.GridGroups.Dispatcher.BeginInvoke(
                _swt.DispatcherPriority.Background, System.Action(_do_refresh))
        except Exception:
            pass

    def OnlyEmpty_Changed(self, sender, args):
        self._refresh_preview()

    def RefreshGroups_Click(self, sender, args):
        self._load_groups()

    def ApplyComments_Click(self, sender, args):
        if not self._groups:
            forms.alert(u'Nothing loaded — click Refresh first.')
            return
        config_map = {row.Key: (row.Prefix or u'', row.Suffix or u'') for row in self._rows}
        only_empty = bool(self.ChkOnlyEmpty.IsChecked)
        if not forms.alert(
                u'Apply Comments to {} type(s) / {} element(s)?'.format(
                    len(self._groups), sum(len(g.elements) for g in self._groups.values())),
                yes=True, no=True):
            return
        self.SetLoading(True, u'Applying Comments…')
        try:
            written, groups_written = self._tlogic.apply_comments(
                self._groups, config_map, only_empty=only_empty)
        finally:
            self.SetLoading(False)
        forms.alert(
            u'Comments applied.\n\nElements updated: {}\nTypes updated: {}'.format(
                written, groups_written),
            title=u'Element Comments Hub')
        self._load_groups()

    # ── automatic tab (DMU) ──────────────────────────────────────────────

    def _restore_auto_state(self):
        try:
            cfg = _dmu.read_config()
            is_active = cfg.get('active', False)
            self._apply_auto_ui(is_active)
            wanted = set(cfg.get('categories') or [])
            for item in self._auto_cat_items():
                item.IsChecked = item.Key in wanted
        except Exception:
            pass

    def _auto_cat_items(self):
        return list(self.ListAutoCategories.ItemsSource or [])

    def _apply_auto_ui(self, is_active):
        try:
            import System.Windows.Media as Media
            self.TglAuto.IsChecked = is_active
            self.TglAuto.Content = u'DISABLE' if is_active else u'ENABLE'
            if is_active:
                self.AutoDot.Fill = Media.Brushes.LimeGreen
                self.TxtAutoStatus.Text = (
                    u'Active — new elements in the ticked categories get a Comments '
                    u'code automatically (copied from a matching Type, or a new one).')
            else:
                self.AutoDot.Fill = Media.Brushes.LightGray
                self.TxtAutoStatus.Text = (
                    u'Inactive — enable to auto-assign Comments when elements are placed.')
        except Exception:
            pass

    def AutoInit(self):
        """Called once after XAML load to seed the Automatic-tab category list."""
        self._auto_cats = ObservableCollection[object]()
        for key, label, _bic in _logic.CATEGORY_CHOICES:
            self._auto_cats.Add(CategoryItem(key, label, True))
        self.ListAutoCategories.ItemsSource = self._auto_cats

    def ToggleAuto_Click(self, sender, args):
        try:
            is_active = (self.TglAuto.IsChecked == True)  # noqa: E712
            cats = [c.Key for c in (self.ListAutoCategories.ItemsSource or []) if c.IsChecked]
            _dmu.write_config({'active': is_active, 'categories': cats})
            self._apply_auto_ui(is_active)
        except Exception as e:
            forms.alert(u'Automatic mode error: {}'.format(e), title=u'Error')

    def AutoCategoryCheck_Changed(self, sender, args):
        try:
            cfg = _dmu.read_config()
            cats = [c.Key for c in (self.ListAutoCategories.ItemsSource or []) if c.IsChecked]
            cfg['categories'] = cats
            _dmu.write_config(cfg)
        except Exception:
            pass

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
