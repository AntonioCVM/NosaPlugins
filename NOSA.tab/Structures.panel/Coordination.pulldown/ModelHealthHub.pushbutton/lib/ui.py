# -*- coding: utf-8 -*-
import io, csv, os, sys, imp, datetime
import System.Windows
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger

_here = os.path.dirname(os.path.abspath(__file__))
_hs_logic  = imp.load_source('mhh_hs_logic',  os.path.join(_here, 'logic_health_score.py'))
_wt_logic  = imp.load_source('mhh_wt_logic',  os.path.join(_here, 'logic_warnings_triage.py'))
_sc_logic  = imp.load_source('mhh_sc_logic',  os.path.join(_here, 'logic_model_sync.py'))
_ah_logic  = imp.load_source('mhh_ah_logic',  os.path.join(_here, 'logic_analytical_health.py'))
_cc_logic  = imp.load_source('mhh_cc_logic',  os.path.join(_here, 'logic_connection_checker.py'))
_cv_logic  = imp.load_source('mhh_cv_logic',  os.path.join(_here, 'logic_cover_compliance.py'))
_fl_logic  = imp.load_source('mhh_fl_logic',  os.path.join(_here, 'logic_foundation_loads.py'))
_lgs_logic = imp.load_source('mhh_lgs_logic', os.path.join(_here, 'logic_level_grid_sync.py'))
_pd_logic  = imp.load_source('mhh_pd_logic',  os.path.join(_here, 'logic_parameter_drift.py'))

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


class _DictRow(object):
    """Generic dict-to-attrs row, used by AH/FL tabs."""
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class CCIssueRow(object):
    def __init__(self, d):
        self.Severity = d['severity']
        self.Category = d['category']
        self.Level    = d['level']
        self.Name     = d['name']
        self.Check    = d['check']
        self.Id       = d['id']


class CVRebarRow(object):
    def __init__(self, rec):
        self.Host     = rec['host']
        self.Category = rec['category']
        self.CoverMm  = u'{:.1f}'.format(rec['cover_mm'])
        self.MinMm    = u'{:.0f}'.format(rec['min_mm'])
        self.Status   = rec['status']
        self._rec     = rec


class LGSLinkItem(object):
    def __init__(self, link, title):
        self.Link  = link
        self.Title = title
    def __str__(self):
        return self.Title


class PDParamItem(object):
    def __init__(self, name):
        self.Name      = name
        self.IsChecked = False


