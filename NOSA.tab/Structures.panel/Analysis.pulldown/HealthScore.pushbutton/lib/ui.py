# -*- coding: utf-8 -*-
import io
import os
import sys
import csv

import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

# ── local lib path ──────────────────────────────────────────────────────────
_lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

from nosa_utils.loader import load_local_module as _lm
_logic_module = _lm('healthscore_logic_local', os.path.join(os.path.dirname(__file__), 'logic.py'))
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
        self.SaveConfig(cfg)

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

        self.SetLoading(True, "Running checks...")
        self._rows.Clear()
        self.BtnExport.IsEnabled  = False
        self.BtnFix.IsEnabled     = False
        self.BtnSelect.IsEnabled  = False
        self.BtnDetails.IsEnabled = False

        try:
            data = run_all_checks(self.doc, active)
        except Exception as e:
            self.SetLoading(False)
            logger.error("HealthScore run failed", e)
            forms.alert("Error running checks: {}".format(e))
            return

        self._results = data
        score = data['score']

        # Update score gauge
        self.ScoreBar.Value   = score
        self.TxtScore.Text    = str(int(round(score)))
        self.TxtScoreLabel.Text = self._score_label(score)

        # Score bar colour (green >80 / orange >50 / red)
        if score >= 80:
            self.ScoreBar.Foreground = System.Windows.Media.Brushes.SeaGreen
        elif score >= 50:
            self.ScoreBar.Foreground = System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromRgb(255, 95, 0))
        else:
            self.ScoreBar.Foreground = System.Windows.Media.Brushes.Crimson

        # Summary pills
        checks = data['checks']
        high   = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'High')
        med    = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'Medium')
        low    = sum(1 for c in checks if c['count'] > 0 and c['severity'] == 'Low')
        self.TxtCountHigh.Text = "{} High".format(high)
        self.TxtCountMed.Text  = "{} Medium".format(med)
        self.TxtCountLow.Text  = "{} Low".format(low)

        # Populate grid
        for c in checks:
            row = CheckRow(
                c['key'], c['label'], c['count'],
                c['severity'], c['weight'],
                data['results'].get(c['key'], [])
            )
            self._rows.Add(row)

        self.SetLoading(False)
        self.BtnExport.IsEnabled = True

        # Persist score history
        try:
            title = self.doc.Title or 'Unknown'
            _logic_module.save_score_history(title, score, data['counts'])
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
            from pyrevit import DB
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
            from pyrevit import DB
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
            from pyrevit import DB
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
            from pyrevit import DB
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
            from pyrevit import DB
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
