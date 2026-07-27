# -*- coding: utf-8 -*-
import imp
import os
import sys

import System.Windows
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Windows.Media import SolidColorBrush, Color
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('waffleslab_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
_preview = imp.load_source('waffleslab_ui_preview', os.path.join(os.path.dirname(__file__), 'ui_preview.py'))


class WaffleSlabWindow(NOSAWindow):

    def __init__(self, doc, uidoc, output):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'waffleslab')
        self.doc = doc
        self.uidoc = uidoc
        self.output = output

        cfg = _logic.load_config(output)
        self.TxtIntereje.Text = str(cfg.get('default_intereje', 800))
        self.TxtAncho.Text    = str(cfg.get('default_ancho_nervio', 120))
        self.TxtCanto.Text    = str(cfg.get('default_canto', 300))
        self.TxtLosa.Text     = str(cfg.get('default_losa', 50))

        saved = self.LoadConfig()
        self.ApplyTheme(saved.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = saved.get('dark_mode', False)

        self.LogLine(u'Waffle Slab ready — enter parameters and click Create.')

        self.TxtIntereje.TextChanged += lambda s, a: self._refresh_inline_preview()
        self.TxtAncho.TextChanged    += lambda s, a: self._refresh_inline_preview()
        self.TxtCanto.TextChanged    += lambda s, a: self._refresh_inline_preview()
        self.TxtLosa.TextChanged     += lambda s, a: self._refresh_inline_preview()
        self.InlinePreviewCanvas.SizeChanged += lambda s, a: self._refresh_inline_preview()

    def _refresh_inline_preview(self):
        canvas = self.InlinePreviewCanvas
        canvas.Children.Clear()
        try:
            intereje = max(100, int(self.TxtIntereje.Text.strip() or '800')) / 1000.0
            ancho    = max(10,  int(self.TxtAncho.Text.strip()    or '120')) / 1000.0
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
        while x <= W + intereje * 0.5:
            rib = SWS.Rectangle()
            rib.Width  = max(1.0, ancho * scale)
            rib.Height = H * scale
            rib.Fill   = SolidColorBrush(Color.FromArgb(90, 100, 149, 237))
            SWC.Canvas.SetLeft(rib, sx(x - ancho / 2.0)); SWC.Canvas.SetTop(rib, sy(H))
            canvas.Children.Add(rib)
            x += intereje

        y = 0.0
        while y <= H + intereje * 0.5:
            rib = SWS.Rectangle()
            rib.Width  = W * scale
            rib.Height = max(1.0, ancho * scale)
            rib.Fill   = SolidColorBrush(Color.FromArgb(90, 100, 149, 237))
            SWC.Canvas.SetLeft(rib, sx(0)); SWC.Canvas.SetTop(rib, sy(y + ancho / 2.0))
            canvas.Children.Add(rib)
            y += intereje

        caseton = max(0.0, intereje - ancho)
        xv = intereje / 2.0
        while xv < W:
            yv = intereje / 2.0
            while yv < H:
                void = SWS.Rectangle()
                void.Width  = max(1.0, caseton * scale)
                void.Height = max(1.0, caseton * scale)
                void.Fill   = SolidColorBrush(Color.FromArgb(55, 200, 200, 200))
                void.Stroke = SWM.Brushes.LightGray
                void.StrokeThickness = 0.5
                SWC.Canvas.SetLeft(void, sx(xv - caseton / 2.0))
                SWC.Canvas.SetTop(void,  sy(yv + caseton / 2.0))
                canvas.Children.Add(void)
                yv += intereje
            xv += intereje

        n_x = max(0, int(W / intereje))
        n_y = max(0, int(H / intereje))
        void_pct = ((caseton / intereje) ** 2 * 100) if intereje > 0 else 0
        try:
            self.TxtPreviewDims.Text = (
                u'Example 5×5 m slab — '
                u'spacing {:.0f} mm · rib {:.0f} mm · '
                u'{:.0f}% voids ({}×{} bays)'.format(
                    intereje * 1000, ancho * 1000, void_pct, n_x, n_y))
        except Exception:
            pass

    def _read_params(self):
        try:
            return {
                'intereje': int(self.TxtIntereje.Text.strip()),
                'ancho_nervio': int(self.TxtAncho.Text.strip()),
                'canto': int(self.TxtCanto.Text.strip()),
                'losa': int(self.TxtLosa.Text.strip()),
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

        valid, message, warnings = _logic.validar_parametros_multinormativa(
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
                boundary = _logic.crear_boundary_rectangular(self.uidoc)
            else:
                boundary = _logic.seleccionar_boundary_curves(self.doc, self.uidoc)
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
            creator = _logic.ForjadoReticularReal(self.doc, params, self.output)
            success = creator.generar_forjado(boundary)
        finally:
            self.SetLoading(False)

        if success:
            self.LogLine(u'Main floor: {}'.format('Yes' if creator.forjado_principal else 'No'))
            self.LogLine(u'Compression slab: {}'.format('Yes' if creator.losa_compresion else 'No'))
            self.LogLine(u'Voids created: {}'.format(creator.openings_creados))
            if creator.openings_fallidos:
                self.LogLine(u'Voids failed: {}'.format(creator.openings_fallidos))
            self.LogLine(u'Solid zones (columns): {}'.format(len(creator.columnas)))
            forms.alert(
                u'Waffle slab created.\n\n'
                u'Main floor: {}\n'
                u'Compression slab: {}\n'
                u'Voids: {}\n'
                u'Failed voids: {}'.format(
                    'Yes' if creator.forjado_principal else 'No',
                    'Yes' if creator.losa_compresion else 'No',
                    creator.openings_creados,
                    creator.openings_fallidos,
                ),
                title=u'Success',
            )
        else:
            forms.alert(u'Failed to create waffle slab. See log for details.')


def run(doc, uidoc, output):
    win = WaffleSlabWindow(doc, uidoc, output)
    win.ShowDialog()
