# -*- coding: utf-8 -*-
import os, sys
import System.Windows
from System.Windows.Controls import Canvas as WPFCanvas
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Shapes import Ellipse, Rectangle
from System.Windows.Shapes import Polygon as WPFPolygon
from System.Windows import Point
from System.Windows.Media import PointCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.bootstrap import load_module
_logic = load_module('createpilecap_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_CAP_FILL   = Color.FromRgb(220, 220, 220)
_CAP_STROKE = Color.FromRgb(140, 140, 140)
_PILE_COL   = Color.FromRgb(255, 95, 0)


class _Item(object):
    def __init__(self, eid, name):
        self.Id   = eid
        self.Name = name


class CreatePilecapWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'create_pilecap')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.CboShape.SelectionChanged += self.Shape_Changed
        self.doc    = doc
        self._mode  = 'regular'
        self._shape_keys = list(_logic.IRREGULAR_SHAPES.keys())

        # Element type combos
        piles = _logic.get_pile_types(doc)
        self.CboPileType.ItemsSource = [_Item(eid, n) for eid, n in piles]
        if piles: self.CboPileType.SelectedIndex = 0

        caps = _logic.get_cap_types(doc)
        self.CboCapType.ItemsSource = [_Item(eid, n) for eid, n in caps]
        if caps: self.CboCapType.SelectedIndex = 0

        levels = _logic.get_all_levels(doc)
        self.CboLevel.ItemsSource = [_Item(eid, n) for eid, n in levels]
        if levels: self.CboLevel.SelectedIndex = 0

        # Shape combo
        for k in self._shape_keys:
            self.CboShape.Items.Add(_logic.IRREGULAR_SHAPES[k]['label'])
        self.CboShape.SelectedIndex = 0

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self._apply_shape_labels()
        self._refresh_preview()

    # ── Mode switching ─────────────────────────────────────────────────────────

    def ModeRegular_Click(self, sender, args):
        self._mode = 'regular'
        vis = System.Windows.Visibility
        self.PanelRegular.Visibility   = vis.Visible
        self.PanelIrregular.Visibility = vis.Collapsed
        self.BtnModeReg.Tag = 'Active'
        self.BtnModeIrr.Tag = ''
        self._refresh_preview()

    def ModeIrregular_Click(self, sender, args):
        self._mode = 'irregular'
        vis = System.Windows.Visibility
        self.PanelRegular.Visibility   = vis.Collapsed
        self.PanelIrregular.Visibility = vis.Visible
        self.BtnModeReg.Tag = ''
        self.BtnModeIrr.Tag = 'Active'
        self._refresh_preview()

    # ── Shape selection ────────────────────────────────────────────────────────

    def Shape_Changed(self, sender, args):
        self._apply_shape_labels()
        self._refresh_preview()

    def _current_shape_key(self):
        idx = self.CboShape.SelectedIndex
        if 0 <= idx < len(self._shape_keys):
            return self._shape_keys[idx]
        return None

    def _apply_shape_labels(self):
        key = self._current_shape_key()
        if key is None:
            return
        info   = _logic.IRREGULAR_SHAPES[key]
        params = info['params']
        vis    = System.Windows.Visibility

        self.TxtShapeDesc.Text = info['desc']

        for pid, ctrl_lbl, ctrl_box, ctrl_row in [
            ('A', self.TxtParamALabel, self.TxtParamA, self.RowParamA),
            ('B', self.TxtParamBLabel, self.TxtParamB, self.RowParamB),
            ('C', self.TxtParamCLabel, self.TxtParamC, self.RowParamC),
            ('D', self.TxtParamDLabel, self.TxtParamD, self.RowParamD),
        ]:
            p = params.get(pid)
            if p is None:
                ctrl_row.Visibility = vis.Collapsed
            else:
                ctrl_row.Visibility = vis.Visible
                ctrl_lbl.Text       = p[0] + ':'
                try:
                    # Only reset value when switching shapes (avoid resetting on param edits)
                    if ctrl_box.Text.strip() == '':
                        ctrl_box.Text = str(p[1])
                except Exception:
                    ctrl_box.Text = str(p[1])

    def _get_param(self, ctrl, default):
        try:
            return max(1, int(ctrl.Text or str(default)))
        except (ValueError, AttributeError):
            return default

    # ── Preview ────────────────────────────────────────────────────────────────

    def Params_Changed(self, sender, args):
        self._refresh_preview()

    def _refresh_preview(self):
        try:
            if self._mode == 'regular':
                self._draw_regular()
            else:
                self._draw_irregular()
        except Exception:
            pass

    def _parse_spacing_clearance(self):
        try: spc = max(100.0, float(self.TxtSpacing.Text   or '900'))
        except ValueError: spc = 900.0
        try: clr = max(0.0,   float(self.TxtClearance.Text or '150'))
        except ValueError: clr = 150.0
        return spc, clr

    # ── Regular preview ────────────────────────────────────────────────────────

    def _draw_regular(self):
        n_h = max(1, self._get_param(self.TxtNH, 2))
        n_v = max(1, self._get_param(self.TxtNV, 2))
        spc, clr = self._parse_spacing_clearance()
        cap_w, cap_h = _logic.calc_dimensions(n_h, n_v, spc, clr)

        self.TxtInfoPiles.Text = u'Piles: {}  ({} \xd7 {})'.format(n_h * n_v, n_h, n_v)
        self.TxtInfoCap.Text   = u'Cap: {:.0f} \xd7 {:.0f} mm'.format(cap_w, cap_h)
        self.TxtDims.Text      = u'{}\xd7{} piles — {:.0f}\xd7{:.0f} mm'.format(
                                    n_h, n_v, cap_w, cap_h)

        self.PileCanvas.Children.Clear()
        cw, ch, margin = 400.0, 260.0, 24.0
        if cap_w <= 0 or cap_h <= 0:
            return
        scale    = min((cw - 2*margin) / cap_w, (ch - 2*margin) / cap_h)
        cap_px_w = cap_w * scale
        cap_px_h = cap_h * scale
        ox = (cw - cap_px_w) / 2.0
        oy = (ch - cap_px_h) / 2.0

        rect = Rectangle()
        rect.Width           = cap_px_w
        rect.Height          = cap_px_h
        rect.Fill            = SolidColorBrush(_CAP_FILL)
        rect.Stroke          = SolidColorBrush(_CAP_STROKE)
        rect.StrokeThickness = 1.5
        WPFCanvas.SetLeft(rect, ox)
        WPFCanvas.SetTop(rect,  oy)
        self.PileCanvas.Children.Add(rect)

        pile_dia = max(6.0, min(26.0, spc * scale * 0.35))
        for ri in range(n_v):
            for ci in range(n_h):
                px = ox + clr*scale + ci*spc*scale
                py = oy + clr*scale + ri*spc*scale
                self._draw_pile_dot(px, py, pile_dia)

    # ── Irregular preview ──────────────────────────────────────────────────────

    def _draw_irregular(self):
        key = self._current_shape_key()
        if key is None:
            return
        info   = _logic.IRREGULAR_SHAPES[key]
        params = info['params']

        a = self._get_param(self.TxtParamA, params['A'][1]) if params.get('A') else 1
        b = self._get_param(self.TxtParamB, params['B'][1]) if params.get('B') else 1
        c = self._get_param(self.TxtParamC, params['C'][1]) if params.get('C') else 1
        d = self._get_param(self.TxtParamD, params['D'][1]) if params.get('D') else 1

        spc, clr = self._parse_spacing_clearance()

        try:
            cells   = _logic.get_irregular_cells(key, a, b, c, d)
            poly_mm = _logic.compute_cap_polygon(cells, spc, clr)
            offsets = _logic.pile_offsets_mm(cells, spc)
        except Exception:
            return

        n_piles = len(cells)
        self.TxtInfoPiles.Text = u'Piles: {}'.format(n_piles)
        self.TxtInfoCap.Text   = u'{} — {}mm spacing, {}mm clearance'.format(
                                    info['label'], int(spc), int(clr))

        try:
            ok, problems = _logic.validate_cap_polygon(poly_mm, offsets, clr)
        except Exception:
            ok, problems = True, []
        if ok:
            self.TxtDims.Text = u'{} — {} piles'.format(info['label'], n_piles)
        else:
            self.TxtDims.Text = u'{} — {} piles — GEOMETRY WARNING: {}'.format(
                info['label'], n_piles, problems[0])

        self.PileCanvas.Children.Clear()
        cw, ch, margin = 400.0, 260.0, 24.0

        if not poly_mm or not offsets:
            return

        # Polygon mm coords are already centred on pile centroid (same origin as pile offsets).
        # Use combined extent of polygon + pile dots to compute a consistent scale.
        all_x  = [p[0] for p in poly_mm]
        all_y  = [p[1] for p in poly_mm]
        w_mm   = max(all_x) - min(all_x)
        h_mm   = max(all_y) - min(all_y)
        if w_mm <= 0 or h_mm <= 0:
            return

        scale  = min((cw - 2*margin) / w_mm, (ch - 2*margin) / h_mm)
        # Both polygon and pile offsets are relative to the pile centroid (origin = centroid).
        # Shift the canvas centre so the BOUNDING BOX of the polygon is centred on screen.
        bb_cx = (max(all_x) + min(all_x)) / 2.0
        bb_cy = (max(all_y) + min(all_y)) / 2.0
        ox = cw / 2.0 - bb_cx * scale
        oy = ch / 2.0 + bb_cy * scale   # +bb_cy because y is flipped

        # Cap polygon — drawn with same origin/scale as pile offsets
        pts = PointCollection()
        for (x, y) in poly_mm:
            pts.Add(Point(ox + x*scale, oy - y*scale))
        poly_shape = WPFPolygon()
        poly_shape.Points          = pts
        poly_shape.Fill            = SolidColorBrush(_CAP_FILL)
        poly_shape.Stroke          = SolidColorBrush(_CAP_STROKE)
        poly_shape.StrokeThickness = 1.5
        self.PileCanvas.Children.Add(poly_shape)

        # Piles — same origin/scale
        pile_dia = max(5.0, min(22.0, spc * scale * 0.32))
        for (dx, dy) in offsets:
            self._draw_pile_dot(ox + dx*scale, oy - dy*scale, pile_dia)

    def _draw_pile_dot(self, px, py, dia):
        e = Ellipse()
        e.Width  = dia
        e.Height = dia
        e.Fill   = SolidColorBrush(_PILE_COL)
        WPFCanvas.SetLeft(e, px - dia/2.0)
        WPFCanvas.SetTop(e,  py - dia/2.0)
        self.PileCanvas.Children.Add(e)

    # ── Config builders ────────────────────────────────────────────────────────

    def _common_config(self):
        pile_item = self.CboPileType.SelectedItem
        cap_item  = self.CboCapType.SelectedItem
        lvl_item  = self.CboLevel.SelectedItem
        if pile_item is None: forms.alert('Select a pile type.'); return None
        if cap_item  is None: forms.alert('Select a cap slab type.'); return None
        if lvl_item  is None: forms.alert('Select a level.'); return None
        spc, clr = self._parse_spacing_clearance()
        try:
            cut = max(0.0, float(self.TxtCutoff.Text or '75'))
        except ValueError:
            forms.alert('Cutoff must be a number.'); return None
        return {
            'spacing_mm':   spc,
            'clearance_mm': clr,
            'cutoff_mm':    cut,
            'cap_type_id':  cap_item.Id,
            'pile_type_id': pile_item.Id,
            'level_id':     lvl_item.Id,
        }

    def _build_regular_config(self):
        cfg = self._common_config()
        if cfg is None: return None
        try:
            cfg['n_h'] = max(1, int(self.TxtNH.Text or '2'))
            cfg['n_v'] = max(1, int(self.TxtNV.Text or '2'))
        except ValueError:
            forms.alert('Pile counts must be integers.'); return None
        return cfg

    def _build_irregular_config(self):
        cfg = self._common_config()
        if cfg is None: return None
        key = self._current_shape_key()
        if key is None: forms.alert('Select a shape.'); return None
        info   = _logic.IRREGULAR_SHAPES[key]
        params = info['params']
        try:
            a = self._get_param(self.TxtParamA, params['A'][1]) if params.get('A') else 1
            b = self._get_param(self.TxtParamB, params['B'][1]) if params.get('B') else 1
            c = self._get_param(self.TxtParamC, params['C'][1]) if params.get('C') else 1
            d = self._get_param(self.TxtParamD, params['D'][1]) if params.get('D') else 1
        except Exception:
            forms.alert('Shape parameters must be integers.'); return None
        cfg.update({'shape_key': key,
                    'param_a': a, 'param_b': b,
                    'param_c': c, 'param_d': d})
        return cfg

    # ── Place ──────────────────────────────────────────────────────────────────

    def Place_Click(self, sender, args):
        if self._mode == 'regular':
            config    = self._build_regular_config()
            create_fn = _logic.create_pilecap
        else:
            config    = self._build_irregular_config()
            create_fn = _logic.create_pilecap_irregular
        if config is None:
            return

        self.Hide()
        pt = None
        try:
            pt = revit.uidoc.Selection.PickPoint('Click to place pile cap centre')
        except Exception:
            pass
        self.Show()
        if pt is None:
            return

        self.SetLoading(True, 'Creating pile cap...')
        try:
            created, errors = create_fn(self.doc, config, pt)
        except Exception as e:
            self.SetLoading(False)
            forms.alert('Creation failed: {}'.format(e))
            return
        self.SetLoading(False)

        msg = 'Created {} elements.'.format(created)
        if errors:
            msg += '\n\nWarnings:\n' + '\n'.join(errors[:5])
        forms.alert(msg, title='Pile Cap Created')
