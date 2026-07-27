# -*- coding: utf-8 -*-
import io, json
import os, sys, csv, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit
from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)
_logic = imp.load_source('connchk_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow


class IssueRow(object):
    def __init__(self, d):
        self.Severity = d['severity']
        self.Category = d['category']
        self.Level    = d['level']
        self.Name     = d['name']
        self.Check    = d['check']
        self.Id       = d['id']


class ConnectionCheckerWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'connection_checker')
        self.doc           = doc
        self._rows         = ObservableCollection[IssueRow]()
        self._custom_rules = []
        self.GridResults.ItemsSource = self._rows
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._populate_combos()
        self._load_rules()

    def _populate_combos(self):
        for cond in _logic._CONDITION_OPS:
            self.CboCondition.Items.Add(cond)
        self.CboCondition.SelectedIndex = 0
        for sev in ['High', 'Medium', 'Low']:
            self.CboSeverity.Items.Add(sev)
        self.CboSeverity.SelectedIndex = 1
        for cat in _logic._RULE_CATEGORIES:
            self.CboRuleCat.Items.Add(cat)
        self.CboRuleCat.SelectedIndex = 3  # Any

    def _load_rules(self):
        self._custom_rules = _logic.load_custom_rules()
        self._refresh_rules_list()

    def _refresh_rules_list(self):
        self.LstRules.Items.Clear()
        for r in self._custom_rules:
            lbl = r.get('label') or u'{} — {} {} {}'.format(
                r.get('category', 'Any'), r.get('param', ''),
                r.get('condition', ''), r.get('threshold', ''))
            self.LstRules.Items.Add(u'[{}]  {}'.format(r.get('severity', 'Medium'), lbl))

    def NavTab_Click(self, sender, args):
        tag = (sender.Tag or '').lower()
        self.TabResults.Visibility = System.Windows.Visibility.Collapsed
        self.TabRules.Visibility   = System.Windows.Visibility.Collapsed
        if tag == 'rules':
            self.TabRules.Visibility = System.Windows.Visibility.Visible
        else:
            self.TabResults.Visibility = System.Windows.Visibility.Visible

    def AddRule_Click(self, sender, args):
        param = (self.TxtRuleParam.Text or '').strip()
        if not param:
            forms.alert(u'Enter a parameter name.'); return
        cond = str(self.CboCondition.SelectedItem or 'is_empty')
        thr  = (self.TxtThreshold.Text or '').strip()
        sev  = str(self.CboSeverity.SelectedItem or 'Medium')
        cat  = str(self.CboRuleCat.SelectedItem or 'Any')
        lbl  = (self.TxtRuleLabel.Text or '').strip() or None
        self._custom_rules.append(
            {'param': param, 'condition': cond, 'threshold': thr,
             'severity': sev, 'category': cat, 'label': lbl})
        self._refresh_rules_list()

    def RemoveRule_Click(self, sender, args):
        idx = self.LstRules.SelectedIndex
        if 0 <= idx < len(self._custom_rules):
            del self._custom_rules[idx]
            self._refresh_rules_list()

    def SaveRules_Click(self, sender, args):
        try:
            _logic.save_custom_rules(self._custom_rules)
            forms.alert(u'Rules saved ({} total).'.format(len(self._custom_rules)))
        except Exception as e:
            forms.alert(u'Save failed: {}'.format(e))

    def ImportRules_Click(self, sender, args):
        path = forms.pick_file(file_ext='json')
        if not path: return
        try:
            with io.open(path, encoding='utf-8') as f:
                imported = json.load(f)
            self._custom_rules = imported
            self._refresh_rules_list()
            forms.alert(u'Imported {} rule(s).'.format(len(imported)))
        except Exception as e:
            forms.alert(u'Import failed: {}'.format(e))

    def ExportRules_Click(self, sender, args):
        path = forms.save_file(file_ext='json')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8') as f:
                json.dump(self._custom_rules, f, indent=2, ensure_ascii=False)
            forms.alert(u'Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    def _active(self):
        active = set()
        if self.ChkAnalytical.IsChecked  == True: active.add('analytical')
        if self.ChkUsage.IsChecked       == True: active.add('usage')
        if self.ChkAttachment.IsChecked  == True: active.add('attachment')
        if self.ChkJoins.IsChecked       == True: active.add('joins')
        return active

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking structural connections...')
        self._rows.Clear(); self.BtnExport.IsEnabled = False; self.BtnExport2.IsEnabled = False
        try:
            data = _logic.run_all_checks(self.doc, self._active(), self._custom_rules or None)
        except Exception as e:
            self.SetLoading(False); forms.alert("Error: {}".format(e)); return
        self.TxtHigh.Text   = "{} High".format(data['high'])
        self.TxtMedium.Text = "{} Medium".format(data['medium'])
        self.TxtLow.Text    = "{} Low".format(data['low'])
        for r in data['issues']:
            self._rows.Add(IssueRow(r))
        self.SetLoading(False)
        self.BtnExport.IsEnabled = self.BtnExport2.IsEnabled = len(data['issues']) > 0
        if len(data['issues']) == 0:
            forms.alert("No connection issues found in the model.\n\nAll checked elements look good.",
                        title="Connection Checker")

    def Grid_SelectionChanged(self, sender, args):
        has = self.GridResults.SelectedItem is not None
        self.BtnSelect.IsEnabled = has

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row: return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Severity', 'Category', 'Level', 'Name', 'Check'])
                for r in self._rows:
                    w.writerow([r.Severity, r.Category, r.Level, r.Name, r.Check])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
