# -*- coding: utf-8 -*-
import imp
import os, sys
import System.Windows

from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('gadim_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class GAAutoDimWindow(NOSAWindow):

    def __init__(self, doc, view):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'ga_auto_dim')
        self.doc  = doc
        self.view = view

        self.TxtViewName.Text = u'View: {}'.format(view.Name)
        grids = _logic.get_grids(doc)
        self.TxtGridCount.Text = (
            u'{} H-grids + {} V-grids'.format(len(grids['h']), len(grids['v'])))

        if not grids['h'] and not grids['v']:
            forms.alert(
                u'No gridlines found in this project.\n'
                u'This tool requires at least one grid axis.',
                title=u'No gridlines')

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
        try:
            self.TxtTolerance.Text = str(cfg.get('tolerance_mm', 50))
            self.TxtOffset.Text    = str(cfg.get('offset_paper_mm', 8))
        except Exception:
            pass

    def _get_options(self, dry_run=False):
        try:
            tol = float(self.TxtTolerance.Text.strip())
        except Exception:
            tol = 50.0
        try:
            offset_mm = float(self.TxtOffset.Text.strip())
            if offset_mm <= 0:
                offset_mm = 8.0
        except Exception:
            offset_mm = 8.0
        return {
            'mod1':            bool(self.ChkMod1.IsChecked),
            'mod2':            bool(self.ChkMod2.IsChecked),
            'mod3':            bool(self.ChkMod3.IsChecked),
            'mod4':            bool(self.ChkMod4.IsChecked),
            'tolerance_mm':    tol,
            'offset_paper_mm': offset_mm,
            'dry_run':         dry_run,
        }

    def _save_settings(self, opts):
        cfg = self.LoadConfig()
        cfg['tolerance_mm']    = opts['tolerance_mm']
        cfg['offset_paper_mm'] = opts['offset_paper_mm']
        cfg['dark_mode']       = self.dark_mode
        self.SaveConfig(cfg)

    def _show_status(self, text, running=False):
        Vis = System.Windows.Visibility
        self.StatusPanel.Visibility = Vis.Visible if (text or running) else Vis.Collapsed
        self.ProgBar.Visibility     = Vis.Visible if running else Vis.Collapsed
        self.TxtStatus.Text         = text or u''

    def _show_count(self, badge_tb, count):
        if count is not None and count > 0:
            badge_tb.Text       = u'~{} dims'.format(count)
            badge_tb.Visibility = System.Windows.Visibility.Visible
        else:
            badge_tb.Visibility = System.Windows.Visibility.Collapsed

    def DryRun_Click(self, sender, args):
        opts = self._get_options(dry_run=True)
        if not any([opts['mod1'], opts['mod2'], opts['mod3'], opts['mod4']]):
            forms.alert(u'Enable at least one module.')
            return

        self._show_status(u'Analysing model…', running=True)
        self.BtnDryRun.IsEnabled = False
        self.BtnRun.IsEnabled    = False
        try:
            results = _logic.run(self.doc, self.view, opts)
        except Exception as e:
            self._show_status(u'')
            self.BtnDryRun.IsEnabled = True
            self.BtnRun.IsEnabled    = True
            forms.alert(u'Error: {}'.format(e))
            return

        self._show_status(u'')
        self.BtnDryRun.IsEnabled = True
        self.BtnRun.IsEnabled    = True

        m1 = results.get('mod1')
        m2 = results.get('mod2')
        m3 = results.get('mod3')
        m4 = results.get('mod4')

        self._show_count(self.Mod1Count, m1['created'] if m1 else None)
        self._show_count(self.Mod2Count, m2['created'] if m2 else None)
        self._show_count(self.Mod3Count, m3['created'] if m3 else None)
        self._show_count(self.Mod4Count, m4['created'] if m4 else None)

        total = sum(r['created'] for r in [m1, m2, m3, m4] if r is not None)
        self.TxtResult.Text = (
            u'Preview: ~{} dimensions across {} H-grids + {} V-grids. '
            u'Press CREATE DIMENSIONS to apply.'.format(
                total, results['grids_h'], results['grids_v']))

    def Run_Click(self, sender, args):
        opts = self._get_options(dry_run=False)
        if not any([opts['mod1'], opts['mod2'], opts['mod3'], opts['mod4']]):
            forms.alert(u'Enable at least one module.')
            return

        mods = []
        if opts['mod1']: mods.append(u'M1')
        if opts['mod2']: mods.append(u'M2')
        if opts['mod3']: mods.append(u'M3')
        if opts['mod4']: mods.append(u'M4')

        if not forms.alert(
            u'Automatic dimensions will be created on view:\n«{}»\n\n'
            u'Active modules: {}\n\nContinue?'.format(
                self.view.Name, u', '.join(mods)),
            yes=True, no=True
        ):
            return

        self._save_settings(opts)
        self._show_status(u'Creating dimensions…', running=True)
        self.BtnRun.IsEnabled    = False
        self.BtnDryRun.IsEnabled = False

        try:
            results = _logic.run(self.doc, self.view, opts)
        except Exception as e:
            self._show_status(u'')
            self.BtnRun.IsEnabled    = True
            self.BtnDryRun.IsEnabled = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self._show_status(u'')
        self.BtnRun.IsEnabled    = True
        self.BtnDryRun.IsEnabled = True

        lines         = []
        total_created = 0
        total_skipped = 0
        all_errors    = []

        for key, label in [('mod1', 'M1'), ('mod2', 'M2'),
                            ('mod3', 'M3'), ('mod4', 'M4')]:
            r = results.get(key)
            if r is None:
                continue
            total_created += r['created']
            total_skipped += r['skipped']
            all_errors    += r['errors']
            lines.append(u'  {} → {} created, {} skipped'.format(
                label, r['created'], r['skipped']))

        summary = u'{} dimensions created.\n{}'.format(
            total_created, u'\n'.join(lines))

        if all_errors:
            summary += u'\n\n{} warnings:\n'.format(len(all_errors))
            summary += u'\n'.join(all_errors[:10])
            if len(all_errors) > 10:
                summary += u'\n… and {} more'.format(len(all_errors) - 10)

        self.TxtResult.Text = u'{} dimensions created, {} skipped.'.format(
            total_created, total_skipped)

        forms.alert(summary, title=u'GA Auto-Dimension — Result')

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
