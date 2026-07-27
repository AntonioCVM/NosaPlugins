# -*- coding: utf-8 -*-
import imp
import os
import sys

import System.Windows
from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_logic = None


def _get_logic():
    global _logic
    if _logic is None:
        _logic = imp.load_source(
            'ifcexportqa_logic',
            os.path.join(os.path.dirname(__file__), 'logic.py'))
    return _logic


from nosa_utils.base_window import NOSAWindow

_STATUS_COLOUR = {'green': '#22c55e', 'amber': '#f59e0b', 'red': '#ef4444'}


class IFCStructuralExportQAWindow(NOSAWindow):

    def __init__(self, doc):
        try:
            xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
            NOSAWindow.__init__(self, xaml, 'ifc_structural_export_qa')
            self.doc = doc
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
            self._run_checks()
        except Exception as e:
            self._init_ok = False
            forms.alert(u'IFC Structural Export QA init error:\n{}'.format(e), title=u'Error')
            raise

    def _run_checks(self):
        self.SetLoading(True, u'Running IFC QA checks…')
        try:
            results = _get_logic().run_all_checks(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._render(results)

    def _render(self, results):
        import System.Windows.Controls as WC
        import System.Windows.Media as Media

        panel = self.ResultsPanel
        panel.Children.Clear()

        for r in results:
            card = WC.Border()
            card.CornerRadius = System.Windows.CornerRadius(6)
            card.Padding = System.Windows.Thickness(12, 10, 12, 10)
            card.Margin = System.Windows.Thickness(0, 0, 0, 8)
            card.Background = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(
                    {'green': '#f0fdf4', 'amber': '#fffbeb', 'red': '#fef2f2'}[r.status]))

            sp = WC.StackPanel()
            hdr = WC.TextBlock()
            hdr.Text = u'{} — {} issue(s)'.format(r.check_name, r.count)
            hdr.FontWeight = System.Windows.FontWeights.SemiBold
            hdr.Foreground = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(_STATUS_COLOUR[r.status]))
            sp.Children.Add(hdr)
            for line in r.detail[:8]:
                tb = WC.TextBlock()
                tb.Text = u'  · ' + line
                tb.FontSize = 10
                tb.TextWrapping = System.Windows.TextWrapping.Wrap
                sp.Children.Add(tb)
            card.Child = sp
            panel.Children.Add(card)

    def Refresh_Click(self, sender, args):
        self._run_checks()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
