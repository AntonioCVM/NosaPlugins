# -*- coding: utf-8 -*-
"""
Drawing check report (T8.12): NOSA naming protocol and sheet content findings, shown before an
export (or on demand). Choice: export everything, only the sheets without errors, or cancel.
"""
import os

import System
from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow
from nosa_utils import protocol_rules

ALL = u'all'
COMPLIANT = u'compliant'


class ProtocolReportDialog(NOSAWindow):
    """findings: [nosa_utils.sheet_checks.Finding]; sheet_labels: labels of the checked sheets."""

    def __init__(self, findings, sheet_labels, for_export=True):
        NOSAWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'protocol_report_dialog.xaml'),
                            'sheetexporthub_protocol_report')
        self.choice = None
        order = {protocol_rules.ERROR: 0, protocol_rules.WARNING: 1}
        rows = ObservableCollection[object]()
        for f in sorted(findings, key=lambda f: (order.get(f.Severity, 2), f.Sheet)):
            rows.Add(f)
        self.GridFindings.ItemsSource = rows
        failing = set(f.Sheet for f in findings if f.Severity == protocol_rules.ERROR)
        self.compliant_labels = [s for s in sheet_labels if s not in failing]
        errors = sum(1 for f in findings if f.Severity == protocol_rules.ERROR)
        warnings = len(findings) - errors
        self.TxtTitle.Text = u'{} sheet(s) checked — {} with errors'.format(len(sheet_labels), len(failing))
        self.TxtSubtitle.Text = (u'{} error(s), {} warning(s). Errors break the NOSA File Naming Protocol V2.2; '
                                 u'warnings are worth a look (codes missing from the protocol are fine when '
                                 u'recorded in the project BEP).'.format(errors, warnings))
        self.BtnExportCompliant.Content = u'Export compliant only ({})'.format(len(self.compliant_labels))
        self.BtnExportCompliant.IsEnabled = bool(self.compliant_labels)
        if not for_export:
            for btn in (self.BtnExportAll, self.BtnExportCompliant):
                btn.Visibility = System.Windows.Visibility.Collapsed
            self.BtnCancel.Content = u'Close'

    def ExportAll_Click(self, sender, args):
        self.choice = ALL
        self.Close()

    def ExportCompliant_Click(self, sender, args):
        self.choice = COMPLIANT
        self.Close()

    def Cancel_Click(self, sender, args):
        self.choice = None
        self.Close()
