# -*- coding: utf-8 -*-
import imp
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('wallfootings_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_ALL_LEVELS = u'(all levels)'


class _WallRow(object):
    def __init__(self, rec):
        self.IsChecked    = not rec['has_footing']
        self.WallType     = rec['type_name']
        self.LevelName    = rec['level']
        self.LengthStr    = u'{:.1f} m'.format(rec['length_m'])
        self.FootingStr   = u'Has footing' if rec['has_footing'] else u''
        self.FootingColor = u'#22AA44' if rec['has_footing'] else u'#333333'
        self._rec         = rec


class WallFootingsWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'wall_footings')
        self.doc = doc
        self._all_rows = []
        self._types    = []

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self._load()
        self._restore_last_type(cfg)

    # ── data ──────────────────────────────────────────────────────────────────

    def _load(self):
        self._all_rows = [_WallRow(r) for r in _logic.collect_structural_walls(self.doc)]
        self._types    = _logic.collect_footing_types(self.doc)

        self.CmbFootingType.Items.Clear()
        for t in self._types:
            self.CmbFootingType.Items.Add(t['name'])
        if self.CmbFootingType.Items.Count > 0:
            self.CmbFootingType.SelectedIndex = 0

        levels = sorted(set(r.LevelName for r in self._all_rows))
        self.CmbLevel.Items.Clear()
        self.CmbLevel.Items.Add(_ALL_LEVELS)
        for lv in levels:
            self.CmbLevel.Items.Add(lv)
        self.CmbLevel.SelectedIndex = 0

        self._apply_filter()

        with_f = sum(1 for r in self._all_rows if r._rec['has_footing'])
        self.TxtSummary.Text = u'{} structural walls · {} with footing'.format(
            len(self._all_rows), with_f)
        if not self._types:
            self.TxtStatus.Text = (u'No wall foundation types in this project — '
                                   u'load a Wall Foundation family type first.')
        else:
            self.TxtStatus.Text = u'Ready.'

    def _apply_filter(self):
        try:
            level = self.CmbLevel.SelectedItem
        except Exception:
            level = _ALL_LEVELS
        visible = [r for r in self._all_rows
                   if level in (None, _ALL_LEVELS) or r.LevelName == level]
        self.ListWalls.ItemsSource = visible

    def _visible_rows(self):
        return list(self.ListWalls.ItemsSource or [])

    def _restore_last_type(self, cfg):
        last = cfg.get('last_footing_type', u'')
        if not last:
            return
        for i, t in enumerate(self._types):
            if t['name'] == last:
                self.CmbFootingType.SelectedIndex = i
                return

    # ── events ────────────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filter()

    def SelectAll_Click(self, sender, args):
        for r in self._visible_rows():
            r.IsChecked = True
        self.ListWalls.Items.Refresh()

    def SelectNone_Click(self, sender, args):
        for r in self._visible_rows():
            r.IsChecked = False
        self.ListWalls.Items.Refresh()

    def Refresh_Click(self, sender, args):
        self._load()

    def Create_Click(self, sender, args):
        from pyrevit import forms

        idx = self.CmbFootingType.SelectedIndex
        if idx < 0 or idx >= len(self._types):
            forms.alert(u'Select a wall foundation type first.')
            return
        ftype = self._types[idx]

        selected = [r._rec for r in self._visible_rows() if r.IsChecked]
        if not selected:
            forms.alert(u'Select at least one wall.')
            return

        cfg = self.LoadConfig()
        cfg['last_footing_type'] = ftype['name']
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)

        self.SetLoading(True, u'Creating footings…')
        try:
            created, skipped, failed, errors = _logic.create_footings(
                self.doc, selected, ftype['id_obj'])
        finally:
            self.SetLoading(False)

        self.TxtStatus.Text = u'Created: {}  ·  Skipped (existing): {}  ·  Failed: {}'.format(
            created, skipped, failed)
        extra = errors[:5] if errors else None
        self.ShowResult(created=created, skipped=skipped, failed=failed,
                        extra_lines=extra)
        self._load()
