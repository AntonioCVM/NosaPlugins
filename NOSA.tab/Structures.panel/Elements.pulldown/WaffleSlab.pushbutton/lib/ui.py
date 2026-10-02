# -*- coding: utf-8 -*-
import os
import sys

import System.Windows
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Windows.Media import SolidColorBrush, Color
from pyrevit import forms, revit
from nosa_utils.telemetry import log_swallowed
_LOG = u'waffleslab'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

from nosa_utils.bootstrap import load_module
_logic = load_module('waffleslab_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
_preview = load_module('waffleslab_ui_preview', os.path.join(os.path.dirname(__file__), 'ui_preview.py'))


class WaffleSlabWindow(NOSAWindow):

    def __init__(self, doc, uidoc, output):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'waffleslab')
        self.doc = doc
        self.uidoc = uidoc
        self.output = output

        cfg = _logic.load_config(output)
        self.TxtGridSpacing.Text = str(cfg.get('default_intereje', 800))
        self.TxtRibWidth.Text    = str(cfg.get('default_ancho_nervio', 120))
        self.TxtTotalDepth.Text    = str(cfg.get('default_canto', 300))
        self.TxtToppingThickness.Text     = str(cfg.get('default_losa', 50))

        saved = self.LoadConfig()
        self.ApplyTheme(saved.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = saved.get('dark_mode', False)

        self.LogLine(u'Waffle Slab ready — enter parameters and click Create.')

        self.TxtGridSpacing.TextChanged += lambda s, a: self._refresh_inline_preview()
        self.TxtRibWidth.TextChanged    += lambda s, a: self._refresh_inline_preview()
        self.TxtTotalDepth.TextChanged    += lambda s, a: self._refresh_inline_preview()
        self.TxtToppingThickness.TextChanged     += lambda s, a: self._refresh_inline_preview()
        self.InlinePreviewCanvas.SizeChanged += lambda s, a: self._refresh_inline_preview()

    def _refresh_inline_preview(self):
        canvas = self.InlinePreviewCanvas
        canvas.Children.Clear()
        try:
            grid_spacing = max(100, int(self.TxtGridSpacing.Text.strip() or '800')) / 1000.0
            width    = max(10,  int(self.TxtRibWidth.Text.strip()    or '120')) / 1000.0
        except (ValueError, Exception):
            return

        W  = 5.0; H = 5.0
        cw = max(200.0, canvas.ActualWidth  or 380.0)
        ch = max(100.0, canvas.ActualHeight or 200.0)

        scale = min(cw * 0.88 / W, ch * 0.88 / H)
        ox = (cw - W * scale) / 2.0
        oy = (ch - H * scale) / 2.0

        def sx(x): return x * scale + ox
        def sy(y): return ch - (y * scale + oy)

        bnd = SWS.Rectangle()
        bnd.Width  = W * scale
        bnd.Height = H * scale
        bnd.Stroke = SolidColorBrush(Color.FromRgb(255, 95, 0))
        bnd.StrokeThickness = 1.5
        bnd.Fill   = SolidColorBrush(Color.FromArgb(12, 255, 95, 0))
        SWC.Canvas.SetLeft(bnd, sx(0)); SWC.Canvas.SetTop(bnd, sy(H))
        canvas.Children.Add(bnd)

        x = 0.0
        while x <= W + grid_spacing * 0.5:
            rib = SWS.Rectangle()
            rib.Width  = max(1.0, width * scale)
            rib.Height = H * scale
            rib.Fill   = SolidColorBrush(Color.FromArgb(90, 100, 149, 237))
            SWC.Canvas.SetLeft(rib, sx(x - width / 2.0)); SWC.Canvas.SetTop(rib, sy(H))
            canvas.Children.Add(rib)
            x += grid_spacing

        y = 0.0
        while y <= H + grid_spacing * 0.5:
            rib = SWS.Rectangle()
            rib.Width  = W * scale
            rib.Height = max(1.0, width * scale)
            rib.Fill   = SolidColorBrush(Color.FromArgb(90, 100, 149, 237))
            SWC.Canvas.SetLeft(rib, sx(0)); SWC.Canvas.SetTop(rib, sy(y + width / 2.0))
            canvas.Children.Add(rib)
            y += grid_spacing

        void_former = max(0.0, grid_spacing - width)
        xv = grid_spacing / 2.0
        while xv < W:
            yv = grid_spacing / 2.0
            while yv < H:
                void = SWS.Rectangle()
                void.Width  = max(1.0, void_former * scale)
                void.Height = max(1.0, void_former * scale)
                void.Fill   = SolidColorBrush(Color.FromArgb(55, 200, 200, 200))
                void.Stroke = SWM.Brushes.LightGray
                void.StrokeThickness = 0.5
                SWC.Canvas.SetLeft(void, sx(xv - void_former / 2.0))
                SWC.Canvas.SetTop(void,  sy(yv + void_former / 2.0))
                canvas.Children.Add(void)
                yv += grid_spacing
            xv += grid_spacing

        n_x = max(0, int(W / grid_spacing))
        n_y = max(0, int(H / grid_spacing))
        void_pct = ((void_former / grid_spacing) ** 2 * 100) if grid_spacing > 0 else 0
        try:
            self.TxtPreviewDims.Text = (
                u'Example 5×5 m slab — '
                u'spacing {:.0f} mm · rib {:.0f} mm · '
                u'{:.0f}% voids ({}×{} bays)'.format(
                    grid_spacing * 1000, width * 1000, void_pct, n_x, n_y))
        except Exception:
            log_swallowed(_LOG, u'WaffleSlabWindow._refresh_inline_preview')

    def _read_params(self):
        try:
            return {
                'intereje': int(self.TxtGridSpacing.Text.strip()),
                'ancho_nervio': int(self.TxtRibWidth.Text.strip()),
                'canto': int(self.TxtTotalDepth.Text.strip()),
                'losa': int(self.TxtToppingThickness.Text.strip()),
                'radio_macizado_factor': 1.5,
            }
        except ValueError:
            forms.alert(u'Enter whole numbers for all dimensions (mm).')
            return None

    def Create_Click(self, sender, args):
        params = self._read_params()
        if not params:
            return

        _logic.save_config({
            'default_intereje': params['intereje'],
            'default_ancho_nervio': params['ancho_nervio'],
            'default_canto': params['canto'],
            'default_losa': params['losa'],
            'radio_macizado_factor': params.get('radio_macizado_factor', 1.5),
        }, self.output)

        valid, message, warnings = _logic.validate_parameters(
            params['intereje'], params['ancho_nervio'], params['canto'], params['losa'])
        if not valid:
            forms.alert(u'Invalid parameters:\n\n{}'.format(message))
            return

        self.LogLine(u'Validation: {}'.format(message))
        for w in warnings:
            self.LogLine(u'Warning: {}'.format(w))

        self.Hide()
        try:
            if self.RbRect.IsChecked:
                boundary = _logic.create_rectangular_boundary(self.uidoc)
            else:
                boundary = _logic.select_boundary_curves(self.doc, self.uidoc)
        finally:
            self.Show()

        if not boundary:
            return

        self.LogLine(u'Area defined with {} curves'.format(len(boundary)))

        try:
            if not _logic.show_preview(self.doc, params, boundary, _preview.WafflePreviewWindow):
                self.LogLine(u'Creation cancelled at preview.')
                return
        except Exception as ex:
            self.LogLine(u'Preview unavailable: {}'.format(ex))

        self.SetLoading(True, u'Creating waffle slab…')
        try:
            creator = _logic.WaffleSlabBuilder(self.doc, params, self.output)
            success = creator.generate_waffle_slab(boundary)
        finally:
            self.SetLoading(False)

        if success:
            self.LogLine(u'Main floor: {}'.format('Yes' if creator.main_slab else 'No'))
            self.LogLine(u'Compression slab: {}'.format('Yes' if creator.topping_slab else 'No'))
            self.LogLine(u'Voids created: {}'.format(creator.openings_created))
            if creator.openings_failed:
                self.LogLine(u'Voids failed: {}'.format(creator.openings_failed))
            self.LogLine(u'Solid zones (columns): {}'.format(len(creator.columns)))
            forms.alert(
                u'Waffle slab created.\n\n'
                u'Main floor: {}\n'
                u'Compression slab: {}\n'
                u'Voids: {}\n'
                u'Failed voids: {}'.format(
                    'Yes' if creator.main_slab else 'No',
                    'Yes' if creator.topping_slab else 'No',
                    creator.openings_created,
                    creator.openings_failed,
                ),
                title=u'Success',
            )
        else:
            forms.alert(u'Failed to create waffle slab. See log for details.')


def run(doc, uidoc, output):
    win = WaffleSlabWindow(doc, uidoc, output)
    win.ShowDialog()
