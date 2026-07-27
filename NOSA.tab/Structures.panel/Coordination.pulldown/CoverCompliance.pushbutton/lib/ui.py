# -*- coding: utf-8 -*-
import imp
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('rebarcoverage_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


class _RebarRow(object):
    def __init__(self, rec):
        self.Host     = rec['host']
        self.Category = rec['category']
        self.CoverMm  = u'{:.1f}'.format(rec['cover_mm'])
        self.MinMm    = u'{:.0f}'.format(rec['min_mm'])
        self.Status   = rec['status']
        self._rec     = rec


class RebarCoverageWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_coverage')
        self.doc = doc
        self._results = []
        self._show_fail_only = False

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        for cls in _logic.ec2_exposure_classes():
            self.CboExposure.Items.Add(cls)
        last_exposure = cfg.get('last_exposure', u'XC3 (moderate humidity)')
        for i in range(self.CboExposure.Items.Count):
            if self.CboExposure.Items[i] == last_exposure:
                self.CboExposure.SelectedIndex = i
                break
        else:
            self.CboExposure.SelectedIndex = 0

        min_cover = _logic.min_cover_for_class(self.CboExposure.SelectedItem or u'')
        self.TxtMinCover.Text = str(int(min_cover))

        self._reset_summary()
        self.TxtStatus.Text = u'Click "Run Check" to analyse rebar coverage.'

    def _reset_summary(self):
        self.TxtTotal.Text = u'—'
        self.TxtOk.Text    = u'—'
        self.TxtFail.Text  = u'—'

    def _update_summary(self):
        total, ok, fail = _logic.summarise(self._results)
        self.TxtTotal.Text = str(total)
        self.TxtOk.Text    = str(ok)
        self.TxtFail.Text  = str(fail)

    def _refresh_grid(self):
        data = self._results
        if self._show_fail_only:
            data = [r for r in data if r['status'] == u'FAIL']
        self.GridResults.ItemsSource = [_RebarRow(r) for r in data]

    def Exposure_Changed(self, sender, args):
        cls = self.CboExposure.SelectedItem
        if cls:
            self.TxtMinCover.Text = str(int(_logic.min_cover_for_class(cls)))

    def MinCover_Changed(self, sender, args):
        pass

    def RunCheck_Click(self, sender, args):
        try:
            min_cover = float(self.TxtMinCover.Text.strip())
        except (ValueError, Exception):
            self.TxtStatus.Text = u'Enter a valid minimum cover in mm.'
            return

        self.SetLoading(True, u'Checking rebar coverage…')
        try:
            self._results = _logic.analyse(self.doc, min_cover)
        finally:
            self.SetLoading(False)

        self._show_fail_only = False
        self._update_summary()
        self._refresh_grid()

        total, ok, fail = _logic.summarise(self._results)
        self.TxtStatus.Text = u'Checked {} bars. {} OK, {} below minimum ({} mm).'.format(
            total, ok, fail, int(min_cover))

        cls = self.CboExposure.SelectedItem or u''
        cfg = self.LoadConfig()
        cfg['last_exposure'] = cls
        self.SaveConfig(cfg)

    def FilterFail_Click(self, sender, args):
        self._show_fail_only = not self._show_fail_only
        self._refresh_grid()
        fail = sum(1 for r in self._results if r['status'] == u'FAIL')
        if self._show_fail_only:
            self.TxtStatus.Text = u'Showing {} failing bars only.'.format(fail)
        else:
            self.TxtStatus.Text = u'Showing all {} bars.'.format(len(self._results))

    def ExportCsv_Click(self, sender, args):
        if not self._results:
            self.TxtStatus.Text = u'Run the check first before exporting.'
            return
        try:
            from pyrevit import forms as _forms
            import csv as _csv
            path = _forms.save_file(
                file_ext=u'csv',
                default_name=u'rebar_coverage.csv',
                title=u'Export rebar coverage report')
            if not path:
                return
            with open(path, 'wb') as f:
                w = _csv.writer(f)
                w.writerow(['Host', 'Category', 'Cover (mm)', 'Min (mm)', 'Status'])
                for r in self._results:
                    w.writerow([r['host'], r['category'],
                                '{:.1f}'.format(r['cover_mm']),
                                '{:.0f}'.format(r['min_mm']),
                                r['status']])
            self.TxtStatus.Text = u'Exported {} records to {}'.format(
                len(self._results), os.path.basename(path))
        except Exception as ex:
            self.TxtStatus.Text = u'Export failed: {}'.format(ex)

    def SelectInModel_Click(self, sender, args):
        rows = list(self.GridResults.SelectedItems or [])
        if rows:
            recs = [r._rec for r in rows]
        else:
            recs = [r for r in self._results if r['status'] == u'FAIL']
        if not recs:
            self.TxtStatus.Text = u'Nothing to select — run the check first.'
            return
        try:
            from pyrevit import revit
            from System.Collections.Generic import List as _List
            from Autodesk.Revit import DB as _DB
            ids = _List[_DB.ElementId]()
            for rec in recs:
                try:
                    ids.Add(rec['element'].Id)
                except Exception:
                    pass
            revit.uidoc.Selection.SetElementIds(ids)
            self.TxtStatus.Text = u'Selected {} bar(s) in the model{}.'.format(
                ids.Count, u'' if rows else u' (all failing)')
        except Exception as ex:
            self.TxtStatus.Text = u'Selection failed: {}'.format(ex)

    def Close_Click(self, sender, args):
        self.Close()
