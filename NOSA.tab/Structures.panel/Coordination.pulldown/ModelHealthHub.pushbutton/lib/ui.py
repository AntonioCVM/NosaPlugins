# -*- coding: utf-8 -*-
import io, csv, os, sys, imp, datetime
import System.Windows
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger

_here = os.path.dirname(os.path.abspath(__file__))
_hs_logic = imp.load_source('mhh_hs_logic', os.path.join(_here, 'logic_health_score.py'))
_wt_logic = imp.load_source('mhh_wt_logic', os.path.join(_here, 'logic_warnings_triage.py'))
_sc_logic = imp.load_source('mhh_sc_logic', os.path.join(_here, 'logic_model_sync.py'))

logger = Logger()


class CheckRow(object):
    def __init__(self, key, label, count, severity, weight, detail_items):
        self.Key      = key
        self.Label    = label
        self.Count    = count
        self.Severity = severity
        self.Weight   = weight
        self.Impact   = u'{:.1f}'.format(weight * max(0, 100 - count) / 100.0) if count else u'—'
        self.Detail   = u', '.join(str(x) for x in detail_items[:5]) if detail_items else u''
        self._items   = detail_items


class WarningRow(object):
    def __init__(self, d, idx):
        self.Index         = idx
        self.Severity      = d.get('severity', u'')
        self.Description   = d.get('description', u'')
        self.ElementsStr   = u', '.join(str(x) for x in d.get('elements', [])[:5])
        self.CountElements = len(d.get('elements', []))
        self.Action        = d.get('action', u'')
        self.IsIgnored     = d.get('ignored', False)
        self._raw          = d


class SyncRow(object):
    STATUS_COLORS = {
        u'OK':      u'#4CAF50',
        u'Missing': u'#F44336',
        u'Issue':   u'#FF9800',
    }

    def __init__(self, d):
        self.status       = d.get('status', u'')
        self.status_color = self.STATUS_COLORS.get(self.status, u'#888888')
        self.mark         = d.get('mark', u'')
        self.calc_sec     = d.get('calc_section', u'')
        self.revit_sec    = d.get('revit_section', u'')
        self.calc_len     = u'{:.2f}'.format(d['calc_length']) if d.get('calc_length') is not None else u''
        self.revit_len    = u'{:.2f}'.format(d['revit_length']) if d.get('revit_length') is not None else u''
        self.calc_level   = d.get('calc_level', u'')
        self.revit_level  = d.get('revit_level', u'')
        self.revit_id     = str(d.get('revit_id', u''))
        self._raw         = d


class ModelHealthHubWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'model_health_hub')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._hs_init(cfg)
        self._wt_init()
        self._sc_init()

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: HEALTH SCORE
    # ══════════════════════════════════════════════════════════════════

    def _hs_init(self, cfg):
        self._hs_rows    = ObservableCollection[CheckRow]()
        self._hs_results = None
        self.HS_GridResults.ItemsSource = self._hs_rows

        weights = cfg.get('hs_weights', {})
        sliders = {
            'no_material':    self.HS_SldMaterial,
            'no_analytical':  self.HS_SldAnalytical,
            'orphan_found':   self.HS_SldOrphan,
            'warnings':       self.HS_SldWarnings,
            'param_missing':  self.HS_SldParams,
            'bad_offset':     self.HS_SldOffsets,
            'dup_marks':      self.HS_SldDupMarks,
            'no_level':       self.HS_SldNoLevel,
            'unhosted_rebar': self.HS_SldRebar,
        }
        for key, sld in sliders.items():
            if key in weights:
                sld.Value = float(weights[key])
        self._hs_sliders = sliders

    def _hs_get_weights(self):
        return {k: int(sld.Value) for k, sld in self._hs_sliders.items()}

    def _hs_save_config(self):
        cfg = self.LoadConfig()
        cfg['hs_weights'] = self._hs_get_weights()
        cfg['hs_checks'] = {
            'no_material':    self.HS_ChkMaterial.IsChecked      == True,
            'no_analytical':  self.HS_ChkAnalytical.IsChecked    == True,
            'orphan_found':   self.HS_ChkOrphan.IsChecked        == True,
            'warnings':       self.HS_ChkWarnings.IsChecked      == True,
            'param_missing':  self.HS_ChkParams.IsChecked        == True,
            'bad_offset':     self.HS_ChkOffsets.IsChecked       == True,
            'dup_marks':      self.HS_ChkDupMarks.IsChecked      == True,
            'no_level':       self.HS_ChkNoLevel.IsChecked       == True,
            'unhosted_rebar': self.HS_ChkUnhostedRebar.IsChecked == True,
        }
        self.SaveConfig(cfg)

    def _hs_score_label(self, score):
        if score >= 90: return u'Excellent — model is in great shape.'
        if score >= 75: return u'Good — minor issues to review.'
        if score >= 50: return u'Fair — several issues need attention.'
        return u'Poor — critical issues found.'

    def _hs_draw_trend(self, history):
        try:
            canvas = self.HS_TrendCanvas
            canvas.Children.Clear()
            if not history or len(history) < 2:
                return
            pts = [(i, float(h.get('score', 0))) for i, h in enumerate(history[-12:])]
            n   = len(pts)
            w   = canvas.ActualWidth or 600.0
            h   = canvas.ActualHeight or 80.0
            pad = 8.0
            xs  = [pad + (p[0] / float(n - 1)) * (w - 2 * pad) for p in pts]
            ys  = [(h - pad) - (p[1] / 100.0) * (h - 2 * pad) for p in pts]

            poly = SWS.Polyline()
            poly.Stroke          = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 95, 0))
            poly.StrokeThickness = 2.0
            poly.StrokeLineJoin  = SWM.PenLineJoin.Round
            for x, y in zip(xs, ys):
                poly.Points.Add(SWM.Point(x, y))
            canvas.Children.Add(poly)

            for i, (x, y) in enumerate(zip(xs, ys)):
                dot = SWS.Ellipse()
                dot.Width  = 6; dot.Height = 6
                dot.Fill   = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 95, 0))
                SWC.Canvas.SetLeft(dot, x - 3)
                SWC.Canvas.SetTop(dot, y - 3)
                canvas.Children.Add(dot)

                lbl = SWC.TextBlock()
                lbl.Text     = str(int(round(pts[i][1])))
                lbl.FontSize = 9
                lbl.Foreground = SWM.SolidColorBrush(SWM.Color.FromArgb(140, 80, 80, 80))
                SWC.Canvas.SetLeft(lbl, max(0, x - 10))
                SWC.Canvas.SetTop(lbl, max(0, y - 16))
                canvas.Children.Add(lbl)

                if i == 0 or i == n - 1:
                    date_lbl = SWC.TextBlock()
                    date_lbl.Text     = history[-(n - i)].get('date', '')[-5:]
                    date_lbl.FontSize = 8
                    date_lbl.Foreground = SWM.SolidColorBrush(SWM.Color.FromArgb(140, 100, 100, 100))
                    SWC.Canvas.SetLeft(date_lbl, max(0, x - 18))
                    SWC.Canvas.SetTop(date_lbl, h - 12)
                    canvas.Children.Add(date_lbl)
        except Exception:
            pass

    def HS_Run_Click(self, sender, args):
        self._hs_save_config()
        active = set()
        if self.HS_ChkMaterial.IsChecked      == True: active.add('no_material')
        if self.HS_ChkAnalytical.IsChecked    == True: active.add('no_analytical')
        if self.HS_ChkOrphan.IsChecked        == True: active.add('orphan_found')
        if self.HS_ChkWarnings.IsChecked      == True: active.add('warnings')
        if self.HS_ChkParams.IsChecked        == True: active.add('param_missing')
        if self.HS_ChkOffsets.IsChecked       == True: active.add('bad_offset')
        if self.HS_ChkDupMarks.IsChecked      == True: active.add('dup_marks')
        if self.HS_ChkNoLevel.IsChecked       == True: active.add('no_level')
        if self.HS_ChkUnhostedRebar.IsChecked == True: active.add('unhosted_rebar')

        weights = self._hs_get_weights()
        self.SetLoading(True, u'Running checks...')
        self._hs_rows.Clear()
        self.HS_BtnExport.IsEnabled = False
        self.HS_BtnReport.IsEnabled = False
        self.HS_BtnSelect.IsEnabled = False

        try:
            data = _hs_logic.run_all_checks(self.doc, active, weights=weights)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks: {}'.format(e))
            return

        self._hs_results = data
        score = data['score']

        self.HS_ScoreBar.Value     = score
        self.HS_TxtScore.Text      = str(int(round(score)))
        self.HS_TxtScoreLabel.Text = self._hs_score_label(score)

        if score >= 80:
            self.HS_ScoreBar.Foreground = SWM.Brushes.SeaGreen
        elif score >= 50:
            self.HS_ScoreBar.Foreground = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 95, 0))
        else:
            self.HS_ScoreBar.Foreground = SWM.Brushes.Crimson

        checks = data['checks']
        high = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'High')
        med  = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'Medium')
        low  = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'Low')
        self.HS_TxtHigh.Text   = u'{} High'.format(high)
        self.HS_TxtMedium.Text = u'{} Medium'.format(med)
        self.HS_TxtLow.Text    = u'{} Low'.format(low)

        for c in checks:
            self._hs_rows.Add(CheckRow(
                c['key'], c['label'], c['count'],
                c['severity'], c['weight'],
                data['results'].get(c['key'], [])
            ))

        self.SetLoading(False)
        self.HS_BtnExport.IsEnabled = True
        self.HS_BtnReport.IsEnabled = True

        try:
            title   = self.doc.Title or u'Unknown'
            _hs_logic.save_score_history(title, score, data['counts'])
            history = _hs_logic.get_score_history(title)
            self._hs_draw_trend(history)
        except Exception:
            pass

    def HS_Grid_SelectionChanged(self, sender, args):
        self.HS_BtnSelect.IsEnabled = self.HS_GridResults.SelectedItem is not None

    def HS_Select_Click(self, sender, args):
        row = self.HS_GridResults.SelectedItem
        if not row or not row._items:
            return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(x)) for x in row._items
                                      if str(x).isdigit()])
            if ids.Count:
                revit.uidoc.Selection.SetElementIds(ids)
        except Exception as e:
            forms.alert(u'Could not select: {}'.format(e))

    def HS_History_Click(self, sender, args):
        try:
            title   = self.doc.Title or u'Unknown'
            history = _hs_logic.get_score_history(title)
        except Exception as e:
            forms.alert(u'Could not load history: {}'.format(e))
            return
        if not history:
            forms.alert(u'No score history for this document yet.',
                        title=u'Score History')
            return
        lines = [u'Score history for: {}\n'.format(title)]
        for entry in reversed(history[-10:]):
            lines.append(u'{}  →  {}/100'.format(entry.get('date', '?'), entry.get('score', '?')))
        forms.alert(u'\n'.join(lines), title=u'Score History')

    def HS_Export_Click(self, sender, args):
        if not self._hs_results:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Check', 'Issues', 'Severity', 'Weight', 'Detail'])
                for r in self._hs_rows:
                    w.writerow([r.Label, r.Count, r.Severity, r.Weight, r.Detail])
            forms.alert(u'Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    def HS_Report_Click(self, sender, args):
        if not self._hs_results:
            return
        path = forms.save_file(file_ext='html')
        if not path:
            return
        try:
            self._hs_export_html(path)
            import subprocess
            subprocess.Popen(['start', '', path], shell=True)
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    def _hs_export_html(self, path):
        score     = self._hs_results['score']
        title     = self.doc.Title or u'Revit Model'
        now       = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        col       = '#4CAF50' if score >= 80 else ('#FF9800' if score >= 50 else '#F44336')
        rows_html = []
        for row in self._hs_rows:
            sev_col = {'High': '#F44336', 'Medium': '#FF9800', 'Low': '#607D8B'}.get(row.Severity, '#888')
            rows_html.append(u'<tr><td>{}</td><td>{}</td><td style="color:{};font-weight:bold">{}</td>'
                             u'<td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                row.Label, row.Count, sev_col, row.Severity,
                row.Weight, row.Impact, row.Detail))
        html = u"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<title>Health Report — {title}</title>
