# -*- coding: utf-8 -*-
import os
import sys

import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = None


def _get_logic():
    global _logic
    if _logic is None:
        from nosa_utils.bootstrap import load_module
        _logic = load_module(
            'drawingprotocol_logic',
            os.path.join(os.path.dirname(__file__), 'logic.py'))
    return _logic


class ResultRow(object):
    def __init__(self, result):
        self.sheet_number = result.sheet_number
        self.sheet_name = result.sheet_name
        self.status = result.status.upper()
        self.issue_count = len(result.issues)
        self.issues_text = u'; '.join(result.issues)


class DrawingProtocolCheckerWindow(NOSAWindow):

    def __init__(self, doc):
        try:
            xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
            NOSAWindow.__init__(self, xaml, 'drawing_protocol_checker')
            self.doc = doc
            self._rows = ObservableCollection[ResultRow]()
            self.GridResults.ItemsSource = self._rows
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
            self._run_checks()
        except Exception as e:
            self._init_ok = False
            forms.alert(u'Drawing Protocol Checker init error:\n{}'.format(e), title=u'Error')
            raise

    def _run_checks(self):
        self.SetLoading(True, u'Checking sheets…')
        try:
            results = _get_logic().run_protocol_checks(self.doc)
            summary = _get_logic().summarise(results)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks:\n{}'.format(e))
            return
        self.SetLoading(False)

        self._rows.Clear()
        for r in results:
            if r.status != 'green':
                self._rows.Add(ResultRow(r))

        self.TxtSummary.Text = (
            u'{} sheets — {} compliant, {} warnings, {} errors'.format(
                summary['total'], summary['green'], summary['amber'], summary['red']))

        if summary['red'] == 0 and summary['amber'] == 0:
            self.TxtBanner.Text = u'All sheets comply with NOSA v2.2.'
            self.TxtBanner.Foreground = System.Windows.Media.Brushes.ForestGreen
        elif summary['red'] > 0:
            self.TxtBanner.Text = u'Protocol errors found — review before issue.'
            self.TxtBanner.Foreground = System.Windows.Media.Brushes.Firebrick
        else:
            self.TxtBanner.Text = u'Warnings only — review suggested fields.'
            self.TxtBanner.Foreground = System.Windows.Media.Brushes.DarkOrange

    def Refresh_Click(self, sender, args):
        self._run_checks()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
