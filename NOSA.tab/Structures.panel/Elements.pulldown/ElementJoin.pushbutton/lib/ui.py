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
from nosa_utils.revit_helpers import get_id_value
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

        # RUN button label
        if self._active_tab == 'manual':
            self.BtnRun.Content = "APPLY TO PAIR"
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
        return cats

    def _tolerance_mm(self):
        try:
            return float(self.TxtTolerance.Text)
        except (ValueError, TypeError):
            return 50.0

    # ── manual pick ─────────────────────────────────────────────────────────

    def PickA_Click(self, sender, args):
        self.Hide()
        try:
            from Autodesk.Revit.UI.Selection import ObjectType
            ref = revit.uidoc.Selection.PickObject(ObjectType.Element, "Pick Element A (dominant)")
            self._picked_a = self.doc.GetElement(ref.ElementId)
            name = getattr(self._picked_a, 'Name', str(self._picked_a.Id)) if self._picked_a else "None"
            self.TxtPickedA.Text = "A: {}".format(name)
        except Exception:
            pass
        self.Show()

    def PickB_Click(self, sender, args):
        self.Hide()
        try:
            from Autodesk.Revit.UI.Selection import ObjectType
            ref = revit.uidoc.Selection.PickObject(ObjectType.Element, "Pick Element B (subordinate)")
            self._picked_b = self.doc.GetElement(ref.ElementId)
            name = getattr(self._picked_b, 'Name', str(self._picked_b.Id)) if self._picked_b else "None"
            self.TxtPickedB.Text = "B: {}".format(name)
        except Exception:
            pass
        self.Show()

    # ── main run ─────────────────────────────────────────────────────────────

    def Run_Click(self, sender, args):
        if self._active_tab == 'priority':
            self.Close()
            return
        if self._active_tab == 'manual':
            self._run_manual()
        else:
            self._run_batch()

    def _run_manual(self):
        if self._picked_a is None or self._picked_b is None:
            forms.alert("Please pick both Element A and Element B first.")
            return
        self._rows.Clear()
        op = ('unjoin' if self.RbManualUnjoin.IsChecked == True else
              'swap'   if self.RbManualSwap.IsChecked   == True else 'join')
        try:
            with revit.Transaction(u"NOSA — Element Join — Manual"):
                if op == 'join':
                    ok, msg = _logic.join_ordered(self.doc, self._picked_a, self._picked_b)
                elif op == 'unjoin':
                    ok, msg = _logic.unjoin_elements(self.doc, self._picked_a, self._picked_b)
                else:
                    ok, msg = _logic.swap_join_order(self.doc, self._picked_a, self._picked_b)
            status = op if ok else 'failed'
            self._rows.Add(JoinRow({
                'id1': get_id_value(self._picked_a.Id),
                'name1': getattr(self._picked_a, 'Name', str(self._picked_a.Id)),
                'cat1': '',
                'id2': get_id_value(self._picked_b.Id),
                'name2': getattr(self._picked_b, 'Name', str(self._picked_b.Id)),
                'cat2': '',
                'status': status, 'msg': msg,
            }))
            self._update_pills(
                joined=1 if ok else 0,
                fixed=0, failed=0 if ok else 1, skipped=0
            )
        except Exception as e:
            forms.alert("Operation failed: {}".format(e))

    def _run_batch(self):
        self.SetLoading(True, 'Collecting elements...')
        self._rows.Clear()
        self.BtnExport.IsEnabled = False
        self.BtnSelect.IsEnabled = False

        cats    = self._selected_categories()
        tol_mm  = self._tolerance_mm()
        priority_join = self.RbJoin.IsChecked == True
        fix_existing  = self.ChkFixExisting.IsChecked == True

        if not cats:
            self.SetLoading(False)
            forms.alert("Select at least one category.")
            return

        try:
            if self.RbSelection.IsChecked == True:
                sel_ids  = list(revit.uidoc.Selection.GetElementIds())
                elements = []
                for eid in sel_ids:
                    try:
                        el = self.doc.GetElement(eid)
                        if el is None:
                            continue
                        for name, bic in _logic._JOINABLE_BICS.items():
                            if el.Category and el.Category.Id == DB.ElementId(bic) and name in cats:
                                elements.append({
                                    'id': get_id_value(el.Id),
                                    'name': getattr(el, 'Name', str(el.Id)),
                                    'category': name,
                                    'element': el,
                                })
                                break
                    except Exception:
                        pass
            else:
                elements = _logic.collect_joinable_elements(self.doc, cats)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Collection failed: {}".format(e))
            return

        self.SetLoading(True, 'Processing {} elements...'.format(len(elements)))

        try:
            if self.RbJoin.IsChecked == True:
                results = _logic.batch_join_ordered(
                    self.doc, elements,
                    priority_list=self._current_priority(),
                    tolerance_mm=tol_mm,
                    fix_existing=fix_existing,
                )
            else:
                operation = ('unjoin' if self.RbUnjoin.IsChecked == True else
                             'swap'   if self.RbSwap.IsChecked   == True else 'join')
                results = _logic.batch_join_by_proximity(
                    self.doc, elements, operation=operation, tolerance_mm=tol_mm)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Operation failed: {}".format(e))
            return

        joined = fixed = failed = skipped = 0
        for r in results:
            self._rows.Add(JoinRow(r))
            s = r['status']
            if s in ('joined', 'joined', 'unjoined', 'swapped'): joined += 1
            elif s == 'fixed':    fixed   += 1
            elif s == 'failed':   failed  += 1
            else:                 skipped += 1

        self._update_pills(joined, fixed, failed, skipped)
        self.SetLoading(False)
        self.BtnExport.IsEnabled = len(results) > 0

    def _update_pills(self, joined, fixed, failed, skipped):
        self.TxtJoined.Text  = "{} joined".format(joined)
        self.TxtFixed.Text   = "{} fixed".format(fixed)
        self.TxtFailed.Text  = "{} failed".format(failed)
        self.TxtSkipped.Text = "{} skipped".format(skipped)

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
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Status', 'Category A', 'Element A', 'Category B', 'Element B', 'Note'])
                for r in self._rows:
                    w.writerow([r.Status, r.Cat1, r.Name1, r.Cat2, r.Name2, r.Msg])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
