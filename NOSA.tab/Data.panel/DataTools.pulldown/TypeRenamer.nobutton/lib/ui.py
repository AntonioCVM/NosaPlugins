# -*- coding: utf-8 -*-
import imp
import os
import sys

import System.Windows

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('typerenamer_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_VIS = System.Windows.Visibility.Visible
_COL = System.Windows.Visibility.Collapsed


class _TypeRow(object):
    def __init__(self, rec, new_name=u''):
        self.Name    = rec['name']
        self.NewName = new_name if new_name != rec['name'] else u''
        self._rec    = rec


class TypeRenamerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'type_renamer')
        self.doc = doc
        self._type_data = []

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        for cat in _logic.category_names():
            self.CboCategory.Items.Add(cat)
        if self.CboCategory.Items.Count > 0:
            self.CboCategory.SelectedIndex = 0

        self.RbFindReplace.IsChecked = True
        self.PnlFindReplace.Visibility  = _VIS
        self.PnlPrefixSuffix.Visibility = _COL
        self.TxtStatus.Text = u'Select a category to load types.'

    def _get_mode(self):
        return u'find_replace' if self.RbFindReplace.IsChecked else u'prefix_suffix'

    def _rebuild_preview(self):
        mode    = self._get_mode()
        find    = self.TxtFind.Text
        replace = self.TxtReplace.Text
        prefix  = self.TxtPrefix.Text
        suffix  = self.TxtSuffix.Text

        pairs = _logic.preview_rename(
            [r['name'] for r in self._type_data],
            mode, find, replace, prefix, suffix)

        rows = []
        for i, (old, new) in enumerate(pairs):
            rows.append(_TypeRow(self._type_data[i], new))

        try:
            search = (self.TxtSearch.Text or u'').strip().lower()
        except Exception:
            search = u''
        if search:
            rows = [r for r in rows
                    if search in r.Name.lower() or search in r.NewName.lower()]
        self.GridTypes.ItemsSource = rows

    def Category_Changed(self, sender, args):
        cat = self.CboCategory.SelectedItem
        if not cat:
            return
        self._type_data = _logic.get_types_for_category(self.doc, cat)
        self._rebuild_preview()
        self.TxtStatus.Text = u'{} types loaded.'.format(len(self._type_data))

    def Mode_Changed(self, sender, args):
        is_fr = bool(self.RbFindReplace.IsChecked)
        self.PnlFindReplace.Visibility  = _VIS if is_fr else _COL
        self.PnlPrefixSuffix.Visibility = _COL if is_fr else _VIS
        self._rebuild_preview()

    def Rule_Changed(self, sender, args):
        self._rebuild_preview()

    def Search_Changed(self, sender, args):
        self._rebuild_preview()

    def Grid_SelectionChanged(self, sender, args):
        n = self.GridTypes.SelectedItems.Count
        if n:
            self.TxtStatus.Text = u'{} type{} selected.'.format(n, u's' if n != 1 else u'')
        else:
            self.TxtStatus.Text = u'{} types loaded.'.format(len(self._type_data))

    def SelectAll_Click(self, sender, args):
        self.GridTypes.SelectAll()

    def ApplyRename_Click(self, sender, args):
        selected = list(self.GridTypes.SelectedItems)
        if not selected:
            self.TxtFormStatus.Text = u'Select at least one type to rename.'
            return

        pairs = []
        for row in selected:
            new = row.NewName
            if new and new != row.Name:
                pairs.append((row._rec['element'], new))

        if not pairs:
            self.TxtFormStatus.Text = u'No name changes detected — check find/prefix settings.'
            return

        self.SetLoading(True, u'Renaming types…')
        try:
            renamed, failed, errors = _logic.apply_renames(self.doc, pairs)
        finally:
            self.SetLoading(False)

        msg = u'Renamed {}. Failed: {}.'.format(renamed, failed)
        if errors:
            msg += u'  ' + u'; '.join(errors[:3])
        self.TxtFormStatus.Text = msg
        self.Category_Changed(None, None)

    def Close_Click(self, sender, args):
        self.Close()
