# -*- coding: utf-8 -*-
import imp
import io
import os
import sys
import csv
import datetime

import System.Windows
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit
from Autodesk.Revit import DB

# ── local lib path ──────────────────────────────────────────────────────────
_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

_logic_module = imp.load_source('healthscore_logic_local', os.path.join(os.path.dirname(__file__), 'logic.py'))
run_all_checks = _logic_module.run_all_checks

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger

logger = Logger()


# ── Data model for DataGrid ─────────────────────────────────────────────────

class CheckRow(object):
    def __init__(self, key, label, count, severity, weight, issues):
        self.Key      = key
        self.Label    = label
        self.Count    = count
        self.Severity = severity
        self.Weight   = weight
        self.Issues   = issues  # raw list of dicts

        max_for_zero  = {
            'no_material': 20, 'no_analytical': 10, 'orphan_found': 5,
            'warnings': 30, 'param_missing': 30, 'bad_offset': 10,
        }
        cap = max_for_zero.get(key, 10)
        ratio  = min(1.0, count / float(cap)) if cap > 0 else float(count > 0)
        deduct = round(weight * ratio, 1)
        self.Impact = "-{} pts".format(deduct) if deduct > 0 else "OK"
        self.Detail = (
            "{} issues found".format(count) if count > 0
            else "No issues detected"
        )


# ── Main window ─────────────────────────────────────────────────────────────

class HealthScoreWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'health_score')
        self.doc      = doc
        self._rows    = ObservableCollection[CheckRow]()
        self._results = None

        self.GridResults.ItemsSource = self._rows
        self._restore_config()
        # Draw trend chart from existing history
        try:
            title = self.doc.Title or 'Unknown'
            history = _logic_module.get_score_history(title)
            self._draw_trend(history)
        except Exception:
            pass

    # ── Config ──────────────────────────────────────────────────────────────

    def _restore_config(self):
        cfg = self.LoadConfig()
        dm = cfg.get('dark_mode', self.dark_mode)
        if dm != self.dark_mode:
            self.ApplyTheme(dm)
        self.ChkDarkMode.IsChecked = self.dark_mode

    def _save_config(self):
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        cfg['checks'] = {
            'no_material':    self.ChkMaterial.IsChecked == True,
            'no_analytical':  self.ChkAnalytical.IsChecked == True,
            'orphan_found':   self.ChkOrphan.IsChecked == True,
            'warnings':       self.ChkWarnings.IsChecked == True,
            'param_missing':  self.ChkParams.IsChecked == True,
            'bad_offset':     self.ChkOffsets.IsChecked == True,
            'dup_marks':      self.ChkDupMarks.IsChecked == True,
            'no_level':       self.ChkNoLevel.IsChecked == True,
            'unhosted_rebar': self.ChkUnhostedRebar.IsChecked == True,
        }
        cfg['weights'] = self._get_weights()
        self.SaveConfig(cfg)

    def _get_weights(self):
        """Read weight slider values from the UI."""
        def _v(slider):
            try: return int(slider.Value)
            except Exception: return 10
        return {
            'no_material':    _v(self.SldMaterial),
            'no_analytical':  _v(self.SldAnalytical),
            'orphan_found':   _v(self.SldOrphan),
            'warnings':       _v(self.SldWarnings),
            'param_missing':  _v(self.SldParams),
            'bad_offset':     _v(self.SldOffsets),
            'dup_marks':      _v(self.SldDupMarks),
            'no_level':       _v(self.SldNoLevel),
            'unhosted_rebar': _v(self.SldRebar),
        }

    def _draw_trend(self, history):
        """Draw a polyline score trend on TrendCanvas."""
        try:
            canvas = self.TrendCanvas
            canvas.Children.Clear()
            entries = [e for e in history if isinstance(e.get('score'), (int, float))]
            if len(entries) < 2:
                lbl = SWC.TextBlock()
                lbl.Text = u'No trend yet — run more checks to see history.'
                lbl.FontSize = 10
                lbl.Opacity = 0.5
                SWC.Canvas.SetLeft(lbl, 10)
                SWC.Canvas.SetTop(lbl, 28)
                canvas.Children.Add(lbl)
                return

            points = SWM.PointCollection()
            n   = len(entries)
            w   = 0.0  # will be read after layout; use 600 as fallback
            h   = 72.0
            w   = max(canvas.ActualWidth, 600.0)
            step = w / max(n - 1, 1)

            # grid lines at 25, 50, 75, 100
            for pct in [25, 50, 75, 100]:
                y = h - (pct / 100.0) * h
                line = SWS.Line()
                line.X1 = 0; line.Y1 = y; line.X2 = w; line.Y2 = y
                line.Stroke = SWM.SolidColorBrush(SWM.Color.FromArgb(30, 0, 0, 0))
                line.StrokeThickness = 1
                canvas.Children.Add(line)
                lbl = SWC.TextBlock()
                lbl.Text = str(pct)
                lbl.FontSize = 8
                lbl.Opacity = 0.4
                SWC.Canvas.SetLeft(lbl, 2)
                SWC.Canvas.SetTop(lbl, y - 9)
                canvas.Children.Add(lbl)

            for i, entry in enumerate(entries):
                score = min(max(entry['score'], 0), 100)
                x = i * step
                y = h - (score / 100.0) * h
                points.Add(SWM.Point(x, y))

            pl = SWS.Polyline()
            pl.Points = points
            pl.Stroke = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 95, 0))
            pl.StrokeThickness = 2.5
            pl.StrokeLineJoin = SWM.PenLineJoin.Round
            canvas.Children.Add(pl)

            # Dots + date labels
            for i, entry in enumerate(entries):
                score = min(max(entry['score'], 0), 100)
                x = i * step
                y = h - (score / 100.0) * h
                dot = SWS.Ellipse()
                dot.Width = 7; dot.Height = 7
                dot.Fill = SWM.SolidColorBrush(SWM.Color.FromRgb(255, 95, 0))
                SWC.Canvas.SetLeft(dot, x - 3.5)
                SWC.Canvas.SetTop(dot, y - 3.5)
                canvas.Children.Add(dot)

                # Show date for first, last and every 5th point
                if i == 0 or i == n - 1 or i % 5 == 0:
                    date_str = entry.get('date', '')[:10]
                    date_lbl = SWC.TextBlock()
                    date_lbl.Text = date_str
                    date_lbl.FontSize = 8
                    date_lbl.Opacity = 0.55
                    SWC.Canvas.SetLeft(date_lbl, max(0, x - 18))
                    SWC.Canvas.SetTop(date_lbl, h)
                    canvas.Children.Add(date_lbl)
        except Exception:
            pass

    # ── UI event handlers ───────────────────────────────────────────────────

    def Run_Click(self, sender, args):
        self._save_config()
        active = set()
        if self.ChkMaterial.IsChecked      == True: active.add('no_material')
        if self.ChkAnalytical.IsChecked    == True: active.add('no_analytical')
        if self.ChkOrphan.IsChecked        == True: active.add('orphan_found')
        if self.ChkWarnings.IsChecked      == True: active.add('warnings')
        if self.ChkParams.IsChecked        == True: active.add('param_missing')
        if self.ChkOffsets.IsChecked       == True: active.add('bad_offset')
        if self.ChkDupMarks.IsChecked      == True: active.add('dup_marks')
        if self.ChkNoLevel.IsChecked       == True: active.add('no_level')
        if self.ChkUnhostedRebar.IsChecked == True: active.add('unhosted_rebar')

        weights = self._get_weights()

        self.SetLoading(True, "Running checks...")
        self._rows.Clear()
        self.BtnExport.IsEnabled  = False
        self.BtnReport.IsEnabled  = False
        self.BtnFix.IsEnabled     = False
        self.BtnSelect.IsEnabled  = False
        self.BtnDetails.IsEnabled = False

        try:
            data = run_all_checks(self.doc, active, weights=weights)
        except Exception as e:
            self.SetLoading(False)
            logger.error("HealthScore run failed", e)
            forms.alert("Error running checks: {}".format(e))
            return

        self._results = data
        score = data['score']

        self.ScoreBar.Value     = score
        self.TxtScore.Text      = str(int(round(score)))
        self.TxtScoreLabel.Text = self._score_label(score)

        if score >= 80:
            self.ScoreBar.Foreground = SWM.Brushes.SeaGreen
        elif score >= 50:
            self.ScoreBar.Foreground = SWM.SolidColorBrush(
                SWM.Color.FromRgb(255, 95, 0))
        else:
            self.ScoreBar.Foreground = SWM.Brushes.Crimson

        checks = data['checks']
        high = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'High')
        med  = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'Medium')
        low  = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'Low')
        self.TxtCountHigh.Text = "{} High".format(high)
        self.TxtCountMed.Text  = "{} Medium".format(med)
        self.TxtCountLow.Text  = "{} Low".format(low)

        for c in checks:
            self._rows.Add(CheckRow(
                c['key'], c['label'], c['count'],
                c['severity'], c['weight'],
                data['results'].get(c['key'], [])
            ))

        self.SetLoading(False)
        self.BtnExport.IsEnabled = True
        self.BtnReport.IsEnabled = True

        try:
            title = self.doc.Title or 'Unknown'
            _logic_module.save_score_history(title, score, data['counts'])
            history = _logic_module.get_score_history(title)
            self._draw_trend(history)
        except Exception:
            pass

    def History_Click(self, sender, args):
        try:
            title   = self.doc.Title or 'Unknown'
            history = _logic_module.get_score_history(title)
        except Exception as e:
            forms.alert("Could not load history: {}".format(e))
            return
        if not history:
            forms.alert("No score history for this document yet.\nRun a health check to record the first entry.",
                        title="Score History")
            return
        lines = ["Score history for: {}\n".format(title)]
        for entry in reversed(history[-10:]):
            lines.append("{}  →  {}/100".format(entry.get('date', '?'), entry.get('score', '?')))
        forms.alert("\n".join(lines), title="Score History")

    def Report_Click(self, sender, args):
        """Generate an HTML health report and open it in the default browser."""
        if not self._results:
            return
        path = forms.save_file(file_ext='html')
        if not path:
            return
        try:
            self._export_html(path)
            import subprocess
            subprocess.Popen(['start', '', path], shell=True)
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    def _export_html(self, path):
        score   = self._results['score']
        title   = self.doc.Title or 'Revit Model'
        now     = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        col     = '#4CAF50' if score >= 80 else ('#FF9800' if score >= 50 else '#F44336')
        rows_html = []
        for row in self._rows:
            sev_col = {'High': '#F44336', 'Medium': '#FF9800', 'Low': '#607D8B'}.get(
                row.Severity, '#888')
            rows_html.append(u"""
            <tr>
              <td>{label}</td>
              <td>{count}</td>
              <td style="color:{sev_col};font-weight:bold">{sev}</td>
              <td>{weight}</td>
              <td>{impact}</td>
              <td>{detail}</td>
            </tr>""".format(
                label=row.Label, count=row.Count,
                sev_col=sev_col, sev=row.Severity,
                weight=row.Weight, impact=row.Impact,
                detail=row.Detail))

        html = u"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Health Report — {title}</title>
