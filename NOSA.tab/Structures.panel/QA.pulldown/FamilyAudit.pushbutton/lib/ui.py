# -*- coding: utf-8 -*-
import imp
import os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit
from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value
_logic = imp.load_source('familyaudit_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_SEARCH_PH   = "Search families..."
_ALL_CATS    = "All Categories"


class FamilyRow(object):
    def __init__(self, data):
        self.Id            = data['id']
        self.Name          = data['name']
        self.Category      = data['category']
        self.TypeCount     = data['type_count']
        self.InstanceCount = data['instance_count']
        self.SizeMB        = '{:.3f}'.format(data['size_mb']) if data['size_mb'] else '—'
        self.ParamFill     = '{:.0%}'.format(data['completeness'])
        self.Editable      = 'Yes' if data['is_editable'] else 'No'
        self.IsChecked     = False
        self.IsUnused      = data['instance_count'] == 0
        self._family       = data['family']
        self._raw          = data


class FamilyAuditWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'family_audit')
        self.doc = doc

        self._all_rows = []
        self._rows     = ObservableCollection[FamilyRow]()
        self.GridFamilies.ItemsSource = self._rows

        self._search_on = False

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self.CboCategory.ItemsSource   = [_ALL_CATS]
        self.CboCategory.SelectedIndex = 0

    # ── scan ────────────────────────────────────────────────────────────────

    def Scan_Click(self, sender, args):
        self.SetLoading(True, "Scanning families...")
        try:
            raw = _logic.collect_families(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error scanning families: {}".format(e))
            return

        self._all_rows = [FamilyRow(r) for r in raw]

        # Populate category combo
        cats = sorted(set(r.Category for r in self._all_rows))
        self.CboCategory.ItemsSource   = [_ALL_CATS] + cats
        self.CboCategory.SelectedIndex = 0

        self.SetLoading(False)
        self._apply_filters()

        self.BtnExport.IsEnabled = True
        self.TxtFamilyCount.Text = "{} families loaded".format(len(self._all_rows))

    # ── filters ──────────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filters()

    def Category_Changed(self, sender, args):
        self._apply_filters()

    def _apply_filters(self):
        cat_sel      = self.CboCategory.SelectedItem
        only_unused  = self.ChkOnlyUnused.IsChecked    == True
        only_edit    = self.ChkOnlyEditable.IsChecked  == True
        only_incomplete = self.ChkOnlyIncomplete.IsChecked == True
        search_txt   = (self.TxtSearch.Text or '').strip().lower()
        if search_txt == _SEARCH_PH.lower():
            search_txt = ''

        visible = []
        for row in self._all_rows:
            if cat_sel and cat_sel != _ALL_CATS and row.Category != cat_sel:
                continue
            if only_unused and not row.IsUnused:
                continue
            if only_edit and row.Editable != 'Yes':
                continue
            if only_incomplete and row._raw['completeness'] >= 1.0:
                continue
            if search_txt and search_txt not in row.Name.lower() \
                          and search_txt not in row.Category.lower():
                continue
            visible.append(row)

        self._rows.Clear()
        for row in visible:
            self._rows.Add(row)

        self._update_pills()

    # ── search ────────────────────────────────────────────────────────────────

    def Search_GotFocus(self, sender, args):
        if self.TxtSearch.Text == _SEARCH_PH:
            self.TxtSearch.Text = ''
            self.TxtSearch.Foreground = System.Windows.Media.Brushes.Black
            self._search_on = True

    def Search_LostFocus(self, sender, args):
        if not self.TxtSearch.Text.strip():
            self.TxtSearch.Text = _SEARCH_PH
            self.TxtSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._search_on = False

    def Search_Changed(self, sender, args):
        if self._search_on or self.TxtSearch.Text != _SEARCH_PH:
            self._apply_filters()

    # ── checkboxes ───────────────────────────────────────────────────────────

    def RowCheck_Click(self, sender, args):
        self._update_pills()

    def CheckAll_Click(self, sender, args):
        for row in self._rows:
            row.IsChecked = True
        self.GridFamilies.Items.Refresh()
        self._update_pills()

    def CheckNone_Click(self, sender, args):
        for row in self._rows:
            row.IsChecked = False
        self.GridFamilies.Items.Refresh()
        self._update_pills()

    # ── pills ────────────────────────────────────────────────────────────────

    def _update_pills(self):
        total     = len(self._rows)
        unused    = sum(1 for r in self._rows if r.IsUnused)
        checked   = sum(1 for r in self._rows if r.IsChecked)
        instances = sum(r.InstanceCount for r in self._rows)

        self.TxtPillTotal.Text     = "{} families".format(total)
        self.TxtPillUnused.Text    = "{} unused".format(unused)
        self.TxtPillSelected.Text  = "{} checked".format(checked)
        self.TxtPillInstances.Text = "{} instances".format(instances)

        self.BtnPurge.IsEnabled  = checked > 0
        self.BtnSelect.IsEnabled = self.GridFamilies.SelectedItem is not None

    # ── grid selection ────────────────────────────────────────────────────────

    def Grid_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridFamilies.SelectedItem is not None

    # ── purge ────────────────────────────────────────────────────────────────

    def Purge_Click(self, sender, args):
        checked = [r for r in self._rows if r.IsChecked]
        if not checked:
            return

        names = '\n'.join('  • ' + r.Name for r in checked[:10])
        if len(checked) > 10:
            names += '\n  ...and {} more'.format(len(checked) - 10)

        if not forms.alert(
            "Permanently delete {} family(ies) from the project?\n\n{}".format(
                len(checked), names),
            yes=True, no=True
        ):
            return

        fids = [r.Id for r in checked]
        self.SetLoading(True, "Purging...")
        try:
            deleted, failed = _logic.purge_families(self.doc, fids)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Purge failed: {}".format(e))
            return

        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, len(failed)),
                    title="Purge Complete")
        self.Scan_Click(None, None)

    # ── select in model ──────────────────────────────────────────────────────

    def SelectInModel_Click(self, sender, args):
        row = self.GridFamilies.SelectedItem
        if row is None:
            return
        type_ids = set(get_id_value(tid) for tid in row._family.GetFamilySymbolIds())
        col = DB.FilteredElementCollector(self.doc)\
                 .WhereElementIsNotElementType()\
                 .OfClass(DB.FamilyInstance)\
                 .ToElements()
        ids = [inst.Id for inst in col
               if inst.Symbol and get_id_value(inst.Symbol.Id) in type_ids]
        if ids:
            from pyrevit import revit as _rv
            _rv.get_selection().set_to(ids)
            forms.alert("Selected {} instance(s) of '{}'.".format(len(ids), row.Name))
        else:
            forms.alert("No instances of '{}' found in model.".format(row.Name))

    # ── export ────────────────────────────────────────────────────────────────

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            raw = [r._raw for r in self._rows]
            _logic.export_to_csv(raw, path)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
