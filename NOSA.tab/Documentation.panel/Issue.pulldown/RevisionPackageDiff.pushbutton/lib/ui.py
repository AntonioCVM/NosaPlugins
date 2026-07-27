# -*- coding: utf-8 -*-
import imp
import os
import sys

from System.Collections.ObjectModel import ObservableCollection

from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('revpkgdiff_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_CHANGE_COLORS = {
    u'New Sheet': u'#1A7F37',
    u'Revised':   u'#0550AE',
    u'Removed':   u'#CF222E',
    u'Unchanged': u'#6E7781',
}


class DiffRow(object):
    def __init__(self, r):
        self.SheetNumber = r.get('number', u'')
        self.SheetName   = r.get('name', u'')
        self.Change      = r.get('change', u'')
        self.OldRev      = r.get('old_rev', u'')
        self.NewRev      = r.get('new_rev', u'')
        self.NewDate     = r.get('new_date', u'')


class RevisionPackageDiffWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'revision_package_diff')
        self.doc    = doc
        self._rows  = ObservableCollection[object]()
        self._diffs = []

        self.DiffGrid.ItemsSource = self._rows

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._baseline     = cfg.get('baseline', {})
        self._baseline_ts  = cfg.get('baseline_ts', u'')
        self._refresh_baseline_label()

    def _refresh_baseline_label(self):
        if self._baseline:
            self.TxtBaselineInfo.Text = u'Baseline: {} — {} sheets'.format(
                self._baseline_ts or u'saved', len(self._baseline))
        else:
            self.TxtBaselineInfo.Text = u'No baseline saved. Click "Save Baseline" first.'

    # ── handlers ──────────────────────────────────────────────────────────────

    def SaveBaseline_Click(self, sender, args):
        self.SetLoading(True, u'Capturing revision state…')
        try:
            self._baseline = _logic.snapshot_revisions(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'Revision Package Diff')
            return
        import datetime
        self._baseline_ts = datetime.datetime.now().strftime(u'%Y-%m-%d %H:%M')
        self._save_cfg()
        self.SetLoading(False)
        self._refresh_baseline_label()
        self._rows.Clear()
        self._diffs = []
        self.TxtResult.Text = u'Baseline saved — {} sheets.'.format(len(self._baseline))

    def Compare_Click(self, sender, args):
        if not self._baseline:
            forms.alert(u'Save a baseline first.', title=u'Revision Package Diff')
            return
        self.SetLoading(True, u'Comparing revisions…')
        try:
            current     = _logic.snapshot_revisions(self.doc)
            self._diffs = _logic.diff_snapshots(self._baseline, current)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'Revision Package Diff')
            return
        self._rows.Clear()
        for r in self._diffs:
            self._rows.Add(DiffRow(r))
        self.SetLoading(False)

        changed = [r for r in self._diffs if r['change'] != u'Unchanged']
        self.TxtResult.Text = u'{} sheet{} changed since baseline ({} new, {} revised, {} removed).'.format(
            len(changed), u's' if len(changed) != 1 else u'',
            sum(1 for r in changed if r['change'] == u'New Sheet'),
            sum(1 for r in changed if r['change'] == u'Revised'),
            sum(1 for r in changed if r['change'] == u'Removed'),
        )
        self.BtnExport.IsEnabled = len(changed) > 0

    def ShowAll_Checked(self, sender, args):
        self._rows.Clear()
        for r in self._diffs:
            self._rows.Add(DiffRow(r))

    def ShowAll_Unchecked(self, sender, args):
        self._rows.Clear()
        for r in self._diffs:
            if r.get('change') != u'Unchanged':
                self._rows.Add(DiffRow(r))

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv', title=u'Save Transmittal List')
        if not path:
            return
        try:
            _logic.export_transmittal_csv(self._diffs, path)
            self.TxtResult.Text = u'Transmittal exported to {}'.format(os.path.basename(path))
        except Exception as e:
            forms.alert(u'Export failed:\n{}'.format(e), title=u'Revision Package Diff')

    def _save_cfg(self):
        self.SaveConfig({
            'dark_mode':   bool(self.ChkDarkMode.IsChecked),
            'baseline':    self._baseline,
            'baseline_ts': self._baseline_ts,
        })

    def Close_Click(self, sender, args):
        self._save_cfg()
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
