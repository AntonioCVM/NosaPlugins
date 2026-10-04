# -*- coding: utf-8 -*-
import io
import os
import sys
import csv

import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit
from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils import unit_conversion as _uc10
from nosa_utils.revit_helpers import element_id_from_int
from nosa_utils.bootstrap import load_module
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_logic = load_module('pilechk_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class PhaseItem(object):
    def __init__(self, phase_id, name):
        self.PhaseId = phase_id
        self.Name    = name


class CapRow(object):
    def __init__(self, r):
        self.Status    = r['status']
        self.Etype     = r.get('type', 'Cap')
        self.Name      = r['name']
        self.PileCount = r['pile_count']
        self.IssueText = (
            ' | '.join(
                "{check}: {value} (limit {limit})".format(**i) for i in r['issues']
            ) if r['issues'] else 'OK'
        )
        self.Id        = r['id']
        self.Issues    = r['issues']
        _fmt = lambda v: u'{:.1f}'.format(v) if v is not None else u'—'
        self.N_kN      = _fmt(r.get('N_kN'))
        self.Mx_kNm    = _fmt(r.get('Mx_kNm'))
        self.My_kNm    = _fmt(r.get('My_kNm'))
        self.Util      = u'{:.0%}'.format(r['util']) if r.get('util') is not None else u'—'
        self.Semaphore = r.get('semaphore', u'—')


class ParamEditRow(object):
    def __init__(self, d):
        self.ParamName    = d.get('name', '')
        self.Value        = str(d.get('value', ''))
        self.Unit         = d.get('unit', '')
        self._bip_or_name = d.get('bip_or_name')


class PilecapLoadCheckerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'pilecap_load_checker')
        self.doc       = doc
        self._rows     = ObservableCollection[CapRow]()
        self._edit_rows = ObservableCollection[ParamEditRow]()
        self.GridResults.ItemsSource   = self._rows
        self.GridEditParams.ItemsSource = self._edit_rows
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._load_phases()
        self._load_rules_to_ui()

    # ── phases ───────────────────────────────────────────────────────────────

    def _load_phases(self):
        self.CmbPhase.Items.Clear()
        self.CmbPhase.Items.Add(PhaseItem(None, '(All phases)'))
        for ph in _logic.get_phases(self.doc):
            self.CmbPhase.Items.Add(PhaseItem(ph['id'], ph['name']))
        self.CmbPhase.SelectedIndex = 0

    # ── rules UI helpers ─────────────────────────────────────────────────────

    def _load_rules_to_ui(self):
        rules = _logic.load_rules()
        self.TxtSpacing.Text    = str(rules.get('min_pile_spacing_diameters',  3.0))
        self.TxtEdge.Text       = str(rules.get('min_edge_distance_diameters', 1.5))
        self.TxtDepth.Text      = str(rules.get('min_cap_depth_mm',            600))
        self.TxtAspect.Text     = str(rules.get('max_cap_aspect_ratio',        2.5))
        self.TxtEmbedment.Text  = str(rules.get('min_cutoff_embedment_mm',      75))
        self.TxtBearingCap.Text = str(rules.get('pile_bearing_capacity_kN',  2000.0))

    def _rules_from_ui(self):
        def _f(txt, default):
            try:
                return float(txt)
            except (ValueError, TypeError):
                return default
        return {
            'min_pile_spacing_diameters':  _f(self.TxtSpacing.Text,    3.0),
            'min_edge_distance_diameters': _f(self.TxtEdge.Text,       1.5),
            'min_cap_depth_mm':            _f(self.TxtDepth.Text,      600),
            'max_cap_aspect_ratio':        _f(self.TxtAspect.Text,     2.5),
            'min_cutoff_embedment_mm':     _f(self.TxtEmbedment.Text,   75),
            'pile_bearing_capacity_kN':    _f(self.TxtBearingCap.Text, 2000.0),
        }

    def _selected_bics(self):
        bics = set()
        if self.ChkIncludeCaps.IsChecked   == True: bics.add('caps')
        if self.ChkIncludeStrip.IsChecked  == True: bics.add('strips')
        if self.ChkIncludeWalls.IsChecked  == True: bics.add('walls')
        return bics or {'caps'}

    def _selected_phase_id(self):
        sel = self.CmbPhase.SelectedItem
        if sel is None:
            return None
        return sel.PhaseId

    # ── edit panel helpers ───────────────────────────────────────────────────

    def _load_edit_params(self, cap_id):
        self._edit_rows.Clear()
        try:
            params = _logic.get_editable_params(self.doc, cap_id)
            for p in params:
                self._edit_rows.Add(ParamEditRow(p))
            vis = System.Windows.Visibility
            self.EditPanel.Visibility = vis.Visible if params else vis.Collapsed
        except Exception as e:
            self.EditPanel.Visibility = System.Windows.Visibility.Collapsed
            forms.alert("Could not load parameters: {}".format(e))

    # ── event handlers ───────────────────────────────────────────────────────

    def SaveRules_Click(self, sender, args):
        rules = self._rules_from_ui()
        if _logic.save_rules(rules):
            forms.alert('Rules saved as default.')
        else:
            forms.alert('Could not save rules file — check folder permissions.')

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking pilecaps...')
        self._rows.Clear()
        self._edit_rows.Clear()
        self.EditPanel.Visibility = System.Windows.Visibility.Collapsed
        self.BtnExport.IsEnabled  = False
        rules    = self._rules_from_ui()
        phase_id = self._selected_phase_id()
        bics     = self._selected_bics()
        try:
            data = _logic.check_all_pilecaps(
                self.doc, phase_id=phase_id, selected_bics=bics, rules=rules)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error: {}".format(e))
            return
        self.TxtOK.Text   = "{} OK".format(data['ok'])
        self.TxtFail.Text = "{} FAIL".format(data['fail'])
        for r in data['results']:
            self._rows.Add(CapRow(r))
        self.SetLoading(False)
        self.BtnExport.IsEnabled = True

    def Grid_SelectionChanged(self, sender, args):
        row = self.GridResults.SelectedItem
        self.BtnSelect.IsEnabled = row is not None
        if row is not None:
            self._load_edit_params(row.Id)
        else:
            self.EditPanel.Visibility = System.Windows.Visibility.Collapsed

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row:
            return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([element_id_from_int(row.Id)])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def ApplyParams_Click(self, sender, args):
        """Write edited parameter values back to the Revit element."""
        row = self.GridResults.SelectedItem
        if not row:
            return
        try:
            el = self.doc.GetElement(element_id_from_int(row.Id))
            if el is None:
                forms.alert("Element not found.")
                return
            ok = fail = 0
            with nosa_tx.revit_transaction("NOSA — Edit pilecap parameters"):
                for erow in self._edit_rows:
                    try:
                        val_mm = float(erow.Value)
                        val_ft = val_mm * _uc10.MM_TO_FT
                        bip_or_name = erow._bip_or_name
                        if isinstance(bip_or_name, DB.BuiltInParameter):
                            p = el.get_Parameter(bip_or_name)
                        else:
                            p = el.LookupParameter(str(bip_or_name))
                        if p and not p.IsReadOnly:
                            p.Set(val_ft)
                            ok += 1
                        else:
                            fail += 1
                    except Exception:
                        fail += 1
            forms.alert("Applied: {}   /   Failed: {}".format(ok, fail))
            # Reload params to reflect saved values
            self._load_edit_params(row.Id)
        except Exception as e:
            forms.alert("Error applying parameters: {}".format(e))

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
                w = csv.writer(f)
                w.writerow(['Status', 'Type', 'Name', 'Piles',
                            'N (kN)', 'Mx (kN·m)', 'My (kN·m)',
                            'Utilisation', 'Load Check', 'Issues'])
                for r in self._rows:
                    w.writerow([r.Status, r.Type, r.Name, r.PileCount,
                                r.N_kN, r.Mx_kNm, r.My_kNm,
                                r.Util, r.Semaphore, r.IssueText])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
