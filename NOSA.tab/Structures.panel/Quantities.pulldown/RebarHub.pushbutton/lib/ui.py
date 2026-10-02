# -*- coding: utf-8 -*-
import os, sys, io, csv
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarhub'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from Autodesk.Revit import DB
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from System import Int64
import System.Windows
import System.Windows.Media as WM
from System.Windows.Media import Brushes

from nosa_utils.base_window import NOSAWindow

# ── Paths to existing plugin logic modules ─────────────────────────────────────
_HERE    = os.path.dirname(__file__)
_QTY_DIR = os.path.abspath(os.path.join(_HERE, '..', '..'))   # Quantities.pulldown

from nosa_utils.bootstrap import load_module
_bs_logic    = load_module('rebarhub_bslogic',
    os.path.join(_QTY_DIR, 'RebarManager.nobutton',  'lib', 'logic.py'))
_sched_logic = load_module('rebarhub_schedlogic',
    os.path.join(_QTY_DIR, 'RebarSchedule.nobutton', 'lib', 'logic.py'))
_aud_logic   = load_module('rebarhub_audlogic',
    os.path.join(_QTY_DIR, 'RebarAuditor.nobutton',  'lib', 'logic.py'))

EXPOSURE_CLASSES = ['X0', 'XC1', 'XC2', 'XC3', 'XC4',
                    'XD1', 'XD2', 'XD3', 'XS1', 'XS2', 'XS3',
                    'XF1', 'XF2', 'XF3', 'XF4', 'XA1', 'XA2', 'XA3']

_ALL_LEVELS = u'— All levels —'
_NO_EXCLUDE = u'— None (include all) —'

ACCENT = WM.Color.FromRgb(255, 95, 0)
DARK   = WM.Color.FromRgb(51, 51, 51)


# ── BS 8666 row types ──────────────────────────────────────────────────────────

class BsSchedRow(object):
    def __init__(self, g):
        self.Mark      = g['mark']
        self.DiamLabel = g['diameter_label']
        self.Quantity  = str(g['quantity'])
        self.Shape     = g['shape']
        self.ShapeDesc = g['shape_desc']
        self.TotalLenM = u'{:.2f}'.format(g['total_len_m'])
        self.MassKg    = u'{:.2f}'.format(g['mass_kg'])
        self.Levels    = g['levels']
        self.Hosts     = g['hosts']


class BsMarkRow(object):
    def __init__(self, g, dupe_marks):
        self.Selected    = False
        self.Mark        = g['mark']
        self.Diameter    = str(g['diameter'])
        self.Quantity    = str(g['quantity'])
        self.Shape       = g['shape']
        self.Levels      = g['levels']
        self.DupeWarning = u'⚠ DUPE' if g['mark'] in dupe_marks else u''


