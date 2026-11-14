# -*- coding: utf-8 -*-
import io
import os
import sys
import csv

import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit
from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'elementjoin'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.revit_helpers import element_id_from_int
from nosa_utils.bootstrap import load_module
_logic = load_module('elemjoin_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


# ── Data rows ────────────────────────────────────────────────────────────────

class JoinRow(object):
    def __init__(self, r):
        self.Status = r['status']
        self.Cat1   = r['cat1']
        self.Name1  = r['name1']
        self.Cat2   = r['cat2']
        self.Name2  = r['name2']
        self.Msg    = r.get('msg', '')
        self.Id1    = r['id1']
        self.Id2    = r['id2']


class PriorityItem(object):
    """One row in the priority ListBox."""
    def __init__(self, rank, name):
        self.Rank = "{}. ".format(rank)
        self.Name = name
        self._name = name  # raw name for logic

    @property
    def CategoryName(self):
        return self._name


# ── Main window ──────────────────────────────────────────────────────────────

class ElementJoinWindow(NOSAWindow):

    # ── init ─────────────────────────────────────────────────────────────────

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'smartjoin_pro')
        self.doc       = doc
        self._rows     = ObservableCollection[JoinRow]()
        self._picked_a = None
        self._picked_b = None
        self.GridResults.ItemsSource = self._rows

        self._priority_items = ObservableCollection[PriorityItem]()
        self.LstPriority.ItemsSource = self._priority_items
        self._load_priority_list()

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._active_tab = 'join'
        self._update_tabs()

    # ── priority helpers ─────────────────────────────────────────────────────

    def _load_priority_list(self):
        self._priority_items.Clear()
        priority = _logic.load_priority()
        for i, cat in enumerate(priority, 1):
            self._priority_items.Add(PriorityItem(i, cat))

    def _current_priority(self):
        return [item.CategoryName for item in self._priority_items]

    def _refresh_ranks(self):
        for i, item in enumerate(self._priority_items, 1):
            item.Rank = "{}. ".format(i)
        self.LstPriority.Items.Refresh()

    def MoveUp_Click(self, sender, args):
        idx = self.LstPriority.SelectedIndex
        if idx <= 0:
            return
        item = self._priority_items[idx]
        self._priority_items.RemoveAt(idx)
        self._priority_items.Insert(idx - 1, item)
        self.LstPriority.SelectedIndex = idx - 1
        self._refresh_ranks()
        _logic.save_priority(self._current_priority())

    def MoveDown_Click(self, sender, args):
        idx = self.LstPriority.SelectedIndex
        if idx < 0 or idx >= self._priority_items.Count - 1:
            return
        item = self._priority_items[idx]
        self._priority_items.RemoveAt(idx)
        self._priority_items.Insert(idx + 1, item)
        self.LstPriority.SelectedIndex = idx + 1
        self._refresh_ranks()
        _logic.save_priority(self._current_priority())

    def ResetPriority_Click(self, sender, args):
        _logic.save_priority(_logic.DEFAULT_PRIORITY)
        self._load_priority_list()

    # ── tab navigation ───────────────────────────────────────────────────────

    def TabJoin_Click(self, sender, args):
        self._active_tab = 'join'
        self._update_tabs()

    def TabPriority_Click(self, sender, args):
        self._active_tab = 'priority'
        self._update_tabs()

    def TabManual_Click(self, sender, args):
        self._active_tab = 'manual'
        self._update_tabs()

    def _update_tabs(self):
        vis = System.Windows.Visibility
        tabs = {
            'join':     (self.PanelTabJoin,     self.BtnTabJoin),
            'priority': (self.PanelTabPriority, self.BtnTabPriority),
            'manual':   (self.PanelTabManual,   self.BtnTabManual),
        }
        for key, (panel, btn) in tabs.items():
            panel.Visibility = vis.Visible if key == self._active_tab else vis.Collapsed
            btn.Tag = "Selected" if key == self._active_tab else ""
        priority = self._active_tab == 'priority'
        self.BtnPreview.Visibility = vis.Collapsed if priority else vis.Visible
        System.Windows.Controls.Grid.SetColumn(self.BtnRun, 0 if priority else 2)
        System.Windows.Controls.Grid.SetColumnSpan(self.BtnRun, 3 if priority else 1)
        for btn in (self.BtnSelect, self.BtnSelectFailed, self.BtnExport):
            btn.Visibility = vis.Collapsed if priority else vis.Visible

        # RUN button label
        if self._active_tab == 'manual':
            self.BtnRun.Content = "APPLY"
        elif self._active_tab == 'priority':
            self.BtnRun.Content = "SAVE & CLOSE"
        else:
            self.BtnRun.Content = "RUN"

    # ── category / operation helpers ─────────────────────────────────────────

    def _selected_categories(self):
        cats = []
        if self.ChkFloors.IsChecked      == True: cats.append('Floors')
        if self.ChkFraming.IsChecked     == True: cats.append('Framing')
        if self.ChkColumns.IsChecked     == True: cats.append('Columns')
        if self.ChkWalls.IsChecked       == True: cats.append('Walls')
        if self.ChkFoundations.IsChecked == True: cats.append('Foundations')
        if self.ChkRoofs.IsChecked       == True: cats.append('Roofs')
        if self.ChkCeilings.IsChecked    == True: cats.append('Ceilings')
        return cats

    def _tolerance_mm(self):
        try:
            return float(self.TxtTolerance.Text)
        except (ValueError, TypeError):
            return 50.0

    # ── settings / scope helpers ─────────────────────────────────────────────

    def _settings(self):
        return _logic.Settings(
            priority=self._current_priority(),
            tolerance_mm=self._tolerance_mm(),
            fix_existing=self.ChkFixExisting.IsChecked == True,
            require_overlap=self.ChkOverlapOnly.IsChecked == True,
            simple=self.RbJoinSimple.IsChecked == True)

    def _batch_operation(self):
        if self.RbUnjoin.IsChecked == True:
            return 'unjoin'
        if self.RbSwap.IsChecked == True:
            return 'swap'
        return 'join'

    # ── manual pick ─────────────────────────────────────────────────────────

    def _pick(self, prompt):
        self.Hide()
        try:
            from Autodesk.Revit.UI.Selection import ObjectType
            ref = revit.uidoc.Selection.PickObject(ObjectType.Element, prompt)
            return self.doc.GetElement(ref.ElementId)
        except Exception:
            log_swallowed(_LOG, u'ElementJoinWindow._pick')
            return None
        finally:
            self.Show()

    def PickA_Click(self, sender, args):
        el = self._pick("Pick Element A (dominant)")
        if el is not None:
            self._picked_a = el
            self.TxtPickedA.Text = "A: {}".format(element_name(el) or get_id_value(el.Id))

    def PickB_Click(self, sender, args):
        el = self._pick("Pick Element B (subordinate)")
        if el is not None:
            self._picked_b = el
            self.TxtPickedB.Text = "B: {}".format(element_name(el) or get_id_value(el.Id))

    # ── main run ─────────────────────────────────────────────────────────────

    def Run_Click(self, sender, args):
        if self._active_tab == 'priority':
            self.Close()
            return
        self._run(preview=False)

    def Preview_Click(self, sender, args):
        if self._active_tab != 'priority':
            self._run(preview=True)

    def _run(self, preview):
        self.SetLoading(True, 'Checking the elements...')
        self._rows.Clear()
        self.BtnExport.IsEnabled = False
        self.BtnSelect.IsEnabled = False
        self.BtnSelectFailed.IsEnabled = False
        try:
            rows, tx_name = (self._manual_rows() if self._active_tab == 'manual' else self._batch_rows())
            if rows is None:
                return
            self.SetLoading(True, 'Processing {} pairs...'.format(len(rows)))
            results = _logic.execute(self.doc, rows, preview, tx_name)
        except Exception as e:
            forms.alert("Operation failed: {}".format(e))
            return
        finally:
            self.SetLoading(False)
        self._show(results, preview)

    def _batch_rows(self):
        cats = self._selected_categories()
        if not cats:
            forms.alert("Select at least one category.")
            return None, ''
        op = self._batch_operation()
        universe = _logic.collect_joinable_elements(self.doc, cats)
        primary = None
        if self.RbSelection.IsChecked == True:
            primary = _logic.items_from_ids(self.doc, list(revit.uidoc.Selection.GetElementIds()), cats)
            if not primary:
                forms.alert("None of the selected elements belongs to the ticked categories.")
                return None, ''
        if op == 'join':
            return _logic.plan_join(self.doc, universe, primary, self._settings()), 'Join'
        return _logic.plan_joined(self.doc, universe, primary, op), op.capitalize()

    def _manual_rows(self):
        many = self.RbTargetCats.IsChecked == True
        if self._picked_a is None or (not many and self._picked_b is None):
            forms.alert("Please pick Element A{}.".format('' if many else ' and Element B'))
            return None, ''
        op = ('unjoin' if self.RbManualUnjoin.IsChecked == True else
              'swap'   if self.RbManualSwap.IsChecked   == True else 'join')
        a = _logic.item_from_element(self._picked_a)
        if many:
            cats = self._selected_categories()
            if not cats:
                forms.alert("Tick at least one category in the Join / Unjoin tab.")
                return None, ''
            universe = _logic.collect_joinable_elements(self.doc, cats)
            if op == 'join':
                return _logic.plan_one_to_many(self.doc, a, universe, self._settings(),
                                               self.ChkReverse.IsChecked != True), 'Manual'
            if not any(u['id'] == a['id'] for u in universe):
                universe.append(a)
            return _logic.plan_joined(self.doc, universe, [a], op), 'Manual'
        b = _logic.item_from_element(self._picked_b)
        if op == 'join':
            return _logic.plan_pair(self.doc, a, b, self._settings()), 'Manual'
        if not _logic.is_joined(self.doc, a['element'], b['element']):
            return [{'a': a, 'b': b, 'action': 'skip', 'dominant': None,
                     'msg': u'The elements are not joined'}], 'Manual'
        return [{'a': a, 'b': b, 'action': op, 'dominant': None, 'msg': u'Joined'}], 'Manual'

    def _show(self, results, preview):
        changed = fixed = failed = skipped = 0
        for r in results:
            self._rows.Add(JoinRow(r))
            s = r['status']
            if s in ('joined', 'unjoined', 'swapped', 'will join', 'will unjoin', 'will swap'):
                changed += 1
            elif s in ('fixed', 'will fix'):
                fixed += 1
            elif s == 'failed':
                failed += 1
            else:
                skipped += 1
        self._update_pills(changed, fixed, failed, skipped, preview)
        self.BtnExport.IsEnabled = len(results) > 0
        self.BtnSelectFailed.IsEnabled = failed > 0

    def _update_pills(self, changed, fixed, failed, skipped, preview=False):
        self.TxtJoined.Text  = "{} {}".format(changed, "to change" if preview else "changed")
        self.TxtFixed.Text   = "{} {}".format(fixed, "to fix" if preview else "fixed")
        self.TxtFailed.Text  = "{} failed".format(failed)
        self.TxtSkipped.Text = "{} skipped / ok".format(skipped)

    def SelectFailed_Click(self, sender, args):
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]()
            for r in self._rows:
                if r.Status == 'failed':
                    ids.Add(element_id_from_int(r.Id1))
                    ids.Add(element_id_from_int(r.Id2))
            if ids.Count:
                revit.uidoc.Selection.SetElementIds(ids)
                revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    # ── grid / select / export ───────────────────────────────────────────────

    def Grid_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridResults.SelectedItem is not None

    def Select_Click(self, sender, args):
        row = self.GridResults.SelectedItem
        if not row:
            return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([
                element_id_from_int(row.Id1),
                element_id_from_int(row.Id2),
            ])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
                w = csv.writer(f)
                w.writerow(['Status', 'Category A', 'Element A', 'Category B', 'Element B', 'Note'])
                for r in self._rows:
                    w.writerow([r.Status, r.Cat1, r.Name1, r.Cat2, r.Name2, r.Msg])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