<style>
body{{font-family:'Century Gothic',Arial,sans-serif;margin:0;background:#f5f5f5;color:#333}}
.header{{background:#333;padding:24px 32px;color:white}}
.header h1{{margin:0;font-size:22px;color:#FF5F00}}
.score-box{{display:inline-block;background:white;border-radius:8px;padding:20px 32px;
            margin:24px 32px;box-shadow:0 1px 4px rgba(0,0,0,.12)}}
.score-num{{font-size:64px;font-weight:bold;color:{col};line-height:1}}
table{{border-collapse:collapse;width:calc(100% - 64px);margin:0 32px 32px;background:white;
       border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
th{{background:#FF5F00;color:white;padding:10px 14px;text-align:left;font-size:12px}}
td{{padding:9px 14px;border-bottom:1px solid #eee;font-size:12px}}
.footer{{text-align:center;padding:16px;font-size:11px;opacity:.45}}
</style></head><body>
<div class="header"><h1>NOSA Structural Health Report</h1>
<p>{title} &nbsp;·&nbsp; {now}</p></div>
<div class="score-box">
  <div class="score-num">{score_int}/100</div>
  <div style="font-size:13px;opacity:.65;margin-top:4px">{label}</div>
</div>
<table><thead><tr><th>Check</th><th>Issues</th><th>Severity</th>
<th>Weight</th><th>Score impact</th><th>Detail</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="footer">Generated by NOSA Model Health Hub &nbsp;·&nbsp; NOSA Engineering Gibraltar</div>
</body></html>""".format(
            title=title, now=now, col=col,
            score_int=int(round(score)),
            label=self._hs_score_label(score),
            rows=u''.join(rows_html))
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: WARNINGS TRIAGE
    # ══════════════════════════════════════════════════════════════════

    def _wt_init(self):
        self._wt_rows     = ObservableCollection[WarningRow]()
        self._wt_all_rows = []
        self._wt_raw      = []
        self.WT_GridResults.ItemsSource = self._wt_rows

    def _wt_apply_filter(self):
        show_high   = self.WT_ChkHigh.IsChecked   == True
        show_medium = self.WT_ChkMedium.IsChecked == True
        show_low    = self.WT_ChkLow.IsChecked    == True
        show_ign    = self.WT_ChkShowIgnored.IsChecked == True
        search      = (self.WT_TxtSearch.Text or u'').lower()

        sev_map = {'High': show_high, 'Medium': show_medium, 'Low': show_low}
        self._wt_rows.Clear()
        high = med = low = 0
        for r in self._wt_all_rows:
            if not sev_map.get(r.Severity, True):
                continue
            if r.IsIgnored and not show_ign:
                continue
            if search and search not in r.Description.lower() \
                      and search not in r.ElementsStr.lower():
                continue
            self._wt_rows.Add(r)
            if r.Severity == 'High':   high += 1
            elif r.Severity == 'Medium': med += 1
            else: low += 1

        self.WT_TxtHigh.Text   = u'{} High'.format(high)
        self.WT_TxtMedium.Text = u'{} Medium'.format(med)
        self.WT_TxtLow.Text    = u'{} Low'.format(low)
        self.WT_TxtTotal.Text  = u'({} total)'.format(len(self._wt_all_rows))

    def WT_Run_Click(self, sender, args):
        self.SetLoading(True, u'Collecting warnings...')
        try:
            self._wt_raw = _wt_logic.get_all_warnings(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error: {}'.format(e))
            return
        self._wt_all_rows = [WarningRow(d, i + 1) for i, d in enumerate(self._wt_raw)]
        self._wt_apply_filter()
        self.SetLoading(False)
        self.WT_BtnExport.IsEnabled = True

    def WT_Filter_Changed(self, sender, args):
        self._wt_apply_filter()

    def WT_Search_Changed(self, sender, args):
        self._wt_apply_filter()

    def WT_Grid_SelectionChanged(self, sender, args):
        row = self.WT_GridResults.SelectedItem
        if row:
            self.WT_PanelAction.Visibility = System.Windows.Visibility.Visible
            self.WT_TxtAction.Text         = row.Action or u'No automatic fix available.'
            self.WT_BtnAutoFix.IsEnabled   = bool(row.Action)
            self.WT_BtnIgnore.IsEnabled    = True
            self.WT_BtnSelect.IsEnabled    = True
            self.WT_BtnJumpView.IsEnabled  = bool(row._raw.get('element_ids'))
        else:
            self.WT_PanelAction.Visibility = System.Windows.Visibility.Collapsed
            self.WT_BtnAutoFix.IsEnabled   = False
            self.WT_BtnIgnore.IsEnabled    = False
            self.WT_BtnSelect.IsEnabled    = False
            self.WT_BtnJumpView.IsEnabled  = False

    def WT_AutoFix_Click(self, sender, args):
        row = self.WT_GridResults.SelectedItem
        if not row or not row.Action:
            return
        try:
            with DB.Transaction(self.doc, u'NOSA — Auto-fix Warning') as t:
                t.Start()
                _wt_logic.auto_fix(self.doc, row._raw)
                t.Commit()
            self._wt_raw = _wt_logic.get_all_warnings(self.doc)
            self._wt_all_rows = [WarningRow(d, i + 1) for i, d in enumerate(self._wt_raw)]
            self._wt_apply_filter()
        except Exception as e:
            forms.alert(u'Fix failed: {}'.format(e))

    def WT_Ignore_Click(self, sender, args):
        row = self.WT_GridResults.SelectedItem
        if not row:
            return
        row._raw['ignored'] = True
        row.IsIgnored = True
        self._wt_apply_filter()

    def WT_JumpView_Click(self, sender, args):
        row = self.WT_GridResults.SelectedItem
        if not row:
            return
        ids_raw = row._raw.get('element_ids', [])
        if not ids_raw:
            forms.alert(u'No elements associated with this warning.', title=u'Jump to View')
            return
        try:
            from System.Collections.Generic import List
            target_view = None
            for v in DB.FilteredElementCollector(self.doc).OfClass(DB.View3D).ToElements():
                try:
                    if not v.IsTemplate:
                        target_view = v
                        break
                except Exception:
                    pass
            if target_view is None:
                for v in DB.FilteredElementCollector(self.doc).OfClass(DB.ViewPlan).ToElements():
                    try:
                        if not v.IsTemplate:
                            target_view = v
                            break
                    except Exception:
                        pass
            if target_view is None:
                forms.alert(u'No suitable view found to jump to.', title=u'Jump to View')
                return
            revit.uidoc.RequestViewChange(target_view)
            ids = List[DB.ElementId]([DB.ElementId(int(x)) for x in ids_raw])
            if ids.Count:
                revit.uidoc.Selection.SetElementIds(ids)
        except Exception as e:
            forms.alert(u'Jump failed: {}'.format(e), title=u'Jump to View')

    def WT_Select_Click(self, sender, args):
        row = self.WT_GridResults.SelectedItem
        if not row:
            return
        try:
            ids_raw = row._raw.get('element_ids', [])
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(x)) for x in ids_raw])
            if ids.Count:
                revit.uidoc.Selection.SetElementIds(ids)
        except Exception as e:
            forms.alert(u'Could not select: {}'.format(e))

    def WT_Export_Click(self, sender, args):
        if not self._wt_all_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['#', 'Severity', 'Description', 'Elements', 'Count', 'Action'])
                for r in self._wt_all_rows:
                    w.writerow([r.Index, r.Severity, r.Description,
                                r.ElementsStr, r.CountElements, r.Action])
            forms.alert(u'Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 3: BIM SYNC CHECKER
    # ══════════════════════════════════════════════════════════════════

    def _sc_init(self):
        self._sc_rows   = ObservableCollection[SyncRow]()
        self._sc_csv    = None
        self.SC_GridSync.ItemsSource = self._sc_rows

    def SC_Browse_Click(self, sender, args):
        path = forms.pick_file(file_ext='csv')
        if not path:
            return
        self._sc_csv = path
        self.SC_TxtCsvPath.Text    = os.path.basename(path)
        self.SC_TxtCsvPath.Opacity = 1.0
        self.SC_BtnRun.IsEnabled   = True
        self.SC_TxtStatus.Text     = u'CSV loaded — click ▶ COMPARE to run.'

    def SC_Run_Click(self, sender, args):
        if not self._sc_csv:
            return
        self.SC_ProgBar.Visibility   = System.Windows.Visibility.Visible
        self.SC_BtnRun.IsEnabled     = False
        self.SC_BtnSelect.IsEnabled  = False
        self.SC_BtnExport.IsEnabled  = False
        self._sc_rows.Clear()

        try:
            results = _sc_logic.compare(self.doc, self._sc_csv)
        except Exception as e:
            self.SC_ProgBar.Visibility = System.Windows.Visibility.Collapsed
            self.SC_BtnRun.IsEnabled   = True
            forms.alert(u'Compare failed: {}'.format(e))
            return

        for d in results:
            self._sc_rows.Add(SyncRow(d))

        ok      = sum(1 for d in results if d.get('status') == 'OK')
        missing = sum(1 for d in results if d.get('status') == 'Missing')
        issues  = sum(1 for d in results if d.get('status') == 'Issue')

        self.SC_TxtOK.Text      = str(ok)
        self.SC_TxtMissing.Text = str(missing)
        self.SC_TxtIssues.Text  = str(issues)
        self.SC_TxtStatus.Text  = u'{} OK · {} missing · {} discrepancies'.format(ok, missing, issues)

        self.SC_ProgBar.Visibility  = System.Windows.Visibility.Collapsed
        self.SC_BtnRun.IsEnabled    = True
        self.SC_BtnSelect.IsEnabled = ok > 0
        self.SC_BtnExport.IsEnabled = len(results) > 0

    def SC_Select_Click(self, sender, args):
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]()
            for row in self._sc_rows:
                if row.status == u'OK' and row.revit_id.isdigit():
                    ids.Add(DB.ElementId(int(row.revit_id)))
            if ids.Count:
                revit.uidoc.Selection.SetElementIds(ids)
        except Exception as e:
            forms.alert(u'Could not select: {}'.format(e))

    def SC_Export_Click(self, sender, args):
        if not self._sc_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Status', 'Mark', 'Calc section', 'Revit section',
                            'Calc L (m)', 'Revit L (m)', 'Calc level', 'Revit level', 'Revit ID'])
                for r in self._sc_rows:
                    w.writerow([r.status, r.mark, r.calc_sec, r.revit_sec,
                                r.calc_len, r.revit_len, r.calc_level, r.revit_level, r.revit_id])
            forms.alert(u'Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
