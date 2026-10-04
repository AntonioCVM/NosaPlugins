# -*- coding: utf-8 -*-
import os, sys
import System.Windows
from System import Int64
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from Autodesk.Revit import DB
from pyrevit import forms, revit
from nosa_utils.telemetry import log_swallowed
_LOG = u'surveyexport'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_here = os.path.dirname(os.path.abspath(__file__))
from nosa_utils.bootstrap import load_module
_sv_logic = load_module('se_survey_logic', os.path.join(_here, 'logic_cuadro_replanteo.py'))
_ps_logic = load_module('se_pile_logic',   os.path.join(_here, 'logic_pile_survey_export.py'))

_ALL        = u'— All —'
_ALL_LEVELS = u'— All levels —'


class _Row(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class SurveyExportWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'survey_export')
        self.doc = doc

        self._sv_rows   = []
        self._sv_lv_map = {}
        self._ps_rows   = []
        self._ps_lv_map = {}

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._sv_init()
        self._ps_init()

        self._mode = 'survey'
        self._update_mode_panels()

    # ══════════════════════════════════════════════════════════════════
    # Tab toggle
    # ══════════════════════════════════════════════════════════════════

    def _update_mode_panels(self):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        survey = self._mode == 'survey'
        self.PanelSurvey.Visibility = V if survey else C
        self.PanelPile.Visibility   = C if survey else V
        self.BtnModeSurvey.Tag = u'Active' if survey else u''
        self.BtnModePile.Tag   = u'' if survey else u'Active'

    def ModeSurvey_Click(self, sender, args):
        self._mode = 'survey'
        self._update_mode_panels()

    def ModePile_Click(self, sender, args):
        self._mode = 'pile'
        self._update_mode_panels()

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: SURVEY LAYOUT  (ex. CuadroReplanteo)
    # ══════════════════════════════════════════════════════════════════

    def _sv_init(self):
        self.SV_CboCategory.Items.Add(_ALL)
        for opt in _sv_logic.FILTER_OPTIONS:
            self.SV_CboCategory.Items.Add(opt)
        self.SV_CboCategory.SelectedIndex = 0

        self.SV_CboLevel.Items.Add(_ALL)
        for name, lvid in _sv_logic.get_levels(self.doc):
            self.SV_CboLevel.Items.Add(name)
            self._sv_lv_map[name] = lvid
        self.SV_CboLevel.SelectedIndex = 0

    def SV_Generate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.SV_ProgBar.Visibility    = Vis.Visible
        self.SV_BtnGenerate.IsEnabled = False

        cat_sel = self.SV_CboCategory.SelectedItem
        lv_sel  = self.SV_CboLevel.SelectedItem

        if self.SV_RbMark.IsChecked:    sort_by = 'mark'
        elif self.SV_RbLevel.IsChecked: sort_by = 'level'
        elif self.SV_RbX.IsChecked:     sort_by = 'x'
        else:                           sort_by = 'y'

        try:
            dec = int(self.SV_CboDecimals.SelectedItem.Content)
        except Exception:
            dec = 1

        opts = {
            'filter_category': cat_sel if cat_sel and cat_sel != _ALL else None,
            'filter_level_id': self._sv_lv_map.get(lv_sel) if lv_sel and lv_sel != _ALL else None,
            'sort_by':         sort_by,
            'coord_decimals':  dec,
        }

        try:
            rows = _sv_logic.collect_survey(self.doc, opts)
        except Exception as e:
            self.SV_ProgBar.Visibility    = Vis.Collapsed
            self.SV_BtnGenerate.IsEnabled = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.SV_ProgBar.Visibility    = Vis.Collapsed
        self.SV_BtnGenerate.IsEnabled = True
        self._sv_rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_Row(r))
        self.SV_GridSurvey.ItemsSource = src

        self.SV_TxtStatus.Text = u'{} elements found.'.format(len(rows))
        has = len(rows) > 0
        self.SV_BtnXlsx.IsEnabled          = has
        self.SV_BtnCsv.IsEnabled           = has
        self.SV_BtnSelect.IsEnabled        = has
        self.SV_BtnCompareSurvey.IsEnabled = has

    def SV_Grid_SelectionChanged(self, sender, args):
        selected = list(self.SV_GridSurvey.SelectedItems)
        if not selected:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r.id))) for r in selected])
            revit.uidoc.Selection.SetElementIds(ids)
        except Exception:
            log_swallowed(_LOG, u'SurveyExportWindow.SV_Grid_SelectionChanged')

    def SV_Select_Click(self, sender, args):
        if not self._sv_rows:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r['id']))) for r in self._sv_rows])
            revit.uidoc.Selection.SetElementIds(ids)
            self.SV_TxtStatus.Text = u'{} elements selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Selection error: {}'.format(e))

    def SV_ExportXlsx_Click(self, sender, args):
        if not self._sv_rows:
            return
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            name = ''
            try:
                name = self.doc.ProjectInformation.Name or ''
            except Exception:
                log_swallowed(_LOG, u'SurveyExportWindow.SV_ExportXlsx_Click')
            _sv_logic.export_xlsx(self._sv_rows, path, name)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use CSV export.')
        except Exception as e:
            forms.alert(u'Export error: {}'.format(e))

    def SV_ExportCsv_Click(self, sender, args):
        if not self._sv_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _sv_logic.export_csv(self._sv_rows, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error: {}'.format(e))

    def SV_CompareSurvey_Click(self, sender, args):
        if not self._sv_rows:
            return
        import System.Windows.Forms as WinForms
        dlg = WinForms.OpenFileDialog()
        dlg.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        dlg.Title  = "Open surveyed-coordinates CSV"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return

        try:
            tol = float(self.SV_TxtTolerance.Text or '10')
        except (ValueError, AttributeError):
            tol = 10.0

        self.SetLoading(True, u'Comparing survey to model…')
        try:
            survey_pts = _sv_logic.load_survey_csv(dlg.FileName)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Could not read survey file:\n{}'.format(e))
            return

        try:
            results = _sv_logic.compare_survey(self._sv_rows, survey_pts, tolerance_mm=tol)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Comparison error:\n{}'.format(e))
            return
        self.SetLoading(False)

        out_path = forms.save_file(file_ext='csv')
        if out_path:
            try:
                _sv_logic.export_compare_csv(results, out_path)
            except Exception as e:
                forms.alert(u'Could not save results:\n{}'.format(e))
                return

        out_of_tol = [r for r in results if 'OUT OF TOLERANCE' in str(r.get('status', ''))]
        no_match   = [r for r in results if r.get('status') in (u'No survey point', u'No model element')]
        matched    = len(results) - len(no_match)

        summary = (
            u'Survey vs Model Comparison\n'
            u'  Matched:          {}\n'
            u'  Out of tolerance: {}\n'
            u'  Unmatched:        {}\n'
            u'  Tolerance:        {:.0f} mm'
        ).format(matched, len(out_of_tol), len(no_match), tol)
        if out_path:
            summary += u'\n\nFull report saved:\n{}'.format(out_path)
        forms.alert(summary, title=u'Survey Comparison')

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: PILE SURVEY EXPORT
    # ══════════════════════════════════════════════════════════════════

    def _ps_init(self):
        self.PS_CboLevel.Items.Add(_ALL_LEVELS)
        for name, lvid in _ps_logic.get_levels(self.doc):
            self.PS_CboLevel.Items.Add(name)
            self._ps_lv_map[name] = lvid
        self.PS_CboLevel.SelectedIndex = 0

    def PS_Generate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.PS_ProgBar.Visibility    = Vis.Visible
        self.PS_BtnGenerate.IsEnabled = False

        lv_sel = self.PS_CboLevel.SelectedItem

        if self.PS_RbMark.IsChecked: sort_by = 'mark'
        elif self.PS_RbX.IsChecked:  sort_by = 'x'
        else:                        sort_by = 'y'

        try:
            dec = int(self.PS_CboDecimals.SelectedItem.Content)
        except Exception:
            dec = 1

        opts = {
            'filter_level_id': self._ps_lv_map.get(lv_sel) if lv_sel and lv_sel != _ALL_LEVELS else None,
            'sort_by':         sort_by,
            'coord_decimals':  dec,
            'only_flagged':    bool(self.PS_RbFlagged.IsChecked),
        }

        try:
            rows = _ps_logic.collect_piles(self.doc, opts)
        except Exception as e:
            self.PS_ProgBar.Visibility    = Vis.Collapsed
            self.PS_BtnGenerate.IsEnabled = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.PS_ProgBar.Visibility    = Vis.Collapsed
        self.PS_BtnGenerate.IsEnabled = True
        self._ps_rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_Row(r))
        self.PS_GridPiles.ItemsSource = src

        self.PS_TxtStatus.Text = u'{} pile(s) found.'.format(len(rows))
        has = len(rows) > 0
        self.PS_BtnXlsx.IsEnabled   = has
        self.PS_BtnCsv.IsEnabled    = has
        self.PS_BtnSelect.IsEnabled = has

    def PS_Grid_SelectionChanged(self, sender, args):
        selected = list(self.PS_GridPiles.SelectedItems)
        if not selected:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r.id))) for r in selected])
            revit.uidoc.Selection.SetElementIds(ids)
        except Exception:
            log_swallowed(_LOG, u'SurveyExportWindow.PS_Grid_SelectionChanged')

    def PS_Select_Click(self, sender, args):
        if not self._ps_rows:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r['id']))) for r in self._ps_rows])
            revit.uidoc.Selection.SetElementIds(ids)
            self.PS_TxtStatus.Text = u'{} pile(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def PS_ExportXlsx_Click(self, sender, args):
        if not self._ps_rows:
            return
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            name = ''
            try:
                name = self.doc.ProjectInformation.Name or ''
            except Exception:
                log_swallowed(_LOG, u'SurveyExportWindow.PS_ExportXlsx_Click')
            _ps_logic.export_xlsx(self._ps_rows, path, name)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use CSV.')
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))

    def PS_ExportCsv_Click(self, sender, args):
        if not self._ps_rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _ps_logic.export_csv(self._ps_rows, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
