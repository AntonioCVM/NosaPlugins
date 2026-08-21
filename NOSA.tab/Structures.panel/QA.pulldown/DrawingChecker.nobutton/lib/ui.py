# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys
from pyrevit import forms, revit
import System.Windows

_lib_ext = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         '..', '..', '..', '..', '..', 'lib'))
if _lib_ext not in sys.path:
    sys.path.insert(0, _lib_ext)

_logic = imp.load_source('drawingchecker_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow


_STATUS_EMOJI = {'green': u'✅', 'amber': u'⚠', 'red': u'❌'}
_STATUS_COLOR = {'green': '#22c55e', 'amber': '#f59e0b', 'red': '#ef4444'}


class DrawingCheckerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'drawing_checker')
        self.doc = doc
        self._results = []
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def OnWindowLoaded(self, sender, args):
        self._run_checks()

    def _run_checks(self):
        self.SetLoading(True, u'Running checks…')
        try:
            self._results = _logic.run_all_checks(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._render_results()

    def _render_results(self):
        import System.Windows.Controls as WC
        import System.Windows.Media as Media
        import System.Windows

        panel = self.ResultsPanel
        panel.Children.Clear()

        overall = 'green'
        for r in self._results:
            if r.status == 'red':
                overall = 'red'
                break
            if r.status == 'amber' and overall == 'green':
                overall = 'amber'

        # Overall banner
        banner = WC.Border()
        banner.CornerRadius = System.Windows.CornerRadius(6)
        banner.Padding = System.Windows.Thickness(12, 8, 12, 8)
        banner.Margin  = System.Windows.Thickness(0, 0, 0, 12)
        banner.Background = Media.SolidColorBrush(
            Media.ColorConverter.ConvertFromString(_STATUS_COLOR[overall]))
        lbl = WC.TextBlock()
        lbl.Text = u'{} Overall: {}'.format(
            _STATUS_EMOJI[overall],
            {'green': 'READY TO ISSUE', 'amber': 'REVIEW RECOMMENDED', 'red': 'ISSUES FOUND'}[overall]
        )
        lbl.FontWeight = System.Windows.FontWeights.Bold
        lbl.FontSize = 14
        lbl.Foreground = Media.Brushes.White
        banner.Child = lbl
        panel.Children.Add(banner)

        for r in self._results:
            card = WC.Border()
            card.BorderThickness = System.Windows.Thickness(0, 0, 0, 0)
            card.CornerRadius = System.Windows.CornerRadius(6)
            card.Padding = System.Windows.Thickness(12, 10, 12, 10)
            card.Margin  = System.Windows.Thickness(0, 0, 0, 8)
            card.Background = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(
                    {'green': '#f0fdf4', 'amber': '#fffbeb', 'red': '#fef2f2'}[r.status]))
            left_border = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(_STATUS_COLOR[r.status]))

            sp = WC.StackPanel()

            # Header row
            hdr = WC.StackPanel()
            hdr.Orientation = System.Windows.Controls.Orientation.Horizontal
            ico = WC.TextBlock()
            ico.Text = _STATUS_EMOJI[r.status]
            ico.FontSize = 14
            ico.Margin = System.Windows.Thickness(0, 0, 8, 0)
            hdr.Children.Add(ico)
            title_tb = WC.TextBlock()
            title_tb.Text = r.check_name
            title_tb.FontWeight = System.Windows.FontWeights.SemiBold
            title_tb.FontSize = 12
            hdr.Children.Add(title_tb)
            count_tb = WC.TextBlock()
            count_tb.Text = u'  ({} issue{})'.format(r.count, '' if r.count == 1 else 's')
            count_tb.FontSize = 11
            count_tb.Opacity = 0.6
            hdr.Children.Add(count_tb)
            sp.Children.Add(hdr)

            # Detail items
            if r.detail:
                for d in r.detail[:8]:
                    dtb = WC.TextBlock()
                    dtb.Text = u'  · ' + d
                    dtb.FontSize = 10
                    dtb.Opacity = 0.7
                    dtb.Margin = System.Windows.Thickness(0, 2, 0, 0)
                    sp.Children.Add(dtb)
                if len(r.detail) > 8:
                    more = WC.TextBlock()
                    more.Text = u'  … and {} more'.format(len(r.detail) - 8)
                    more.FontSize = 10
                    more.Opacity = 0.5
                    sp.Children.Add(more)

            card.Child = sp
            panel.Children.Add(card)

    def Refresh_Click(self, sender, args):
        self._run_checks()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)


