# -*- coding: utf-8 -*-
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import imp
_logic = imp.load_source('cbp_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow
from Autodesk.Revit import DB
from System.Collections.ObjectModel import ObservableCollection


class ColorRow(object):
    def __init__(self, value, count, rgb):
        self.Value    = value
        self.Count    = str(count)
        r, g, b       = rgb
        self.SwatchHex = u'#{:02X}{:02X}{:02X}'.format(r, g, b)
        self.HexStr    = self.SwatchHex
        self._rgb      = rgb


class ColourByParamWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'colour_by_param')
        self.doc   = doc
        self.uidoc = uidoc
        self._value_map     = {}
        self._color_assign  = {}
        self._color_rows    = ObservableCollection[ColorRow]()
        self.GridColors.ItemsSource = self._color_rows

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._populate_categories()

    def _active_view(self):
        return self.uidoc.ActiveView

    def _populate_categories(self):
        view = self._active_view()
        if view is None:
            self.TxtStatus.Text = u'No active view.'
            return
        cats = _logic.get_categories_in_view(self.doc, view)
        self.CmbCategory.Items.Clear()
        for cid, cname in cats:
            self.CmbCategory.Items.Add(u'{}'.format(cname))
        self._cats_data = cats
        if cats:
            self.CmbCategory.SelectedIndex = 0

    def _populate_params(self):
        idx = self.CmbCategory.SelectedIndex
        if idx < 0 or idx >= len(self._cats_data):
            return
        cid, cname = self._cats_data[idx]
        view = self._active_view()
        if view is None:
            return
        params = _logic.get_instance_params_for_category(self.doc, view, cid)
        self.CmbParam.Items.Clear()
        for p in params:
            self.CmbParam.Items.Add(p)
        cfg = self.LoadConfig()
        last = cfg.get('last_param', '')
        if last in params:
            self.CmbParam.SelectedIndex = params.index(last)
        elif params:
            self.CmbParam.SelectedIndex = 0

    def _collect_values(self):
        idx_cat = self.CmbCategory.SelectedIndex
        if idx_cat < 0 or idx_cat >= len(self._cats_data):
            return
        cid, _ = self._cats_data[idx_cat]
        param_name = self.CmbParam.SelectedItem
        if not param_name:
            return

        view = self._active_view()
        if view is None:
            return

        self._value_map    = _logic.collect_values_for_param(self.doc, view, cid, str(param_name))
        self._color_assign = _logic.assign_colors(list(self._value_map.keys()))

        self._color_rows.Clear()
        for val_str, ids in sorted(self._value_map.items()):
            rgb = self._color_assign.get(val_str, (180, 180, 180))
            self._color_rows.Add(ColorRow(val_str, len(ids), rgb))

        self.TxtStatus.Text = u'{} unique values across {} elements'.format(
            len(self._value_map),
            sum(len(v) for v in self._value_map.values()))

    # Event handlers
    def Refresh_Click(self, sender, args):
        self._populate_categories()
        self._populate_params()
        self._collect_values()

    def Category_Changed(self, sender, args):
        self._populate_params()
        self._collect_values()

    def Param_Changed(self, sender, args):
        param_name = self.CmbParam.SelectedItem
        if param_name:
            cfg = self.LoadConfig()
            cfg['last_param'] = str(param_name)
            self.SaveConfig(cfg)
        self._collect_values()

    def Apply_Click(self, sender, args):
        view = self._active_view()
        if view is None or not self._value_map:
            self.TxtStatus.Text = u'Nothing to apply.'
            return
        # Rebuild color assignment from current rows
        ca = {}
        for row in self._color_rows:
            r = int(row.SwatchHex[1:3], 16)
            g = int(row.SwatchHex[3:5], 16)
            b = int(row.SwatchHex[5:7], 16)
            ca[row.Value] = (r, g, b)

        with DB.Transaction(self.doc, u'NOSA — Colour by Parameter') as t:
            t.Start()
            n = _logic.apply_overrides(self.doc, view, self._value_map, ca)
            t.Commit()
        self.TxtStatus.Text = u'Applied overrides to {} elements.'.format(n)

    def Clear_Click(self, sender, args):
        view = self._active_view()
        if view is None or not self._value_map:
            return
        with DB.Transaction(self.doc, u'NOSA — Clear Colour Overrides') as t:
            t.Start()
            _logic.clear_overrides(self.doc, view, self._value_map)
            t.Commit()
        self.TxtStatus.Text = u'Overrides cleared.'

    def Close_Click(self, sender, args):
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
