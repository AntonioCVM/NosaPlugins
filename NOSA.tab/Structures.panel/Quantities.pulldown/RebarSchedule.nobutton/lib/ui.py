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

_logic = imp.load_source('rebar_sched_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_ALL_LEVELS = u'— All levels —'
_NO_EXCLUDE = u'— None (include all) —'


class RebarScheduleWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_schedule')
        self.doc         = doc
        self._rows       = []
        self._totals     = None
        self._level_map  = {}
        self._phase_map  = {}

        # Host category filter
        for name in _logic.get_host_filter_names():
            self.CboHostCat.Items.Add(name)
        self.CboHostCat.SelectedIndex = 0

        # Level filter
        self.CboLevel.Items.Add(_ALL_LEVELS)
        for name, lvid in _logic.get_levels(doc):
            self.CboLevel.Items.Add(name)
            self._level_map[name] = lvid
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
        self.TxtProgress.Text      = u'Scanning rebar…'
        self.BtnGenerate.IsEnabled = False
        self.BtnXlsx.IsEnabled     = False
        self.BtnCsv.IsEnabled      = False

        if self.RbGroupHost.IsChecked:
            group_by = 'host'
        elif self.RbGroupDiameter.IsChecked:
            group_by = 'diameter'
        else:
            group_by = 'shape'

        # Host category filter
        host_idx     = self.CboHostCat.SelectedIndex
        host_options = _logic._host_filter_options()
        host_bic     = host_options[host_idx][1] if 0 <= host_idx < len(host_options) else None

        # Level filter
        lv_sel = self.CboLevel.SelectedItem
        lv_id  = self._level_map.get(lv_sel) if lv_sel and lv_sel != _ALL_LEVELS else None

        # Phase filter
        ph_sel = self.CboPhase.SelectedItem
        ph_id  = self._phase_map.get(ph_sel) if ph_sel and ph_sel != _NO_EXCLUDE else None

        options = {
            'group_by':        group_by,
            'filter_host_bic': host_bic,
            'filter_level_id': lv_id,
            'filter_phase_id': ph_id,
            'show_subtotals':  bool(self.ChkSubtotals.IsChecked),
        }

        try:
            rows, totals = _logic.collect_schedule(self.doc, options)
        except Exception as e:
            self.ProgBar.Visibility    = Vis.Collapsed
            self.TxtProgress.Text      = u''
            self.BtnGenerate.IsEnabled = True
            forms.alert(u'Error generating schedule:\n{}'.format(e))
            return

        self._rows   = rows
        self._totals = totals

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(r)
        self.GridSchedule.ItemsSource = src

        if totals:
            self.TxtTotalBars.Text   = str(totals.n_bars or 0)
            self.TxtTotalLength.Text = u'{:.2f} m'.format(totals.total_length_m or 0)
            self.TxtTotalWeight.Text = totals.total_wt_str

        self.ProgBar.Visibility    = Vis.Collapsed
        detail_rows = [r for r in rows if not r.is_subtotal]
        self.TxtProgress.Text      = u'{} bar groups found.'.format(len(detail_rows))
        self.BtnGenerate.IsEnabled = True
        self.BtnXlsx.IsEnabled       = True
        self.BtnCsv.IsEnabled        = True
        self.BtnCompliance.IsEnabled = True

    # ── Selection ────────────────────────────────────────────────────────────

    def Grid_SelectionChanged(self, sender, args):
        selected = list(self.GridSchedule.SelectedItems)
        ids = []
        for r in selected:
            if not r.is_subtotal:
                ids.extend(r.el_ids or [])
        if ids:
            try:
                eid_list = List[DB.ElementId](
                    [DB.ElementId(Int64(int(i))) for i in ids])
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
            proj = ''
            try:
                proj = self.doc.ProjectInformation.Name or ''
            except Exception:
                pass
            _logic.export_xlsx(self._rows, self._totals, path, proj)
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

    # ── Compliance ────────────────────────────────────────────────────────────

    def Compliance_Click(self, sender, args):
        if not self._rows:
            return
        try:
            std_item = self.CboStandard.SelectedItem
            std = 'EHE' if std_item and 'EHE' in (std_item.Content or '') else 'EC2'
        except Exception:
            std = 'EC2'

        try:
            issues = _logic.check_compliance(self._rows, standard=std)
            summary = _logic.compliance_summary(issues)
        except Exception as e:
            forms.alert(u'Compliance check error:\n{}'.format(e))
            return

        forms.alert(summary, title=u'Rebar Compliance — {}'.format(std))
