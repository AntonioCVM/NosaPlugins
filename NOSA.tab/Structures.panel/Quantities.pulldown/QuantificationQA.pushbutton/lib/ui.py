# -*- coding: utf-8 -*-
import io
import os, sys, csv, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_logic = imp.load_source('quantqa_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
run_all                  = _logic.run_all
get_available_levels     = _logic.get_available_levels
get_available_categories = _logic.get_available_categories
get_all_family_names     = _logic.get_all_family_names

from nosa_utils.base_window import NOSAWindow
from nosa_utils.logging import Logger
logger = Logger()


class QuantRow(object):
    """Row for the Concrete tab."""
    def __init__(self, d):
        self.Category = d.get('category', '')
        self.Material = d.get('material', '')
        self.Level    = d.get('level', '')
        self.VolStr   = '{:.3f}'.format(d.get('volume_m3', 0))
        self.AreaStr  = '{:.2f}'.format(d.get('area_m2', 0))
        self.Count    = d.get('count', 0)


class SteelRow(object):
    """Row for the Steel tab."""
    def __init__(self, d):
        self.Category   = d.get('category', '')
        self.Material   = d.get('material', '')
        self.Level      = d.get('level', '')
        self.WeightKg   = '{:.1f}'.format(d.get('weight_kg', 0))
        self.WeightTonne = '{:.3f}'.format(d.get('weight_t', 0))
        self.Count      = d.get('count', 0)


class RebarRow(object):
    """Row for the Rebar tab."""
    def __init__(self, d):
        self.Level     = d.get('level', '')
        self.DiamStr   = '{:.0f}'.format(d.get('diam_mm', 0))
        self.Count     = d.get('count', 0)
        self.LengthStr = '{:.2f}'.format(d.get('total_length_m', 0))
        self.WeightStr = '{:.1f}'.format(d.get('weight_kg', 0))


class QARow(object):
    def __init__(self, d):
        self.Severity = d.get('severity', '')
        self.Category = d.get('category', '')
        self.Level    = d.get('level', '')
        self.Name     = d.get('name', '')
        self.Problem  = d.get('problem', '')
        self.Id       = d.get('id')


class QuantificationQAWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'quantification_qa')
        self.doc   = doc
        self._data = None
        self._tabs = {
            'BtnTabConcrete': self.TabConcrete,
            'BtnTabSteel':    self.TabSteel,
            'BtnTabRebar':    self.TabRebar,
            'BtnTabQA':       self.TabQA,
        }
        self._quant_rows = ObservableCollection[QuantRow]()
        self._steel_rows = ObservableCollection[SteelRow]()
        self._rebar_rows = ObservableCollection[RebarRow]()
        self._qa_rows    = ObservableCollection[QARow]()
        self.GridConcrete.ItemsSource = self._quant_rows
        self.GridSteel.ItemsSource    = self._steel_rows
        self.GridRebar.ItemsSource    = self._rebar_rows
        self.GridQA.ItemsSource       = self._qa_rows
        self._load_filters()
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def _load_filters(self):
        try:
            cats   = get_available_categories()
            levels = get_available_levels(self.doc)
            families = get_all_family_names(self.doc)
            self.ListCats.ItemsSource          = cats
            self.ListLevels.ItemsSource        = levels
            self.ListExcludeFamilies.ItemsSource = families
            self.ListCats.SelectAll()
            self.ListLevels.SelectAll()
        except Exception as e:
            logger.debug('QuantQA _load_filters: {}'.format(e))

    def _selected_cats(self):
        return [str(i) for i in self.ListCats.SelectedItems] or None

    def _selected_levels(self):
        return [str(i) for i in self.ListLevels.SelectedItems] or None

    def _excluded_families(self):
        items = self.ListExcludeFamilies.SelectedItems
        return [str(i) for i in items] if items else None

    def SelectAll_Click(self, sender, args):
        self.ListCats.SelectAll()
        self.ListLevels.SelectAll()

    def NavButton_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)

    def _run_analysis(self, excluded_families=None):
        self.SetLoading(True, 'Calculating quantities...')
        self._quant_rows.Clear()
        self._steel_rows.Clear()
        self._rebar_rows.Clear()
        self._qa_rows.Clear()
        self.BtnExport.IsEnabled = False
        try:
            excl_phase = getattr(self, 'ChkExcludeExisting', None)
            excl_piles = getattr(self, 'ChkExcludePiles', None)
            self._data = run_all(
                self.doc,
                self._selected_cats(),
                self._selected_levels(),
                excluded_families,
                exclude_existing_phase=(excl_phase is not None and excl_phase.IsChecked == True),
                exclude_piles=(excl_piles is not None and excl_piles.IsChecked == True),
            )
        except Exception as e:
            self.SetLoading(False)
            forms.alert('Error: {}'.format(e))
            return

        for r in self._data['agg_concrete']:
            self._quant_rows.Add(QuantRow(r))
        for r in self._data['agg_steel']:
            self._steel_rows.Add(SteelRow(r))
        for r in self._data['agg_rebar']:
            self._rebar_rows.Add(RebarRow(r))
        for r in self._data['qa_issues']:
            self._qa_rows.Add(QARow(r))

        t = self._data['totals']
        self.TxtTotalVol.Text   = 'Concrete: {:.2f} m³'.format(t['volume_m3'])
        self.TxtTotalSteel.Text = 'Steel: {:.0f} kg'.format(t['steel_kg'])
        self.TxtTotalRebar.Text = 'Rebar: {:.0f} kg'.format(t['rebar_kg'])
        qa_n = t['qa_issues']
        self.TxtQACount.Text    = '{} QA issues'.format(qa_n) if qa_n else ''

        self.SetLoading(False)
        self.BtnExport.IsEnabled = True
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)

    def Run_Click(self, sender, args):
        self._run_analysis(self._excluded_families())

    def ApplyExclusion_Click(self, sender, args):
        self._run_analysis(self._excluded_families())

    def QAGrid_SelectionChanged(self, sender, args):
        rows = list(self.GridQA.SelectedItems) if self.GridQA.SelectedItems else []
        has  = len(rows) > 0
        self.BtnQASelect.IsEnabled       = has
        self.BtnAssignMaterial.IsEnabled  = has
        self.TxtQASelection.Text = "{} selected".format(len(rows)) if rows else ""

    def QASelect_Click(self, sender, args):
        rows = list(self.GridQA.SelectedItems) if self.GridQA.SelectedItems else []
        if not rows:
            return
        try:
            from pyrevit import DB
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([DB.ElementId(int(r.Id)) for r in rows if r.Id])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def AssignMaterial_Click(self, sender, args):
        """Assign a material to QA-selected elements with missing material."""
        rows = [r for r in (self.GridQA.SelectedItems or []) if r.Id]
        if not rows:
            return
        try:
            from pyrevit import DB
            mats = sorted(
                DB.FilteredElementCollector(self.doc).OfClass(DB.Material).ToElements(),
                key=lambda m: m.Name
            )
            if not mats:
                forms.alert("No materials found in the project.")
                return
            chosen = forms.SelectFromList.show(
                [m.Name for m in mats], title="Select material to assign", button_name="Assign"
            )
            if not chosen:
                return
            mat = next((m for m in mats if m.Name == chosen), None)
            if not mat:
                return
            ok = fail = 0
            with revit.Transaction("NOSA — Assign Material"):
                for row in rows:
                    assigned = False
                    try:
                        el = self.doc.GetElement(DB.ElementId(int(row.Id)))
                        if not el:
                            fail += 1
                            continue
                        p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                        if p and not p.IsReadOnly:
                            p.Set(mat.Id)
                            ok += 1
                            continue
                        try:
                            type_id = el.GetTypeId()
                            if type_id and type_id != DB.ElementId.InvalidElementId:
                                type_el = self.doc.GetElement(type_id)
                                if type_el:
                                    tp = type_el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                                    if tp and not tp.IsReadOnly:
                                        tp.Set(mat.Id)
                                        ok += 1
                                        assigned = True
                        except Exception:
                            pass
                        if not assigned:
                            fail += 1
                    except Exception:
                        fail += 1
            forms.alert("Material '{}' assigned.\n\nUpdated: {}\nFailed: {}".format(chosen, ok, fail))
        except Exception as e:
            forms.alert("Error: {}".format(e))

    def Export_Click(self, sender, args):
        if not self._data:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['=== CONCRETE QUANTITIES ==='])
                w.writerow(['Category', 'Material', 'Level', 'Volume m3', 'Area m2', 'Count'])
                for r in self._quant_rows:
                    w.writerow([r.Category, r.Material, r.Level, r.VolStr, r.AreaStr, r.Count])
                w.writerow([])
                w.writerow(['=== STEEL QUANTITIES ==='])
                w.writerow(['Category', 'Material', 'Level', 'Weight kg', 'Weight t', 'Count'])
                for r in self._steel_rows:
                    w.writerow([r.Category, r.Material, r.Level, r.WeightKg, r.WeightTonne, r.Count])
                w.writerow([])
                w.writerow(['=== REBAR ==='])
                w.writerow(['Level', 'Diameter mm', 'Count', 'Total length m', 'Weight kg'])
                for r in self._rebar_rows:
                    w.writerow([r.Level, r.DiamStr, r.Count, r.LengthStr, r.WeightStr])
                w.writerow([])
                w.writerow(['=== QA ISSUES ==='])
                w.writerow(['Severity', 'Category', 'Level', 'Element', 'Problem'])
                for r in self._qa_rows:
                    w.writerow([r.Severity, r.Category, r.Level, r.Name, r.Problem])
            forms.alert('Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert('Export failed: {}'.format(e))
