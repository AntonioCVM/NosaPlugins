# -*- coding: utf-8 -*-
import os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.loader import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('materialmanager_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_SEARCH_PH   = "Search materials..."
_ALL_CLASSES = "All Classes"
_ALL_CATS    = "All Categories"
_ALL_LEVELS  = "All Levels"


class MatRow(object):
    def __init__(self, data, is_near_dup=False):
        self.Id        = data['id']
        self.Name      = data['name']
        self.MatClass  = data['class']
        self.MatCat    = data['category']
        self.UseCount  = data['use_count']
        self.IsUnused  = data['is_unused']
        self.IsNearDup = is_near_dup
        self.Status    = ('Unused' if self.IsUnused else '') + \
                         (u' ⚠ similar name' if is_near_dup else '')
        if not self.Status:
            self.Status = 'OK'
        self._raw = data


class MatItem(object):
    """Lightweight wrapper for the Assign material ComboBox."""
    def __init__(self, mid, name):
        self.Id   = mid
        self.Name = name


class ElementRow(object):
    def __init__(self, data):
        self.Id           = data['id']
        self.Category     = data['category']
        self.Level        = data['level']
        self.TypeName     = data['type_name']
        self.MaterialName = data['material_name']
        self.IsMissing    = data['is_missing']
        self.Status       = 'Missing' if self.IsMissing else 'OK'
        self.ProposedId   = data['proposed_id']
        self.ProposedName = data['proposed_name'] if self.IsMissing else ''
        self._raw         = data


class MaterialManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'material_manager')
        self.doc = doc

        # ── Materials tab state ───────────────────────────────────────────────
        self._all_rows       = []
        self._rows           = ObservableCollection[MatRow]()
        self._near_dup_names = set()
        self._search_on      = False
        self.GridMaterials.ItemsSource = self._rows

        self.CboClass.ItemsSource   = [_ALL_CLASSES]
        self.CboClass.SelectedIndex = 0

        # ── Elements tab state ────────────────────────────────────────────────
        self._all_el_rows = []
        self._el_rows     = ObservableCollection[ElementRow]()
        self.GridElements.ItemsSource = self._el_rows

        self.CboElCategory.ItemsSource = [_ALL_CATS]
        self.CboElCategory.SelectedIndex = 0
        self.CboElLevel.ItemsSource = [_ALL_LEVELS]
        self.CboElLevel.SelectedIndex = 0

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ── tab switching ─────────────────────────────────────────────────────────

    def Tab_Changed(self, sender, args):
        try:
            idx = self.TabMain.SelectedIndex
            v   = System.Windows.Visibility
            if idx == 0:
                self.SidebarMaterials.Visibility = v.Visible
                self.SidebarElements.Visibility  = v.Collapsed
            else:
                self.SidebarMaterials.Visibility = v.Collapsed
                self.SidebarElements.Visibility  = v.Visible
        except Exception:
            pass

    # ── materials scan ────────────────────────────────────────────────────────

    def Scan_Click(self, sender, args):
        self.SetLoading(True, "Collecting materials...")
        try:
            raw = _logic.collect_materials(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error scanning materials: {}".format(e))
            return

        self.SetLoading(True, "Detecting near-duplicates...")
        self._near_dup_names = _logic.find_near_duplicates(raw, threshold=3)
        self._all_rows = [MatRow(r, r['name'] in self._near_dup_names) for r in raw]

        classes = sorted(set(r.MatClass for r in self._all_rows))
        self.CboClass.ItemsSource   = [_ALL_CLASSES] + classes
        self.CboClass.SelectedIndex = 0

        self.SetLoading(False)
        self._apply_filters()
        self.TxtMatCount.Text    = "{} materials loaded".format(len(self._all_rows))
        self.BtnExport.IsEnabled = True

        unused_count = sum(1 for r in self._all_rows if r.IsUnused)
        self.BtnDelete.IsEnabled = unused_count > 0

    # ── materials filters ─────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filters()

    def Class_Changed(self, sender, args):
        self._apply_filters()

    def _apply_filters(self):
        cls_sel     = self.CboClass.SelectedItem
        only_unused = self.ChkOnlyUnused.IsChecked == True
        only_dups   = self.ChkNearDups.IsChecked   == True
        txt = (self.TxtSearch.Text or '').strip().lower()
        if txt == _SEARCH_PH.lower():
            txt = ''

        visible = []
        for row in self._all_rows:
            if cls_sel and cls_sel != _ALL_CLASSES and row.MatClass != cls_sel:
                continue
            if only_unused and not row.IsUnused:
                continue
            if only_dups and not row.IsNearDup:
                continue
            if txt and txt not in row.Name.lower():
                continue
            visible.append(row)

        self._rows.Clear()
        for row in visible:
            self._rows.Add(row)

        total    = len(visible)
        unused   = sum(1 for r in visible if r.IsUnused)
        near_dup = sum(1 for r in visible if r.IsNearDup)
        self.TxtPillTotal.Text  = "{} materials".format(total)
        self.TxtPillUnused.Text = "{} unused".format(unused)
        self.TxtPillDups.Text   = "{} near-duplicates".format(near_dup)

    # ── materials search ──────────────────────────────────────────────────────

    def Search_GotFocus(self, sender, args):
        if self.TxtSearch.Text == _SEARCH_PH:
            self.TxtSearch.Text       = ''
            self.TxtSearch.Foreground = System.Windows.Media.Brushes.Black
            self._search_on           = True

    def Search_LostFocus(self, sender, args):
        if not self.TxtSearch.Text.strip():
            self.TxtSearch.Text       = _SEARCH_PH
            self.TxtSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._search_on           = False

    def Search_Changed(self, sender, args):
        if self._search_on or self.TxtSearch.Text != _SEARCH_PH:
            self._apply_filters()

    # ── delete unused ─────────────────────────────────────────────────────────

    def Delete_Click(self, sender, args):
        unused = [r for r in self._all_rows if r.IsUnused]
        if not unused:
            forms.alert("No unused materials found.")
            return

        names = '\n'.join('  • ' + r.Name for r in unused[:10])
        if len(unused) > 10:
            names += '\n  ... and {} more'.format(len(unused) - 10)

        if not forms.alert(
            "Permanently delete {} unused material(s)?\n\n{}".format(len(unused), names),
            yes=True, no=True
        ):
            return

        ids = [r.Id for r in unused]
        self.SetLoading(True, "Deleting materials...")
        try:
            deleted, failed = _logic.delete_materials(self.doc, ids)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Delete failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, failed), title="Delete Materials")
        self.Scan_Click(None, None)

    # ── materials export ──────────────────────────────────────────────────────

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            raw = [r._raw for r in self._rows]
            _logic.export_csv(raw, path)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    # ── elements scan ─────────────────────────────────────────────────────────

    def ScanElements_Click(self, sender, args):
        self.SetLoading(True, "Scanning structural elements...")
        try:
            raw = _logic.collect_element_materials(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error scanning elements: {}".format(e))
            return

        self._all_el_rows = [ElementRow(r) for r in raw]

        mat_pairs = _logic.get_all_materials(self.doc)
        self.CboAssignMaterial.ItemsSource = [MatItem(mid, name) for mid, name in mat_pairs]

        cats = sorted(set(r.Category for r in self._all_el_rows))
        lvls = sorted(set(r.Level   for r in self._all_el_rows))
        self.CboElCategory.ItemsSource = [_ALL_CATS] + cats
        self.CboElCategory.SelectedIndex = 0
        self.CboElLevel.ItemsSource = [_ALL_LEVELS] + lvls
        self.CboElLevel.SelectedIndex = 0

        self.SetLoading(False)
        self._apply_element_filters()
        self.BtnAssign.IsEnabled         = True
        self.BtnExportElements.IsEnabled = True

        if not self._all_el_rows:
            forms.alert(
                u"No structural elements found in the active document.\n\n"
                u"The scan covers:\n"
                u"  • Structural Framing\n"
                u"  • Structural Columns\n"
                u"  • Walls\n"
                u"  • Floors\n"
                u"  • Structural Foundations\n\n"
                u"Make sure you have the correct document active and that "
                u"it contains elements in these categories.",
                title="Scan Complete — 0 elements"
            )
        else:
            self.TxtMatCount.Text = u"{} elements scanned".format(len(self._all_el_rows))

    # ── elements filters ──────────────────────────────────────────────────────

    def ElementFilter_Changed(self, sender, args):
        self._apply_element_filters()

    def _apply_element_filters(self):
        cat_sel      = self.CboElCategory.SelectedItem
        lvl_sel      = self.CboElLevel.SelectedItem
        missing_only = self.ChkMissingOnly.IsChecked == True

        visible = []
        for row in self._all_el_rows:
            if cat_sel and cat_sel != _ALL_CATS and row.Category != cat_sel:
                continue
            if lvl_sel and lvl_sel != _ALL_LEVELS and row.Level != lvl_sel:
                continue
            if missing_only and not row.IsMissing:
                continue
            visible.append(row)

        self._el_rows.Clear()
        for row in visible:
            self._el_rows.Add(row)

        total    = len(visible)
        missing  = sum(1 for r in visible if r.IsMissing)
        proposed = sum(1 for r in visible if r.IsMissing and r.ProposedId is not None)
        self.TxtPillElTotal.Text    = "{} elements".format(total)
        self.TxtPillElMissing.Text  = "{} missing material".format(missing)
        self.TxtPillElProposed.Text = "{} with proposal".format(proposed)

    # ── elements assign ───────────────────────────────────────────────────────

    def AssignMaterial_Click(self, sender, args):
        mat_item = self.CboAssignMaterial.SelectedItem
        if not mat_item:
            forms.alert("Select a material to assign from the dropdown.")
            return

        selected = list(self.GridElements.SelectedItems)
        if not selected:
            forms.alert("Select at least one element in the grid.")
            return

        if not forms.alert(
            "Assign '{}' to {} element(s)?".format(mat_item.Name, len(selected)),
            yes=True, no=True
        ):
            return

        ids = [r.Id for r in selected]
        self.SetLoading(True, "Assigning material...")
        try:
            ok, failed = _logic.assign_material_to_elements(self.doc, ids, mat_item.Id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Assignment failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert("Assigned: {}  |  Failed: {}".format(ok, failed), title="Assign Material")
        self.ScanElements_Click(None, None)

    # ── elements export ───────────────────────────────────────────────────────

    def ExportElements_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            raw = [r._raw for r in self._el_rows]
            _logic.export_element_materials_csv(raw, path)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
