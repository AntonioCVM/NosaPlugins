# -*- coding: utf-8 -*-
import io
import os, sys, csv, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)

_logic = imp.load_source('tguard_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
run_all_checks = _logic.run_all_checks

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger
logger = Logger()


class IssueRow(object):
    def __init__(self, d):
        self.Key      = d.get('key', '')
        self.Label    = d.get('label', '')
        self.Severity = d.get('severity', '')
        self.Sheet    = d.get('sheet', '—')
        self.ViewName = d.get('view', '')
        self.ViewType = d.get('type', '')
        self.Detail   = d.get('detail', '')
        self.Id       = d.get('id')


class TemplateGuardWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'template_guard')
        self.doc      = doc
        self._all_rows = []
        self._rows    = ObservableCollection[IssueRow]()
        self._data    = None
        self._sheet_view_ids = self._collect_sheet_view_ids()
        self.GridResults.ItemsSource = self._rows
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def _collect_sheet_view_ids(self):
        ids = set()
        try:
            from pyrevit import DB as _DB
            for s in _DB.FilteredElementCollector(self.doc).OfClass(_DB.ViewSheet).ToElements():
                for vpid in s.GetAllViewports():
                    try:
                        vp = self.doc.GetElement(vpid)
                        vid = vp.ViewId.IntegerValue if hasattr(vp.ViewId,'IntegerValue') else int(str(vp.ViewId))
                        ids.add(vid)
                    except Exception:
                        pass
        except Exception:
            pass
        return ids

    def _active_checks(self):
        m = {'no_template': self.ChkNoTemplate, 'wrong_scale': self.ChkWrongScale,
             'sheet_naming': self.ChkSheetNaming, 'manual_overrides': self.ChkOverrides,
             'crop_missing': self.ChkCrop, 'wrong_detail_level': self.ChkDetailLevel}
        return {k for k, cb in m.items() if cb.IsChecked == True}

    def _active_severities(self):
        s = set()
        if self.ChkSevHigh.IsChecked   == True: s.add('High')
        if self.ChkSevMedium.IsChecked == True: s.add('Medium')
        if self.ChkSevLow.IsChecked    == True: s.add('Low')
        return s

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking views & sheets...')
        self._rows.Clear(); self._all_rows = []
        self.BtnExport.IsEnabled = False
        try:
            self._data = run_all_checks(self.doc, self._active_checks())
        except Exception as e:
            self.SetLoading(False)
            forms.alert('Error: {}'.format(e)); return
        self._all_rows = [IssueRow(d) for d in self._data['issues']]
        self._apply_filter()
        self.SetLoading(False)
        self.BtnExport.IsEnabled = True
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode; self.SaveConfig(cfg)

    def _apply_filter(self):
        sevs = self._active_severities()
        search = self.TxtSearch.Text.lower() if hasattr(self, 'TxtSearch') else ''
        only_sheets = False
        try:
            only_sheets = self.ChkOnlyOnSheets.IsChecked == True
        except Exception:
            pass
        self._rows.Clear()
        high = med = low = 0
        for r in self._all_rows:
            if r.Severity not in sevs: continue
            if search and search not in r.ViewName.lower() and search not in r.Sheet.lower() and search not in r.Detail.lower(): continue
            if only_sheets and r.Id is not None:
                vid = r.Id
                if vid not in self._sheet_view_ids:
                    continue
            self._rows.Add(r)
            if r.Severity == 'High':   high += 1
            elif r.Severity == 'Medium': med += 1
            else: low += 1
        self.TxtHigh.Text   = '{} High'.format(high)
        self.TxtMedium.Text = '{} Medium'.format(med)
        self.TxtLow.Text    = '{} Low'.format(low)
        total = self._data['total'] if self._data else 0
        self.TxtTotal.Text  = '{} total issues'.format(total)

    def Search_Changed(self, sender, args): self._apply_filter()

    def Grid_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridResults.SelectedItem is not None

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row or row.Id is None: return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert('Could not select: {}'.format(e))

    def EditRules_Click(self, sender, args):
        rules_path = os.path.join(os.path.dirname(__file__), 'rules.json')
        try:
            import subprocess
            subprocess.Popen(['notepad.exe', rules_path])
        except Exception as e:
            forms.alert('Could not open rules.json:\n{}'.format(rules_path))

    def Export_Click(self, sender, args):
        if not self._data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Severity','Rule','Sheet','View','Type','Detail'])
                for r in self._rows:
                    w.writerow([r.Severity, r.Label, r.Sheet, r.ViewName, r.ViewType, r.Detail])
            forms.alert('Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert('Export failed: {}'.format(e))
