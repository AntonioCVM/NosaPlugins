# -*- coding: utf-8 -*-
import io
import os, sys, csv, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)
_logic = imp.load_source('connchk_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow


class IssueRow(object):
    def __init__(self, d):
        self.Severity = d['severity']
        self.Category = d['category']
        self.Level    = d['level']
        self.Name     = d['name']
        self.Check    = d['check']
        self.Id       = d['id']


class ConnectionCheckerWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'connection_checker')
        self.doc   = doc
        self._rows = ObservableCollection[IssueRow]()
        self.GridResults.ItemsSource = self._rows
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def _active(self):
        active = set()
        if self.ChkAnalytical.IsChecked  == True: active.add('analytical')
        if self.ChkUsage.IsChecked       == True: active.add('usage')
        if self.ChkAttachment.IsChecked  == True: active.add('attachment')
        if self.ChkJoins.IsChecked       == True: active.add('joins')
        return active

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking structural connections...')
        self._rows.Clear(); self.BtnExport.IsEnabled = False; self.BtnExport2.IsEnabled = False
        try:
            data = _logic.run_all_checks(self.doc, self._active())
        except Exception as e:
            self.SetLoading(False); forms.alert("Error: {}".format(e)); return
        self.TxtHigh.Text   = "{} High".format(data['high'])
        self.TxtMedium.Text = "{} Medium".format(data['medium'])
        self.TxtLow.Text    = "{} Low".format(data['low'])
        for r in data['issues']:
            self._rows.Add(IssueRow(r))
        self.SetLoading(False)
        self.BtnExport.IsEnabled = self.BtnExport2.IsEnabled = len(data['issues']) > 0
        if len(data['issues']) == 0:
            forms.alert("No connection issues found in the model.\n\nAll checked elements look good.", title="Connection Checker")

    def Grid_SelectionChanged(self, sender, args):
        has = self.GridResults.SelectedItem is not None
        self.BtnSelect.IsEnabled = has

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row: return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Severity','Category','Level','Name','Check'])
                for r in self._rows:
                    w.writerow([r.Severity, r.Category, r.Level, r.Name, r.Check])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
