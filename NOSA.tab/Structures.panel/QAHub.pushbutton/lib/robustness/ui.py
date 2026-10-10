# -*- coding: utf-8 -*-
"""T8.50 — Robustness ties (IStructE SMDSC 5.1.9 / EC2 9.10): tie forces and steel, and the ties a floor's bars give."""
import os

from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow
from nosa_utils import ties


class _Row(object):
    def __init__(self, element, check, result, detail):
        self.Element = element
        self.Check = check
        self.Result = result
        self.Detail = detail


class RobustnessWindow(NOSAWindow):

    _FIELDS = (('TxtStoreys', 'storeys', u'4'), ('TxtLoads', 'loads', u'8.5'), ('TxtSpan', 'span', u'7.5'),
               ('TxtHeight', 'height', u'3.0'), ('TxtColumnLoad', 'column_load', u'1500'), ('TxtDia', 'dia', u'12'))

    def __init__(self, doc):
        NOSAWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'ui.xaml'), 'robustness_ties')
        self.doc = doc
        config = self.LoadConfig() or {}
        for name, key, default in self._FIELDS:
            getattr(self, name).Text = u'{}'.format(config.get(key, default))
        self.TxtStatus.Text = u'Give the building data and calculate; select floors to check the ties their bars give.'

    def _values(self):
        out = {}
        for name, key, _default in self._FIELDS:
            try:
                out[key] = float(getattr(self, name).Text.replace(u',', u'.'))
            except Exception:
                raise ValueError(u'{} is not a number.'.format(key.replace(u'_', u' ').capitalize()))
        self.SaveConfig(dict((k, v) for k, v in out.items()))
        return out

    def Calculate_Click(self, sender, args):
        try:
            v = self._values()
        except ValueError as e:
            self.TxtStatus.Text = u'{}'.format(e)
            return
        n, dia = int(v['storeys']), v['dia']
        rows = [
            (u'Ft = (20 + 4 n0) <= 60', u'{:.0f} kN'.format(ties.ft_kn(n))),
            (u'Peripheral tie, within 1.2 m of the edge', u'{:.0f} kN: {:.0f} mm2, {} H{:.0f}'.format(
                ties.peripheral_kn(n), ties.area_mm2(ties.peripheral_kn(n)), ties.bars_needed(ties.peripheral_kn(n), dia),
                dia)),
            (u'Internal ties, each direction', u'{:.1f} kN/m: {:.0f} mm2/m; grouped at most {:.1f} m apart'.format(
                ties.internal_kn_per_m(v['loads'], v['span'], n),
                ties.area_mm2(ties.internal_kn_per_m(v['loads'], v['span'], n)), ties.internal_max_spacing_m(v['span']))),
            (u'Edge column / wall ties', u'{:.0f} kN (per column, per metre of wall): {:.0f} mm2, {} H{:.0f}'.format(
                ties.column_tie_kn(n, v['height'], v['column_load']),
                ties.area_mm2(ties.column_tie_kn(n, v['height'], v['column_load'])),
                ties.bars_needed(ties.column_tie_kn(n, v['height'], v['column_load']), dia), dia)),
            (u'Vertical ties', u'each column and wall continuous from the lowest to the highest level, for the load '
                               u'of one storey in the accidental situation (EN 1990 6.11b)'),
        ]
        self.TxtResult.Text = u'\n'.join(u'{}: {}'.format(a, b) for a, b in rows)
        self.TxtStatus.Text = u'SMDSC 5.1.9 / EC2 9.10 with the UK NA; accidental situation, fyd = fyk = 500 MPa.'

    def Check_Click(self, sender, args):
        try:
            v = self._values()
        except ValueError as e:
            self.TxtStatus.Text = u'{}'.format(e)
            return
        from pyrevit import revit
        from Autodesk.Revit import DB
        from nosa_utils.revit_helpers import get_id_value
        floors = [self.doc.GetElement(i) for i in revit.uidoc.Selection.GetElementIds()]
        floors = [f for f in floors if isinstance(f, DB.Floor)]
        if not floors:
            self.TxtStatus.Text = u'Select the floors to check first.'
            return
        rows = ObservableCollection[object]()
        bad = 0
        self.SetLoading(True, u'Reading the floors’ bars…')
        try:
            for f in floors:
                for check, ok, text in ties.check_floor(self.doc, f, int(v['storeys']), v['loads'], v['span']):
                    rows.Add(_Row(u'Floor {}'.format(get_id_value(f.Id)), check, u'OK' if ok else u'Missing', text))
                    bad += 0 if ok else 1
        finally:
            self.SetLoading(False)
        self.GridChecks.ItemsSource = rows
        self.TxtStatus.Text = u'{} check(s), {} short. Ties may also run in beams and walls: check those by hand.'.format(
            rows.Count, bad)
