# -*- coding: utf-8 -*-
import imp
import math
import os
import sys

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import unit_conversion, ui_helpers
from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value

_logic = imp.load_source('addpiletopilecap_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

_PATTERNS = [
    ('rectangular', u'Rectangular — standard N×M grid'),
    ('triangular',  u'Triangular — offset rows'),
    ('hexagonal',   u'Hexagonal — honeycomb layout'),
    ('manual',      u'Manual — pick each position'),
]


class AddPileToPilecapWindow(NOSAWindow):

    def __init__(self, doc, uidoc, output):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'addpiletopilecap')
        self.doc = doc
        self.uidoc = uidoc
        self.output = output

        self._slab = None
        self._level = None
        self._layout = None
        self._face_inf = None
        self._slab_bottom_z = None
        self._distribution_details = []
        self._symbol_map = {}
        self._pile_symbols = []

        for _, label in _PATTERNS:
            self.CboPattern.Items.Add(label)
        self.CboPattern.SelectedIndex = 0

        last = _logic.load_last_config()
        self.TxtSpacing.Text   = str(last['spacing_mm'])
        self.TxtEmbedment.Text = str(last['embedment_mm'])

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._load_pile_types(last.get('pile_type'))
        self.LogLine(u'Configure piles, select a foundation slab, then create.')

    def _load_pile_types(self, last_name):
        log_fn = lambda msg: self.LogLine(msg)
        self._pile_symbols, self._symbol_map, names = _logic.build_pile_symbol_map(self.doc, log_fn)
        self.CboPileType.Items.Clear()
        for n in names:
            self.CboPileType.Items.Add(n)
        if not names:
            self.LogLine(u'No pile families found — load Pile Square piling or Pile-Steel Pipe.')
            return
        idx = 0
        if last_name and last_name in names:
            idx = names.index(last_name)
        self.CboPileType.SelectedIndex = idx

    def _current_pattern(self):
        idx = self.CboPattern.SelectedIndex
        if idx < 0 or idx >= len(_PATTERNS):
            return 'rectangular'
        return _PATTERNS[idx][0]

    def _read_numbers(self):
        try:
            spacing = float(self.TxtSpacing.Text.strip())
            embedment = float(self.TxtEmbedment.Text.strip())
        except ValueError:
            forms.alert(u'Enter valid numbers for spacing and embedment (mm).')
            return None, None
        if not (_logic.MIN_SPACING_MM <= spacing <= _logic.MAX_SPACING_MM):
            forms.alert(u'Spacing must be between {} and {} mm.'.format(
                _logic.MIN_SPACING_MM, _logic.MAX_SPACING_MM))
            return None, None
        if not (_logic.MIN_EMBEDMENT_MM <= embedment <= _logic.MAX_EMBEDMENT_MM):
            forms.alert(u'Embedment must be between {} and {} mm.'.format(
                _logic.MIN_EMBEDMENT_MM, _logic.MAX_EMBEDMENT_MM))
            return None, None
        return spacing, embedment

    def SelectSlab_Click(self, sender, args):
        spacing_mm, embedment_mm = self._read_numbers()
        if spacing_mm is None:
            return
        if self.CboPileType.SelectedIndex < 0:
            forms.alert(u'Select a pile type first.')
            return

        self.Hide()
        try:
            slab = self.doc.GetElement(
                self.uidoc.Selection.PickObject(
                    ObjectType.Element,
                    _logic.SlabFilter(),
                    u'Select a foundation slab',
                )
            )
        except OperationCanceledException:
            slab = None
        finally:
            self.Show()

        if not slab:
            return

        level = _logic.get_slab_level(self.doc, slab)
        if not level:
            from Autodesk.Revit import DB
            levels = list(DB.FilteredElementCollector(self.doc).OfClass(DB.Level))
            names = [n.Name for n in levels]
            pick = forms.SelectFromList.show(names, title=u'Select level for piles')
            if pick is None:
                return
            level = levels[names.index(pick)]

        slab_solid = _logic.get_slab_solid_cached(slab)
        if not slab_solid:
            forms.alert(u'Could not obtain slab geometry.')
            return

        face_inf, min_z = _logic.bottom_face(slab_solid)
        if not face_inf:
            forms.alert(u'Could not determine slab bottom face.')
            return

        layout = _logic.compute_slab_layout(face_inf, min_z)
        if not layout['vertices']:
            forms.alert(u'Could not extract slab layout.')
            return

        spacing_ft = unit_conversion.mm_to_feet(spacing_mm)
        n_spaces_u, margin_u = _logic.calculate_pile_distribution(layout['slab_width'], spacing_ft)
        n_spaces_v, margin_v = _logic.calculate_pile_distribution(layout['slab_height'], spacing_ft)
        options = _logic.generate_distribution_options(
            layout['slab_width'], layout['slab_height'], spacing_ft, n_spaces_u, n_spaces_v)

        self._slab = slab
        self._level = level
        self._layout = layout
        self._face_inf = face_inf
        self._slab_bottom_z = layout['slab_z']
        self._distribution_details = options

        self.TxtSlabInfo.Text = u'Slab {} — {:.1f} × {:.1f} ft'.format(
            get_id_value(slab.Id), layout['slab_width'], layout['slab_height'])

        self.CboDistribution.Items.Clear()
        for i, (nu, nv, mu, mv, total) in enumerate(options):
            self.CboDistribution.Items.Add(
                u'{} × {} = {} piles'.format(nu + 1, nv + 1, total))
        self.CboDistribution.SelectedIndex = 0
        self.CboDistribution.IsEnabled = True
        self.BtnCreate.IsEnabled = True
        self.LogLine(u'Slab selected — choose distribution and create.')

        _logic.save_last_config(
            spacing_mm,
            str(self.CboPileType.SelectedItem),
            embedment_mm,
        )

    def Create_Click(self, sender, args):
        if not self._slab or not self._layout:
            forms.alert(u'Select a foundation slab first.')
            return

        spacing_mm, embedment_mm = self._read_numbers()
        if spacing_mm is None:
            return

        pile_name = str(self.CboPileType.SelectedItem)
        pile_symbol = self._symbol_map.get(pile_name)
        if not pile_symbol:
            forms.alert(u'Invalid pile type.')
            return

        if not pile_symbol.IsActive:
            with revit.Transaction(u'Activate Pile Symbol'):
                pile_symbol.Activate()

        pattern = self._current_pattern()
        spacing_ft = unit_conversion.mm_to_feet(spacing_mm)
        embedment_ft = unit_conversion.mm_to_feet(embedment_mm)

        idx = self.CboDistribution.SelectedIndex
        if idx < 0 or idx >= len(self._distribution_details):
            forms.alert(u'Select a pile distribution.')
            return
        n_spaces_u, n_spaces_v, edge_margin_u, edge_margin_v = self._distribution_details[idx]
        n_piles_u = n_spaces_u + 1
        n_piles_v = n_spaces_v + 1

        layout = self._layout
        span_dir = layout['span_dir']
        perp_dir = layout['perp_dir']
        slab_center = layout['slab_center']
        slab_z = layout['slab_z']
        slab_width = layout['slab_width']
        slab_height = layout['slab_height']
        span_rotation_angle = layout['span_rotation_angle']

        slab_boundary = _logic.extract_face_boundary_points(self._face_inf)
        min_edge = max(50 / 304.8, spacing_ft * 0.10,
                       min(edge_margin_u, edge_margin_v, spacing_ft * 0.15))

        is_rect = len(slab_boundary) <= 6
        if is_rect:
            grid_points = _logic.generate_rectangular_grid(
                slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                n_piles_u, n_piles_v, n_spaces_u, n_spaces_v)
        else:
            grid_points, _ = _logic.generate_irregular_grid(
                slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                slab_width, slab_height, slab_boundary, self._face_inf, min_edge)

        self.Hide()
        try:
            grid_points = _logic.apply_pattern_grid(
                pattern, self.uidoc, slab_center, span_dir, perp_dir, slab_z,
                spacing_ft, slab_width, slab_height, slab_boundary,
                self._face_inf, min_edge, grid_points)
        finally:
            self.Show()

        if not grid_points:
            forms.alert(u'No valid pile positions found.')
            return

        if not ui_helpers.confirm_action(
                u'Create {} piles under slab {}?'.format(len(grid_points), get_id_value(self._slab.Id)),
                title=u'Confirm Pile Placement'):
            return

        slab = self._slab
        slab_top_z, slab_bottom_z = _logic.get_slab_elevations(slab)
        if slab_top_z is None or slab_bottom_z is None:
            bbox = slab.get_BoundingBox(None)
            slab_top_z = bbox.Max.Z
            slab_bottom_z = bbox.Min.Z

        pile_top_z = slab_bottom_z + embedment_ft
        pile_height_ft = _logic.get_pile_height(pile_symbol)

        from nosa_utils.progress import nosa_progress
        pile_ids = []
        try:
            with revit.Transaction(u'Create Piles'):
                with nosa_progress(len(grid_points), u'Creating piles',
                                   step=10, window=self) as pb:
                    for i, pt in enumerate(grid_points):
                        pb.update(i)
                        try:
                            inst, _, _ = _logic.create_pile_at_point(
                                self.doc, pt, pile_symbol, self._level, slab,
                                pile_top_z, span_rotation_angle)
                            pile_ids.append(inst.Id)
                        except Exception as ex:
                            self.LogLine(u'Warning: pile at {} failed: {}'.format(pt, ex))
        finally:
            self.SetLoading(False)

        if not pile_ids:
            forms.alert(u'No piles were created.')
            return

        self.LogLine(u'{} piles created.'.format(len(pile_ids)))

        with revit.Transaction(u'Unjoin Piles from Slab'):
            n_unjoin = _logic.unjoin_piles_from_slab(self.doc, pile_ids, slab)
        self.LogLine(u'{} piles unjoined from slab.'.format(n_unjoin))

        next_num = _logic.find_next_core_number(self.doc)
        group_name = u'Core {}'.format(next_num)
        with revit.Transaction(u"Create Group '{}'".format(group_name)):
            try:
                _logic.create_core_group(self.doc, slab.Id, pile_ids, group_name)
                self.LogLine(u'Created group: {}'.format(group_name))
            except Exception as ex:
                self.LogLine(u'Warning: could not create group: {}'.format(ex))

        _logic.save_last_config(spacing_mm, pile_name, embedment_mm)
        forms.alert(
            u'{} piles created and grouped as "{}".'.format(len(pile_ids), group_name),
            title=u'Success',
        )


def run(doc, uidoc, output):
    win = AddPileToPilecapWindow(doc, uidoc, output)
    win.ShowDialog()
