# -*- coding: utf-8 -*-
import os, sys, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
_logic = None


def _get_logic():
    global _logic
    if _logic is None:
        _logic = imp.load_source(
            'levelnav_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
    return _logic


class LevelRow(object):
    def __init__(self, d):
        self.Name       = d['name']
        self.Elevation  = u'{:.3f} m'.format(d['elevation_m'])
        self.ViewName   = d['view_name'] or u'— no view —'
        self.Discipline = d['view_disc']
        self.HasView    = d['view_id'] is not None
        self.StatusIcon = u'✓' if self.HasView else u'–'
        self._view_id   = d['view_id']


class LevelNavigatorWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        try:
            xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
            NOSAWindow.__init__(self, xaml, 'level_navigator')
            self.doc   = doc
            self.uidoc = uidoc
            self._rows = ObservableCollection[LevelRow]()
            self.GridLevels.ItemsSource = self._rows
            cfg = self.LoadConfig()
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
            self._load()
        except Exception as e:
            self._init_ok = False
            from pyrevit import forms
            forms.alert(u'Level Navigator init error:\n{}'.format(e), title=u'Error')
            raise

    # ------------------------------------------------------------------

    def _load(self):
        self._rows.Clear()
        data = _get_logic().get_levels_with_views(self.doc)
        for d in data:
            self._rows.Add(LevelRow(d))
        total    = len(data)
        no_view  = sum(1 for d in data if d['view_id'] is None)
        self.TxtTotal.Text   = u'{} levels'.format(total)
        self.TxtNoView.Text  = u'{} without view'.format(no_view)
        self.BtnActivate.IsEnabled = False

    def Refresh_Click(self, sender, args):
        self._load()

    def Grid_SelectionChanged(self, sender, args):
        row = self.GridLevels.SelectedItem
        self.BtnActivate.IsEnabled = (row is not None and row.HasView)

    def Grid_MouseDoubleClick(self, sender, args):
        self._activate_selected()

    def Activate_Click(self, sender, args):
        self._activate_selected()

    def _activate_selected(self):
        from pyrevit import forms
        row = self.GridLevels.SelectedItem
        if row is None or not row.HasView:
            return
        try:
            _get_logic().activate_view(self.uidoc, row._view_id)
            cfg = self.LoadConfig()
            cfg['dark_mode'] = self.dark_mode
            self.SaveConfig(cfg)
            self.Close()
        except Exception as e:
            forms.alert(u'Could not activate view: {}'.format(e))
