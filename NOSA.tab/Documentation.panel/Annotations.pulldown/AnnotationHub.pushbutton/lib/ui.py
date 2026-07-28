# -*- coding: utf-8 -*-
import os
import sys
import imp
import System.Windows

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_here = os.path.dirname(os.path.abspath(__file__))
_dw_logic = imp.load_source('annhub_dw_logic',  os.path.join(_here, 'logic_dim_walls.py'))
_ga_logic = imp.load_source('annhub_ga_logic',  os.path.join(_here, 'logic_ga_auto_dim.py'))

DimensionLogic = _dw_logic.DimensionLogic


class _ViewItem(object):
    def __init__(self, element):
        self.Element   = element
        self.Name      = element.Name
        self.IsChecked = False


class AnnotationHubWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'annotation_hub')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._dw_init()
        self._ga_init()

    # ──────────────────────────────────────────────────────────────────
    # WALL DIMENSIONS helpers
    # ──────────────────────────────────────────────────────────────────

    def _dw_init(self):
        self._dw_logic = DimensionLogic(self.doc)
        self._dw_all_views = []

        types = self._dw_logic.get_dimension_types()
        self.DW_ComboDimTypes.ItemsSource = types
        if types:
            self.DW_ComboDimTypes.SelectedIndex = 0

        collector = (DB.FilteredElementCollector(self.doc)
                     .OfClass(DB.View)
                     .WhereElementIsNotElementType())
        views = []
        for v in collector:
            if v.IsTemplate:
                continue
            if v.ViewType in (DB.ViewType.FloorPlan,
                              DB.ViewType.EngineeringPlan,
                              DB.ViewType.AreaPlan):
                views.append(v)
        views.sort(key=lambda x: x.Name)

        self._dw_all_views = [_ViewItem(v) for v in views]
        self.DW_ListViews.ItemsSource = list(self._dw_all_views)
        self.DW_TxtCount.Text = u'{} views'.format(len(self._dw_all_views))

        active_id = self.doc.ActiveView.Id
        for item in self._dw_all_views:
            if item.Element.Id == active_id:
                item.IsChecked = True

        self.DW_TxtFilter.TextChanged += self._dw_filter_changed

    def _dw_filter_changed(self, sender, args):
        text = (self.DW_TxtFilter.Text or u'').lower()
        visible = [v for v in self._dw_all_views
                   if not text or text in v.Name.lower()]
        self.DW_ListViews.ItemsSource = visible
        self.DW_TxtCount.Text = u'{} views'.format(len(visible))

    def DW_CheckAll_Checked(self, sender, args):
        for v in list(self.DW_ListViews.ItemsSource or []):
            v.IsChecked = True
        self.DW_ListViews.Items.Refresh()

    def DW_CheckAll_Unchecked(self, sender, args):
        for v in list(self.DW_ListViews.ItemsSource or []):
            v.IsChecked = False
        self.DW_ListViews.Items.Refresh()

    def DW_Run_Click(self, sender, args):
        dim_type = self.DW_ComboDimTypes.SelectedItem
        if not dim_type:
            forms.alert(u'Please select a dimension type.')
            return

        try:
            offset_mm = float(self.DW_TxtOffset.Text.strip())
        except ValueError:
            forms.alert(u'Invalid offset value.')
            return

        selected = [v.Element for v in self._dw_all_views if v.IsChecked]
        if not selected:
            forms.alert(u'Please select at least one view.')
            return

        do_straight = bool(self.DW_ChkStraight.IsChecked)
        do_curved   = bool(self.DW_ChkCurved.IsChecked)
        if not do_straight and not do_curved:
            forms.alert(u'Please select at least one wall type (straight or curved).')
            return

        self.DW_OverlayProgress.Visibility = System.Windows.Visibility.Visible
        try:
            import clr
            clr.AddReference('System.Windows.Forms')
            import System.Windows.Forms as _WF
            _WF.Application.DoEvents()
        except Exception:
            pass

        created  = 0
        failed   = 0
        diag_log = []
        with revit.Transaction(u'NOSA — Dimension Walls'):
            for view in selected:
                walls = self._dw_logic.get_valid_walls_in_view(view)
                for wall in walls:
                    geo    = self._dw_logic.get_wall_curve_data(wall)
                    is_arc = geo['is_arc']
                    if is_arc and do_curved:
                        res = self._dw_logic.create_arc_dimensions(
                            wall, view, dim_type, offset_mm, log_fn=diag_log.append)
                        if res:
                            created += len(res)
                        else:
                            failed += 1
                    elif not is_arc and do_straight:
                        dim = self._dw_logic.create_linear_dimension(wall, view, dim_type, offset_mm)
                        if dim:
                            created += 1
                        else:
                            failed += 1

        self.DW_OverlayProgress.Visibility = System.Windows.Visibility.Collapsed
        msg = u'Created {} dimensions.\n(Failed/skipped: {})'.format(created, failed)
        if diag_log:
            msg += u'\n\nDetails ({} of {}):\n{}'.format(
                min(5, len(diag_log)), len(diag_log), u'\n'.join(diag_log[:5]))
        forms.alert(msg)

    # ──────────────────────────────────────────────────────────────────
    # GA AUTO-DIMENSION helpers
    # ──────────────────────────────────────────────────────────────────

    def _ga_init(self):
        self._ga_view = self.doc.ActiveView
        self.GA_TxtViewName.Text  = u'View: {}'.format(self._ga_view.Name)
        grids = _ga_logic.get_grids(self.doc)
        self.GA_TxtGridCount.Text = u'{} H-grids + {} V-grids'.format(
            len(grids['h']), len(grids['v']))

    def _ga_options(self, dry_run=False):
        try:
            tol = float(self.GA_TxtTolerance.Text.strip())
        except Exception:
            tol = 50.0
        return {
            'mod1':         bool(self.GA_ChkMod1.IsChecked),
            'mod2':         bool(self.GA_ChkMod2.IsChecked),
            'mod3':         bool(self.GA_ChkMod3.IsChecked),
            'mod4':         bool(self.GA_ChkMod4.IsChecked),
            'tolerance_mm': tol,
            'dry_run':      dry_run,
        }

    def _ga_show_status(self, text, running=False):
        Vis = System.Windows.Visibility
        vis = Vis.Visible if (text or running) else Vis.Collapsed
        self.GA_StatusPanel.Visibility = vis
        self.GA_ProgBar.Visibility     = Vis.Visible if running else Vis.Collapsed
        self.GA_TxtStatus.Text         = text or u''

    def _ga_show_count(self, tb, count):
        if count and count > 0:
            tb.Text       = u'~{} dims'.format(count)
            tb.Visibility = System.Windows.Visibility.Visible
        else:
            tb.Visibility = System.Windows.Visibility.Collapsed

    def GA_DryRun_Click(self, sender, args):
        opts = self._ga_options(dry_run=True)
        if not any([opts['mod1'], opts['mod2'], opts['mod3'], opts['mod4']]):
            forms.alert(u'Enable at least one module.')
            return

        self._ga_show_status(u'Analysing model…', running=True)
        self.GA_BtnDryRun.IsEnabled = False
        self.GA_BtnRun.IsEnabled    = False
        try:
            results = _ga_logic.run(self.doc, self._ga_view, opts)
        except Exception as e:
            self._ga_show_status(u'')
            self.GA_BtnDryRun.IsEnabled = True
            self.GA_BtnRun.IsEnabled    = True
            forms.alert(u'Error: {}'.format(e))
            return

        self._ga_show_status(u'')
        self.GA_BtnDryRun.IsEnabled = True
        self.GA_BtnRun.IsEnabled    = True

        for key, tb in [('mod1', self.GA_Mod1Count), ('mod2', self.GA_Mod2Count),
                        ('mod3', self.GA_Mod3Count), ('mod4', self.GA_Mod4Count)]:
            r = results.get(key)
            self._ga_show_count(tb, r['created'] if r else None)

        total = sum(r['created'] for r in [results.get(k)
                    for k in ('mod1','mod2','mod3','mod4')] if r is not None)
        self.GA_TxtResult.Text = (
            u'Preview: ~{} dimensions across {} H-grids + {} V-grids. '
            u'Press CREATE DIMENSIONS to apply.'.format(
                total, results['grids_h'], results['grids_v']))

    def GA_Run_Click(self, sender, args):
        opts = self._ga_options(dry_run=False)
        if not any([opts['mod1'], opts['mod2'], opts['mod3'], opts['mod4']]):
            forms.alert(u'Enable at least one module.')
            return

        mods = [u'M{}'.format(i) for i, k in enumerate(
            ['mod1','mod2','mod3','mod4'], 1) if opts[k]]
        if not forms.alert(
            u'Automatic dimensions will be created on view:\n«{}»\n\n'
            u'Active modules: {}\n\nContinue?'.format(
                self._ga_view.Name, u', '.join(mods)),
            yes=True, no=True
        ):
            return

        self._ga_show_status(u'Creating dimensions…', running=True)
        self.GA_BtnRun.IsEnabled    = False
        self.GA_BtnDryRun.IsEnabled = False
        try:
            results = _ga_logic.run(self.doc, self._ga_view, opts)
        except Exception as e:
            self._ga_show_status(u'')
            self.GA_BtnRun.IsEnabled    = True
            self.GA_BtnDryRun.IsEnabled = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self._ga_show_status(u'')
        self.GA_BtnRun.IsEnabled    = True
        self.GA_BtnDryRun.IsEnabled = True

        total_c = total_s = 0
        lines   = []
        for key, label in [('mod1','M1'),('mod2','M2'),('mod3','M3'),('mod4','M4')]:
            r = results.get(key)
            if r is None:
                continue
            total_c += r['created']
            total_s += r['skipped']
            lines.append(u'  {} → {} created, {} skipped'.format(
                label, r['created'], r['skipped']))

        self.GA_TxtResult.Text = u'{} dimensions created, {} skipped.'.format(total_c, total_s)
        forms.alert(
            u'{} dimensions created.\n{}'.format(total_c, u'\n'.join(lines)),
            title=u'GA Auto-Dimension — Result')

    # ──────────────────────────────────────────────────────────────────
    # Shared
    # ──────────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
