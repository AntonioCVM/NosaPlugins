# -*- coding: utf-8 -*-
import imp
import math
import os
import sys

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import forms, revit

import System.Windows
from System.Windows.Controls import Canvas as WPFCanvas
from System.Windows.Media import SolidColorBrush, Color, PointCollection
from System.Windows.Shapes import Ellipse, Polygon as WPFPolygon
from System.Windows import Point

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

_CAP_FILL   = Color.FromRgb(220, 220, 220)
_CAP_STROKE = Color.FromRgb(140, 140, 140)
_PILE_COL   = Color.FromRgb(255, 95, 0)


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

    def _try_read_numbers(self):
        """Silent variant of _read_numbers() — no alerts, for live preview refresh."""
        try:
            spacing = float(self.TxtSpacing.Text.strip())
            embedment = float(self.TxtEmbedment.Text.strip())
        except (ValueError, AttributeError):
            return None, None
        if not (_logic.MIN_SPACING_MM <= spacing <= _logic.MAX_SPACING_MM):
            return None, None
        if not (_logic.MIN_EMBEDMENT_MM <= embedment <= _logic.MAX_EMBEDMENT_MM):
            return None, None
        return spacing, embedment

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

    # ── Preview ────────────────────────────────────────────────────────────────
    # Shared by Create_Click (real creation) and the live canvas preview, so the
    # preview always shows exactly the grid that would be built.

    def _suggest_distribution(self, spacing_mm):
        """Fill TxtPilesU/TxtPilesV with the geometrically-optimal pile count
        for the current slab and spacing — a sensible starting point, not a
        hard limit; both fields stay freely editable afterwards."""
        if not self._layout:
            return
        spacing_ft = unit_conversion.mm_to_feet(spacing_mm)
        n_spaces_u, _margin_u = _logic.calculate_pile_distribution(self._layout['slab_width'], spacing_ft)
        n_spaces_v, _margin_v = _logic.calculate_pile_distribution(self._layout['slab_height'], spacing_ft)
        self.TxtPilesU.Text = str(n_spaces_u + 1)
        self.TxtPilesV.Text = str(n_spaces_v + 1)

    def SuggestDistribution_Click(self, sender, args):
        spacing_mm, _embedment_mm = self._try_read_numbers()
        if spacing_mm is None:
            forms.alert(u'Enter a valid spacing (mm) first.')
            return
        self._suggest_distribution(spacing_mm)

    def _try_read_pile_counts(self):
        """Silent parse of TxtPilesU/TxtPilesV — None, None if invalid, for
        live preview refresh."""
        try:
            n_u = int(float(self.TxtPilesU.Text.strip()))
            n_v = int(float(self.TxtPilesV.Text.strip()))
        except (ValueError, AttributeError):
            return None, None
        if n_u < 1 or n_v < 1:
            return None, None
        return n_u, n_v

    def _read_pile_counts(self):
        n_u, n_v = self._try_read_pile_counts()
        if n_u is None:
            forms.alert(u'Enter valid whole numbers (≥ 1) for Piles U and Piles V.')
            return None, None
        return n_u, n_v

    def _distribution_margins(self, n_u, n_v, spacing_ft):
        """(margin_u_ft, margin_v_ft) for n_u × n_v piles at the given spacing
        over the current slab's bounding dimensions — used both to size the
        min_edge tolerance for irregular slabs and to warn the user in the
        preview if their chosen count doesn't fit well."""
        layout = self._layout
        margin_u = (layout['slab_width']  - (n_u - 1) * spacing_ft) / 2.0
        margin_v = (layout['slab_height'] - (n_v - 1) * spacing_ft) / 2.0
        return margin_u, margin_v

    def _compute_grid_points(self):
        """
        Returns a list of pile XYZ points for the current slab/pattern/spacing/
        distribution, or None if inputs are incomplete/invalid, or the pattern
        is 'manual' (picked interactively — nothing to precompute).
        """
        if not self._slab or not self._layout:
            return None
        spacing_mm, _embedment_mm = self._try_read_numbers()
        if spacing_mm is None:
            return None
        n_piles_u, n_piles_v = self._try_read_pile_counts()
        if n_piles_u is None:
            return None

        pattern = self._current_pattern()
        if pattern == 'manual':
            return None

        n_spaces_u = n_piles_u - 1
        n_spaces_v = n_piles_v - 1

        layout = self._layout
        span_dir = layout['span_dir']
        perp_dir = layout['perp_dir']
        slab_center = layout['slab_center']
        slab_z = layout['slab_z']
        slab_width = layout['slab_width']
        slab_height = layout['slab_height']

        spacing_ft = unit_conversion.mm_to_feet(spacing_mm)
        slab_boundary = _logic.extract_face_boundary_points(self._face_inf)
        edge_margin_u, edge_margin_v = self._distribution_margins(n_piles_u, n_piles_v, spacing_ft)
        min_edge = max(50 / 304.8, spacing_ft * 0.10,
                       min(edge_margin_u, edge_margin_v, spacing_ft * 0.15))

        is_rect = len(slab_boundary) <= 6
        try:
            if is_rect:
                grid_points = _logic.generate_rectangular_grid(
                    slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                    n_piles_u, n_piles_v, n_spaces_u, n_spaces_v)
            else:
                grid_points, _rejected = _logic.generate_irregular_grid(
                    slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                    slab_width, slab_height, slab_boundary, self._face_inf, min_edge)

            if pattern == 'triangular':
                grid_points = _logic.generate_triangular_grid(
                    slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                    slab_width, slab_height, slab_boundary, self._face_inf, min_edge)
            elif pattern == 'hexagonal':
                grid_points = _logic.generate_hexagonal_grid(
                    slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                    slab_width, slab_height, slab_boundary, self._face_inf, min_edge)
        except Exception:
            return None

        return grid_points

    def _project_uv(self, pt, layout):
        vec = pt - layout['slab_center']
        return self._project_uv_delta(vec.X, vec.Y, layout)

    def _project_uv_xy(self, x, y, layout):
        """Same projection as _project_uv, but from a raw world (x, y) tuple
        (as returned by _logic.extract_face_boundary_points) instead of an
        XYZ point."""
        center = layout['slab_center']
        return self._project_uv_delta(x - center.X, y - center.Y, layout)

    def _project_uv_delta(self, dx, dy, layout):
        u = dx * layout['span_dir'].X + dy * layout['span_dir'].Y
        v = dx * layout['perp_dir'].X + dy * layout['perp_dir'].Y
        return u, v

    def Preview_Changed(self, sender, args):
        self._refresh_preview()

    def _refresh_preview(self):
        try:
            self._draw_preview()
        except Exception:
            pass

    def _draw_preview(self):
        self.PileCanvas.Children.Clear()
        if not self._slab or not self._layout:
            self.TxtPreviewInfo.Text = u'Select a foundation slab to preview piles.'
            return

        layout = self._layout
        # extract_face_boundary_points() walks the OUTER edge loop only, in
        # sequential order — unlike layout['vertices'] (get_face_vertices),
        # which concatenates every edge loop (incl. any inner ones) with no
        # guaranteed relative order, producing a self-intersecting shape if
        # drawn directly as a polygon.
        boundary = _logic.extract_face_boundary_points(self._face_inf)
        verts_uv = [self._project_uv_xy(x, y, layout) for x, y in boundary]

        pattern = self._current_pattern()
        if pattern == 'manual':
            grid_points = []
            self.TxtPreviewInfo.Text = u'Manual mode — positions are picked interactively on Create.'
        else:
            grid_points = self._compute_grid_points() or []
            info = (u'{} piles'.format(len(grid_points)) if grid_points
                    else u'No valid pile positions for the current settings.')
            n_u, n_v = self._try_read_pile_counts()
            spacing_mm, _emb = self._try_read_numbers()
            if n_u is not None and spacing_mm is not None:
                spacing_ft = unit_conversion.mm_to_feet(spacing_mm)
                margin_u, margin_v = self._distribution_margins(n_u, n_v, spacing_ft)
                info += u'  —  edge margin U: {:.0f} mm, V: {:.0f} mm'.format(
                    unit_conversion.feet_to_mm(margin_u), unit_conversion.feet_to_mm(margin_v))
                if margin_u < 0 or margin_v < 0:
                    info += u'  ⚠ piles would fall outside the slab — reduce Piles U/V.'
            self.TxtPreviewInfo.Text = info

        piles_uv = [self._project_uv(p, layout) for p in grid_points]

        all_u = [u for u, v in verts_uv] + [u for u, v in piles_uv]
        all_v = [v for u, v in verts_uv] + [v for u, v in piles_uv]
        if not all_u or not all_v:
            return
        w_ft = max(all_u) - min(all_u)
        h_ft = max(all_v) - min(all_v)
        if w_ft <= 0 or h_ft <= 0:
            return

        cw, ch, margin = 360.0, 220.0, 20.0
        scale = min((cw - 2 * margin) / w_ft, (ch - 2 * margin) / h_ft)
        cx = (max(all_u) + min(all_u)) / 2.0
        cy = (max(all_v) + min(all_v)) / 2.0
        ox, oy = cw / 2.0, ch / 2.0

        def to_px(u, v):
            return ox + (u - cx) * scale, oy - (v - cy) * scale

        pts = PointCollection()
        for u, v in verts_uv:
            x, y = to_px(u, v)
            pts.Add(Point(x, y))
        poly = WPFPolygon()
        poly.Points          = pts
        poly.Fill            = SolidColorBrush(_CAP_FILL)
        poly.Stroke          = SolidColorBrush(_CAP_STROKE)
        poly.StrokeThickness = 1.5
        self.PileCanvas.Children.Add(poly)

        spacing_mm, _ = self._try_read_numbers()
        spacing_ft = unit_conversion.mm_to_feet(spacing_mm) if spacing_mm else 3.0
        pile_dia_px = max(5.0, min(20.0, spacing_ft * scale * 0.3))
        for u, v in piles_uv:
            x, y = to_px(u, v)
            e = Ellipse()
            e.Width  = pile_dia_px
            e.Height = pile_dia_px
            e.Fill   = SolidColorBrush(_PILE_COL)
            WPFCanvas.SetLeft(e, x - pile_dia_px / 2.0)
            WPFCanvas.SetTop(e,  y - pile_dia_px / 2.0)
            self.PileCanvas.Children.Add(e)

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

        self._slab = slab
        self._level = level
        self._layout = layout
        self._face_inf = face_inf
        self._slab_bottom_z = layout['slab_z']

        self.TxtSlabInfo.Text = u'Slab {} — {:.1f} × {:.1f} ft'.format(
            get_id_value(slab.Id), layout['slab_width'], layout['slab_height'])

        self.TxtPilesU.IsEnabled = True
        self.TxtPilesV.IsEnabled = True
        self.BtnSuggestDistribution.IsEnabled = True
        self.BtnCreate.IsEnabled = True
        self._suggest_distribution(spacing_mm)
        self.LogLine(u'Slab selected — adjust distribution and create.')
        self._refresh_preview()

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
        embedment_ft = unit_conversion.mm_to_feet(embedment_mm)

        if pattern != 'manual':
            n_u, n_v = self._read_pile_counts()
            if n_u is None:
                return

        layout = self._layout
        span_rotation_angle = layout['span_rotation_angle']

        if pattern == 'manual':
            self.Hide()
            try:
                grid_points = _logic.generate_manual_grid(self.uidoc, layout['slab_z'])
            finally:
                self.Show()
        else:
            # Same computation the live preview already showed — no re-derivation.
            grid_points = self._compute_grid_points()

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
