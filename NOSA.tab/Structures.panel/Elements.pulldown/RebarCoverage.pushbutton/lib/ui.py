# -*- coding: utf-8 -*-
import io
import os, sys, csv, imp
import System.Windows, System.Windows.Media
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)

_logic = imp.load_source('rebarcov_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
check_rebar_coverage     = _logic.check_rebar_coverage
get_available_categories = _logic.get_available_categories

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger
logger = Logger()


class MissingRow(object):
    def __init__(self, d):
        self.Category = d['category']
        self.Level    = d['level']
        self.Name     = d['name']
        self.Id       = d['id']


class SummaryRow(object):
    def __init__(self, d):
        self.Category    = d['category']
        self.WithRebar   = d['with_rebar']
        self.WithoutRebar= d['without_rebar']
        self.Coverage    = "{}%".format(d['coverage'])


class RebarCoverageWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_coverage')
        self.doc  = doc
        self._data = None
        self._missing = ObservableCollection[MissingRow]()
        self._summary = ObservableCollection[SummaryRow]()
        self.GridMissing.ItemsSource = self._missing
        self.GridSummary.ItemsSource = self._summary
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def _selected_cats(self):
        cats = []
        m = {'Structural Columns': self.ChkColumns,
             'Structural Framing': self.ChkFraming,
             'Structural Foundations': self.ChkFoundations,
             'Floors': self.ChkFloors, 'Walls': self.ChkWalls}
        return [c for c, cb in m.items() if cb.IsChecked == True] or None

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking rebar coverage...')
        self._missing.Clear(); self._summary.Clear()
        self.BtnExport.IsEnabled = False
        try:
            self._data = check_rebar_coverage(self.doc, self._selected_cats())
        except Exception as e:
            self.SetLoading(False); forms.alert('Error: {}'.format(e)); return

        pct = self._data['coverage_pct']
        self.CoverageBar.Value = pct
        self.TxtCoverage.Text  = "{}%".format(int(round(pct)))

        if pct >= 90:
            self.CoverageBar.Foreground = System.Windows.Media.Brushes.SeaGreen
            self.TxtCoverageLabel.Text = "Excellent — almost all elements have rebar."
        elif pct >= 70:
            self.CoverageBar.Foreground = System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromRgb(255,95,0))
            self.TxtCoverageLabel.Text = "Good — some elements are missing rebar."
        else:
            self.CoverageBar.Foreground = System.Windows.Media.Brushes.Crimson
            self.TxtCoverageLabel.Text = "Poor — many structural elements have no rebar."

        for s in self._data['summary']:
            self._summary.Add(SummaryRow(s))
        for r in self._data['without_rebar']:
            self._missing.Add(MissingRow(r))

        n = len(self._data['without_rebar'])
        self.TxtMissingLabel.Text = "{} elements without rebar".format(n)
        self.SetLoading(False)
        self.BtnExport.IsEnabled = True
        cfg = self.LoadConfig(); cfg['dark_mode'] = self.dark_mode; self.SaveConfig(cfg)

    def Grid_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridMissing.SelectedItem is not None

    def Select_Click(self, sender, args):
        rows = list(self.GridMissing.SelectedItems)
        if not rows: return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(r.Id)) for r in rows])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert('Could not select: {}'.format(e))

    def Export_Click(self, sender, args):
        if not self._data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Coverage', '{}%'.format(self._data['coverage_pct'])])
                w.writerow([])
                w.writerow(['Category','With rebar','Without rebar','Coverage %'])
                for r in self._summary:
                    w.writerow([r.Category, r.WithRebar, r.WithoutRebar, r.Coverage])
                w.writerow([])
                w.writerow(['Category','Level','Name','ID'])
                for r in self._missing:
                    w.writerow([r.Category, r.Level, r.Name, r.Id])
            forms.alert('Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert('Export failed: {}'.format(e))
