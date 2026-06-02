# -*- coding: utf-8 -*-
import os, sys, csv, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..','..','..','..','lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)
_logic = imp.load_source('revtrack_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow
logger = __import__('nosa_utils.logging', fromlist=['Logger']).Logger()


class SnapItem(object):
    def __init__(self, d): self.File=d['file']; self.Label=d['label']; self.Ts=d['ts']; self.Count=d['count']
    def __str__(self): return "{} ({} elements)".format(self.Label, self.Count)

class DeltaRow(object):
    def __init__(self, change_type, entry, detail=''):
        self.ChangeType = change_type
        self.Category   = entry.get('category','')
        self.Name       = entry.get('name','') or entry.get('type','')
        self.Id         = entry.get('id','')
        self.Detail     = detail


class RevisionTrackerWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'revision_tracker')
        self.doc   = doc
        self._rows = ObservableCollection[DeltaRow]()
        self._data = None
        self.GridDelta.ItemsSource = self._rows
        self._refresh_snapshots()

    def _refresh_snapshots(self):
        self.ListSnapshots.Items.Clear()
        for s in _logic.list_snapshots():
            self.ListSnapshots.Items.Add(SnapItem(s))

    def Snapshot_SelectionChanged(self, sender, args):
        has = self.ListSnapshots.SelectedItem is not None
        self.BtnCompare.IsEnabled = has
        self.BtnDelete.IsEnabled  = has

    def TakeSnapshot_Click(self, sender, args):
        label = forms.ask_for_string(prompt="Snapshot label (e.g. Rev C, IFC-2026):", title="New Snapshot")
        if label is None: return
        self.SetLoading(True, 'Taking snapshot...')
        try:
            path, lbl, n = _logic.take_snapshot(self.doc, label.strip() or None)
            self._refresh_snapshots()
            forms.alert("Snapshot saved: {}\n{} elements captured.".format(lbl, n))
        except Exception as e:
            forms.alert("Error: {}".format(e))
        finally:
            self.SetLoading(False)

    def Compare_Click(self, sender, args):
        item = self.ListSnapshots.SelectedItem
        if not item: return
        self.SetLoading(True, 'Comparing with snapshot...')
        self._rows.Clear(); self.BtnExport.IsEnabled = False
        try:
            snap = _logic.load_snapshot(item.File)
            self._data = _logic.compare(self.doc, snap)
        except Exception as e:
            self.SetLoading(False); forms.alert("Error: {}".format(e)); return
        s = self._data['summary']
        self.TxtAdded.Text   = "{} Added".format(s['added'])
        self.TxtRemoved.Text = "{} Removed".format(s['removed'])
        self.TxtChanged.Text = "{} Changed".format(s['changed'])
        self.TxtSnapInfo.Text = "vs: {}".format(item.Label)
        for r in self._data['added']:
            self._rows.Add(DeltaRow('ADDED', r))
        for r in self._data['removed']:
            self._rows.Add(DeltaRow('REMOVED', r))
        for r in self._data['changed']:
            params = ', '.join(r['diff_params'])
            loc = 'location moved' if r['location_changed'] else ''
            detail = ' | '.join(filter(None, [params, loc]))
            self._rows.Add(DeltaRow('CHANGED', r['current'], detail))
        self.SetLoading(False); self.BtnExport.IsEnabled = True

    def Delete_Click(self, sender, args):
        item = self.ListSnapshots.SelectedItem
        if not item: return
        _logic.delete_snapshot(item.File)
        self._refresh_snapshots()

    def Grid_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridDelta.SelectedItem is not None

    def Select_Click(self, sender, args):
        row = self.GridDelta.SelectedItem
        if not row or not row.Id: return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def Export_Click(self, sender, args):
        if not self._data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with open(path, 'w') as f:
                w = csv.writer(f)
                w.writerow(['Change','Category','Name','ID','Detail'])
                for r in self._rows:
                    w.writerow([r.ChangeType, r.Category, r.Name, r.Id, r.Detail])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