class PDDriftRow(object):
    def __init__(self, d):
        self.Element   = d.get('key', u'')
        self.Parameter = d.get('param', u'')
        self.Change    = d.get('change', u'')
        self.Baseline  = d.get('baseline', u'')
        self.Current   = d.get('current', u'')


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
        self._ah_init()
        self._cc_init()
        self._cv_init(cfg)
        self._fl_init()
        self._lgs_init()
        self._pd_init(cfg)

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
    # TAB 4: ANALYTICAL HEALTH CHECK
    # ══════════════════════════════════════════════════════════════════

    def _ah_init(self):
        self._ah_rows = []

    def AH_Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.AH_ProgBar.Visibility  = Vis.Visible
        self.AH_TxtStatus.Text      = u'Analysing model…'
        self.AH_BtnRun.IsEnabled    = False
        self.AH_BtnExport.IsEnabled = False
        self.AH_BtnSelect.IsEnabled = False

        try:
            results = _ah_logic.run_all(self.doc)
        except Exception as e:
            self.AH_ProgBar.Visibility = Vis.Collapsed
            self.AH_TxtStatus.Text     = u''
            self.AH_BtnRun.IsEnabled   = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.AH_ProgBar.Visibility = Vis.Collapsed
        self.AH_TxtStatus.Text     = u''
        self.AH_BtnRun.IsEnabled   = True

        self._ah_rows = results['all']
        src = ObservableCollection[object]()
        for r in self._ah_rows:
            src.Add(_DictRow(r))
        self.AH_GridResults.ItemsSource = src

        self.AH_TxtErrors.Text   = str(results['errors'])
        self.AH_TxtWarnings.Text = str(results['warnings_count'])
        self.AH_TxtTotal.Text    = str(results['total'])

        self.AH_TxtSummary.Text = (
            u'{} issue(s): {} error(s), {} warning(s).'.format(
                results['total'], results['errors'], results['warnings_count']))

        if self._ah_rows:
            self.AH_BtnExport.IsEnabled = True

    def AH_GridResults_SelectionChanged(self, sender, args):
        self.AH_BtnSelect.IsEnabled = self.AH_GridResults.SelectedItem is not None

    def AH_Select_Click(self, sender, args):
        selected = list(self.AH_GridResults.SelectedItems)
        if not selected:
            return
        try:
            from System import Int64
            ids = List[DB.ElementId]([
                DB.ElementId(Int64(int(r.id))) for r in selected
                if r.id and str(r.id).lstrip('-').isdigit()
            ])
            if ids:
                revit.uidoc.Selection.SetElementIds(ids)
                self.AH_TxtSummary.Text = u'{} element(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def AH_Export_Click(self, sender, args):
        if not self._ah_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            keys = ['severity', 'etype', 'mark', 'level', 'id', 'issue']
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow([u'Severity', u'Type', u'Mark', u'Level', u'ID', u'Issue'])
                for r in self._ah_rows:
                    w.writerow([r.get(k, '') for k in keys])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 5: CONNECTION CHECKER
    # ══════════════════════════════════════════════════════════════════

    def _cc_init(self):
        self._cc_rows         = ObservableCollection[CCIssueRow]()
        self._cc_custom_rules = []
        self.CC_GridResults.ItemsSource = self._cc_rows
        for cond in _cc_logic._CONDITION_OPS:
            self.CC_CboCondition.Items.Add(cond)
        self.CC_CboCondition.SelectedIndex = 0
        for sev in ['High', 'Medium', 'Low']:
            self.CC_CboSeverity.Items.Add(sev)
        self.CC_CboSeverity.SelectedIndex = 1
        for cat in _cc_logic._RULE_CATEGORIES:
            self.CC_CboRuleCat.Items.Add(cat)
        self.CC_CboRuleCat.SelectedIndex = 3  # Any
        self._cc_custom_rules = _cc_logic.load_custom_rules()
        self._cc_refresh_rules_list()

    def _cc_refresh_rules_list(self):
        self.CC_LstRules.Items.Clear()
        for r in self._cc_custom_rules:
            lbl = r.get('label') or u'{} — {} {} {}'.format(
                r.get('category', 'Any'), r.get('param', ''),
                r.get('condition', ''), r.get('threshold', ''))
            self.CC_LstRules.Items.Add(u'[{}]  {}'.format(r.get('severity', 'Medium'), lbl))

    def CC_NavTab_Click(self, sender, args):
        tag = (sender.Tag or '').lower()
        self.CC_TabResults.Visibility = System.Windows.Visibility.Collapsed
        self.CC_TabRules.Visibility   = System.Windows.Visibility.Collapsed
        if tag == 'rules':
            self.CC_TabRules.Visibility = System.Windows.Visibility.Visible
        else:
            self.CC_TabResults.Visibility = System.Windows.Visibility.Visible

    def CC_AddRule_Click(self, sender, args):
        param = (self.CC_TxtRuleParam.Text or '').strip()
        if not param:
            forms.alert(u'Enter a parameter name.'); return
        cond = str(self.CC_CboCondition.SelectedItem or 'is_empty')
        thr  = (self.CC_TxtThreshold.Text or '').strip()
        sev  = str(self.CC_CboSeverity.SelectedItem or 'Medium')
        cat  = str(self.CC_CboRuleCat.SelectedItem or 'Any')
        lbl  = (self.CC_TxtRuleLabel.Text or '').strip() or None
        self._cc_custom_rules.append(
            {'param': param, 'condition': cond, 'threshold': thr,
             'severity': sev, 'category': cat, 'label': lbl})
        self._cc_refresh_rules_list()

    def CC_RemoveRule_Click(self, sender, args):
        idx = self.CC_LstRules.SelectedIndex
        if 0 <= idx < len(self._cc_custom_rules):
            del self._cc_custom_rules[idx]
            self._cc_refresh_rules_list()

    def CC_SaveRules_Click(self, sender, args):
        try:
            _cc_logic.save_custom_rules(self._cc_custom_rules)
            forms.alert(u'Rules saved ({} total).'.format(len(self._cc_custom_rules)))
        except Exception as e:
            forms.alert(u'Save failed: {}'.format(e))

    def CC_ImportRules_Click(self, sender, args):
        path = forms.pick_file(file_ext='json')
        if not path: return
        try:
            import json as _json
            with io.open(path, encoding='utf-8') as f:
                imported = _json.load(f)
            self._cc_custom_rules = imported
            self._cc_refresh_rules_list()
            forms.alert(u'Imported {} rule(s).'.format(len(imported)))
        except Exception as e:
            forms.alert(u'Import failed: {}'.format(e))

    def CC_ExportRules_Click(self, sender, args):
        path = forms.save_file(file_ext='json')
        if not path: return
        try:
            import json as _json
            with io.open(path, 'w', encoding='utf-8') as f:
                _json.dump(self._cc_custom_rules, f, indent=2, ensure_ascii=False)
            forms.alert(u'Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    def _cc_active(self):
        active = set()
        if self.CC_ChkAnalytical.IsChecked  == True: active.add('analytical')
        if self.CC_ChkUsage.IsChecked       == True: active.add('usage')
        if self.CC_ChkAttachment.IsChecked  == True: active.add('attachment')
        if self.CC_ChkJoins.IsChecked       == True: active.add('joins')
        return active

    def CC_Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking structural connections...')
        self._cc_rows.Clear(); self.CC_BtnExport.IsEnabled = False; self.CC_BtnExport2.IsEnabled = False
        try:
            data = _cc_logic.run_all_checks(self.doc, self._cc_active(), self._cc_custom_rules or None)
        except Exception as e:
            self.SetLoading(False); forms.alert("Error: {}".format(e)); return
        self.CC_TxtHigh.Text   = "{} High".format(data['high'])
        self.CC_TxtMedium.Text = "{} Medium".format(data['medium'])
        self.CC_TxtLow.Text    = "{} Low".format(data['low'])
        for r in data['issues']:
            self._cc_rows.Add(CCIssueRow(r))
        self.SetLoading(False)
        self.CC_BtnExport.IsEnabled = self.CC_BtnExport2.IsEnabled = len(data['issues']) > 0
        if len(data['issues']) == 0:
            forms.alert("No connection issues found in the model.\n\nAll checked elements look good.",
                        title="Connection Checker")

    def CC_Grid_SelectionChanged(self, sender, args):
        self.CC_BtnSelect.IsEnabled = self.CC_GridResults.SelectedItem is not None

    def CC_Select_Click(self, sender, args):
        row = self.CC_GridResults.SelectedItem
        if not row: return
        try:
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def CC_Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Severity', 'Category', 'Level', 'Name', 'Check'])
                for r in self._cc_rows:
                    w.writerow([r.Severity, r.Category, r.Level, r.Name, r.Check])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 6: COVER COMPLIANCE
    # ══════════════════════════════════════════════════════════════════

    def _cv_init(self, cfg):
        self._cv_results = []
        self._cv_show_fail_only = False

        for cls in _cv_logic.ec2_exposure_classes():
            self.CV_CboExposure.Items.Add(cls)
        last_exposure = cfg.get('cv_last_exposure', u'XC3 (moderate humidity)')
        for i in range(self.CV_CboExposure.Items.Count):
            if self.CV_CboExposure.Items[i] == last_exposure:
                self.CV_CboExposure.SelectedIndex = i
                break
        else:
            self.CV_CboExposure.SelectedIndex = 0

        min_cover = _cv_logic.min_cover_for_class(self.CV_CboExposure.SelectedItem or u'')
        self.CV_TxtMinCover.Text = str(int(min_cover))
        self._cv_reset_summary()
        self.CV_TxtStatus.Text = u'Click "Run Check" to analyse rebar coverage.'

    def _cv_reset_summary(self):
        self.CV_TxtTotal.Text = u'—'
        self.CV_TxtOk.Text    = u'—'
        self.CV_TxtFail.Text  = u'—'

    def _cv_update_summary(self):
        total, ok, fail = _cv_logic.summarise(self._cv_results)
        self.CV_TxtTotal.Text = str(total)
        self.CV_TxtOk.Text    = str(ok)
        self.CV_TxtFail.Text  = str(fail)

    def _cv_refresh_grid(self):
        data = self._cv_results
        if self._cv_show_fail_only:
            data = [r for r in data if r['status'] == u'FAIL']
        self.CV_GridResults.ItemsSource = [CVRebarRow(r) for r in data]

    def CV_Exposure_Changed(self, sender, args):
        cls = self.CV_CboExposure.SelectedItem
        if cls:
            self.CV_TxtMinCover.Text = str(int(_cv_logic.min_cover_for_class(cls)))

    def CV_MinCover_Changed(self, sender, args):
        pass

    def CV_RunCheck_Click(self, sender, args):
        try:
            min_cover = float(self.CV_TxtMinCover.Text.strip())
        except (ValueError, Exception):
            self.CV_TxtStatus.Text = u'Enter a valid minimum cover in mm.'
            return

        self.SetLoading(True, u'Checking rebar coverage…')
        try:
            self._cv_results = _cv_logic.analyse(self.doc, min_cover)
        finally:
            self.SetLoading(False)

        self._cv_show_fail_only = False
        self._cv_update_summary()
        self._cv_refresh_grid()

        total, ok, fail = _cv_logic.summarise(self._cv_results)
        self.CV_TxtStatus.Text = u'Checked {} bars. {} OK, {} below minimum ({} mm).'.format(
            total, ok, fail, int(min_cover))

        cls = self.CV_CboExposure.SelectedItem or u''
        cfg = self.LoadConfig()
        cfg['cv_last_exposure'] = cls
        self.SaveConfig(cfg)

    def CV_FilterFail_Click(self, sender, args):
        self._cv_show_fail_only = not self._cv_show_fail_only
        self._cv_refresh_grid()
        fail = sum(1 for r in self._cv_results if r['status'] == u'FAIL')
        if self._cv_show_fail_only:
            self.CV_TxtStatus.Text = u'Showing {} failing bars only.'.format(fail)
        else:
            self.CV_TxtStatus.Text = u'Showing all {} bars.'.format(len(self._cv_results))

    def CV_ExportCsv_Click(self, sender, args):
        if not self._cv_results:
            self.CV_TxtStatus.Text = u'Run the check first before exporting.'
            return
        try:
            path = forms.save_file(
                file_ext=u'csv',
                default_name=u'rebar_coverage.csv',
                title=u'Export rebar coverage report')
            if not path:
                return
            with open(path, 'wb') as f:
                w = csv.writer(f)
                w.writerow(['Host', 'Category', 'Cover (mm)', 'Min (mm)', 'Status'])
                for r in self._cv_results:
                    w.writerow([r['host'], r['category'],
                                '{:.1f}'.format(r['cover_mm']),
                                '{:.0f}'.format(r['min_mm']),
                                r['status']])
            self.CV_TxtStatus.Text = u'Exported {} records to {}'.format(
                len(self._cv_results), os.path.basename(path))
        except Exception as ex:
            self.CV_TxtStatus.Text = u'Export failed: {}'.format(ex)

    def CV_SelectInModel_Click(self, sender, args):
        rows = list(self.CV_GridResults.SelectedItems or [])
        if rows:
            recs = [r._rec for r in rows]
        else:
            recs = [r for r in self._cv_results if r['status'] == u'FAIL']
        if not recs:
            self.CV_TxtStatus.Text = u'Nothing to select — run the check first.'
            return
        try:
            ids = List[DB.ElementId]()
            for rec in recs:
                try:
                    ids.Add(rec['element'].Id)
                except Exception:
                    pass
            revit.uidoc.Selection.SetElementIds(ids)
            self.CV_TxtStatus.Text = u'Selected {} bar(s) in the model{}.'.format(
                ids.Count, u'' if rows else u' (all failing)')
        except Exception as ex:
            self.CV_TxtStatus.Text = u'Selection failed: {}'.format(ex)

    # ══════════════════════════════════════════════════════════════════
    # TAB 7: FOUNDATION LOAD EXTRACTOR
    # ══════════════════════════════════════════════════════════════════

    def _fl_init(self):
        self._fl_rows = []

    def FL_Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.FL_ProgBar.Visibility = Vis.Visible
        self.FL_BtnRun.IsEnabled   = False

        try:
            rows = _fl_logic.get_foundation_loads(self.doc)
        except Exception as e:
            self.FL_ProgBar.Visibility = Vis.Collapsed
            self.FL_BtnRun.IsEnabled   = True
            forms.alert(u'Error extracting loads:\n{}'.format(e))
            return

        self.FL_ProgBar.Visibility = Vis.Collapsed
        self.FL_BtnRun.IsEnabled   = True
        self._fl_rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_DictRow(r))
        self.FL_GridLoads.ItemsSource = src

        no_data = sum(1 for r in rows if r.get('N_kN') == u'—')
        self.FL_TxtStatus.Text = (
            u'{} foundations found. {} with analytical reactions; {} without.'.format(
                len(rows), len(rows) - no_data, no_data))
        self.FL_BtnExport.IsEnabled    = bool(rows)
        self.FL_BtnSelect.IsEnabled    = bool(rows)
        self.FL_BtnExportPDF.IsEnabled = bool(rows)

    def FL_Select_Click(self, sender, args):
        if not self._fl_rows:
            return
        try:
            from System import Int64
            ids = List[DB.ElementId]([
                DB.ElementId(Int64(int(r['id']))) for r in self._fl_rows
            ])
            revit.uidoc.Selection.SetElementIds(ids)
            self.FL_TxtStatus.Text = u'{} element(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def FL_Export_Click(self, sender, args):
        if not self._fl_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _fl_logic.export_csv(self._fl_rows, path)
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    def FL_ExportPDF_Click(self, sender, args):
        if not self._fl_rows:
            return
        import System.Windows.Forms as WinForms
        dlg = WinForms.SaveFileDialog()
        dlg.Filter   = "PDF files (*.pdf)|*.pdf|HTML files (*.html)|*.html|All files (*.*)|*.*"
        dlg.Title    = "Save foundation load report"
        dlg.FileName = "foundation_load_report.pdf"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        try:
            proj = ''
            try:
                proj = self.doc.ProjectInformation.Name or ''
            except Exception:
                pass
            out_path, is_pdf = _fl_logic.export_pdf_report(self._fl_rows, dlg.FileName, proj)
            if is_pdf:
                forms.alert(u'PDF report exported:\n{}'.format(out_path))
            else:
                import subprocess
                subprocess.Popen(['start', out_path], shell=True)
                forms.alert(
                    u'Chrome not found — report saved as HTML:\n{}\n\n'
                    u'Open in a browser and use File > Print to save as PDF.'.format(out_path))
        except Exception as e:
            forms.alert(u'PDF export error:\n{}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 8: LEVEL & GRID SYNC
    # ══════════════════════════════════════════════════════════════════

    def _lgs_init(self):
        self._lgs_links   = []
        self._lgs_report  = None
        self._lgs_load_links()

    def _lgs_load_links(self):
        links = _lgs_logic.get_linked_models(self.doc)
        self._lgs_links = links
        items = [LGSLinkItem(lnk, title) for lnk, title in links]
        self.LGS_CboLinks.ItemsSource   = items
        self.LGS_CboLinks.DisplayMemberPath = 'Title'
        if items:
            self.LGS_CboLinks.SelectedIndex = 0
        else:
            self.LGS_TxtStatus.Text = u'No linked Revit models found in the project.'

    def LGS_Run_Click(self, sender, args):
        sel = self.LGS_CboLinks.SelectedItem
        if sel is None:
            forms.alert(u'Select a linked model first.')
            return

        try:
            tol = float(self.LGS_TxtTolerance.Text or '1')
        except Exception:
            tol = 1.0

        self.SetLoading(True, u'Comparing…')
        link_doc = sel.Link.GetLinkDocument()
        if link_doc is None:
            self.SetLoading(False)
            forms.alert(u'Linked model is not loaded. Load it first.')
            return

        try:
            self._lgs_report = _lgs_logic.compare(self.doc, link_doc, tol)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error during comparison:\n{}'.format(e))
            return

        self.SetLoading(False)
        self._lgs_render_report()

    def _lgs_render_report(self):
        r = self._lgs_report
        panel = self.LGS_ResultsPanel
        panel.Children.Clear()

        if not r.has_issues:
            ok = SWC.TextBlock()
            ok.Text = u'✅  No discrepancies found against "{}".'.format(r.link_title)
            ok.FontSize = 13
            ok.FontWeight = System.Windows.FontWeights.SemiBold
            ok.Foreground = SWM.SolidColorBrush(
                SWM.ColorConverter.ConvertFromString('#22c55e'))
            ok.Margin = System.Windows.Thickness(0, 8, 0, 0)
            panel.Children.Add(ok)
            return

        self.LGS_TxtStatus.Text = u'{} issue(s) found vs. "{}"'.format(r.issue_count, r.link_title)

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
            hdr = SWC.TextBlock()
            hdr.Text = u'{} ({})'.format(title, len(items))
            hdr.FontWeight = System.Windows.FontWeights.SemiBold
            hdr.FontSize = 12
            hdr.Margin = System.Windows.Thickness(0, 10, 0, 4)
            panel.Children.Add(hdr)
            for it in items:
                tb = SWC.TextBlock()
                tb.Text = u'  · ' + it
                tb.FontSize = 11
                tb.Opacity = 0.75
                tb.Margin = System.Windows.Thickness(0, 1, 0, 1)
                panel.Children.Add(tb)

    # ══════════════════════════════════════════════════════════════════
    # TAB 9: PARAMETER DRIFT MONITOR
    # ══════════════════════════════════════════════════════════════════

    def _pd_init(self, cfg):
        self._pd_params   = ObservableCollection[object]()
        self._pd_rows     = ObservableCollection[object]()
        self._pd_baseline = {}

        self.PD_ParamList.ItemsSource = self._pd_params
        self.PD_DriftGrid.ItemsSource = self._pd_rows

        self._pd_saved_params = cfg.get('pd_watched_params', [])
        self._pd_baseline     = cfg.get('pd_baseline', {})
        self._pd_load_params()

        if self._pd_baseline:
            self.PD_TxtBaselineInfo.Text = u'Baseline saved — {} elements tracked'.format(
                len(self._pd_baseline))
        else:
            self.PD_TxtBaselineInfo.Text = u'No baseline saved yet.'

    def _pd_load_params(self):
        self._pd_params.Clear()
        for name in _pd_logic.get_shared_param_names(self.doc):
            item = PDParamItem(name)
            item.IsChecked = name in self._pd_saved_params
            self._pd_params.Add(item)
        self.PD_TxtStatus.Text = u'{} shared parameters found.'.format(len(self._pd_params))

    def _pd_selected_param_names(self):
        return [p.Name for p in self._pd_params if p.IsChecked]

    def PD_SaveBaseline_Click(self, sender, args):
        names = self._pd_selected_param_names()
        if not names:
            forms.alert(u'Select at least one parameter to monitor.', title=u'Parameter Drift Monitor')
            return
        self.SetLoading(True, u'Scanning model…')
        try:
            self._pd_baseline = _pd_logic.snapshot_model(self.doc, names)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error scanning model:\n{}'.format(e), title=u'Parameter Drift Monitor')
            return
        self.SetLoading(False)
        self._pd_save_cfg()
        self.PD_TxtBaselineInfo.Text = u'Baseline saved — {} elements tracked'.format(
            len(self._pd_baseline))
        self.PD_TxtStatus.Text = u'Baseline saved ({} elements, {} params).'.format(
            len(self._pd_baseline), len(names))
        self._pd_rows.Clear()

    def PD_Compare_Click(self, sender, args):
        if not self._pd_baseline:
            forms.alert(u'Save a baseline first.', title=u'Parameter Drift Monitor')
            return
        names = self._pd_selected_param_names()
        if not names:
            forms.alert(u'Select at least one parameter to compare.', title=u'Parameter Drift Monitor')
            return
        self.SetLoading(True, u'Comparing…')
        try:
            current = _pd_logic.snapshot_model(self.doc, names)
            diffs   = _pd_logic.compare_snapshots(self._pd_baseline, current)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error comparing:\n{}'.format(e), title=u'Parameter Drift Monitor')
            return
        self._pd_rows.Clear()
        for d in diffs:
            self._pd_rows.Add(PDDriftRow(d))
        self.SetLoading(False)
        if diffs:
            self.PD_TxtStatus.Text = u'{} drift{} detected.'.format(
                len(diffs), u's' if len(diffs) != 1 else u'')
        else:
            self.PD_TxtStatus.Text = u'No drift detected — model matches baseline.'

    def PD_ImportExcel_Click(self, sender, args):
        path = forms.pick_file(file_ext='xlsx', title=u'Select Reference Excel')
        if not path:
            return
        try:
            self._pd_baseline = _pd_logic.import_from_excel(path)
            self._pd_save_cfg()
            self.PD_TxtBaselineInfo.Text = u'Excel baseline loaded — {} elements'.format(
                len(self._pd_baseline))
        except Exception as e:
            forms.alert(u'Could not read Excel:\n{}'.format(e), title=u'Parameter Drift Monitor')

    def PD_ExportCSV_Click(self, sender, args):
        if not self._pd_rows:
            return
        path = forms.save_file(file_ext='csv', title=u'Save Drift Report')
        if not path:
            return
        diffs = [{'key': r.Element, 'param': r.Parameter, 'change': r.Change,
                  'baseline': r.Baseline, 'current': r.Current} for r in self._pd_rows]
        try:
            _pd_logic.export_diffs_csv(diffs, path)
            self.PD_TxtStatus.Text = u'Exported to {}'.format(os.path.basename(path))
        except Exception as e:
            forms.alert(u'Export failed:\n{}'.format(e), title=u'Parameter Drift Monitor')

    def PD_SelectInModel_Click(self, sender, args):
        rows = list(self.PD_DriftGrid.SelectedItems or [])
        if not rows:
            rows = list(self._pd_rows)
        keys = set(r.Element for r in rows if r.Element)
        if not keys:
            self.PD_TxtStatus.Text = u'No drift rows to select — run a comparison first.'
            return
        self.SetLoading(True, u'Resolving elements…')
        try:
            ids = _pd_logic.resolve_key_elements(self.doc, keys)
        finally:
            self.SetLoading(False)
        if not ids:
            self.PD_TxtStatus.Text = u'No matching elements found in the model.'
            return
        try:
            net_ids = List[DB.ElementId]()
            for i in ids:
                net_ids.Add(i)
            revit.uidoc.Selection.SetElementIds(net_ids)
            self.PD_TxtStatus.Text = u'Selected {} element(s) in the model.'.format(net_ids.Count)
        except Exception as e:
            self.PD_TxtStatus.Text = u'Selection failed: {}'.format(e)

    def PD_SelectAll_Click(self, sender, args):
        for p in self._pd_params:
            p.IsChecked = True
        self.PD_ParamList.Items.Refresh()

    def PD_ClearAll_Click(self, sender, args):
        for p in self._pd_params:
            p.IsChecked = False
        self.PD_ParamList.Items.Refresh()

    def _pd_save_cfg(self):
        cfg = self.LoadConfig()
        cfg['pd_watched_params'] = self._pd_selected_param_names()
        cfg['pd_baseline']       = self._pd_baseline
        self.SaveConfig(cfg)

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
