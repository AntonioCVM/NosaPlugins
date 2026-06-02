# -*- coding: utf-8 -*-
import os, sys
import System.Windows
from System.Windows.Controls import Canvas as WPFCanvas
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Shapes import Ellipse, Rectangle
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.loader      import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('createpilecap_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class _Item(object):
    def __init__(self, eid, name):
        self.Id   = eid
        self.Name = name


class CreatePilecapWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'create_pilecap')
        self.doc = doc

        # Populate ComboBoxes
        piles = _logic.get_pile_types(doc)
        self.CboPileType.ItemsSource = [_Item(eid, n) for eid, n in piles]
        if piles:
            self.CboPileType.SelectedIndex = 0

        caps = _logic.get_cap_types(doc)
        self.CboCapType.ItemsSource = [_Item(eid, n) for eid, n in caps]
        if caps:
            self.CboCapType.SelectedIndex = 0

        levels = _logic.get_all_levels(doc)
        self.CboLevel.ItemsSource = [_Item(eid, n) for eid, n in levels]
        if levels:
            self.CboLevel.SelectedIndex = 0

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._update_canvas()

    # ── parameter change ──────────────────────────────────────────────────────

    def Params_Changed(self, sender, args):
        self._update_canvas()

    def _update_canvas(self):
        try:
            n_h = max(1, int(self.TxtNH.Text or '2'))
            n_v = max(1, int(self.TxtNV.Text or '2'))
            spc = max(100.0, float(self.TxtSpacing.Text   or '900'))
            clr = max(0.0,   float(self.TxtClearance.Text or '150'))

            cap_w, cap_h = _logic.calc_dimensions(n_h, n_v, spc, clr)

            self.TxtInfoPiles.Text = "Piles: {}  ({} × {})".format(n_h * n_v, n_h, n_v)
            self.TxtInfoCap.Text   = "Cap: {:.0f} × {:.0f} mm".format(cap_w, cap_h)
            self.TxtDims.Text      = "{}×{} piles — {:.0f}×{:.0f} mm".format(
                                        n_h, n_v, cap_w, cap_h)
            self._draw_canvas(n_h, n_v, spc, clr, cap_w, cap_h)
        except Exception:
            pass

    def _draw_canvas(self, n_h, n_v, spacing_mm, clearance_mm, cap_w_mm, cap_h_mm):
        self.PileCanvas.Children.Clear()

        canvas_w = 400.0
        canvas_h = 260.0
        margin   = 20.0

        if cap_w_mm <= 0 or cap_h_mm <= 0:
            return

        scale   = min((canvas_w - 2 * margin) / cap_w_mm,
                      (canvas_h - 2 * margin) / cap_h_mm)
        cap_px_w = cap_w_mm * scale
        cap_px_h = cap_h_mm * scale
        ox = (canvas_w - cap_px_w) / 2.0
        oy = (canvas_h - cap_px_h) / 2.0

        # Cap background
        rect = Rectangle()
        rect.Width  = cap_px_w
        rect.Height = cap_px_h
        rect.Fill            = SolidColorBrush(Color.FromRgb(220, 220, 220))
        rect.Stroke          = SolidColorBrush(Color.FromRgb(160, 160, 160))
        rect.StrokeThickness = 1.0
        WPFCanvas.SetLeft(rect, ox)
        WPFCanvas.SetTop(rect,  oy)
        self.PileCanvas.Children.Add(rect)

        # Piles
        pile_dia = max(8.0, min(28.0, spacing_mm * scale * 0.35))
        for row_idx in range(n_v):
            for col_idx in range(n_h):
                px = ox + clearance_mm * scale + col_idx * spacing_mm * scale
                py = oy + clearance_mm * scale + row_idx * spacing_mm * scale
                e = Ellipse()
                e.Width  = pile_dia
                e.Height = pile_dia
                e.Fill = SolidColorBrush(Color.FromRgb(255, 95, 0))
                WPFCanvas.SetLeft(e, px - pile_dia / 2.0)
                WPFCanvas.SetTop(e,  py - pile_dia / 2.0)
                self.PileCanvas.Children.Add(e)

    # ── build config ──────────────────────────────────────────────────────────

    def _build_config(self):
        try:
            n_h = max(1, int(self.TxtNH.Text or '2'))
            n_v = max(1, int(self.TxtNV.Text or '2'))
            spc = max(100.0, float(self.TxtSpacing.Text   or '900'))
            clr = max(0.0,   float(self.TxtClearance.Text or '150'))
            cut = max(0.0,   float(self.TxtCutoff.Text    or '75'))
        except ValueError:
            forms.alert("Arrangement values must be numbers.")
            return None

        pile_item = self.CboPileType.SelectedItem
        cap_item  = self.CboCapType.SelectedItem
        lvl_item  = self.CboLevel.SelectedItem

        if pile_item is None:
            forms.alert("Select a pile type.")
            return None
        if cap_item is None:
            forms.alert("Select a cap slab type.")
            return None
        if lvl_item is None:
            forms.alert("Select a level.")
            return None

        return {
            'n_h':          n_h,
            'n_v':          n_v,
            'spacing_mm':   spc,
            'clearance_mm': clr,
            'cutoff_mm':    cut,
            'cap_type_id':  cap_item.Id,
            'pile_type_id': pile_item.Id,
            'level_id':     lvl_item.Id,
        }

    # ── place ─────────────────────────────────────────────────────────────────

    def Place_Click(self, sender, args):
        config = self._build_config()
        if config is None:
            return

        # Hide window, pick point, re-show
        self.Hide()
        pt = None
        try:
            pt = revit.uidoc.Selection.PickPoint(
                "Click to place pile cap centre")
        except Exception:
            pass  # Escape pressed
        self.Show()

        if pt is None:
            return

        self.SetLoading(True, "Creating pile cap...")
        try:
            created, errors = _logic.create_pilecap(self.doc, config, pt)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Creation failed: {}".format(e))
            return
        self.SetLoading(False)

        msg = "Created {} elements.".format(created)
        if errors:
            msg += "\n\nWarnings:\n" + '\n'.join(errors[:5])
        forms.alert(msg, title="Pile Cap Created")
