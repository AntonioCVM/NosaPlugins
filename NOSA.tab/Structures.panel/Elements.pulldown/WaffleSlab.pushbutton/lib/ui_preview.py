# -*- coding: utf-8 -*-
import imp
"""
WaffleSlab 2D Preview Window.

Shows an interactive canvas with a live preview of the rib/void grid
and quantification (m² concrete, m² formwork) before the user confirms.
"""
import os, sys, math
import System.Windows
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Windows import Thickness, Window
from System.Windows.Media import SolidColorBrush, Color

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_ACCENT  = SolidColorBrush(Color.FromRgb(255, 95, 0))
_GREY    = SolidColorBrush(Color.FromArgb(40, 0, 0, 0))
_BLUE    = SolidColorBrush(Color.FromArgb(120, 33, 150, 243))
_SOLID   = SolidColorBrush(Color.FromArgb(80, 255, 152, 0))


class WafflePreviewWindow(NOSAWindow):
    """
    Shown before creating the slab.
    Params dict keys: intereje, ancho_nervio, canto, losa, area_m2, n_cols, n_rows
    User can confirm or cancel.
    """

    def __init__(self, params, boundary_bbox, column_locations=None):
        """
        params          : dict with intereje, ancho_nervio, canto, losa (all mm)
        boundary_bbox   : (min_x_m, min_y_m, max_x_m, max_y_m) in metres
        column_locations: list of (cx_m, cy_m) in metres
        """
        xaml = os.path.join(os.path.dirname(__file__), 'ui_preview.xaml')
        NOSAWindow.__init__(self, xaml, 'waffle_preview')
        self.params     = params
        self.bbox       = boundary_bbox
        self.col_locs   = column_locations or []
        self.confirmed  = False
        self._draw_preview()
        self._update_quant()

    def _draw_preview(self):
        """Draw the waffle pattern on the canvas."""
        canvas = self.PreviewCanvas
        canvas.Children.Clear()

        bx0, by0, bx1, by1 = self.bbox
        W = bx1 - bx0 or 1
        H = by1 - by0 or 1

        cw = max(canvas.ActualWidth, 540.0)
        ch = max(canvas.ActualHeight, 320.0)

        scale  = min(cw * 0.9 / W, ch * 0.9 / H)
        off_x  = (cw - W * scale) / 2.0
        off_y  = (ch - H * scale) / 2.0

        def sx(x_m): return (x_m - bx0) * scale + off_x
        def sy(y_m): return ch - ((y_m - by0) * scale + off_y)

        # Boundary
        bnd = SWS.Rectangle()
        bnd.Width  = W * scale
        bnd.Height = H * scale
        bnd.Stroke = _ACCENT
        bnd.StrokeThickness = 2
        bnd.Fill   = SolidColorBrush(Color.FromArgb(20, 255, 95, 0))
        SWC.Canvas.SetLeft(bnd, sx(bx0))
        SWC.Canvas.SetTop(bnd, sy(by1))
        canvas.Children.Add(bnd)

        grid_spacing = self.params.get('intereje', 800) / 1000.0   # m
        width    = self.params.get('ancho_nervio', 120) / 1000.0

        # Vertical ribs
        x = bx0
        while x <= bx1:
            rib = SWS.Rectangle()
            rib.Width  = max(1.0, width * scale)
            rib.Height = max(1.0, H * scale)
            rib.Fill   = SolidColorBrush(Color.FromArgb(90, 100, 149, 237))
            rib.Stroke = SWM.Brushes.Transparent
            SWC.Canvas.SetLeft(rib, sx(x - width / 2.0))
            SWC.Canvas.SetTop(rib, sy(by1))
            canvas.Children.Add(rib)
            x += grid_spacing

        # Horizontal ribs
        y = by0
        while y <= by1:
            rib = SWS.Rectangle()
            rib.Width  = max(1.0, W * scale)
            rib.Height = max(1.0, width * scale)
            rib.Fill   = SolidColorBrush(Color.FromArgb(90, 100, 149, 237))
            rib.Stroke = SWM.Brushes.Transparent
            SWC.Canvas.SetLeft(rib, sx(bx0))
            SWC.Canvas.SetTop(rib, sy(y + width / 2.0))
            canvas.Children.Add(rib)
            y += grid_spacing

        # Voids (casetones)
        void_former = grid_spacing - width
        xv = bx0 + grid_spacing / 2.0
        while xv < bx1:
            yv = by0 + grid_spacing / 2.0
            while yv < by1:
                void = SWS.Rectangle()
                void.Width  = max(1.0, void_former * scale)
                void.Height = max(1.0, void_former * scale)
                void.Fill   = SolidColorBrush(Color.FromArgb(60, 200, 200, 200))
                void.Stroke = SWM.Brushes.LightGray
                void.StrokeThickness = 0.5
                SWC.Canvas.SetLeft(void, sx(xv - void_former / 2.0))
                SWC.Canvas.SetTop(void, sy(yv + void_former / 2.0))
                canvas.Children.Add(void)
                yv += grid_spacing
            xv += grid_spacing

        # Column solid zones
        solid_r = max(grid_spacing * 1.5, width * 3) / 2.0
        for (cx, cy) in self.col_locs:
            dot = SWS.Ellipse()
            dot.Width  = max(4.0, solid_r * scale * 2)
            dot.Height = max(4.0, solid_r * scale * 2)
            dot.Fill   = SolidColorBrush(Color.FromArgb(60, 255, 152, 0))
            dot.Stroke = SolidColorBrush(Color.FromRgb(255, 152, 0))
            dot.StrokeThickness = 1
            SWC.Canvas.SetLeft(dot, sx(cx) - dot.Width / 2.0)
            SWC.Canvas.SetTop(dot, sy(cy) - dot.Height / 2.0)
            canvas.Children.Add(dot)

        # Legend
        leg_items = [
            (SolidColorBrush(Color.FromArgb(90, 100, 149, 237)), 'Ribs'),
            (SolidColorBrush(Color.FromArgb(60, 200, 200, 200)), 'Voids (casetones)'),
            (SolidColorBrush(Color.FromArgb(60, 255, 152, 0)),   'Solid zone around columns'),
        ]
        for i, (brush, text) in enumerate(leg_items):
            box = SWS.Rectangle()
            box.Width  = 12; box.Height = 12
            box.Fill   = brush
            box.Stroke = SWM.Brushes.Gray
            box.StrokeThickness = 0.5
            SWC.Canvas.SetLeft(box, 10)
            SWC.Canvas.SetTop(box, 10 + i * 20)
            canvas.Children.Add(box)
            lbl = SWC.TextBlock()
            lbl.Text     = text
            lbl.FontSize = 10
            lbl.Opacity  = 0.7
            SWC.Canvas.SetLeft(lbl, 26)
            SWC.Canvas.SetTop(lbl, 10 + i * 20 - 1)
            canvas.Children.Add(lbl)

    def _update_quant(self):
        """Calculate and display m² concrete and formwork."""
        try:
            bx0, by0, bx1, by1 = self.bbox
            W = bx1 - bx0
            H = by1 - by0
            total_area = W * H

            grid_spacing = self.params.get('intereje', 800) / 1000.0
            width    = self.params.get('ancho_nervio', 120) / 1000.0
            depth    = self.params.get('canto', 300) / 1000.0
            slab     = self.params.get('losa', 50) / 1000.0

            # Void fraction
            void_former = grid_spacing - width
            void_frac = (void_former / grid_spacing) ** 2

            # Concrete = (total - voids) × depth + compression_slab × total
            concrete_m3 = total_area * (1 - void_frac) * depth + total_area * slab
            # Formwork = bottom face of voids + side faces of ribs
            n_voids_x = max(1, int(W / grid_spacing))
            n_voids_y = max(1, int(H / grid_spacing))
            formwork_m2 = (n_voids_x * n_voids_y * void_former * void_former +  # void bottoms
                           total_area * (1 - void_frac))                  # rib sides approx

            self.TxtQuant.Text = (
                u'Area: {:.1f} m²  |  '
                u'Concrete: {:.2f} m³  |  '
                u'Formwork: {:.1f} m²'.format(total_area, concrete_m3, formwork_m2))
        except Exception as e:
            self.TxtQuant.Text = u'Quantification error: {}'.format(e)

    def Confirm_Click(self, sender, args):
        self.confirmed = True
        self.DialogResult = True

    def Cancel_Click(self, sender, args):
        self.confirmed = False
        self.DialogResult = False
