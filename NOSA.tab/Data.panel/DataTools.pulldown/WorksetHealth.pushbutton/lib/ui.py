# -*- coding: utf-8 -*-
import imp
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('worksethealth_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


class _WorksetRow(object):
    def __init__(self, rec):
        self.Name     = rec['name']
        self.Count    = str(rec['count'])
        self.Owner    = rec['owner'] or u'—'
        self.Editable = u'Yes' if rec['editable'] else u'No'
        self.Open     = u'Yes' if rec['open'] else u'No'
        self.Visible  = u'Yes' if rec['visible'] else u'No'
        self._id      = rec['id']


class WorksetHealthWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'workset_health')
        self.doc = doc
        self._stats = []

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        if not _logic.is_workshared(doc):
            self.TxtStatus.Text = u'This model is not workshared. Worksets are not available.'
            self.TxtSubtitle.Text = u'(not workshared)'
        else:
            self._load()

    def _load(self):
        self._stats = _logic.get_workset_stats(self.doc)
        self._rows  = [_WorksetRow(s) for s in self._stats]
        self._apply_search()

        self.CboTargetWorkset.Items.Clear()
        for s in self._stats:
            self.CboTargetWorkset.Items.Add(s)
        if self.CboTargetWorkset.Items.Count > 0:
            self.CboTargetWorkset.SelectedIndex = 0

        total_el = sum(s['count'] for s in self._stats)
        self.TxtSubtitle.Text = u'{} worksets · {} elements total'.format(
            len(self._stats), total_el)
        self.TxtStatus.Text = u'Ready.'

    def _apply_search(self):
        try:
            text = (self.TxtSearch.Text or u'').strip().lower()
        except Exception:
            text = u''
        rows = getattr(self, '_rows', [])
        if text:
            rows = [r for r in rows
                    if text in r.Name.lower() or text in r.Owner.lower()]
        self.GridWorksets.ItemsSource = rows

    def Search_Changed(self, sender, args):
        self._apply_search()

    def Grid_SelectionChanged(self, sender, args):
        pass

    def MoveElements_Click(self, sender, args):
        selected_rows = list(self.GridWorksets.SelectedItems)
        if not selected_rows:
            self.TxtStatus.Text = u'Select a source workset row first.'
            return
        target = self.CboTargetWorkset.SelectedItem
        if target is None:
            self.TxtStatus.Text = u'Select a target workset.'
            return

        source_ids = {row._id for row in selected_rows}
        if target['id'] in source_ids:
            self.TxtStatus.Text = u'Source and target worksets must differ.'
            return

        els = []
        for sid in source_ids:
            els.extend(_logic.get_elements_on_workset(self.doc, sid))

        if not els:
            self.TxtStatus.Text = u'No elements on selected workset(s).'
            return

        el_ids = [el.Id for el in els]
        self.SetLoading(True, u'Moving elements…')
        try:
            moved, failed = _logic.move_elements_to_workset(
                self.doc, el_ids, target['id'])
        finally:
            self.SetLoading(False)

        self.TxtStatus.Text = u'Moved {} elements to "{}". {} could not be moved.'.format(
            moved, target['name'], failed)
        self._load()

    def Refresh_Click(self, sender, args):
        self._load()

    def Close_Click(self, sender, args):
        self.Close()
