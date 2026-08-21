# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys
import System.Windows
from System import Int64
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from pyrevit import forms, revit
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('pilesurvey_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_ALL = u'— All levels —'


class _Row(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class PileSurveyWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'pile_survey')
        self.doc     = doc
        self._rows   = []
        self._lv_map = {}

        self.CboLevel.Items.Add(_ALL)
        for name, lvid in _logic.get_levels(doc):
            self.CboLevel.Items.Add(name)
            self._lv_map[name] = lvid
        self.CboLevel.SelectedIndex = 0

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def Generate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility    = Vis.Visible
        self.BtnGenerate.IsEnabled = False

        lv_sel = self.CboLevel.SelectedItem

        if self.RbMark.IsChecked: sort_by = 'mark'
        elif self.RbX.IsChecked:  sort_by = 'x'
        else:                     sort_by = 'y'

        try:
            dec = int(self.CboDecimals.SelectedItem.Content)
        except Exception:
            dec = 1

        opts = {
            'filter_level_id': self._lv_map.get(lv_sel) if lv_sel and lv_sel != _ALL else None,
            'sort_by':         sort_by,
            'coord_decimals':  dec,
            'only_flagged':    bool(self.RbFlagged.IsChecked),
        }

        try:
            rows = _logic.collect_piles(self.doc, opts)
        except Exception as e:
            self.ProgBar.Visibility    = Vis.Collapsed
            self.BtnGenerate.IsEnabled = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.ProgBar.Visibility    = Vis.Collapsed
        self.BtnGenerate.IsEnabled = True
        self._rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_Row(r))
        self.GridPiles.ItemsSource = src

        self.TxtStatus.Text = u'{} pile(s) found.'.format(len(rows))
        has = len(rows) > 0
        self.BtnXlsx.IsEnabled   = has
        self.BtnCsv.IsEnabled    = has
        self.BtnSelect.IsEnabled = has

    def Grid_SelectionChanged(self, sender, args):
        selected = list(self.GridPiles.SelectedItems)
        if not selected:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r.id))) for r in selected])
            revit.uidoc.Selection.SetElementIds(ids)
        except Exception:
            pass

    def Select_Click(self, sender, args):
        if not self._rows:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r['id']))) for r in self._rows])
            revit.uidoc.Selection.SetElementIds(ids)
            self.TxtStatus.Text = u'{} pile(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def ExportXlsx_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            name = ''
            try:
                name = self.doc.ProjectInformation.Name or ''
            except Exception:
                pass
            _logic.export_xlsx(self._rows, path, name)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use CSV.')
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))

    def ExportCsv_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv(self._rows, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
