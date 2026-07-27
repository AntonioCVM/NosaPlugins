# -*- coding: utf-8 -*-
import imp
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_place = imp.load_source('sheetgen_place_logic',
                         os.path.join(os.path.dirname(__file__), 'logic_place.py'))
_sglogic = imp.load_source('sheetgen_place_sglogic',
                           os.path.join(os.path.dirname(__file__), 'logic.py'))


class ViewRow(object):
    def __init__(self, rec):
        self.ViewName = rec['name']
        self.ViewKind = rec['type']
        self._rec     = rec


class SheetRow(object):
    def __init__(self, rec):
        self.Label = rec['label']
        self._rec  = rec


class PhRow(object):
    def __init__(self, rec):
        self.Number = rec['number']
        self.PhName = rec['name']
        self._rec   = rec


class TbItem(object):
    def __init__(self, mid, name):
        self.Id   = mid
        self.Name = name

    def __str__(self):
        return self.Name


class PlaceViewsWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui_place.xaml')
        NOSAWindow.__init__(self, xaml, 'sheet_gen_place')
        self.doc = doc
        self._tabs = {
            'BtnTabPlace':  self.TabPlace,
            'BtnTabLegend': self.TabLegend,
            'BtnTabPh':     self.TabPh,
        }
        self._load_all()

    def _load_all(self):
        self._views   = _place.unplaced_views(self.doc)
        self._sheets  = _place.real_sheets(self.doc)
        self._legends = _place.legend_views(self.doc)
        self._phs     = _place.placeholder_sheets(self.doc)

        self.GridViews.ItemsSource        = [ViewRow(r) for r in self._views]
        self.GridLegendSheets.ItemsSource = [SheetRow(r) for r in self._sheets]
        self.GridPh.ItemsSource           = [PhRow(r) for r in self._phs]

        tbs = _sglogic.get_titleblock_types(self.doc)
        tb_items = [TbItem(mid, n) for mid, n in tbs]
        for combo in (self.CmbTb, self.CmbPhTb):
            combo.ItemsSource = tb_items
            combo.SelectedIndex = 0 if tb_items else -1

        self.CmbTargetSheet.Items.Clear()
        for r in self._sheets:
            self.CmbTargetSheet.Items.Add(r['label'])
        if self._sheets:
            self.CmbTargetSheet.SelectedIndex = 0

        self.CmbLegend.Items.Clear()
        for r in self._legends:
            self.CmbLegend.Items.Add(r['name'])
        if self._legends:
            self.CmbLegend.SelectedIndex = 0

        self.TxtStatus.Text = u'{} unplaced views · {} sheets · {} legends · {} placeholders'.format(
            len(self._views), len(self._sheets), len(self._legends), len(self._phs))

    def Tab_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)

    def _int(self, box, default):
        try:
            return int(box.Text.strip())
        except Exception:
            return default

    def _float(self, box, default):
        try:
            return float(box.Text.strip())
        except Exception:
            return default

    # ── Place Views ───────────────────────────────────────────────────────────

    def Place_Click(self, sender, args):
        from pyrevit import forms
        rows = list(self.GridViews.SelectedItems or [])
        if not rows:
            forms.alert(u'Select at least one view in the list.')
            return
        recs = [r._rec for r in rows]

        if self.RbSheetPerView.IsChecked:
            tb = self.CmbTb.SelectedItem
            if not tb:
                forms.alert(u'Select a title block.')
                return
            if not forms.alert(u'Create {} sheet(s), one per view?'.format(len(recs)),
                               yes=True, no=True):
                return
            self.SetLoading(True, u'Creating sheets…')
            try:
                created, failed, errors = _place.create_sheets_with_views(
                    self.doc, recs, tb.Id,
                    self.TxtNumPrefix.Text or u'S-',
                    self._int(self.TxtNumStart, 1),
                    self._int(self.TxtNumPad, 3),
                    name_from_view=self.ChkNameFromView.IsChecked == True)
            finally:
                self.SetLoading(False)
            self.TxtStatus.Text = u'Created {} sheet(s). Failed: {}.'.format(created, failed)
            if errors:
                forms.alert(u'\n'.join(errors[:8]), title=u'Place Views — errors')
        else:
            idx = self.CmbTargetSheet.SelectedIndex
            if idx < 0 or idx >= len(self._sheets):
                forms.alert(u'Select a target sheet.')
                return
            sheet = self._sheets[idx]['sheet']
            self.SetLoading(True, u'Placing views…')
            try:
                placed, skipped, errors = _place.place_views_grid(
                    self.doc, sheet, recs,
                    self._int(self.TxtGridCols, 2),
                    self._float(self.TxtGridMargin, 20.0))
            finally:
                self.SetLoading(False)
            self.TxtStatus.Text = u'Placed {}  ·  Skipped {}.'.format(placed, skipped)
            if errors:
                forms.alert(u'\n'.join(errors[:8]), title=u'Place Views — warnings')
        self._load_all()

    # ── Legends ───────────────────────────────────────────────────────────────

    def PlaceLegend_Click(self, sender, args):
        from pyrevit import forms
        idx = self.CmbLegend.SelectedIndex
        if idx < 0 or idx >= len(self._legends):
            forms.alert(u'Select a legend.')
            return
        rows = list(self.GridLegendSheets.SelectedItems or [])
        if not rows:
            forms.alert(u'Select at least one sheet.')
            return
        legend = self._legends[idx]['view']
        sheets = [r._rec for r in rows]
        if not forms.alert(u'Place "{}" on {} sheet(s)?'.format(
                self._legends[idx]['name'], len(sheets)), yes=True, no=True):
            return
        self.SetLoading(True, u'Placing legend…')
        try:
            placed, skipped, errors = _place.place_legend_on_sheets(
                self.doc, legend, sheets,
                self._float(self.TxtLegU, 30.0),
                self._float(self.TxtLegV, 30.0))
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Legend placed on {} sheet(s). Skipped: {}.'.format(placed, skipped)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'Legends — warnings')

    # ── Placeholders ──────────────────────────────────────────────────────────

    def CreatePh_Click(self, sender, args):
        from pyrevit import forms
        count = self._int(self.TxtPhCount, 0)
        if count <= 0:
            forms.alert(u'Enter a count greater than zero.')
            return
        self.SetLoading(True, u'Creating placeholders…')
        try:
            created, failed, errors = _place.create_placeholders(
                self.doc,
                self.TxtPhPrefix.Text or u'S-',
                self._int(self.TxtPhStart, 1),
                count,
                self._int(self.TxtPhPad, 3),
                self.TxtPhName.Text or u'PLACEHOLDER')
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Created {} placeholder(s). Failed: {}.'.format(created, failed)
        self._load_all()

    def ConvertPh_Click(self, sender, args):
        from pyrevit import forms
        rows = list(self.GridPh.SelectedItems or [])
        if not rows:
            forms.alert(u'Select placeholders to convert.')
            return
        tb = self.CmbPhTb.SelectedItem
        if not tb:
            forms.alert(u'Select a title block for the real sheets.')
            return
        if not forms.alert(
                u'Convert {} placeholder(s) to real sheets?\n'
                u'The placeholder is deleted and recreated as a real sheet '
                u'with the same number and name.'.format(len(rows)),
                yes=True, no=True):
            return
        self.SetLoading(True, u'Converting…')
        try:
            converted, failed, errors = _place.convert_placeholders(
                self.doc, [r._rec for r in rows], tb.Id)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Converted {}  ·  Failed {}.'.format(converted, failed)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'Placeholders — errors')
        self._load_all()
