# -*- coding: utf-8 -*-
import imp
import os, sys
import System.Windows
from System import Int64
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('replanteo_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_ALL = u'— All —'


class _Row(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class CuadroReplanteoWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'cuadro_replanteo')
        self.doc     = doc
        self._rows   = []
        self._lv_map = {}

        # Category filter
        self.CboCategory.Items.Add(_ALL)
        for opt in _logic.FILTER_OPTIONS:
            self.CboCategory.Items.Add(opt)
        self.CboCategory.SelectedIndex = 0

        # Level filter
        self.CboLevel.Items.Add(_ALL)
        for name, lvid in _logic.get_levels(doc):
            self.CboLevel.Items.Add(name)
            self._lv_map[name] = lvid
        self.CboLevel.SelectedIndex = 0

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def Generate_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility    = Vis.Visible
        self.BtnGenerate.IsEnabled = False

        cat_sel = self.CboCategory.SelectedItem
        lv_sel  = self.CboLevel.SelectedItem

        if self.RbMark.IsChecked:    sort_by = 'mark'
        elif self.RbLevel.IsChecked: sort_by = 'level'
        elif self.RbX.IsChecked:     sort_by = 'x'
        else:                        sort_by = 'y'

        try:
            dec = int(self.CboDecimals.SelectedItem.Content)
        except Exception:
            dec = 1

        opts = {
            'filter_category': cat_sel if cat_sel and cat_sel != _ALL else None,
            'filter_level_id': self._lv_map.get(lv_sel) if lv_sel and lv_sel != _ALL else None,
            'sort_by':         sort_by,
            'coord_decimals':  dec,
        }

        try:
            rows = _logic.collect_survey(self.doc, opts)
        except Exception as e:
            self.ProgBar.Visibility    = Vis.Collapsed
            self.BtnGenerate.IsEnabled = True
            forms.alert(u'Error:\n{}'.format(e))
            return

        self.ProgBar.Visibility    = Vis.Collapsed
        self.BtnGenerate.IsEnabled = True
        self._rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_Row(r))
        self.GridSurvey.ItemsSource = src

        self.TxtStatus.Text = u'{} elements found.'.format(len(rows))
        has = len(rows) > 0
        self.BtnXlsx.IsEnabled          = has
        self.BtnCsv.IsEnabled           = has
        self.BtnSelect.IsEnabled        = has
        self.BtnCompareSurvey.IsEnabled = has

    def Grid_SelectionChanged(self, sender, args):
        selected = list(self.GridSurvey.SelectedItems)
        if not selected:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r.id))) for r in selected])
            revit.uidoc.Selection.SetElementIds(ids)
        except Exception:
            pass

    def Select_Click(self, sender, args):
        if not self._rows:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(Int64(int(r['id']))) for r in self._rows])
            revit.uidoc.Selection.SetElementIds(ids)
            self.TxtStatus.Text = u'{} elements selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Selection error: {}'.format(e))

    def ExportXlsx_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            name = ''
            try:
                name = self.doc.ProjectInformation.Name or ''
            except Exception:
                pass
            _logic.export_xlsx(self._rows, path, name)
            forms.alert(u'Excel exported:\n{}'.format(path))
        except ImportError:
            forms.alert(u'openpyxl not available. Use CSV export.')
        except Exception as e:
            forms.alert(u'Export error: {}'.format(e))

    def ExportCsv_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv(self._rows, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error: {}'.format(e))

    # ── Survey comparison ─────────────────────────────────────────────────────

    def CompareSurvey_Click(self, sender, args):
        if not self._rows:
            return
        import System.Windows.Forms as WinForms
        dlg = WinForms.OpenFileDialog()
        dlg.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        dlg.Title  = "Open surveyed-coordinates CSV"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return

        try:
            tol = float(self.TxtTolerance.Text or '10')
        except (ValueError, AttributeError):
            tol = 10.0

        self.SetLoading(True, u'Comparing survey to model…')
        try:
            survey_pts = _logic.load_survey_csv(dlg.FileName)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Could not read survey file:\n{}'.format(e))
            return

        try:
            results = _logic.compare_survey(self._rows, survey_pts, tolerance_mm=tol)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Comparison error:\n{}'.format(e))
            return
        self.SetLoading(False)

        out_path = forms.save_file(file_ext='csv')
        if out_path:
            try:
                _logic.export_compare_csv(results, out_path)
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
