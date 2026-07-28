# -*- coding: utf-8 -*-
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import imp
_logic = imp.load_source('baysections_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow
from nosa_utils import unit_conversion as _uc10
from Autodesk.Revit import DB
from System.Collections.ObjectModel import ObservableCollection


class GridRow(object):
    def __init__(self, grid_dict):
        self.SelA     = False
        self.SelB     = False
        self._grid_id = grid_dict['id']
        self.Name     = grid_dict['name']
        self.GridType = u'Arc' if grid_dict['is_arc'] else u'Linear'


class BaySectionsWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'bay_sections')
        self.doc   = doc
        self.uidoc = uidoc
        self._grid_rows = ObservableCollection[GridRow]()

        try:
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
            self.TxtPrefix.Text = cfg.get('prefix', u'S')
            self.TxtDepthOffset.Text = str(cfg.get('depth_offset', 3000))
            self._populate_view_types()
            self._populate_grids()
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Bay Sections init error:\n{}'.format(e), title='Error')

    def _populate_view_types(self):
        self.CmbViewType.Items.Clear()
        self._view_types = _logic.get_view_family_types(self.doc)
        for vt in self._view_types:
            self.CmbViewType.Items.Add(_logic.safe_element_name(vt))
        if self._view_types:
            self.CmbViewType.SelectedIndex = 0

    def _populate_grids(self):
        self._grid_rows.Clear()
        for g in _logic.get_grids(self.doc):
            self._grid_rows.Add(GridRow(g))
        self.GridList.ItemsSource = self._grid_rows
        self.LogLine(u'Loaded {} grids.'.format(self._grid_rows.Count))

    def Generate_Click(self, sender, args):
        grids_a = [r for r in self._grid_rows if r.SelA]
        grids_b = [r for r in self._grid_rows if r.SelB]

        if not grids_a or not grids_b:
            self.LogLine(u'Select at least one grid as A and one as B.')
            return

        vt_idx = self.CmbViewType.SelectedIndex
        if vt_idx < 0 or vt_idx >= len(self._view_types):
            self.LogLine(u'Select a section view type.')
            return
        vt_id = self._view_types[vt_idx].Id

        try:
            depth_mm = float(self.TxtDepthOffset.Text or u'3000')
        except Exception:
            depth_mm = 3000.0
        depth_ft = depth_mm * _uc10.MM_TO_FT

        prefix = self.TxtPrefix.Text or u'S'

        self.SetLoading(True, u'Generating sections...')
        created = 0
        errors  = 0
        try:
            with DB.Transaction(self.doc, u'NOSA — Bay Sections') as t:
                t.Start()
                for row_a in grids_a:
                    for row_b in grids_b:
                        if row_a._grid_id == row_b._grid_id:
                            continue
                        views = _logic.create_bay_sections(
                            self.doc,
                            row_a._grid_id, row_b._grid_id,
                            vt_id, depth_ft, depth_ft / 2.0, prefix)
                        created += len(views)
                t.Commit()
        except Exception as e:
            self.LogLine(u'Error: {}'.format(e))
            errors += 1
        finally:
            self.SetLoading(False)

        self.LogLine(u'Created {} section view(s). {} error(s).'.format(created, errors))

        cfg = self.LoadConfig()
        cfg.update({'prefix': prefix, 'depth_offset': depth_mm, 'dark_mode': self.dark_mode})
        self.SaveConfig(cfg)

    def SelectAllA_Click(self, sender, args):
        for row in self._grid_rows:
            row.SelA = True
        self.GridList.Items.Refresh()

    def Close_Click(self, sender, args):
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
