# -*- coding: utf-8 -*-
"""T8.14 — Standards Audit tab of the QA Hub (read-only)."""
import io
import os

from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow
from nosa_utils import standards_audit


class StandardsAuditWindow(NOSAWindow):

    def __init__(self, doc):
        NOSAWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'ui.xaml'), 'standards_audit')
        self.doc = doc
        self._findings = []
        self.TxtStatus.Text = u'Run the audit to list what departs from the NOSA standards.'

    def Run_Click(self, sender, args):
        self.SetLoading(True, u'Auditing the model…')
        try:
            self._findings = standards_audit.audit(self.doc, check_purge=self.ChkPurge.IsChecked == True)
        finally:
            self.SetLoading(False)
        rows = ObservableCollection[object]()
        for f in sorted(self._findings, key=lambda f: (f.Area, f.Item)):
            rows.Add(f)
        self.GridFindings.ItemsSource = rows
        areas = {}
        for f in self._findings:
            areas[f.Area] = areas.get(f.Area, 0) + 1
        self.TxtStatus.Text = u'{} finding(s): {}'.format(
            len(self._findings), u', '.join(u'{} {}'.format(n, a.lower()) for a, n in sorted(areas.items())))

    def Export_Click(self, sender, args):
        if not self._findings:
            self.TxtStatus.Text = u'Run the audit first.'
            return
        from System.Windows.Forms import SaveFileDialog, DialogResult
        dlg = SaveFileDialog()
        dlg.Filter = 'CSV files (*.csv)|*.csv'
        dlg.FileName = u'{} - standards audit.csv'.format(self.doc.Title or u'model')
        if dlg.ShowDialog() != DialogResult.OK:
            return

        def cell(v):
            v = u'{}'.format(v or u'')
            return u'"{}"'.format(v.replace(u'"', u'""')) if (u',' in v or u'"' in v) else v
        with io.open(dlg.FileName, 'w', encoding='utf-8-sig') as f:
            f.write(u'Area,Item,Issue,Unused\n')
            for x in self._findings:
                f.write(u','.join(cell(v) for v in (x.Area, x.Item, x.Issue, x.Unused)) + u'\n')
        self.TxtStatus.Text = u'Exported to {}'.format(dlg.FileName)
