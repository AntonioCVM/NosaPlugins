# -*- coding: utf-8 -*-
import io, csv, os, sys, imp

from pyrevit import forms
from System.Collections.ObjectModel import ObservableCollection

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_st_logic = imp.load_source('st_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


def _fmt(val, decimals=0):
    if val is None:
        return u'—'
    return u'{:,.{}f}'.format(val, decimals)


class TopoRow(object):
    def __init__(self, d):
        self.Kind      = d['kind']
        self.ElemId    = d['id']
        self.ElemName  = d['name']
        self.ZMin      = _fmt(d['z_min'])
        self.ZMax      = _fmt(d['z_max'])
        self.Footprint = _fmt(d['footprint_sqm'], 1)


class PropLineRow(object):
    def __init__(self, d):
        self.ElemId    = d['id']
        self.ElemName  = d['name']
        self.Segments  = d['segments']
        self.Perimeter = _fmt(d['perimeter_mm'])


class SiteRefRow(object):
    def __init__(self, d):
        self.Label      = d['label'] if d['found'] else u'{} (not found)'.format(d['label'])
        self.EastWest   = _fmt(d['ew_mm'])
        self.NorthSouth = _fmt(d['ns_mm'])
        self.Elevation  = _fmt(d['elev_mm'])
        self.Angle      = _fmt(d['angle_deg'], 2)


class SiteToolkitWindow(NOSAWindow):

    def __init__(self, doc):
        self._is_loaded = False
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'site_toolkit')
        self.doc = doc

        self._topo_rows = ObservableCollection[TopoRow]()
        self.GridTopo.ItemsSource = self._topo_rows
        self._prop_rows = ObservableCollection[PropLineRow]()
        self.GridProp.ItemsSource = self._prop_rows
        self._site_rows = ObservableCollection[SiteRefRow]()
        self.GridSite.ItemsSource = self._site_rows

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._refresh_all()
        self._is_loaded = True

    # ── refresh ───────────────────────────────────────────────────────────

    def Refresh_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._refresh_all()

    def _refresh_all(self):
        self.SetLoading(True, u'Scanning model…')
        try:
            topo = _st_logic.get_topography(self.doc)
            props = _st_logic.get_property_lines(self.doc)
            site = _st_logic.get_site_reference(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Scan failed:\n{}'.format(e))
            return
        self.SetLoading(False)

        self._topo_rows.Clear()
        for d in topo:
            self._topo_rows.Add(TopoRow(d))
        self.TxtTopoSummary.Text = u'{} topography element(s) found.'.format(len(topo))

        self._prop_rows.Clear()
        for d in props:
            self._prop_rows.Add(PropLineRow(d))
        self.TxtPropSummary.Text = u'{} property line(s) found.'.format(len(props))

        self._site_rows.Clear()
        for d in site:
            self._site_rows.Add(SiteRefRow(d))

    # ── export ────────────────────────────────────────────────────────────

    def Export_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        idx = self.TabsMain.SelectedIndex
        if idx == 0:
            self._export_rows(u'topography.csv',
                               ['Type', 'Id', 'Name', 'Min elev. (mm)', 'Max elev. (mm)', 'Footprint (m2, approx.)'],
                               [(r.Kind, r.ElemId, r.ElemName, r.ZMin, r.ZMax, r.Footprint) for r in self._topo_rows])
        elif idx == 1:
            self._export_rows(u'property_lines.csv',
                               ['Id', 'Name', 'Segments', 'Perimeter (mm)'],
                               [(r.ElemId, r.ElemName, r.Segments, r.Perimeter) for r in self._prop_rows])
        else:
            self._export_rows(u'site_reference.csv',
                               ['Point', 'East/West (mm)', 'North/South (mm)', 'Elevation (mm)', 'Angle to true north (deg)'],
                               [(r.Label, r.EastWest, r.NorthSouth, r.Elevation, r.Angle) for r in self._site_rows])

    def _export_rows(self, default_name, header, rows):
        if not rows:
            forms.alert(u'Nothing to export on this tab.')
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(header)
                for row in rows:
                    w.writerow(list(row))
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