<style>
  body{{font-family:'Century Gothic',Arial,sans-serif;margin:0;background:#f5f5f5;color:#333}}
  .header{{background:#333;padding:24px 32px;color:white}}
  .header h1{{margin:0;font-size:22px;color:#FF5F00}}
  .header p{{margin:4px 0 0;opacity:.7;font-size:13px}}
  .score-box{{display:inline-block;background:white;border-radius:8px;padding:20px 32px;
              margin:24px 32px;box-shadow:0 1px 4px rgba(0,0,0,.12)}}
  .score-num{{font-size:64px;font-weight:bold;color:{col};line-height:1}}
  .score-lbl{{font-size:13px;opacity:.65;margin-top:4px}}
  .bar-wrap{{background:#e0e0e0;border-radius:4px;height:12px;width:280px;margin:10px 0}}
  .bar-fill{{background:{col};height:12px;border-radius:4px;width:{pct}%}}
  table{{border-collapse:collapse;width:calc(100% - 64px);margin:0 32px 32px;background:white;
         border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  th{{background:#FF5F00;color:white;padding:10px 14px;text-align:left;font-size:12px}}
  td{{padding:9px 14px;border-bottom:1px solid #eee;font-size:12px}}
  tr:hover td{{background:#fff8f4}}
  .footer{{text-align:center;padding:16px;font-size:11px;opacity:.45}}
</style>
</head>
<body>
<div class="header">
  <h1>NOSA Structural Health Report</h1>
  <p>{title} &nbsp;·&nbsp; {now}</p>
</div>
<div class="score-box">
  <div class="score-num">{score_int}</div>
  <div class="bar-wrap"><div class="bar-fill"></div></div>
  <div class="score-lbl">{label}</div>
</div>
<table>
  <thead>
    <tr><th>Check</th><th>Issues</th><th>Severity</th>
        <th>Weight</th><th>Score Impact</th><th>Detail</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
<div class="footer">Generated by NOSA Health Score &nbsp;·&nbsp; NOSA Engineering Gibraltar</div>
</body>
</html>""".format(
            title=title, now=now, col=col,
            pct=min(100, max(0, int(score))),
            score_int=int(round(score)),
            label=self._score_label(score),
            rows=u''.join(rows_html))

        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    def _score_label(self, score):
        if score >= 90: return "Excellent — model is in great shape."
        if score >= 75: return "Good — minor issues to review."
        if score >= 50: return "Fair — several issues need attention."
        return "Poor — critical issues found."

    def Grid_SelectionChanged(self, sender, args):
        has = self.GridResults.SelectedItem is not None
        self.BtnFix.IsEnabled     = has
        self.BtnSelect.IsEnabled  = has
        self.BtnDetails.IsEnabled = has

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row or not row.Issues:
            forms.alert("No issues to select for this check.")
            return
        try:
            from System.Collections.Generic import List
            ids = []
            for issue in row.Issues:
                try:
                    raw_id = issue.get('id')
                    if raw_id is None:
                        continue
                    eid = DB.ElementId(int(raw_id))
                    # Validate the element actually exists
                    if self.doc.GetElement(eid) is not None:
                        ids.append(eid)
                except Exception:
                    pass
            if not ids:
                forms.alert("No selectable elements found for this check.\n(Warning IDs are not selectable directly — try 'View Issue Details').")
                return
            id_list = List[DB.ElementId](ids)
            revit.uidoc.Selection.SetElementIds(id_list)
            try:
                revit.uidoc.ShowElements(id_list)
            except Exception:
                pass  # ShowElements may fail for elements not in active view; selection still applied
            forms.alert("{} element(s) selected.".format(len(ids)))
        except Exception as e:
            forms.alert("Could not select elements: {}".format(e))

    def Details_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row:
            return
        if not row.Issues:
            forms.alert("No issues for: {}".format(row.Label))
            return
        lines = []
        for i, issue in enumerate(row.Issues[:20], 1):
            name = issue.get('name') or issue.get('warning', '')
            cat  = issue.get('category', '')
            eid  = issue.get('id', '')
            lines.append("{}. [{}] {} (ID:{})".format(i, cat, name, eid))
        if len(row.Issues) > 20:
            lines.append("... and {} more.".format(len(row.Issues) - 20))
        forms.alert("\n".join(lines), title=row.Label)

    # ── Fix actions ─────────────────────────────────────────────────────────

    def Fix_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row:
            return
        key = row.Key

        if key == 'no_material':
            self._fix_no_material(row)
        elif key == 'no_analytical':
            self._fix_no_analytical(row)
        elif key == 'param_missing':
            self._fix_param_missing(row)
        elif key == 'bad_offset':
            self._fix_bad_offset(row)
        else:
            forms.alert(
                "No automatic fix available for: {}\n\nReview manually.".format(row.Label)
            )

    def _fix_no_material(self, row):
        """Prompt user to pick a material and assign it to all affected elements."""
        if not row.Issues:
            forms.alert("No elements to fix.")
            return
        try:
            mats = list(
                DB.FilteredElementCollector(self.doc)
                  .OfClass(DB.Material)
                  .ToElements()
            )
            mat_names = sorted(m.Name for m in mats if m.Name)
            chosen_name = forms.SelectFromList.show(
                mat_names, title="Select Material to Assign",
                multiselect=False
            )
            if not chosen_name:
                return
            mat = next((m for m in mats if m.Name == chosen_name), None)
            if mat is None:
                forms.alert("Material not found.")
                return
            with DB.Transaction(self.doc, "Assign Material") as t:
                t.Start()
                fixed = 0
                for issue in row.Issues:
                    try:
                        el = self.doc.GetElement(DB.ElementId(int(issue['id'])))
                        if el is None:
                            continue
                        p = el.get_Parameter(
                            DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                        if p and not p.IsReadOnly:
                            p.Set(mat.Id)
                            fixed += 1
                    except Exception:
                        pass
                t.Commit()
            forms.alert("Assigned '{}' to {} element(s).".format(chosen_name, fixed))
        except Exception as e:
            forms.alert("Fix failed: {}".format(e))

    def _fix_no_analytical(self, row):
        """Enable analytical model on all affected elements."""
        if not row.Issues:
            forms.alert("No elements to fix.")
            return
        try:
            with DB.Transaction(self.doc, "Enable Analytical Model") as t:
                t.Start()
                fixed = 0
                for issue in row.Issues:
                    try:
                        el = self.doc.GetElement(DB.ElementId(int(issue['id'])))
                        if el is None:
                            continue
                        p = el.get_Parameter(
                            DB.BuiltInParameter.STRUCTURAL_ANALYTICAL_MODEL)
                        if p and not p.IsReadOnly:
                            p.Set(1)
                            fixed += 1
                    except Exception:
                        pass
                t.Commit()
            forms.alert("Analytical model enabled on {} element(s).".format(fixed))
        except Exception as e:
            forms.alert("Fix failed: {}".format(e))

    def _fix_param_missing(self, row):
        """Prompt for a Mark value and apply it to all elements missing Mark."""
        if not row.Issues:
            forms.alert("No elements to fix.")
            return
        mark_val = forms.ask_for_string(
            prompt="Enter Mark value to assign to all {} elements:".format(
                len(row.Issues)),
            title="Set Mark Parameter"
        )
        if not mark_val:
            return
        try:
            with DB.Transaction(self.doc, "Set Mark Parameter") as t:
                t.Start()
                fixed = 0
                for issue in row.Issues:
                    try:
                        el = self.doc.GetElement(DB.ElementId(int(issue['id'])))
                        if el is None:
                            continue
                        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                        if p and not p.IsReadOnly:
                            p.Set(mark_val)
                            fixed += 1
                    except Exception:
                        pass
                t.Commit()
            forms.alert("Mark set to '{}' on {} element(s).".format(mark_val, fixed))
        except Exception as e:
            forms.alert("Fix failed: {}".format(e))

    def _fix_bad_offset(self, row):
        """Show details and offer to reset level offset to 0 for all affected elements."""
        if not row.Issues:
            forms.alert("No elements to fix.")
            return
        lines = []
        for i, issue in enumerate(row.Issues[:15], 1):
            lines.append("{}. [{}] {} — offset: {} mm (ID:{})".format(
                i, issue.get('category', ''), issue.get('name', ''),
                issue.get('offset_mm', '?'), issue.get('id', '')))
        if len(row.Issues) > 15:
            lines.append("... and {} more.".format(len(row.Issues) - 15))
        detail = "\n".join(lines)
        answer = forms.alert(
            "Elements with excessive level offsets:\n\n{}\n\n"
            "Reset FLOOR_HEIGHTABOVELEVEL_PARAM to 0 for all?".format(detail),
            yes=True, no=True
        )
        if not answer:
            return
        try:
            bips = [
                DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,
                DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM,
            ]
            with DB.Transaction(self.doc, "Reset Level Offsets") as t:
                t.Start()
                fixed = 0
                for issue in row.Issues:
                    try:
                        el = self.doc.GetElement(DB.ElementId(int(issue['id'])))
                        if el is None:
                            continue
                        for bip in bips:
                            p = el.get_Parameter(bip)
                            if p and not p.IsReadOnly:
                                p.Set(0.0)
                        fixed += 1
                    except Exception:
                        pass
                t.Commit()
            forms.alert("Offset reset to 0 on {} element(s).".format(fixed))
        except Exception as e:
            forms.alert("Fix failed: {}".format(e))

    def Export_Click(self, sender, args):
        if not self._results:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Check', 'Issues', 'Severity', 'Score Impact', 'Detail'])
                for row in self._rows:
                    w.writerow([row.Label, row.Count, row.Severity, row.Impact, row.Detail])
                w.writerow([])
                w.writerow(['Overall Score', round(self._results['score'], 1)])
            forms.alert("Exported to:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
