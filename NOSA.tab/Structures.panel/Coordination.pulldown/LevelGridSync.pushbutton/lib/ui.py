# -*- coding: utf-8 -*-
import imp
import os, sys
from pyrevit import forms, revit
import System.Windows
import System.Windows.Controls as WC
import System.Windows.Media as Media

_lib_ext = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         '..', '..', '..', '..', '..', 'lib'))
if _lib_ext not in sys.path:
    sys.path.insert(0, _lib_ext)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('levelgridsync_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class LinkItem(object):
    def __init__(self, link, title):
        self.Link  = link
        self.Title = title
    def __str__(self):
        return self.Title


class LevelGridSyncWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'level_grid_sync')
        self.doc    = doc
        self._links = []
        self._report = None
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
        self._load_links()

    def OnWindowLoaded(self, sender, args):
        self._load_links()

    def _load_links(self):
        links = _logic.get_linked_models(self.doc)
        self._links = links
        items = [LinkItem(lnk, title) for lnk, title in links]
        self.CboLinks.ItemsSource   = items
        self.CboLinks.DisplayMemberPath = 'Title'
        if items:
            self.CboLinks.SelectedIndex = 0
        else:
            self.TxtStatus.Text = u'No linked Revit models found in the project.'

    def Run_Click(self, sender, args):
        sel = self.CboLinks.SelectedItem
        if sel is None:
            forms.alert(u'Select a linked model first.')
            return

        try:
            tol = float(self.TxtTolerance.Text or '1')
        except Exception:
            tol = 1.0

        self.SetLoading(True, u'Comparing…')
        link_doc = sel.Link.GetLinkDocument()
        if link_doc is None:
            self.SetLoading(False)
            forms.alert(u'Linked model is not loaded. Load it first.')
            return

        try:
            self._report = _logic.compare(self.doc, link_doc, tol)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error during comparison:\n{}'.format(e))
            return

        self.SetLoading(False)
        self._render_report()

    def _render_report(self):
        r = self._report
        panel = self.ResultsPanel
        panel.Children.Clear()

        if not r.has_issues:
            ok = WC.TextBlock()
            ok.Text = u'✅  No discrepancies found against "{}".'.format(r.link_title)
            ok.FontSize = 13
            ok.FontWeight = System.Windows.FontWeights.SemiBold
            ok.Foreground = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString('#22c55e'))
            ok.Margin = System.Windows.Thickness(0, 8, 0, 0)
            panel.Children.Add(ok)
            return

        self.TxtStatus.Text = u'{} issue(s) found vs. "{}"'.format(r.issue_count, r.link_title)

        sections = [
            (u'⚠ Level elevation mismatches', [
                u'{} — host {:.1f} mm / link {:.1f} mm (Δ {:.1f} mm)'.format(n, h, l, d)
                for n, h, l, d in r.level_elevation_mismatches
            ]),
            (u'Levels only in HOST model', r.levels_only_in_host),
            (u'Levels only in LINKED model', r.levels_only_in_link),
            (u'Grids only in HOST model', r.grids_only_in_host),
            (u'Grids only in LINKED model', r.grids_only_in_link),
        ]

        for title, items in sections:
            if not items:
                continue
            hdr = WC.TextBlock()
            hdr.Text = u'{} ({})'.format(title, len(items))
            hdr.FontWeight = System.Windows.FontWeights.SemiBold
            hdr.FontSize = 12
            hdr.Margin = System.Windows.Thickness(0, 10, 0, 4)
            panel.Children.Add(hdr)
            for it in items:
                tb = WC.TextBlock()
                tb.Text = u'  · ' + it
                tb.FontSize = 11
                tb.Opacity = 0.75
                tb.Margin = System.Windows.Thickness(0, 1, 0, 1)
                panel.Children.Add(tb)

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