class AudDictRow(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


# ── Main hub window ────────────────────────────────────────────────────────────

class RebarHubWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_hub')
        self.doc   = doc
        self.uidoc = uidoc

        # BS 8666 state
        self._bs_bars        = []
        self._bs_groups      = {}
        self._bs_dupe_marks  = {}
        self._bs_sched_rows  = ObservableCollection[object]()
        self._bs_mark_rows   = ObservableCollection[object]()
        self.GridBsSchedule.ItemsSource = self._bs_sched_rows
        self.GridBsMarks.ItemsSource    = self._bs_mark_rows

        # Rebar Schedule state
        self._rs_rows       = []
        self._rs_totals     = None
        self._rs_level_map  = {}
        self._rs_phase_map  = {}

        try:
            for name in _sched_logic.get_host_filter_names():
                self.CboRsHostCat.Items.Add(name)
            self.CboRsHostCat.SelectedIndex = 0

            self.CboRsLevel.Items.Add(_ALL_LEVELS)
            for name, lvid in _sched_logic.get_levels(doc):
                self.CboRsLevel.Items.Add(name)
                self._rs_level_map[name] = lvid
            self.CboRsLevel.SelectedIndex = 0

            self.CboRsPhase.Items.Add(_NO_EXCLUDE)
            for name, phid in _sched_logic.get_phases(doc):
                self.CboRsPhase.Items.Add(name)
                self._rs_phase_map[name] = phid
            self.CboRsPhase.SelectedIndex = 0
        except Exception as e:
            self.LogLine(u'Warning — schedule filters: {}'.format(e))

        # EC2 Audit state
        self._aud_cover_rows  = []
        self._aud_ratio_rows  = []
        self._aud_unrein_rows = []
        self._aud_active_sub  = 'cover'
        for cls in EXPOSURE_CLASSES:
            self.CboAudExposure.Items.Add(cls)
        self.CboAudExposure.SelectedIndex = 1  # XC1

        # Config
        try:
            cfg = self.LoadConfig()
            self.TxtBsProjectNo.Text = cfg.get('project_no', u'')
            self.TxtBsRevision.Text  = cfg.get('revision', u'P01')
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
        except Exception:
            log_swallowed(_LOG, u'RebarHubWindow.__init__')

        self._show_main_tab('BS')
        self._show_bs_tab('Sched')

    # ── Tab navigation ────────────────────────────────────────────────────────

    def _tab_btn_style(self, btn, active):
        if active:
            btn.Background = WM.SolidColorBrush(ACCENT)
            btn.Foreground = Brushes.White
        else:
            btn.Background = Brushes.Transparent
            btn.Foreground = WM.SolidColorBrush(DARK)

    def _show_main_tab(self, tab):
        Vis = System.Windows.Visibility
        panels = {'BS': self.PanelBS, 'Sched': self.PanelSched, 'Audit': self.PanelAudit}
        btns   = {'BS': self.BtnMainBS, 'Sched': self.BtnMainSched, 'Audit': self.BtnMainAudit}
        for k, p in panels.items():
            p.Visibility = Vis.Visible if k == tab else Vis.Collapsed
        for k, b in btns.items():
            self._tab_btn_style(b, k == tab)

    def MainTab_Click(self, sender, args):
        self._show_main_tab(str(sender.Tag))

    def _show_bs_tab(self, sub):
        Vis = System.Windows.Visibility
        self.PanelBsSched.Visibility = Vis.Visible if sub == 'Sched' else Vis.Collapsed
        self.PanelBsMarks.Visibility = Vis.Visible if sub == 'Marks' else Vis.Collapsed
        self._tab_btn_style(self.BtnBsTabSched, sub == 'Sched')
        self._tab_btn_style(self.BtnBsTabMarks, sub == 'Marks')

    def BsTab_Click(self, sender, args):
        self._show_bs_tab(str(sender.Tag))

    # ── BS 8666 — data loading ────────────────────────────────────────────────

    def _bs_load_bars(self):
        self.SetLoading(True, u'Collecting rebar...')
        try:
            self._bs_bars   = _bs_logic.collect_rebar(self.doc)
            self._bs_groups = _bs_logic.group_by_mark(self._bs_bars)
        finally:
            self.SetLoading(False)

    def _bs_populate_schedule(self):
        self._bs_sched_rows.Clear()
        for g in sorted(self._bs_groups.values(), key=lambda x: x['mark']):
            self._bs_sched_rows.Add(BsSchedRow(g))
        total_mass = sum(g['mass_kg'] for g in self._bs_groups.values())
        self.TxtBsSchedStatus.Text = u'{} bar marks  ·  {} bars total  ·  {:.2f} kg total steel'.format(
            len(self._bs_groups),
            sum(g['quantity'] for g in self._bs_groups.values()),
            total_mass)

    def _bs_populate_marks(self):
        self._bs_dupe_marks = _bs_logic.detect_duplicate_marks(self._bs_bars)
        self._bs_mark_rows.Clear()
        for g in sorted(self._bs_groups.values(), key=lambda x: x['mark']):
            self._bs_mark_rows.Add(BsMarkRow(g, self._bs_dupe_marks))
        if self._bs_dupe_marks:
            self.PanelBsDuplicates.Visibility = System.Windows.Visibility.Visible
            msgs = [u'⚠ Bar mark "{}" has multiple diameters: {}'.format(
                        m, u', '.join(u'Ø{}mm'.format(d) for d in sorted(ds)))
                    for m, ds in sorted(self._bs_dupe_marks.items())]
            self.TxtBsDuplicates.Text = u'\n'.join(msgs)
        else:
            self.PanelBsDuplicates.Visibility = System.Windows.Visibility.Collapsed
        self.TxtBsMarksStatus.Text = u'{} unique marks · {} duplicate conflicts'.format(
            len(self._bs_groups), len(self._bs_dupe_marks))

    # ── BS 8666 — event handlers ──────────────────────────────────────────────

    def BsLoad_Click(self, sender, args):
        try:
            self._bs_load_bars()
            self._bs_populate_schedule()
            self.LogLine(u'[BS 8666] Loaded {} rebar elements.'.format(len(self._bs_bars)))
            if not self._bs_bars:
                self.LogLine(u'No rebar found — check model has rebar elements.')
        except Exception as e:
            self.LogLine(u'[BS 8666] Error loading rebar: {}'.format(e))

    def BsExportExcel_Click(self, sender, args):
        if not self._bs_groups:
            self.LogLine(u'[BS 8666] Load rebar first.')
            return
        from pyrevit import forms
        path = forms.save_file(
            file_ext='xlsx',
            default_name=u'{} NOSA RC ZZZ L S 5500 {} RC Schedule'.format(
                self.TxtBsProjectNo.Text or u'00000',
                self.TxtBsRevision.Text  or u'P01'))
        if not path:
            return
        self.SetLoading(True, u'Exporting Excel...')
        try:
            ok, err = _bs_logic.export_bs8666_excel(
                self._bs_groups, path,
                self.TxtBsProjectNo.Text or u'',
                self.TxtBsRevision.Text  or u'P01')
            if ok:
                self.LogLine(u'[BS 8666] Exported: {}'.format(path))
                cfg = self.LoadConfig()
                cfg.update({'project_no': self.TxtBsProjectNo.Text,
                            'revision':   self.TxtBsRevision.Text})
                self.SaveConfig(cfg)
            else:
                self.LogLine(u'[BS 8666] Export error: {}'.format(err))
        finally:
            self.SetLoading(False)

    def BsLoadMarks_Click(self, sender, args):
        try:
            self._bs_load_bars()
            self._bs_populate_marks()
            self.LogLine(u'[BS 8666] Refreshed: {} bars.'.format(len(self._bs_bars)))
        except Exception as e:
            self.LogLine(u'[BS 8666] Error: {}'.format(e))

    def BsDetectDupes_Click(self, sender, args):
        if not self._bs_bars:
            self._bs_load_bars()
        self._bs_populate_marks()

    def BsRenumber_Click(self, sender, args):
        selected = set(r.Mark for r in self._bs_mark_rows if r.Selected)
        if not selected:
            self.LogLine(u'[BS 8666] Select bar marks to renumber.')
            return
        prefix = self.TxtBsMarkPrefix.Text or u'S'
        try:
            start = int(self.TxtBsMarkStart.Text or u'1')
        except Exception:
            start = 1
        bars_sel = [b for b in self._bs_bars if b['mark'] in selected]
        with DB.Transaction(self.doc, u'NOSA — Rebar Renumber') as t:
            t.Start()
            changed, mapping = _bs_logic.renumber_marks(self.doc, bars_sel, prefix, start)
            t.Commit()
        self.LogLine(u'[BS 8666] Renumbered {} bars. {}'.format(
            changed,
            u', '.join(u'{}→{}'.format(k, v) for k, v in sorted(mapping.items())[:5])))
        self._bs_load_bars()
        self._bs_populate_marks()

    # ── Rebar Schedule — event handlers ──────────────────────────────────────

    def RsGenerate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgRs.Visibility      = Vis.Visible
        self.TxtRsProgress.Text     = u'Scanning rebar…'
        self.BtnRsGenerate.IsEnabled = False
        self.BtnRsXlsx.IsEnabled     = False
        self.BtnRsCsv.IsEnabled      = False

        group_by = ('host'   if self.RbRsGroupHost.IsChecked     else
                    'diameter' if self.RbRsGroupDiameter.IsChecked else 'shape')

        host_idx     = self.CboRsHostCat.SelectedIndex
        host_options = _sched_logic._host_filter_options()
        host_bic     = host_options[host_idx][1] if 0 <= host_idx < len(host_options) else None

        lv_sel = self.CboRsLevel.SelectedItem
        lv_id  = self._rs_level_map.get(lv_sel) if lv_sel and lv_sel != _ALL_LEVELS else None

        ph_sel = self.CboRsPhase.SelectedItem
        ph_id  = self._rs_phase_map.get(ph_sel) if ph_sel and ph_sel != _NO_EXCLUDE else None

        options = {
            'group_by':        group_by,
            'filter_host_bic': host_bic,
            'filter_level_id': lv_id,
            'filter_phase_id': ph_id,
            'show_subtotals':  bool(self.ChkRsSubtotals.IsChecked),
        }

        try:
            rows, totals = _sched_logic.collect_schedule(self.doc, options)
        except Exception as e:
            self.ProgRs.Visibility      = Vis.Collapsed
            self.TxtRsProgress.Text     = u''
            self.BtnRsGenerate.IsEnabled = True
            from pyrevit import forms
            forms.alert(u'Error generating schedule:\n{}'.format(e))
            return

        self._rs_rows   = rows
        self._rs_totals = totals

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(r)
        self.GridRsSchedule.ItemsSource = src

        if totals:
            self.TxtRsTotalBars.Text   = str(totals.n_bars or 0)
            self.TxtRsTotalLength.Text = u'{:.2f} m'.format(totals.total_length_m or 0)
            self.TxtRsTotalWeight.Text = totals.total_wt_str

        self.ProgRs.Visibility      = Vis.Collapsed
        detail_rows = [r for r in rows if not r.is_subtotal]
        self.TxtRsProgress.Text     = u'{} bar groups found.'.format(len(detail_rows))
        self.BtnRsGenerate.IsEnabled = True
        self.BtnRsXlsx.IsEnabled     = True
        self.BtnRsCsv.IsEnabled      = True

    def RsGrid_SelectionChanged(self, sender, args):
        selected = list(self.GridRsSchedule.SelectedItems)
        ids = []
        for r in selected:
            if not r.is_subtotal:
                ids.extend(r.el_ids or [])
        if ids:
            try:
                eid_list = List[DB.ElementId](
                    [DB.ElementId(Int64(int(i))) for i in ids])
                self.uidoc.Selection.SetElementIds(eid_list)
            except Exception:
                log_swallowed(_LOG, u'RebarHubWindow.RsGrid_SelectionChanged')

    def RsExportXlsx_Click(self, sender, args):
        if not self._rs_rows:
            return
        from pyrevit import forms
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            proj = ''
            try:
                proj = self.doc.ProjectInformation.Name or ''
            except Exception:
                log_swallowed(_LOG, u'RebarHubWindow.RsExportXlsx_Click')
            _sched_logic.export_xlsx(self._rs_rows, self._rs_totals, path, proj)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use "Export CSV" instead.')
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def RsExportCsv_Click(self, sender, args):
        if not self._rs_rows:
            return
        from pyrevit import forms
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _sched_logic.export_csv(self._rs_rows, self._rs_totals, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    # ── EC2 Audit — event handlers ────────────────────────────────────────────

    def AudTab_Click(self, sender, args):
        Vis = System.Windows.Visibility
        name = sender.Name
        sub_map = {
            'BtnAudTabCover':  ('cover',  self.GridAudCover,  self.GridAudRatio,  self.GridAudUnrein),
            'BtnAudTabRatio':  ('ratio',  self.GridAudRatio,  self.GridAudCover,  self.GridAudUnrein),
            'BtnAudTabUnrein': ('unrein', self.GridAudUnrein, self.GridAudCover,  self.GridAudRatio),
        }
        entry = sub_map.get(name)
        if not entry:
            return
        self._aud_active_sub = entry[0]
        entry[1].Visibility = Vis.Visible
        entry[2].Visibility = Vis.Collapsed
        entry[3].Visibility = Vis.Collapsed
        self._tab_btn_style(self.BtnAudTabCover,  self._aud_active_sub == 'cover')
        self._tab_btn_style(self.BtnAudTabRatio,  self._aud_active_sub == 'ratio')
        self._tab_btn_style(self.BtnAudTabUnrein, self._aud_active_sub == 'unrein')

    def AudRun_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.PanelAudProgress.Visibility = Vis.Visible
        self.BtnAudRun.IsEnabled = False

        exposure = self.CboAudExposure.SelectedItem or u'XC1'
        custom = None
        try:
            v = float((self.TxtAudCustomCover.Text or u'').strip())
            if v > 0:
                custom = v
        except Exception:
            log_swallowed(_LOG, u'RebarHubWindow.AudRun_Click')

        opts = {
            'chk_cover':       True,
            'exposure_class':  exposure,
            'custom_cover_mm': custom,
            'chk_ratio':       True,
            'chk_unrein':      True,
        }

        try:
            result = _aud_logic.run_audit(self.doc, opts)
        except Exception as e:
            self.PanelAudProgress.Visibility = Vis.Collapsed
            self.BtnAudRun.IsEnabled = True
            from pyrevit import forms
            forms.alert(u'Error during audit:\n{}'.format(e))
            return

        self.PanelAudProgress.Visibility = Vis.Collapsed
        self.BtnAudRun.IsEnabled = True

        self._aud_cover_rows  = result.get('cover',        [])
        self._aud_ratio_rows  = result.get('ratio',        [])
        self._aud_unrein_rows = result.get('unreinforced', [])

        # Normalise dict keys to match XAML binding names
        for r in self._aud_cover_rows:
            etype = r.get('element_type', u'')
            mark  = r.get('host_mark', u'') or u''
            r[u'elem_name'] = u'{} — {}'.format(etype, mark).strip(u' —')
            r[u'cover_mm']  = r.get('actual_cover', u'N/D')
            r[u'req_mm']    = r.get('required_cover', u'')
            try:
                cov = r.get('actual_cover')
                req = float(r.get('required_cover', 0))
                r[u'gap_mm'] = round(float(cov) - req, 1) if cov not in (None, u'N/D') else u'N/D'
            except Exception:
                r[u'gap_mm'] = u''
            r[u'bar_id'] = r.get('id', u'')
            r[u'level']  = u''

        for r in self._aud_ratio_rows:
            etype = r.get('element_type', u'')
            mark  = r.get('host_mark', u'') or u''
            r[u'elem_name']   = u'{} — {}'.format(etype, mark).strip(u' —')
            r[u'rho_actual']  = r.get('rho', u'')
            r[u'level']       = u''

        for r in self._aud_unrein_rows:
            r[u'elem_name'] = r.get('family_type', r.get('element_type', u''))
            r[u'category']  = r.get('element_type', u'')

        self._aud_populate_grid(self.GridAudCover,  self._aud_cover_rows)
        self._aud_populate_grid(self.GridAudRatio,  self._aud_ratio_rows)
        self._aud_populate_grid(self.GridAudUnrein, self._aud_unrein_rows)

        cover_fails = sum(1 for r in self._aud_cover_rows if r.get('status') == 'FAIL')
        ratio_fails = sum(1 for r in self._aud_ratio_rows if r.get('status') == 'FAIL')
        self.TxtAudCoverFail.Text = u'{} FAIL'.format(cover_fails + ratio_fails)
        self.TxtAudSummary.Text = u'{} bars · {} cover FAIL · {} ratio FAIL · {} unreinforced'.format(
            len(self._aud_cover_rows), cover_fails, ratio_fails, len(self._aud_unrein_rows))
        self.BtnAudSelectFail.IsEnabled = True
        self.BtnAudExport.IsEnabled     = True

    def _aud_populate_grid(self, grid, rows):
        src = ObservableCollection[object]()
        for r in rows:
            src.Add(AudDictRow(r))
        grid.ItemsSource = src

    def AudSelectFail_Click(self, sender, args):
        if self._aud_active_sub == 'cover':
            ids = [r['id'] for r in self._aud_cover_rows  if r.get('status') == 'FAIL']
        elif self._aud_active_sub == 'ratio':
            ids = [r['id'] for r in self._aud_ratio_rows  if r.get('status') == 'FAIL']
        else:
            ids = [r['id'] for r in self._aud_unrein_rows]
        if not ids:
            from pyrevit import forms
            forms.alert(u'No FAIL elements in the active tab.')
            return
        try:
            eid_list = List[DB.ElementId]([DB.ElementId(Int64(int(i))) for i in ids])
            self.uidoc.Selection.SetElementIds(eid_list)
            self.TxtAudSummary.Text = u'{} element(s) selected in Revit.'.format(len(ids))
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Error selecting: {}'.format(e))

    def AudExport_Click(self, sender, args):
        from pyrevit import forms
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
                w = csv.writer(f)
                for label, rows in [(u'=== COVER ===', self._aud_cover_rows),
                                    (u'=== REBAR RATIO ===', self._aud_ratio_rows),
                                    (u'=== UNREINFORCED ===', self._aud_unrein_rows)]:
                    w.writerow([label])
                    if rows:
                        w.writerow(list(rows[0].keys()))
                        for r in rows:
                            w.writerow([r.get(k, u'') for k in rows[0].keys()])
                    w.writerow([])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    # ── Shared ────────────────────────────────────────────────────────────────

    def Close_Click(self, sender, args):
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
