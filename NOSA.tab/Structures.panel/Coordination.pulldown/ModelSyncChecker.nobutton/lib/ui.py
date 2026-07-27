# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from System.Windows.Media import SolidColorBrush, Color
from pyrevit import forms, revit
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('syncheck_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_STATUS_COLOR = {
    'OK':      '#4CAF50',
    'MISSING': '#F44336',
    'SECTION': '#FF9800',
    'LENGTH':  '#FF9800',
    'LEVEL':   '#2196F3',
    'MULTI':   '#9C27B0',
}


class _Row(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)
        self.status_color = _STATUS_COLOR.get(d.get('status', ''), '#888888')


class ModelSyncWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'model_sync')
        self.doc        = doc
        self._results   = []
        self._csv_path  = None
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def Browse_Click(self, sender, args):
        path = forms.pick_file(file_ext='csv')
        if path:
            self._csv_path = path
            self.TxtCsvPath.Text = path
            self.BtnRun.IsEnabled = True

    def Run_Click(self, sender, args):
        if not self._csv_path:
            return
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility = Vis.Visible
        self.BtnRun.IsEnabled   = False

        try:
            calc_rows    = _logic.parse_calc_csv(self._csv_path)
            revit_index  = _logic.build_revit_index(self.doc)
            results      = _logic.compare(calc_rows, revit_index)
        except Exception as e:
            self.ProgBar.Visibility = Vis.Collapsed
            self.BtnRun.IsEnabled   = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.ProgBar.Visibility = Vis.Collapsed
        self.BtnRun.IsEnabled   = True
        self._results = results

        src = ObservableCollection[object]()
        for r in results:
            src.Add(_Row(r))
        self.GridSync.ItemsSource = src

        total   = len(results)
        ok      = sum(1 for r in results if r['status'] == 'OK')
        missing = sum(1 for r in results if r['status'] == 'MISSING')
        issues  = total - ok - missing

        self.TxtSummaryOK.Text      = str(ok)
        self.TxtSummaryMissing.Text = str(missing)
        self.TxtSummaryIssues.Text  = str(issues)

        self.TxtStatus.Text = (
            u'{} elements compared — {} OK, {} missing, {} discrepancies.'.format(
                total, ok, missing, issues))
        self.BtnExport.IsEnabled  = bool(results)
        self.BtnSelect.IsEnabled  = any(
            r['status'] != 'MISSING' for r in results)

    def Select_Click(self, sender, args):
        try:
            from System import Int64
            ids = List[DB.ElementId]([
                DB.ElementId(Int64(int(r['revit_id'])))
                for r in self._results
                if str(r.get('revit_id', '—')) != '—'
            ])
            revit.uidoc.Selection.SetElementIds(ids)
            self.TxtStatus.Text = u'{} element(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def Export_Click(self, sender, args):
        if not self._results:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv(self._results, path)
            forms.alert(u'Report exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
