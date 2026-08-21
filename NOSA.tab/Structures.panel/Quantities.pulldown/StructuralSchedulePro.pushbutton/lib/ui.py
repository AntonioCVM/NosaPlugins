# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys
import System.Windows
from System import Int64
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value

_here = os.path.dirname(os.path.abspath(__file__))
_sp_logic  = imp.load_source('ssp_schedpro_logic', os.path.join(_here, 'logic_schedule_pro.py'))
_bom_logic = imp.load_source('ssp_bom_logic',       os.path.join(_here, 'logic_structural_bom.py'))

_ALL_LEVELS = u'— All levels —'
_NO_EXCLUDE = u'— None (include all) —'


class _SPRow(object):
    def __init__(self, d):
        self.mark        = d.get('mark',      u'—')
        self.etype       = d.get('etype',     u'—')
        self.level       = d.get('level',     u'—')
        self.length_m    = d.get('length_m',  u'—')
        self.material    = d.get('material',  u'—')
        self.category    = d.get('category',  u'—')
        self.is_subtotal = bool(d.get('is_subtotal', False))
        for k, v in d.items():
            if k.startswith('ep_'):
                setattr(self, k, v)


def _parse_density(tb, default=2500.0):
    try:
        v = float(tb.Text.strip())
        return v if v > 0 else default
    except Exception:
        return default


class ScheduleProWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'schedule_pro')
        self.doc = doc

        self._sp_rows      = []
        self._bom_rows     = []
        self._bom_totals   = None
        self._bom_level_map = {}
        self._bom_phase_map = {}

        try:
            self.SP_TxtProjectName.Text = doc.ProjectInformation.Name or ''
        except Exception:
            pass

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._bom_init()

        self._mode = 'schedule'
        self._update_mode_panels()

    # ══════════════════════════════════════════════════════════════════
    # Tab toggle
    # ══════════════════════════════════════════════════════════════════

    def _update_mode_panels(self):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        sched = self._mode == 'schedule'
        self.PanelSchedule.Visibility = V if sched else C
        self.PanelBOM.Visibility      = C if sched else V
        self.BtnModeSchedule.Tag = u'Active' if sched else u''
        self.BtnModeBOM.Tag      = u'' if sched else u'Active'

    def ModeSchedule_Click(self, sender, args):
        self._mode = 'schedule'
        self._update_mode_panels()

    def ModeBOM_Click(self, sender, args):
        self._mode = 'bom'
        self._update_mode_panels()

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: SCHEDULE PRO
    # ══════════════════════════════════════════════════════════════════

    def _sp_get_selected_cats(self):
        cats = []
        if self.SP_ChkColumns.IsChecked     == True: cats.append('columns')
        if self.SP_ChkBeams.IsChecked       == True: cats.append('beams')
        if self.SP_ChkFoundations.IsChecked == True: cats.append('foundations')
        if self.SP_ChkWalls.IsChecked       == True: cats.append('walls')
        if self.SP_ChkFloors.IsChecked      == True: cats.append('floors')
        return cats or ['columns', 'beams']

    def _sp_get_extra_params(self):
        raw = (self.SP_TxtExtraParams.Text or '').strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(',') if p.strip()]

    def _sp_get_group_by(self):
        if self.SP_RbGroupLevel.IsChecked    == True: return 'level'
        if self.SP_RbGroupCat.IsChecked      == True: return 'category'
        if self.SP_RbGroupMaterial.IsChecked == True: return 'material'
        return None

    def SP_Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.SP_ProgBar.Visibility = Vis.Visible
        self.SP_BtnRun.IsEnabled   = False
        self.SP_TxtStatus.Text     = u'Collecting elements…'

        cats     = self._sp_get_selected_cats()
        extra    = self._sp_get_extra_params()
        group_by = self._sp_get_group_by()

        try:
            rows = _sp_logic.collect_schedule(self.doc, cats, extra)
            if group_by:
                rows = _sp_logic.subtotals(rows, group_by)
        except Exception as e:
            self.SP_ProgBar.Visibility = Vis.Collapsed
            self.SP_BtnRun.IsEnabled   = True
            self.SP_TxtStatus.Text     = u'Error: {}'.format(e)
            forms.alert(u'Schedule error:\n{}'.format(e))
            return

        self.SP_ProgBar.Visibility = Vis.Collapsed
        self.SP_BtnRun.IsEnabled   = True
        self._sp_rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_SPRow(r))
        self.SP_GridSchedule.ItemsSource = src

        total = sum(1 for r in rows if not r.get('is_subtotal'))
        self.SP_TxtStatus.Text         = u'{} elements found.'.format(total)
        self.SP_BtnExport.IsEnabled    = total > 0
        self.SP_BtnExportPDF.IsEnabled = total > 0

    def SP_Export_Click(self, sender, args):
        if not self._sp_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            proj  = self.SP_TxtProjectName.Text.strip()
            extra = self._sp_get_extra_params()
            _sp_logic.export_csv(self._sp_rows, path, proj, extra)
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def SP_ExportPDF_Click(self, sender, args):
        if not self._sp_rows:
            return
        import System.Windows.Forms as WinForms
        dlg = WinForms.SaveFileDialog()
        dlg.Filter   = "PDF files (*.pdf)|*.pdf|HTML files (*.html)|*.html|All files (*.*)|*.*"
        dlg.Title    = "Save PDF report"
        dlg.FileName = "structural_schedule.pdf"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        path = dlg.FileName
        try:
            proj  = self.SP_TxtProjectName.Text.strip()
            extra = self._sp_get_extra_params()
            out_path, is_pdf = _sp_logic.export_pdf(self._sp_rows, path, proj, extra)
            if is_pdf:
                forms.alert(u'PDF exported:\n{}'.format(out_path))
            else:
                import subprocess
                subprocess.Popen(['start', out_path], shell=True)
                forms.alert(
                    u'Chrome not found — schedule saved as HTML:\n{}\n\n'
                    u'Open in a browser and use File > Print to save as PDF.'.format(out_path))
        except Exception as e:
            forms.alert(u'PDF export error:\n{}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: STRUCTURAL BOM
    # ══════════════════════════════════════════════════════════════════

    def _bom_init(self):
        self.BOM_CboLevel.Items.Add(_ALL_LEVELS)
        for name, lvid in _bom_logic.get_levels(self.doc):
            self.BOM_CboLevel.Items.Add(name)
            self._bom_level_map[name] = get_id_value(lvid)
        self.BOM_CboLevel.SelectedIndex = 0

        self.BOM_CboPhase.Items.Add(_NO_EXCLUDE)
        for name, phid in _bom_logic.get_phases(self.doc):
            self.BOM_CboPhase.Items.Add(name)
            self._bom_phase_map[name] = phid
        self.BOM_CboPhase.SelectedIndex = 0

    def BOM_Generate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.BOM_ProgBar.Visibility    = Vis.Visible
        self.BOM_TxtProgress.Text      = u'Collecting data…'
        self.BOM_BtnGenerate.IsEnabled = False
        self.BOM_BtnXlsx.IsEnabled     = False
        self.BOM_BtnCsv.IsEnabled      = False

        if self.BOM_RbLevel.IsChecked:
            group_by = 'level'
        elif self.BOM_RbCategory.IsChecked:
            group_by = 'category'
        else:
            group_by = 'material'

        lv_sel = self.BOM_CboLevel.SelectedItem
        lv_id  = self._bom_level_map.get(lv_sel) if lv_sel and lv_sel != _ALL_LEVELS else None

        ph_sel = self.BOM_CboPhase.SelectedItem
        ph_id  = self._bom_phase_map.get(ph_sel) if ph_sel and ph_sel != _NO_EXCLUDE else None

        densities = {
            u'Structural Columns':     _parse_density(self.BOM_TxtDensCols),
            u'Structural Framing':     _parse_density(self.BOM_TxtDensFrame),
            u'Structural Foundations': _parse_density(self.BOM_TxtDensFound),
            u'Floors':                 _parse_density(self.BOM_TxtDensFloors),
            u'Structural Walls':       _parse_density(self.BOM_TxtDensWalls),
        }

        options = {
            'group_by':         group_by,
            'filter_level_id':  lv_id,
            'exclude_phase_id': ph_id,
            'include_rebar':    bool(self.BOM_ChkRebar.IsChecked),
            'densities':        densities,
        }

        try:
            rows, totals = _bom_logic.collect_bom(self.doc, options)
        except Exception as e:
            self.BOM_ProgBar.Visibility    = Vis.Collapsed
            self.BOM_TxtProgress.Text      = u''
            self.BOM_BtnGenerate.IsEnabled = True
            forms.alert(u'Error generating BOM:\n{}'.format(e))
            return

        if not self.BOM_ChkSubtotals.IsChecked:
            rows = [r for r in rows if not r.is_subtotal]

        self._bom_rows   = rows
        self._bom_totals = totals

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(r)
        self.BOM_GridBOM.ItemsSource = src

        if totals:
            self.BOM_TxtTotalCount.Text = str(totals.count or 0)
            self.BOM_TxtTotalVol.Text   = u'{:.3f} m³'.format(totals.volume_m3 or 0)
            self.BOM_TxtTotalArea.Text  = u'{:.2f} m²'.format(totals.area_m2 or 0)
            self.BOM_TxtTotalRebar.Text = u'{:.1f} kg'.format(totals.rebar_kg or 0)
            self.BOM_TxtTotalSteel.Text = totals.steel_str
            self.BOM_TxtTotalEst.Text   = totals.est_str

        self.BOM_ProgBar.Visibility    = Vis.Collapsed
        detail_rows = [r for r in rows if not r.is_subtotal]
        self.BOM_TxtProgress.Text      = u'{} rows generated.'.format(len(detail_rows))
        self.BOM_BtnGenerate.IsEnabled = True
        self.BOM_BtnXlsx.IsEnabled     = True
        self.BOM_BtnCsv.IsEnabled      = True

    def BOM_Grid_SelectionChanged(self, sender, args):
        selected = list(self.BOM_GridBOM.SelectedItems)
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

    def BOM_ExportXlsx_Click(self, sender, args):
        if not self._bom_rows:
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
            _bom_logic.export_xlsx(self._bom_rows, self._bom_totals, path, proj_name)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use "Export CSV" instead.')
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def BOM_ExportCsv_Click(self, sender, args):
        if not self._bom_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _bom_logic.export_csv(self._bom_rows, self._bom_totals, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
