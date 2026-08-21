# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys
import System.Windows
from System import Int64
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from pyrevit import forms, revit
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value

_logic = imp.load_source('bom_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_ALL_LEVELS  = u'— All levels —'
_NO_EXCLUDE  = u'— None (include all) —'


def _parse_density(tb, default=2500.0):
    try:
        v = float(tb.Text.strip())
        return v if v > 0 else default
    except Exception:
        return default


class StructuralBOMWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'structural_bom')
        self.doc         = doc
        self._rows       = []
        self._totals     = None
        self._level_map  = {}
        self._phase_map  = {}

        # Level filter
        self.CboLevel.Items.Add(_ALL_LEVELS)
        for name, lvid in _logic.get_levels(doc):
            self.CboLevel.Items.Add(name)
            self._level_map[name] = get_id_value(lvid)
        self.CboLevel.SelectedIndex = 0

        # Phase filter
        self.CboPhase.Items.Add(_NO_EXCLUDE)
        for name, phid in _logic.get_phases(doc):
            self.CboPhase.Items.Add(name)
            self._phase_map[name] = phid
        self.CboPhase.SelectedIndex = 0

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    # ── Generate ─────────────────────────────────────────────────────────────

    def Generate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility    = Vis.Visible
        self.TxtProgress.Text      = u'Collecting data…'
        self.BtnGenerate.IsEnabled = False
        self.BtnXlsx.IsEnabled     = False
        self.BtnCsv.IsEnabled      = False

        if self.RbLevel.IsChecked:
            group_by = 'level'
        elif self.RbCategory.IsChecked:
            group_by = 'category'
        else:
            group_by = 'material'

        lv_sel = self.CboLevel.SelectedItem
        lv_id  = self._level_map.get(lv_sel) if lv_sel and lv_sel != _ALL_LEVELS else None

        ph_sel  = self.CboPhase.SelectedItem
        ph_id   = self._phase_map.get(ph_sel) if ph_sel and ph_sel != _NO_EXCLUDE else None

        densities = {
            u'Structural Columns':     _parse_density(self.TxtDensCols),
            u'Structural Framing':     _parse_density(self.TxtDensFrame),
            u'Structural Foundations': _parse_density(self.TxtDensFound),
            u'Floors':                 _parse_density(self.TxtDensFloors),
            u'Structural Walls':       _parse_density(self.TxtDensWalls),
        }

        options = {
            'group_by':         group_by,
            'filter_level_id':  lv_id,
            'exclude_phase_id': ph_id,
            'include_rebar':    bool(self.ChkRebar.IsChecked),
            'densities':        densities,
        }

        try:
            rows, totals = _logic.collect_bom(self.doc, options)
        except Exception as e:
            self.ProgBar.Visibility    = Vis.Collapsed
            self.TxtProgress.Text      = u''
            self.BtnGenerate.IsEnabled = True
            forms.alert(u'Error generating BOM:\n{}'.format(e))
            return

        if not self.ChkSubtotals.IsChecked:
            rows = [r for r in rows if not r.is_subtotal]

        self._rows   = rows
        self._totals = totals

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(r)
        self.GridBOM.ItemsSource = src

        if totals:
            self.TxtTotalCount.Text = str(totals.count or 0)
            self.TxtTotalVol.Text   = u'{:.3f} m³'.format(totals.volume_m3 or 0)
            self.TxtTotalArea.Text  = u'{:.2f} m²'.format(totals.area_m2 or 0)
            self.TxtTotalRebar.Text = u'{:.1f} kg'.format(totals.rebar_kg or 0)
            self.TxtTotalSteel.Text = totals.steel_str
            self.TxtTotalEst.Text   = totals.est_str

        self.ProgBar.Visibility    = Vis.Collapsed
        detail_rows = [r for r in rows if not r.is_subtotal]
        self.TxtProgress.Text      = u'{} rows generated.'.format(len(detail_rows))
        self.BtnGenerate.IsEnabled = True
        self.BtnXlsx.IsEnabled     = True
        self.BtnCsv.IsEnabled      = True

    # ── Selection ────────────────────────────────────────────────────────────

    def Grid_SelectionChanged(self, sender, args):
        selected = list(self.GridBOM.SelectedItems)
        ids = []
        for r in selected:
            if not r.is_subtotal:
                ids.extend(r.el_ids or [])
        if ids:
            try:
                eid_list = List[DB.ElementId]([DB.ElementId(Int64(int(i))) for i in ids])
                revit.uidoc.Selection.SetElementIds(eid_list)
            except Exception:
                pass

    # ── Export ───────────────────────────────────────────────────────────────

    def ExportXlsx_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            proj_name = ''
            try:
                proj_name = self.doc.ProjectInformation.Name or ''
            except Exception:
                pass
            _logic.export_xlsx(self._rows, self._totals, path, proj_name)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use "Export CSV" instead.')
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def ExportCsv_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv(self._rows, self._totals, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)


