# -*- coding: utf-8 -*-
import imp
import os
import sys

import System.Windows

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('vieworganiser_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_VIS = System.Windows.Visibility.Visible
_COL = System.Windows.Visibility.Collapsed


class _ViewRow(object):
    def __init__(self, rec, new_name=u''):
        self.Name    = rec['name']
        self.NewName = new_name if new_name != rec['name'] else u''
        self.Vtype   = rec['vtype']
        self.Level   = rec['level'] or u'—'
        self.Placed  = u'Yes' if rec['placed'] else u'No'
        self._rec    = rec


class ViewOrganiserWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_organiser')
        self.doc = doc
        self._all_views = []
        self._filtered  = []

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        for label in _logic.view_type_labels():
            self.CboViewType.Items.Add(label)
        self.CboViewType.SelectedIndex = self.CboViewType.Items.Count - 1  # 'All types'

        self.RbFindReplace.IsChecked   = True
        self.PnlFindReplace.Visibility  = _VIS
        self.PnlPrefixSuffix.Visibility = _COL

        self._all_views = _logic.collect_views(doc)
        self._apply_filter()

    def _get_mode(self):
        return u'find_replace' if self.RbFindReplace.IsChecked else u'prefix_suffix'

    def _apply_filter(self):
        vtype  = self.CboViewType.SelectedItem or u'All types'
        unplaced_only = bool(self.ChkUnplacedOnly.IsChecked)

        filtered = [v for v in self._all_views
                    if (vtype == u'All types' or v['vtype'] == vtype)
                    and (not unplaced_only or not v['placed'])]
        self._filtered = filtered
        self._rebuild_preview()

    def _rebuild_preview(self):
        mode    = self._get_mode()
        find    = self.TxtFind.Text
        replace = self.TxtReplace.Text
        prefix  = self.TxtPrefix.Text
        suffix  = self.TxtSuffix.Text

        pairs = _logic.preview_rename(
            [v['name'] for v in self._filtered],
            mode, find, replace, prefix, suffix)

        rows = []
        for i, (old, new) in enumerate(pairs):
            rows.append(_ViewRow(self._filtered[i], new))
        self.GridViews.ItemsSource = rows

        placed = sum(1 for v in self._filtered if v['placed'])
        unplaced = len(self._filtered) - placed
        self.TxtSummary.Text = u'{} views  ·  {} placed  ·  {} unplaced'.format(
            len(self._all_views), placed, unplaced)
        self.TxtStatus.Text = u'Showing {} views.'.format(len(self._filtered))

    def ViewType_Changed(self, sender, args):
        self._apply_filter()

    def Filter_Changed(self, sender, args):
        self._apply_filter()

    def Mode_Changed(self, sender, args):
        is_fr = bool(self.RbFindReplace.IsChecked)
        self.PnlFindReplace.Visibility  = _VIS if is_fr else _COL
        self.PnlPrefixSuffix.Visibility = _COL if is_fr else _VIS
        self._rebuild_preview()

    def Rule_Changed(self, sender, args):
        self._rebuild_preview()

    def Grid_SelectionChanged(self, sender, args):
        n = self.GridViews.SelectedItems.Count
        self.TxtStatus.Text = (u'{} view{} selected.'.format(n, u's' if n != 1 else u'')
                               if n else u'Showing {} views.'.format(len(self._filtered)))

    def SelectAll_Click(self, sender, args):
        self.GridViews.SelectAll()

    def RenameSelected_Click(self, sender, args):
        selected = list(self.GridViews.SelectedItems)
        if not selected:
            self.TxtStatus.Text = u'Select views to rename.'
            return
        pairs = [(row._rec['element'], row.NewName)
                 for row in selected if row.NewName and row.NewName != row.Name]
        if not pairs:
            self.TxtStatus.Text = u'No name changes detected — check rename settings.'
            return
        self.SetLoading(True, u'Renaming views…')
        try:
            renamed, failed, errors = _logic.rename_views(self.doc, pairs)
        finally:
            self.SetLoading(False)
        msg = u'Renamed {}. Failed: {}.'.format(renamed, failed)
        if errors:
            msg += u'  ' + u'; '.join(errors[:3])
        self.TxtStatus.Text = msg
        self._all_views = _logic.collect_views(self.doc)
        self._apply_filter()

    def DeleteSelected_Click(self, sender, args):
        selected = list(self.GridViews.SelectedItems)
        if not selected:
            self.TxtStatus.Text = u'Select views to delete.'
            return
        try:
            from pyrevit import forms as _forms
            if not _forms.alert(
                    u'Delete {} view(s)?'.format(len(selected)),
                    title=u'Confirm Delete', yes=True, no=True):
                return
        except Exception:
            pass
        ids = [row._rec['id'] for row in selected]
        self.SetLoading(True, u'Deleting views…')
        try:
            deleted, failed = _logic.delete_views(self.doc, ids)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Deleted {}. Failed: {}.'.format(deleted, failed)
        self._all_views = _logic.collect_views(self.doc)
        self._apply_filter()

    def DeleteUnplaced_Click(self, sender, args):
        unplaced = [v for v in self._all_views if not v['placed']]
        if not unplaced:
            self.TxtStatus.Text = u'No unplaced views found.'
            return
        try:
            from pyrevit import forms as _forms
            if not _forms.alert(
                    u'Delete {} unplaced view(s)?'.format(len(unplaced)),
                    title=u'Confirm Delete', yes=True, no=True):
                return
        except Exception:
            pass
        ids = [v['id'] for v in unplaced]
        self.SetLoading(True, u'Deleting unplaced views…')
        try:
            deleted, failed = _logic.delete_views(self.doc, ids)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Deleted {} unplaced views. Failed: {}.'.format(deleted, failed)
        self._all_views = _logic.collect_views(self.doc)
        self._apply_filter()

    def Close_Click(self, sender, args):
        self.Close()
