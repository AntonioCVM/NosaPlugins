# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys, io, csv
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from pyrevit import forms, revit
from System import Int64

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('analhc_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class _DictRow(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class AnalyticalHealthWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'analytical_health')
        self.doc    = doc
        self._rows  = []
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility  = Vis.Visible
        self.TxtStatus.Text      = u'Analysing model…'
        self.BtnRun.IsEnabled    = False
        self.BtnExport.IsEnabled = False
        self.BtnSelect.IsEnabled = False

        try:
            results = _logic.run_all(self.doc)
        except Exception as e:
            self.ProgBar.Visibility = Vis.Collapsed
            self.TxtStatus.Text     = u''
            self.BtnRun.IsEnabled   = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.ProgBar.Visibility = Vis.Collapsed
        self.TxtStatus.Text     = u''
        self.BtnRun.IsEnabled   = True

        self._rows = results['all']
        src = ObservableCollection[object]()
        for r in self._rows:
            src.Add(_DictRow(r))
        self.GridResults.ItemsSource = src

        self.TxtErrors.Text   = str(results['errors'])
        self.TxtWarnings.Text = str(results['warnings_count'])
        self.TxtTotal.Text    = str(results['total'])

        self.TxtSummary.Text = (
            u'{} issue(s): {} error(s), {} warning(s).'.format(
                results['total'], results['errors'], results['warnings_count']))

        if self._rows:
            self.BtnExport.IsEnabled = True

    def GridResults_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridResults.SelectedItem is not None

    def Select_Click(self, sender, args):
        selected = list(self.GridResults.SelectedItems)
        if not selected:
            return
        try:
            ids = List[DB.ElementId]([
                DB.ElementId(Int64(int(r.id))) for r in selected
                if r.id and str(r.id).lstrip('-').isdigit()
            ])
            if ids:
                revit.uidoc.Selection.SetElementIds(ids)
                self.TxtSummary.Text = u'{} element(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def Export_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            keys = ['severity', 'etype', 'mark', 'level', 'id', 'issue']
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow([u'Severity', u'Type', u'Mark', u'Level', u'ID', u'Issue'])
                for r in self._rows:
                    w.writerow([r.get(k, '') for k in keys])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)


