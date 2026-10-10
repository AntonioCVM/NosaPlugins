# -*- coding: utf-8 -*-
"""T8.48 — Rebar QA tab of the QA Hub (also opened from RebarAutomate > Detailing & Tools). Read-only."""
import io
import os

from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow
from nosa_utils import rebar_qa


class RebarQAWindow(NOSAWindow):

    def __init__(self, doc):
        NOSAWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'ui.xaml'), 'rebar_qa')
        self.doc = doc
        self._findings = []
        self.TxtStatus.Text = u'Select hosts (or their bars) and run, or run on the whole model.'

    def _selected_hosts(self):
        from pyrevit import revit
        from Autodesk.Revit.DB.Structure import Rebar
        hosts = []
        for eid in revit.uidoc.Selection.GetElementIds():
            el = self.doc.GetElement(eid)
            if isinstance(el, Rebar):
                eid = el.GetHostId()
            if eid not in hosts:
                hosts.append(eid)
        return hosts

    def Run_Click(self, sender, args):
        hosts = self._selected_hosts() if self.ChkSelection.IsChecked == True else None
        if self.ChkSelection.IsChecked == True and not hosts:
            self.TxtStatus.Text = u'Nothing selected: select hosts or bars, or untick "Selection only".'
            return
        self.SetLoading(True, u'Checking the reinforcement…')
        try:
            self._findings = rebar_qa.audit(self.doc, hosts)
        finally:
            self.SetLoading(False)
        rows = ObservableCollection[object]()
        order = {rebar_qa.ERROR: 0, rebar_qa.WARNING: 1}
        for f in sorted(self._findings, key=lambda f: (f.Drawing, f.Host, order.get(f.Severity, 2), f.Check)):
            rows.Add(f)
        self.GridFindings.ItemsSource = rows
        errors = sum(1 for f in self._findings if f.Severity == rebar_qa.ERROR)
        self.TxtStatus.Text = u'{} finding(s), {} error(s). Double-click a row to show the element.'.format(
            len(self._findings), errors)

    def Show_Click(self, sender, args):
        row = self.GridFindings.SelectedItem
        if row is None or row.ElementId is None:
            return
        from pyrevit import revit
        from System.Collections.Generic import List
        from Autodesk.Revit import DB
        ids = List[DB.ElementId]()
        ids.Add(row.ElementId)
        try:
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            self.TxtStatus.Text = u'Could not show the element: {}'.format(e)

    def Export_Click(self, sender, args):
        if not self._findings:
            self.TxtStatus.Text = u'Run the check first.'
            return
        from System.Windows.Forms import SaveFileDialog, DialogResult
        dlg = SaveFileDialog()
        dlg.Filter = 'CSV files (*.csv)|*.csv'
        dlg.FileName = u'{} - rebar QA.csv'.format(self.doc.Title or u'model')
        if dlg.ShowDialog() != DialogResult.OK:
            return

        def cell(v):
            v = u'{}'.format(v or u'')
            return u'"{}"'.format(v.replace(u'"', u'""')) if (u',' in v or u'"' in v) else v
        with io.open(dlg.FileName, 'w', encoding='utf-8-sig') as f:
            f.write(u'Drawing,Host,Mark,Check,Severity,Issue\n')
            for x in self._findings:
                f.write(u','.join(cell(v) for v in (x.Drawing, x.Host, x.Mark, x.Check, x.Severity, x.Issue)) + u'\n')
        self.TxtStatus.Text = u'Exported to {}'.format(dlg.FileName)
