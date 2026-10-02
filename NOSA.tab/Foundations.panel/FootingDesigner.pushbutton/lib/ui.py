# -*- coding: utf-8 -*-
import os
import sys
import System.Windows

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_here = os.path.dirname(os.path.abspath(__file__))
from nosa_utils.bootstrap import load_module
_pad_logic  = load_module('fd_pad_logic',  os.path.join(_here, 'logic_pad_footings.py'))
_wall_logic = load_module('fd_wall_logic', os.path.join(_here, 'logic_wall_footings.py'))

_ALL_LEVELS = u'(all levels)'


class _ColumnRow(object):
    def __init__(self, rec):
        self.IsChecked    = not rec['has_footing']
        self.ColumnType   = rec['type_name']
        self.LevelName    = rec['level']
        self.LengthStr    = u''
        self.FootingStr   = u'Has footing' if rec['has_footing'] else u''
        self.FootingColor = u'#22AA44' if rec['has_footing'] else u'#333333'
        self._rec         = rec


class _WallRow(object):
    def __init__(self, rec):
        self.IsChecked    = not rec['has_footing']
        self.WallType     = rec['type_name']
        self.LevelName    = rec['level']
        self.LengthStr    = u'{:.1f} m'.format(rec['length_m'])
        self.FootingStr   = u'Has footing' if rec['has_footing'] else u''
        self.FootingColor = u'#22AA44' if rec['has_footing'] else u'#333333'
        self._rec         = rec


class FootingDesignerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'footing_designer')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.PF_CmbLevel.SelectionChanged += self.PF_Filter_Changed
        self.WF_CmbLevel.SelectionChanged += self.WF_Filter_Changed
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._pad_all_rows  = []
        self._pad_types     = []
        self._pad_status    = u''
        self._wall_all_rows = []
        self._wall_types    = []
        self._wall_status   = u''

        self._pad_load()
        self._pad_restore_last_type(cfg)
        self._wall_load()
        self._wall_restore_last_type(cfg)

        self._mode = 'pad'
        self._update_mode_panels()

    # ══════════════════════════════════════════════════════════════════
    # Tab toggle
    # ══════════════════════════════════════════════════════════════════

    def _update_mode_panels(self):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        pad = self._mode == 'pad'
        self.PanelPad.Visibility  = V if pad else C
        self.PanelWall.Visibility = C if pad else V
        self.BtnModePad.Tag  = u'Active' if pad else u''
        self.BtnModeWall.Tag = u'' if pad else u'Active'
        self.TxtStatus.Text  = self._pad_status if pad else self._wall_status

    def ModePad_Click(self, sender, args):
        self._mode = 'pad'
        self._update_mode_panels()

    def ModeWall_Click(self, sender, args):
        self._mode = 'wall'
        self._update_mode_panels()

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: PAD FOOTINGS  (structural columns)
    # ══════════════════════════════════════════════════════════════════

    def _pad_load(self):
        self._pad_all_rows = [_ColumnRow(r) for r in _pad_logic.collect_structural_columns(self.doc)]
        self._pad_types    = _pad_logic.collect_footing_symbols(self.doc)

        self.PF_CmbFootingType.Items.Clear()
        for t in self._pad_types:
            self.PF_CmbFootingType.Items.Add(t['name'])
        if self.PF_CmbFootingType.Items.Count > 0:
            self.PF_CmbFootingType.SelectedIndex = 0

        levels = sorted(set(r.LevelName for r in self._pad_all_rows))
        self.PF_CmbLevel.Items.Clear()
        self.PF_CmbLevel.Items.Add(_ALL_LEVELS)
        for lv in levels:
            self.PF_CmbLevel.Items.Add(lv)
        self.PF_CmbLevel.SelectedIndex = 0

        self._pad_apply_filter()

        with_f = sum(1 for r in self._pad_all_rows if r._rec['has_footing'])
        self.PF_TxtSummary.Text = u'{} structural columns · {} with footing nearby'.format(
            len(self._pad_all_rows), with_f)
        if not self._pad_types:
            self._pad_status = (u'No point-based structural foundation families '
                                 u'in this project — load a pad footing family first.')
        else:
            self._pad_status = u'Ready.'
        if self._mode_is('pad'):
            self.TxtStatus.Text = self._pad_status

    def _apply_pad_status(self, text):
        self._pad_status = text
        if self._mode_is('pad'):
            self.TxtStatus.Text = text

    def _mode_is(self, mode):
        return getattr(self, '_mode', 'pad') == mode

    def _pad_apply_filter(self):
        try:
            level = self.PF_CmbLevel.SelectedItem
        except Exception:
            level = _ALL_LEVELS
        visible = [r for r in self._pad_all_rows
                   if level in (None, _ALL_LEVELS) or r.LevelName == level]
        self.PF_ListColumns.ItemsSource = visible

    def _pad_visible_rows(self):
        return list(self.PF_ListColumns.ItemsSource or [])

    def _pad_restore_last_type(self, cfg):
        last = cfg.get('pad_last_footing_type', u'')
        if not last:
            return
        for i, t in enumerate(self._pad_types):
            if t['name'] == last:
                self.PF_CmbFootingType.SelectedIndex = i
                return

    def PF_Filter_Changed(self, sender, args):
        self._pad_apply_filter()

    def PF_SelectAll_Click(self, sender, args):
        for r in self._pad_visible_rows():
            r.IsChecked = True
        self.PF_ListColumns.Items.Refresh()

    def PF_SelectNone_Click(self, sender, args):
        for r in self._pad_visible_rows():
            r.IsChecked = False
        self.PF_ListColumns.Items.Refresh()

    def PF_Refresh_Click(self, sender, args):
        self._pad_load()

    def PF_Create_Click(self, sender, args):
        from pyrevit import forms

        idx = self.PF_CmbFootingType.SelectedIndex
        if idx < 0 or idx >= len(self._pad_types):
            forms.alert(u'Select a pad footing type first.')
            return
        ftype = self._pad_types[idx]

        selected = [r._rec for r in self._pad_visible_rows() if r.IsChecked]
        if not selected:
            forms.alert(u'Select at least one column.')
            return

        cfg = self.LoadConfig()
        cfg['pad_last_footing_type'] = ftype['name']
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)

        self.SetLoading(True, u'Creating pad footings…')
        try:
            created, skipped, failed, errors = _pad_logic.create_footings(
                self.doc, selected, ftype['symbol'])
        finally:
            self.SetLoading(False)

        self._apply_pad_status(u'Created: {}  ·  Skipped (existing): {}  ·  Failed: {}'.format(
            created, skipped, failed))
        extra = errors[:5] if errors else None
        self.ShowResult(created=created, skipped=skipped, failed=failed,
                        extra_lines=extra)
        self._pad_load()

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: WALL FOOTINGS  (structural walls)
    # ══════════════════════════════════════════════════════════════════

    def _wall_load(self):
        self._wall_all_rows = [_WallRow(r) for r in _wall_logic.collect_structural_walls(self.doc)]
        self._wall_types    = _wall_logic.collect_footing_types(self.doc)

        self.WF_CmbFootingType.Items.Clear()
        for t in self._wall_types:
            self.WF_CmbFootingType.Items.Add(t['name'])
        if self.WF_CmbFootingType.Items.Count > 0:
            self.WF_CmbFootingType.SelectedIndex = 0

        levels = sorted(set(r.LevelName for r in self._wall_all_rows))
        self.WF_CmbLevel.Items.Clear()
        self.WF_CmbLevel.Items.Add(_ALL_LEVELS)
        for lv in levels:
            self.WF_CmbLevel.Items.Add(lv)
        self.WF_CmbLevel.SelectedIndex = 0

        self._wall_apply_filter()

        with_f = sum(1 for r in self._wall_all_rows if r._rec['has_footing'])
        self.WF_TxtSummary.Text = u'{} structural walls · {} with footing'.format(
            len(self._wall_all_rows), with_f)
        if not self._wall_types:
            self._wall_status = (u'No wall foundation types in this project — '
                                  u'load a Wall Foundation family type first.')
        else:
            self._wall_status = u'Ready.'
        if self._mode_is('wall'):
            self.TxtStatus.Text = self._wall_status

    def _apply_wall_status(self, text):
        self._wall_status = text
        if self._mode_is('wall'):
            self.TxtStatus.Text = text

    def _wall_apply_filter(self):
        try:
            level = self.WF_CmbLevel.SelectedItem
        except Exception:
            level = _ALL_LEVELS
        visible = [r for r in self._wall_all_rows
                   if level in (None, _ALL_LEVELS) or r.LevelName == level]
        self.WF_ListWalls.ItemsSource = visible

    def _wall_visible_rows(self):
        return list(self.WF_ListWalls.ItemsSource or [])

    def _wall_restore_last_type(self, cfg):
        last = cfg.get('wall_last_footing_type', u'')
        if not last:
            return
        for i, t in enumerate(self._wall_types):
            if t['name'] == last:
                self.WF_CmbFootingType.SelectedIndex = i
                return

    def WF_Filter_Changed(self, sender, args):
        self._wall_apply_filter()

    def WF_SelectAll_Click(self, sender, args):
        for r in self._wall_visible_rows():
            r.IsChecked = True
        self.WF_ListWalls.Items.Refresh()

    def WF_SelectNone_Click(self, sender, args):
        for r in self._wall_visible_rows():
            r.IsChecked = False
        self.WF_ListWalls.Items.Refresh()

    def WF_Refresh_Click(self, sender, args):
        self._wall_load()

    def WF_Create_Click(self, sender, args):
        from pyrevit import forms

        idx = self.WF_CmbFootingType.SelectedIndex
        if idx < 0 or idx >= len(self._wall_types):
            forms.alert(u'Select a wall foundation type first.')
            return
        ftype = self._wall_types[idx]

        selected = [r._rec for r in self._wall_visible_rows() if r.IsChecked]
        if not selected:
            forms.alert(u'Select at least one wall.')
            return

        cfg = self.LoadConfig()
        cfg['wall_last_footing_type'] = ftype['name']
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)

        self.SetLoading(True, u'Creating footings…')
        try:
            created, skipped, failed, errors = _wall_logic.create_footings(
                self.doc, selected, ftype['id_obj'])
        finally:
            self.SetLoading(False)

        self._apply_wall_status(u'Created: {}  ·  Skipped (existing): {}  ·  Failed: {}'.format(
            created, skipped, failed))
        extra = errors[:5] if errors else None
        self.ShowResult(created=created, skipped=skipped, failed=failed,
                        extra_lines=extra)
        self._wall_load()

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
