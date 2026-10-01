# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
import os, sys, io, csv
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List

from pyrevit import forms, revit
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

from nosa_utils.bootstrap import load_module
_logic = load_module('rebaraud_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

EXPOSURE_CLASSES = ['X0','XC1','XC2','XC3','XC4',
                    'XD1','XD2','XD3','XS1','XS2','XS3',
                    'XF1','XF2','XF3','XF4','XA1','XA2','XA3']


class _DictRow(object):
    """Wrap a dict as an attribute-access object for DataGrid binding."""
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class RebarAuditorWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_auditor')
        self.doc = doc

        for cls in EXPOSURE_CLASSES:
            self.CboExposure.Items.Add(cls)
        self.CboExposure.SelectedIndex = 1  # XC1 default

        self._cover_rows  = []
        self._ratio_rows  = []
        self._unrein_rows = []
        self._active_tab  = 'cover'

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    # ── Tab navigation ──────────────────────────────────────────────────────

    def Tab_Click(self, sender, args):
        Vis = System.Windows.Visibility
        name_tab_map = {
            'BtnTabCover':  ('cover',  self.GridCover,  self.GridRatio,  self.GridUnrein),
            'BtnTabRatio':  ('ratio',  self.GridRatio,  self.GridCover,  self.GridUnrein),
            'BtnTabUnrein': ('unrein', self.GridUnrein, self.GridCover,  self.GridRatio),
        }
        entry = name_tab_map.get(sender.Name)
        if not entry:
            return
        self._active_tab = entry[0]
        entry[1].Visibility = Vis.Visible
        entry[2].Visibility = Vis.Collapsed
        entry[3].Visibility = Vis.Collapsed

        self.BtnTabCover.Tag  = 'Active' if self._active_tab == 'cover'  else None
        self.BtnTabRatio.Tag  = 'Active' if self._active_tab == 'ratio'  else None
        self.BtnTabUnrein.Tag = 'Active' if self._active_tab == 'unrein' else None

    # ── Run audit ───────────────────────────────────────────────────────────

    def Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgressPanel.Visibility = Vis.Visible
        self.BtnRun.IsEnabled = False

        exposure = self.CboExposure.SelectedItem or 'XC1'
        custom   = None
        try:
            v = float((self.TxtCustomCover.Text or '').strip())
            if v > 0:
                custom = v
        except Exception:
            pass

        opts = {
            'chk_cover':        True,
            'exposure_class':   exposure,
            'custom_cover_mm':  custom,
            'chk_ratio':        True,
            'chk_unrein':       True,
        }

        try:
            result = _logic.run_audit(self.doc, opts)
        except Exception as e:
            self.ProgressPanel.Visibility = Vis.Collapsed
            self.BtnRun.IsEnabled = True
            forms.alert(u'Error during audit:\n{}'.format(e))
            return

        self.ProgressPanel.Visibility = Vis.Collapsed
        self.BtnRun.IsEnabled = True

        self._cover_rows  = result.get('cover',         [])
        self._ratio_rows  = result.get('ratio',         [])
        self._unrein_rows = result.get('unreinforced',  [])

        self._populate_grid(self.GridCover,  self._cover_rows)
        self._populate_grid(self.GridRatio,  self._ratio_rows)
        self._populate_grid(self.GridUnrein, self._unrein_rows)

        cover_fails  = sum(1 for r in self._cover_rows  if r.get('status') == 'FAIL')
        ratio_fails  = sum(1 for r in self._ratio_rows  if r.get('status') == 'FAIL')
        self.TxtCoverFail.Text = u'{} FAIL'.format(cover_fails + ratio_fails)

        total_rebar = len(self._cover_rows)
        self.TxtSummary.Text = (
            u'{} bars · {} cover FAIL · {} ratio FAIL · {} unreinforced'.format(
                total_rebar, cover_fails, ratio_fails, len(self._unrein_rows)))

        self.BtnSelectFail.IsEnabled = True
        self.BtnExport.IsEnabled     = True

    def _populate_grid(self, grid, rows):
        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_DictRow(r))
        grid.ItemsSource = src

    # ── Actions ─────────────────────────────────────────────────────────────

    def SelectFails_Click(self, sender, args):
        if self._active_tab == 'cover':
            ids = [r['id'] for r in self._cover_rows if r.get('status') == 'FAIL']
        elif self._active_tab == 'ratio':
            ids = [r['id'] for r in self._ratio_rows if r.get('status') == 'FAIL']
        else:
            ids = [r['id'] for r in self._unrein_rows]

        if not ids:
            forms.alert(u'No FAIL elements in the active tab.')
            return
        try:
            from System import Int64
            eid_list = List[DB.ElementId]([DB.ElementId(Int64(int(i))) for i in ids])
            revit.uidoc.Selection.SetElementIds(eid_list)
            self.TxtSummary.Text = u'{} element(s) selected in Revit.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                # Cover sheet
                w.writerow([u'=== COVER ==='])
                if self._cover_rows:
                    w.writerow(list(self._cover_rows[0].keys()))
                    for r in self._cover_rows:
                        w.writerow([r.get(k, '') for k in self._cover_rows[0].keys()])
                w.writerow([])
                # Ratio sheet
                w.writerow([u'=== REBAR RATIO ==='])
                if self._ratio_rows:
                    w.writerow(list(self._ratio_rows[0].keys()))
                    for r in self._ratio_rows:
                        w.writerow([r.get(k, '') for k in self._ratio_rows[0].keys()])
                w.writerow([])
                # Unreinforced
                w.writerow([u'=== UNREINFORCED ==='])
                if self._unrein_rows:
                    w.writerow(list(self._unrein_rows[0].keys()))
                    for r in self._unrein_rows:
                        w.writerow([r.get(k, '') for k in self._unrein_rows[0].keys()])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))


