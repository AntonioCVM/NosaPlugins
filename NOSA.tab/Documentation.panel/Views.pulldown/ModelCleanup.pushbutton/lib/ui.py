# -*- coding: utf-8 -*-
import io
import os, sys, csv
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path: sys.path.insert(0, _lib)

from nosa_utils.loader import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('mcleanup_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class OrphanRow(object):
    def __init__(self, d):
        self.VType = d['type']; self.Name = d['name']; self.Id = d['id']
        self.IsChecked = False

class FamilyRow(object):
    def __init__(self, d):
        self.Category = d['category']; self.Family = d['family']
        self.TypeName = d['type']; self.Id = d['id']
        self.IsChecked = False

class TplRow(object):
    def __init__(self, d):
        self.Name = d['name']; self.Id = d['id']
        self.IsChecked = False

class WarnRow(object):
    def __init__(self, d):
        self.Description = d['description'][:120]; self.ElementCount = d['elements']

class CadRow(object):
    def __init__(self, d):
        self.Name = d['name']; self.View = d['view']
        self.Kind = 'Link' if d['is_linked'] else 'Import'
        self.Id = d['id']; self.IsChecked = False

class RoomRow(object):
    def __init__(self, d):
        self.Number = d['number']; self.Name = d['name']
        self.Level = d['level']; self.Id = d['id']
        self.IsChecked = False


class ModelCleanupWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'model_cleanup')
        self.doc   = doc
        self._data = None

        self._tabs = {
            'BtnTabOrphans':   self.TabOrphans,
            'BtnTabFamilies':  self.TabFamilies,
            'BtnTabTemplates': self.TabTemplates,
            'BtnTabCAD':       self.TabCAD,
            'BtnTabRooms':     self.TabRooms,
            'BtnTabWarnings':  self.TabWarnings,
        }

        self._orphan_rows   = ObservableCollection[OrphanRow]()
        self._family_rows   = ObservableCollection[FamilyRow]()
        self._template_rows = ObservableCollection[TplRow]()
        self._warn_rows     = ObservableCollection[WarnRow]()
        self._cad_rows      = ObservableCollection[CadRow]()
        self._room_rows     = ObservableCollection[RoomRow]()

        self.TabOrphans.ItemsSource   = self._orphan_rows
        self.TabFamilies.ItemsSource  = self._family_rows
        self.TabTemplates.ItemsSource = self._template_rows
        self.TabWarnings.ItemsSource  = self._warn_rows
        self.TabCAD.ItemsSource       = self._cad_rows
        self.TabRooms.ItemsSource     = self._room_rows

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ── navigation ────────────────────────────────────────────────────────────

    def NavButton_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)
        self._update_actions()

    # ── scan ─────────────────────────────────────────────────────────────────

    def Scan_Click(self, sender, args):
        self.SetLoading(True, 'Scanning model...')
        for col in (self._orphan_rows, self._family_rows, self._template_rows,
                    self._warn_rows, self._cad_rows, self._room_rows):
            col.Clear()
        self.BtnExport.IsEnabled = self.BtnPurge.IsEnabled = False

        try:
            self._data = _logic.run_all(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error: {}".format(e))
            return

        s = self._data['summary']
        self.TxtOrphans.Text   = "{} orphan views".format(s['orphan_views'])
        self.TxtFamilies.Text  = "{} unused types".format(s['unused_families'])
        self.TxtTemplates.Text = "{} unused templates".format(s['unused_templates'])
        self.TxtWarnings.Text  = "{} trivial warnings".format(s['trivial_warnings'])
        self.TxtCAD.Text       = "{} CAD imports".format(s['cad_imports'])
        self.TxtRooms.Text     = "{} unplaced rooms".format(s['unplaced_rooms'])

        for r in self._data['orphan_views']:    self._orphan_rows.Add(OrphanRow(r))
        for r in self._data['unused_families']: self._family_rows.Add(FamilyRow(r))
        for r in self._data['unused_templates']:self._template_rows.Add(TplRow(r))
        for r in self._data['trivial_warnings']:self._warn_rows.Add(WarnRow(r))
        for r in self._data['cad_imports']:     self._cad_rows.Add(CadRow(r))
        for r in self._data['unplaced_rooms']:  self._room_rows.Add(RoomRow(r))

        self.SetLoading(False)
        self.BtnExport.IsEnabled = True
        self._update_actions()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _active_tab_name(self):
        for name, grid in self._tabs.items():
            if grid.Visibility == System.Windows.Visibility.Visible:
                return name
        return ''

    def _update_actions(self):
        tab = self._active_tab_name()
        can_select = tab == 'BtnTabOrphans' and self.TabOrphans.SelectedItem is not None
        self.BtnSelect.IsEnabled = can_select
        purgeable_tabs = ('BtnTabOrphans', 'BtnTabFamilies', 'BtnTabTemplates',
                          'BtnTabCAD', 'BtnTabRooms')
        tab_grid_map = {
            'BtnTabOrphans':   self.TabOrphans,
            'BtnTabFamilies':  self.TabFamilies,
            'BtnTabTemplates': self.TabTemplates,
            'BtnTabCAD':       self.TabCAD,
            'BtnTabRooms':     self.TabRooms,
        }
        if tab in purgeable_tabs and self._data is not None:
            grid = tab_grid_map.get(tab)
            has_selection = grid is not None and grid.SelectedItems and len(list(grid.SelectedItems)) > 0
            self.BtnPurge.IsEnabled = has_selection
        else:
            self.BtnPurge.IsEnabled = False

    def Grid_SelectionChanged(self, sender, args):
        self._update_actions()

    # ── select ────────────────────────────────────────────────────────────────

    def Select_Click(self, sender, args):
        row = self.TabOrphans.SelectedItem
        if not row or not hasattr(row, 'Id'): return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    # ── purge ─────────────────────────────────────────────────────────────────

    def Purge_Click(self, sender, args):
        tab = self._active_tab_name()
        if tab == 'BtnTabOrphans':
            self._purge_orphans()
        elif tab == 'BtnTabFamilies':
            self._purge_families()
        elif tab == 'BtnTabTemplates':
            self._purge_templates()
        elif tab == 'BtnTabCAD':
            self._purge_cad()
        elif tab == 'BtnTabRooms':
            self._purge_rooms()

    def _selected_rows(self, grid):
        return list(grid.SelectedItems) if grid.SelectedItems else []

    def _confirm_purge(self, label, rows):
        n = len(rows)
        if n == 0:
            forms.alert("Select rows to delete first (Ctrl+click or Shift+click for multiple).")
            return False
        return forms.alert(
            "Permanently delete {} {}?\nThis cannot be undone.".format(n, label),
            yes=True, no=True
        )

    def _purge_orphans(self):
        rows = self._selected_rows(self.TabOrphans)
        if not self._confirm_purge("orphan view(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting orphan views...")
        deleted, failed = _logic.purge_orphan_views(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Views")
        self.Scan_Click(None, None)

    def _purge_families(self):
        rows = self._selected_rows(self.TabFamilies)
        if not self._confirm_purge("unused family type(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting unused families...")
        deleted, failed = _logic.purge_unused_families(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Families")
        self.Scan_Click(None, None)

    def _purge_templates(self):
        rows = self._selected_rows(self.TabTemplates)
        if not self._confirm_purge("unused template(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting unused templates...")
        deleted, failed = _logic.purge_unused_templates(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Templates")
        self.Scan_Click(None, None)

    def _purge_cad(self):
        rows = [r for r in self._selected_rows(self.TabCAD) if r.Kind == 'Import']
        if not self._confirm_purge("CAD import(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting CAD imports...")
        deleted, failed = _logic.purge_cad_imports(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {} (links are skipped)".format(deleted, failed),
                    title="Delete CAD Imports")
        self.Scan_Click(None, None)

    def _purge_rooms(self):
        rows = self._selected_rows(self.TabRooms)
        if not self._confirm_purge("unplaced room(s)", rows): return
        ids = [r.Id for r in rows]
        self.SetLoading(True, "Deleting unplaced rooms...")
        deleted, failed = _logic.purge_unplaced_rooms(self.doc, ids)
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Rooms")
        self.Scan_Click(None, None)

    # ── export ────────────────────────────────────────────────────────────────

    def Export_Click(self, sender, args):
        if not self._data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['=== ORPHAN VIEWS ==='])
                w.writerow(['Type', 'Name', 'ID'])
                for r in self._orphan_rows: w.writerow([r.VType, r.Name, r.Id])
                w.writerow([])
                w.writerow(['=== UNUSED FAMILY TYPES ==='])
                w.writerow(['Category', 'Family', 'Type', 'ID'])
                for r in self._family_rows: w.writerow([r.Category, r.Family, r.TypeName, r.Id])
                w.writerow([])
                w.writerow(['=== UNUSED TEMPLATES ==='])
                w.writerow(['Name', 'ID'])
                for r in self._template_rows: w.writerow([r.Name, r.Id])
                w.writerow([])
                w.writerow(['=== CAD IMPORTS ==='])
                w.writerow(['Name', 'View', 'Kind', 'ID'])
                for r in self._cad_rows: w.writerow([r.Name, r.View, r.Kind, r.Id])
                w.writerow([])
                w.writerow(['=== UNPLACED ROOMS ==='])
                w.writerow(['Number', 'Name', 'Level', 'ID'])
                for r in self._room_rows: w.writerow([r.Number, r.Name, r.Level, r.Id])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
