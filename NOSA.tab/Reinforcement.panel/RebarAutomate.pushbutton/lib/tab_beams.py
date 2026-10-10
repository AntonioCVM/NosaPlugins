# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Beams tab: single spans and continuous beam lines (T7.2).
Methods of RebarAutomateWindow (T8.5 split of ui.py): ui.py loads the shared modules once and
hands them over with bind(), so these methods keep using the same names as before.
"""
try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat


def bind(namespace):
    """Share ui.py's module-level names (modules, helpers, constants) with this module."""
    own = _OWN
    for key, value in namespace.items():
        if not key.startswith('__') and key not in own:
            globals()[key] = value


class BeamsMixin(object):
    # ── Beams (Phase F7) ─────────────────────────────────────────────────

    def _read_beam_inputs(self):
        errors = []
        values = {}
        values['bar_dia'] = self._read_number(self.TxtBeamBarDia.Text, u'Bar diameter', errors)
        try:
            values['n_top'] = int(float(self.TxtBeamTopCount.Text))
            if values['n_top'] < 0:
                errors.append(u'"Top bars" must be zero or positive.')
        except (TypeError, ValueError):
            errors.append(u'"Top bars" must be a number.')
            values['n_top'] = None
        try:
            values['n_bottom'] = int(float(self.TxtBeamBottomCount.Text))
            if values['n_bottom'] < 0:
                errors.append(u'"Bottom bars" must be zero or positive.')
        except (TypeError, ValueError):
            errors.append(u'"Bottom bars" must be a number.')
            values['n_bottom'] = None
        values['stirrup_dia'] = self._read_number(
            self.TxtBeamStirrupDia.Text, u'Stirrup diameter', errors)
        values['stirrup_spacing'] = self._read_number(
            self.TxtBeamStirrupSpacing.Text, u'Stirrup spacing', errors)
        values['end_offset'] = self._read_number(
            self.TxtBeamEndOffset.Text, u'End offset', errors)
        values['stock_length'] = self._read_number(
            self.TxtBeamStockLength.Text, u'Max stock length', errors)
        if values.get('stock_length') is not None and values['stock_length'] < 1000.0:
            errors.append(u'"Max stock length" must be at least 1000 mm.')
        values['interior_ties'] = self.ChkBeamInteriorTies.IsChecked == True
        values['densify_ends'] = self.ChkBeamDensify.IsChecked == True
        if values['densify_ends']:
            values['dense_spacing'] = self._read_number(
                self.TxtBeamDenseSpacing.Text, u'Dense spacing', errors)
            # 0 = auto (2 × beam height); allow zero without failing validation
            try:
                conf = float(self.TxtBeamConfineLength.Text)
            except (TypeError, ValueError):
                errors.append(u'"Confine length" must be a number (0 = auto).')
                conf = None
            if conf is not None and conf < 0:
                errors.append(u'"Confine length" cannot be negative.')
                conf = None
            values['confine_length'] = conf if (conf and conf > 0) else None
        if values.get('n_top') == 0 and values.get('n_bottom') == 0:
            errors.append(u'At least one top or bottom bar is required.')
        values['continuous'] = self.ChkBeamContinuous.IsChecked == True
        values['flexible'] = self.ChkBeamFlexible.IsChecked == True
        if values['continuous'] and values.get('n_top', 0) < 2:
            errors.append(u'A continuous beam needs at least 2 top (hanger) bars.')
        # additional bars (2026-10-05): hogging over the supports, sagging in the spans
        values['n_support'] = values['n_span'] = 0
        if self.ChkBeamSupportBars.IsChecked == True:
            values['support_dia'] = self._read_number(
                self.TxtBeamSupportDia.Text, u'Support bar diameter', errors)
            try:
                values['n_support'] = int(float(self.TxtBeamSupportCount.Text))
            except (TypeError, ValueError):
                errors.append(u'"Support bars" must be a number.')
            if values.get('n_top', 0) < 2 and values['n_support']:
                errors.append(u'Support bars sit between the top bars: at least 2 top bars are needed.')
        if self.ChkBeamSpanBars.IsChecked == True:
            values['span_dia'] = self._read_number(self.TxtBeamSpanDia.Text, u'Span bar diameter', errors)
            try:
                values['n_span'] = int(float(self.TxtBeamSpanCount.Text))
            except (TypeError, ValueError):
                errors.append(u'"Span bars" must be a number.')
            if values.get('n_bottom', 0) < 2 and values['n_span']:
                errors.append(u'Span bars sit between the bottom bars: at least 2 bottom bars are needed.')
        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def BeamDensify_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelBeamDensify.IsEnabled = self.ChkBeamDensify.IsChecked == True
        self._update_beam_preview()

    def BeamPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_beam_preview()

    def _update_beam_preview(self):
        try:
            canvas = self.BeamPreviewCanvas
        except Exception:
            return
        try:
            bar_dia = float(self.TxtBeamBarDia.Text)
            n_top = int(float(self.TxtBeamTopCount.Text))
            n_bottom = int(float(self.TxtBeamBottomCount.Text))
            st_dia = float(self.TxtBeamStirrupDia.Text)
        except (TypeError, ValueError):
            return
        beams = self._selected_beams()
        beam_host = beams[0] if beams else None
        cover = self._preview_cover_mm(beam_host, u'Other', u'beam') if beam_host else \
            self._standard_default_cover_mm(u'beam')
        width_mm, height_mm = 300.0, 500.0
        if beam_host is not None:
            try:
                width_mm, height_mm = beam_rebar.get_beam_section_mm(
                    self.doc, beam_host, cover, bar_dia)
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_beam_preview')
        try:
            data = rebar_preview.compute_beam_section_preview(
                width_mm, height_mm, cover, bar_dia, n_top, n_bottom, st_dia)
        except Exception:
            return
        ties = []
        if self.ChkBeamInteriorTies.IsChecked == True:
            ties = preview_shapes.beam_interior_ties(
                width_mm, height_mm, cover, bar_dia, n_top, n_bottom, st_dia)
        self._draw_shapes(canvas, preview_shapes.beam_section_shapes(
            width_mm, height_mm, cover, bar_dia, n_top, n_bottom, st_dia,
            link_spacing=self._preview_number(self.TxtBeamStirrupSpacing, None), ties=ties))
        self._update_beam_elevation_preview()

    def _update_beam_elevation_preview(self):
        """
        PHASE 2.6 (2026-09-02, explicit live request — "sería
        interesante ver un alzado de la viga") — companion elevation
        (side view) beside the existing section preview, mirroring the
        Columns tab's own Section+Elevation pair. Silently skipped
        (never raises to the caller) if the elevation canvas doesn't
        exist yet in ui.xaml, or if any input is invalid/mid-typing —
        same defensive convention as every other _update_*_preview.
        """
        try:
            canvas = self.BeamElevationCanvas
        except Exception:
            return
        try:
            bar_dia = float(self.TxtBeamBarDia.Text)
            st_dia = float(self.TxtBeamStirrupDia.Text)
            st_spacing = float(self.TxtBeamStirrupSpacing.Text)
            end_offset = float(self.TxtBeamEndOffset.Text)
        except (TypeError, ValueError):
            return

        densify = self.ChkBeamDensify.IsChecked == True
        dense_spacing = confine_length = None
        if densify:
            try:
                dense_spacing = float(self.TxtBeamDenseSpacing.Text)
                confine_txt = float(self.TxtBeamConfineLength.Text)
                confine_length = confine_txt if confine_txt > 0 else None
            except (TypeError, ValueError):
                return
            if dense_spacing <= 0:
                return

        beams = self._selected_beams()
        beam_host = beams[0] if beams else None
        cover = self._preview_cover_mm(beam_host, u'Other', u'beam') if beam_host else \
            self._standard_default_cover_mm(u'beam')
        length_mm, height_mm = 6000.0, 500.0
        if beam_host is not None:
            try:
                _, height_mm = beam_rebar.get_beam_section_mm(self.doc, beam_host, cover, bar_dia)
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_beam_elevation_preview')
            try:
                length_mm = beam_rebar.get_beam_axis(beam_host).Length * 304.8
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_beam_elevation_preview')

        try:
            data = rebar_preview.compute_beam_elevation_preview(
                length_mm, height_mm, cover, bar_dia, bar_dia, st_dia, st_spacing,
                end_offset_mm=end_offset, densify_ends=densify,
                dense_spacing_mm=dense_spacing, confine_length_mm=confine_length)
        except Exception:
            return
        self._draw_beam_elevation_preview(canvas, data)

    def _draw_beam_elevation_preview(self, canvas, data):
        canvas.Children.Clear()
        section = data.get('section') or {}
        w_mm = float(section.get('width_mm') or 6000.0)
        h_mm = float(section.get('height_mm') or 500.0)
        cw = canvas.Width or 700.0
        ch = canvas.Height or 220.0
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        # Centred exactly like _draw_column_elevation_preview — this
        # function's own coordinate system spans x in [0, w_mm], so
        # centring means offsetting by however much blank canvas space
        # the SCALED beam doesn't fill, split evenly on both sides
        # (never a fixed small margin — see _draw_wall_elevation_preview's
        # own BUG FIX note for the "stuck flush-left" failure mode this
        # avoids from the start).
        off_x = (cw - w_mm * scale) / 2.0
        off_y = ch / 2.0

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - (y_mm - h_mm / 2.0) * scale

        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 2.0
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(0.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        for st in data.get('stirrups', []):
            line = SWS.Line()
            line.X1 = line.X2 = sx(st['x_mm'])
            line.Y1 = sy(st['y0_mm'])
            line.Y2 = sy(st['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.0, float(st.get('diameter_mm') or 8.0) * scale * 0.6)
            canvas.Children.Add(line)

        for bar in data.get('bars', []):
            line = SWS.Line()
            line.X1, line.Y1 = sx(bar['x0_mm']), sy(bar['y0_mm'])
            line.X2, line.Y2 = sx(bar['x1_mm']), sy(bar['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.5, float(bar.get('diameter_mm') or 16.0) * scale)
            canvas.Children.Add(line)

    def _update_wall_preview(self):
        cover = self._standard_default_cover_mm(u'wall')
        walls = self._selected_walls()
        wall_host = walls[0] if walls else None
        thickness_mm = 250.0
        length_mm, height_mm = 6000.0, 3000.0
        if wall_host is not None:
            try:
                cover = re_engine.get_native_cover_mm(
                    self.doc, wall_host, u'Exterior', cover)
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_wall_preview')
            try:
                length_mm, height_mm = wall_rebar.get_wall_elevation_mm(wall_host)
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_wall_preview')
            try:
                thickness_mm = wall_host.Width * 304.8
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_wall_preview')

        try:
            vert_dia = float(self.TxtWallVertDia.Text)
            vert_sp = float(self.TxtWallVertSpacing.Text)
            horiz_dia = float(self.TxtWallHorizDia.Text)
            horiz_sp = float(self.TxtWallHorizSpacing.Text)
        except (TypeError, ValueError):
            return
        both_faces = self.ChkWallBothFaces.IsChecked == True

        try:
            elevation_canvas = self.WallPreviewCanvas
        except Exception:
            elevation_canvas = None
        if elevation_canvas is not None:
            include_starters = self.ChkWallStarters.IsChecked == True
            starter_length = None
            if include_starters:
                starter_length = self._preview_splice(
                    self.TxtWallStarterLength, self._preview_number(self.TxtWallVertDia, 12.0))
            try:
                data = rebar_preview.compute_wall_elevation_preview(
                    length_mm=length_mm, height_mm=height_mm, cover_mm=cover,
                    vert_dia_mm=vert_dia, vert_spacing_mm=vert_sp,
                    horiz_spacing_mm=horiz_sp, horiz_dia_mm=horiz_dia,
                    both_faces=both_faces,
                    include_top_ubars=self.ChkWallEndUBars.IsChecked == True,
                    include_end_ubars=self.ChkWallEndUBars.IsChecked == True,
                    include_starters=include_starters, starter_length_mm=starter_length)
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._update_wall_preview')
            else:
                self._draw_wall_elevation_preview(elevation_canvas, data)

        # PHASE 2.6 (2026-09-02, explicit live request — "sería
        # conveniente que se viese una sección, el nombre... dice
        # Section Preview cuando es un alzado", then "la sección no se
        # ve correctamente, necesitaríamos una sección bien hecha") —
        # genuine cross-section (a VERTICAL cut PERPENDICULAR to the
        # wall's own length, through its thickness), alongside the
        # elevation above. Reuses _draw_simple_section_preview (now
        # extended with a 'bar_lines' renderer for the vertical bars —
        # see that method's own note).
        try:
            section_canvas = self.WallSectionCanvas
        except Exception:
            return
        include_ties = self.ChkWallTies.IsChecked == True
        tie_spacing = None
        if include_ties:
            try:
                tie_spacing = float(self.TxtWallTieSpacing.Text)
                if tie_spacing <= 0:
                    include_ties = False
            except (TypeError, ValueError):
                include_ties = False
        # A representative slice, not the wall's real height (same role
        # length_mm/height_mm play in compute_beam_elevation_preview) —
        # tall enough relative to a typical thickness to read clearly as
        # a section rather than a square blob, and to show 2-3 real
        # horizontal-bar row crossings at the user's own spacing.
        section_height_mm = max(900.0, thickness_mm * 3.0)
        try:
            section_data = rebar_preview.compute_wall_section_preview(
                thickness_mm, section_height_mm, cover, vert_dia, horiz_dia, horiz_sp,
                both_faces=both_faces,
                include_ties=include_ties, tie_spacing_mm=tie_spacing,
                include_ubars=self.ChkWallEndUBars.IsChecked == True)
        except Exception:
            return
        straight = self.ChkWallStarters.IsChecked == True
        self._draw_shapes(section_canvas, preview_shapes.wall_section_shapes(
            thickness_mm, min(height_mm, 2400.0), cover, vert_dia, vert_sp, horiz_dia, horiz_sp,
            both_faces=both_faces, vert_outer=self.ChkWallVertOuter.IsChecked == True,
            top_ubar=self.ChkWallEndUBars.IsChecked == True, straight_extension=straight,
            foundation_starters=self.ChkWallFoundationStarters.IsChecked == True,
            starter_dia=vert_dia,
            starter_splice_mm=self._preview_splice(self.TxtWallFoundationSplice, vert_dia),
            kicker_mm=self._kicker_mm()))

    def _draw_simple_section_preview(self, canvas, data, draw_stirrup=False):
        canvas.Children.Clear()
        section = data.get('section') or {}
        w_mm = float(section.get('width_mm') or 300.0)
        h_mm = float(section.get('height_mm') or 500.0)
        cw = canvas.Width or 700.0
        ch = canvas.Height or 220.0
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        off_x = cw / 2.0
        off_y = ch / 2.0

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 2.0
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm / 2.0))
        canvas.Children.Add(outline)

        if draw_stirrup and data.get('stirrup'):
            st = data['stirrup']
            hw, hh = st['half_w_mm'], st['half_h_mm']
            rect = SWS.Rectangle()
            rect.Width = 2.0 * hw * scale
            rect.Height = 2.0 * hh * scale
            rect.Stroke = _PREVIEW_BAR_FILL
            rect.StrokeThickness = 1.5
            rect.Fill = None
            try:
                rect.Fill = SWM.Brushes.Transparent
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._draw_simple_section_preview')
            SWC.Canvas.SetLeft(rect, sx(-hw))
            SWC.Canvas.SetTop(rect, sy(hh))
            canvas.Children.Add(rect)

        for bar in data.get('bars', []):
            d = max(float(bar.get('diameter_mm') or 12.0), 6.0)
            r = (d * scale) / 2.0
            dot = SWS.Ellipse()
            dot.Width = r * 2.0
            dot.Height = r * 2.0
            dot.Fill = _PREVIEW_BAR_FILL
            SWC.Canvas.SetLeft(dot, sx(bar['x_mm']) - r)
            SWC.Canvas.SetTop(dot, sy(bar['y_mm']) - r)
            canvas.Children.Add(dot)

        # PHASE 2.6 (2026-09-02) — generic diameter-scaled bar LINE
        # segments, added for the rewritten wall section preview's
        # vertical bars (one continuous line per face) — a "lines" list
        # already existed for footings' B2/T2 (fixed-y, x0..x1 only);
        # this is the general x0/y0/x1/y1 shape any future caller can
        # reuse for a bar that isn't axis-locked to a single row.
        for bl in data.get('bar_lines', []):
            line = SWS.Line()
            line.X1, line.Y1 = sx(bl['x0_mm']), sy(bl['y0_mm'])
            line.X2, line.Y2 = sx(bl['x1_mm']), sy(bl['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(2.0, float(bl.get('diameter_mm') or 12.0) * scale)
            canvas.Children.Add(line)

        for tie in data.get('ties', []):
            line = SWS.Line()
            line.X1, line.Y1 = sx(tie['x0_mm']), sy(tie['y0_mm'])
            line.X2, line.Y2 = sx(tie['x1_mm']), sy(tie['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.5
            canvas.Children.Add(line)

        for ub in data.get('ubars', []):
            pts = ub.get('points') or []
            for i in range(len(pts) - 1):
                line = SWS.Line()
                line.X1, line.Y1 = sx(pts[i][0]), sy(pts[i][1])
                line.X2, line.Y2 = sx(pts[i + 1][0]), sy(pts[i + 1][1])
                line.Stroke = _PREVIEW_UBAR_WEAVE_STROKE
                line.StrokeThickness = 1.5
                canvas.Children.Add(line)

    def _draw_wall_elevation_preview(self, canvas, data):
        canvas.Children.Clear()
        section = data.get('section') or {}
        w_mm = float(section.get('width_mm') or 6000.0)
        h_mm = float(section.get('height_mm') or 3000.0)
        # BUG FIX (2026-09-02, round 2, live report — "los starter bars
        # no se ven") — same starter_extension_mm pattern _draw_column_
        # elevation_preview already uses: the scale/offset must account
        # for the starter's own extension BELOW y=0, or those bar
        # segments get drawn off the bottom of the canvas / squeezed the
        # scale as if they didn't exist.
        starter_ext = float(data.get('starter_extension_mm') or 0.0)
        total_h_mm = h_mm + starter_ext
        cw = canvas.Width or 700.0
        ch = canvas.Height or 220.0
        margin_x = 24.0
        margin_y = 16.0
        scale = min((cw - 2 * margin_x) / w_mm, (ch - 2 * margin_y) / total_h_mm)
        # BUG FIX (2026-09-02, live report — "la vista de los walls
        # preview no está centrada") — off_x used to be the fixed left
        # MARGIN itself, so the wall was always drawn flush against the
        # left edge with all the leftover canvas width (whenever the
        # wall's own scaled length was shorter than the canvas, e.g. a
        # short wall or a wide window) going unused on the right. Centre
        # the ACTUAL scaled wall width within the canvas instead — same
        # fix shape as _draw_beam_elevation_preview's own centring.
        off_x = (cw - w_mm * scale) / 2.0
        # y=0 (the wall's own base) is shifted UP from the bottom margin
        # by however much room the starter extension needs below it, so
        # the starter's own bottom (y=-starter_ext) still lands exactly
        # at the bottom margin instead of running off the canvas.
        off_y = ch - margin_y - starter_ext * scale

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 2.0
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(0.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        for bar in data.get('bars', []):
            line = SWS.Line()
            line.X1 = sx(bar['x0_mm'])
            line.X2 = sx(bar['x1_mm'])
            line.Y1 = sy(bar['y0_mm'])
            line.Y2 = sy(bar['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.5, float(bar.get('diameter_mm') or 12.0) * scale * 0.5)
            canvas.Children.Add(line)

        for hz in data.get('horizontals', []):
            line = SWS.Line()
            line.X1 = sx(hz['x0_mm'])
            line.X2 = sx(hz['x1_mm'])
            line.Y1 = sy(hz['y0_mm'])
            line.Y2 = sy(hz['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.0, float(hz.get('diameter_mm') or 10.0) * scale * 0.4)
            canvas.Children.Add(line)

        for ub in data.get('ubars', []):
            pts = ub.get('points') or []
            stroke = _PREVIEW_UBAR_WEAVE_STROKE
            for i in range(len(pts) - 1):
                seg = SWS.Line()
                seg.X1, seg.Y1 = sx(pts[i][0]), sy(pts[i][1])
                seg.X2, seg.Y2 = sx(pts[i + 1][0]), sy(pts[i + 1][1])
                seg.Stroke = stroke
                seg.StrokeThickness = 1.5
                canvas.Children.Add(seg)

    def RunBeamReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_beam_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'beams', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_beam_result(self, beams, summary):
        lines = [
            u'{} beam(s) processed.'.format(len(beams)),
            u'{} Rebar element(s) created.'.format(summary.get('created', 0)),
        ]
        if summary.get('errors'):
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — used to silently cap at 12 with no
            # "...and N more" indicator at all — worse than the other
            # tabs' truncation, since there was no sign more existed.
            # TxtBeamResult is now a scrollable, read-only TextBox.
            lines.extend(summary['errors'])
        self.TxtBeamResult.Text = u'\n'.join(lines)

    def _beam_lap_anchorage(self, host, bar_dia):
        """(lap, anchorage) mm for this beam's bars; top bars of beams over 250 mm are in poor bond."""
        bbox = host.get_BoundingBox(None)
        good = ((bbox.Max.Z - bbox.Min.Z) * 304.8 if bbox is not None else 0.0) <= 250.0
        try:
            # confined by the beam links: alpha3 = 0.9 (IStructE SMDSC Table 6.4)
            lap = standards.lap_length_mm(self._host_std(host), bar_dia, False, 100.0, good,
                                          alpha3=standards.CONFINED_ALPHA3)
        except Exception:
            lap = max(40.0 * bar_dia, 300.0)
        try:
            anchorage = standards.anchorage_length_mm(self._host_std(host), bar_dia, good,
                                                      alpha3=standards.CONFINED_ALPHA3)
        except Exception:
            anchorage = 40.0 * bar_dia
        return lap, anchorage

    def _create_spacers(self, wrapper, host_groups, errors, created_rebars):
        """Spacer bars between two layers of main bars at 1 m centres (SMDSC MB1), listed in the BBS."""
        for host, group in host_groups:
            bar_type = re_engine.get_bar_type_by_diameter(self.doc, group['diameter_mm'])
            if bar_type is None:
                errors.append(u'Beam {}: no H{:.0f} bar type for the spacer bars between layers.'.format(
                    get_id_value(host.Id), float(group['diameter_mm'])))
                continue
            self._create_long_group(wrapper, host, group, bar_type, u'Beam Spacer Bar', u'spacer', errors,
                                    created_rebars)

    def _create_long_group(self, wrapper, host, group, bar_type, label, layer, errors, created_rebars):
        """One grouped set of longitudinal bars (one Rebar Set, else bar by bar)."""
        hid = get_id_value(host.Id)
        if group.get('count', 1) > 1 and group.get('array_length_mm', 0) > 0:
            rebar = wrapper.create_rebar_set(
                host, group['curves'], bar_type, group['spacing_mm'], group['array_length_mm'],
                normal=group['normal'], transaction_name=u'NOSA — Create {}'.format(group['label']))
            if rebar is not None:
                self._stamp_layer(rebar, layer)
                created_rebars.append(rebar)
                return
        for chain in group.get('all_curves', [group['curves']]):
            rebar = wrapper.create_from_curves(host, chain, bar_type, normal=group['normal'],
                                               transaction_name=u'NOSA — Create {}'.format(label))
            if rebar is None:
                errors.append(u'Beam {}: {} — {}'.format(hid, label, wrapper.last_error))
            else:
                self._stamp_layer(rebar, layer)
                created_rebars.append(rebar)

    def _process_beam_line(self, line, values, wrapper, bar_types, errors, created_rebars):
        """T7.2 — one line of spans: hanger and support bars, then every span's own bars."""
        first = line[0]
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, first, u'Other', self._standard_default_cover_mm(u'beam'))
        if is_ground_beam(first) and cover_mm < 75.0 - 1e-6:
            errors.append(u'Ground beam {}: cover {:.0f} mm — SMDSC 6.7 asks for 75 mm where it is cast '
                          u'against the ground; set the host cover if so.'.format(get_id_value(first.Id), cover_mm))
        try:
            # T8.47, SMDSC 5.2/5.3: do the top and bottom layers fit inside the links?
            import fit_checks
            width_mm, height_mm = beam_rebar.get_beam_section_mm(self.doc, first, cover_mm, values['bar_dia'])
            label = u'Beam {}'.format(get_id_value(first.Id))
            errors.extend(fit_checks.beam_notes(
                width_mm, cover_mm, values['stirrup_dia'], values['bar_dia'], values['n_top'],
                values.get('n_bottom', values['n_top']), label=label))
            # T8.37, SMDSC 6.3: link pitch, minimum shear ratio, legs across the width
            from nosa_utils import links, standards
            try:
                fck = standards.concrete_fck_mpa(self._host_std(first))
            except Exception:
                fck = 30.0
            legs = 4 if values.get('interior_ties') else 2
            d_mm = links.effective_depth_mm(height_mm, cover_mm, values['stirrup_dia'], values['bar_dia'])
            if (legs < links.legs_needed(width_mm, cover_mm, values['stirrup_dia'], d_mm)
                    and max(values['n_top'], values.get('n_bottom') or 0) > 2):
                # SMDSC 6.3: legs at <= min(600, 0.75d) and every bar within 150 mm of one
                values = dict(values, interior_ties=True)
                legs = 4
                errors.append(u'{}: interior links added: the width needs more than two legs '
                              u'(SMDSC 6.3).'.format(label))
            pitch, link_notes = links.beam_review(width_mm, height_mm, cover_mm, values['stirrup_dia'],
                                                  values['bar_dia'], values['stirrup_spacing'], legs, fck,
                                                  label=label)
            errors.extend(link_notes)
            if pitch != values['stirrup_spacing']:
                values = dict(values, stirrup_spacing=pitch,
                              dense_spacing=min(values.get('dense_spacing') or pitch, pitch))
        except Exception:
            log_swallowed(_LOG, u'beam fit check')
        lap_mm, anchorage_mm = self._beam_lap_anchorage(first, values['bar_dia'])
        data = beam_rebar.build_continuous_line(
            self.doc, line, cover_mm, values['bar_dia'], values['n_top'], values['stirrup_dia'],
            values.get('support_dia') or values['bar_dia'], values.get('n_support', 0),
            values['stock_length'], lap_mm, anchorage_mm, flexible=values.get('flexible', False),
            n_bottom_bars=values.get('n_bottom') or values['n_top'])
        name = u'Beams {}'.format(u', '.join(str(get_id_value(h.Id)) for h in line))
        errors.extend(u'{}: {}'.format(name, w) for w in data['warnings'])
        if len(data['hanger_sets']) > 1:
            # IStructE SMDSC 5.4.3: a lap of H20 or more needs links of sum Ast >= As of one bar in
            # each outer third; the span links (2 legs) are checked, none are added here
            from nosa_utils import laps
            if not laps.lap_transverse_ok(values['bar_dia'], 100.0, lap_mm, values['stirrup_dia'], 2,
                                          values['stirrup_spacing']):
                errors.append(u'{}: the H{:.0f} top-bar laps ({:.0f} mm) need links of at least the area of '
                              u'one lapped bar in each outer third (SMDSC 5.4.3); the H{:.0f} links at '
                              u'{:.0f} mm do not give it: close them up over the laps.'.format(
                                  name, float(values['bar_dia']), float(lap_mm), float(values['stirrup_dia']),
                                  float(values['stirrup_spacing'])))
        bar_type = bar_types.get(values['bar_dia'])
        support_type = bar_types.get(values.get('support_dia'))
        if bar_type is not None:
            for host, group in data['hanger_sets']:
                self._create_long_group(wrapper, host, group, bar_type, u'Beam Hanger Bar', u'top',
                                        errors, created_rebars)
        if support_type is not None:
            for host, group in data['support_sets']:
                self._create_long_group(wrapper, host, group, support_type, u'Beam Support Bar',
                                        u'top_support', errors, created_rebars)
        if bar_type is not None:
            for host, group in data.get('splice_sets', []):
                # a FreeForm group: a shape-driven set in the second layer is re-seated by Revit
                # onto the first layer's line whenever it regenerates (measured 2026-10-07)
                chains = group.get('all_curves') or [group['curves']]
                rebar = wrapper.create_freeform_group(host, chains, bar_type,
                                                      transaction_name=u'NOSA — Create Beam Bottom Splice Bars')
                if rebar is None:
                    errors.append(u'Beam {}: bottom splice bars — {}'.format(get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'bottom_splice')
                    created_rebars.append(rebar)
            for host, group in data.get('end_u_sets', []):
                # FreeForm like the splice bars: both legs sit in a second layer
                chains = group.get('all_curves') or [group['curves']]
                rebar = wrapper.create_freeform_group(host, chains, bar_type,
                                                      transaction_name=u'NOSA — Create Beam End U-Bars')
                if rebar is None:
                    errors.append(u'Beam {}: end U-bars — {}'.format(get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'end_ubar')
                    created_rebars.append(rebar)
        self._create_spacers(wrapper, data.get('spacer_sets', []), errors, created_rebars)
        for host in line:      # the line's bars exist now: a failing span must not redo them
            ends = data['spans'].get(get_id_value(host.Id), {})
            try:
                self._process_beam(host, values, wrapper, bar_types, errors, created_rebars, span=ends)
            except Exception as e:
                errors.append(u'Beam {}: {}'.format(get_id_value(host.Id), e))

    def _process_beam(self, host, values, wrapper, bar_types, errors, created_rebars, span=None):
        # A floor that cuts the beam leaves it only the depth below the slab: the bars,
        # links and anchorage legs then lose that depth (found in the 2026-10-01 smoke test).
        try:
            for joined_id in DB.JoinGeometryUtils.GetJoinedElements(self.doc, host):
                joined = self.doc.GetElement(joined_id)
                if isinstance(joined, DB.Floor) and DB.JoinGeometryUtils.IsCuttingElementInJoin(
                        self.doc, joined, host):
                    errors.append(u'Beam {}: floor {} cuts this beam, so it is reinforced only '
                                  u'below the slab. For a full-depth beam use Modify > Join > '
                                  u'Switch Join Order, then regenerate.'.format(
                                      get_id_value(host.Id), get_id_value(joined_id)))
        except Exception:
            log_swallowed(_LOG, u'RebarAutomateWindow._process_beam')
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Other', self._standard_default_cover_mm(u'beam'))
        if is_ground_beam(host):
            bottom_mm = re_engine.get_native_cover_mm(self.doc, host, u'Bottom', cover_mm)
            if min(bottom_mm, cover_mm) < 75.0 - 1e-6:
                errors.append(u'Ground beam {}: cover {:.0f} mm (bottom {:.0f}) — SMDSC 6.7 asks for 75 mm where it '
                              u'is cast against the ground; set the host cover if so.'.format(
                                  get_id_value(host.Id), cover_mm, bottom_mm))
        try:
            # T8.47, SMDSC 5.2/5.3: do the top and bottom layers fit inside the links?
            import fit_checks
            width_mm, height_mm = beam_rebar.get_beam_section_mm(self.doc, host, cover_mm, values['bar_dia'])
            label = u'Beam {}'.format(get_id_value(host.Id))
            errors.extend(fit_checks.beam_notes(
                width_mm, cover_mm, values['stirrup_dia'], values['bar_dia'], values['n_top'],
                values.get('n_bottom', values['n_top']), label=label))
            # T8.37, SMDSC 6.3: link pitch, minimum shear ratio, legs across the width
            from nosa_utils import links, standards
            try:
                fck = standards.concrete_fck_mpa(self._host_std(host))
            except Exception:
                fck = 30.0
            legs = 4 if values.get('interior_ties') else 2
            d_mm = links.effective_depth_mm(height_mm, cover_mm, values['stirrup_dia'], values['bar_dia'])
            if (legs < links.legs_needed(width_mm, cover_mm, values['stirrup_dia'], d_mm)
                    and max(values['n_top'], values.get('n_bottom') or 0) > 2):
                # SMDSC 6.3: legs at <= min(600, 0.75d) and every bar within 150 mm of one
                values = dict(values, interior_ties=True)
                legs = 4
                errors.append(u'{}: interior links added: the width needs more than two legs '
                              u'(SMDSC 6.3).'.format(label))
            pitch, link_notes = links.beam_review(width_mm, height_mm, cover_mm, values['stirrup_dia'],
                                                  values['bar_dia'], values['stirrup_spacing'], legs, fck,
                                                  label=label)
            errors.extend(link_notes)
            if pitch != values['stirrup_spacing']:
                values = dict(values, stirrup_spacing=pitch,
                              dense_spacing=min(values.get('dense_spacing') or pitch, pitch))
        except Exception:
            log_swallowed(_LOG, u'beam fit check')
        lap_mm = None
        try:
            # Top bars of beams deeper than 250 mm are in poor bond (EC2 Fig. 8.2): the
            # one lap length used for every bar is the longer, top-bar one.
            bbox = host.get_BoundingBox(None)
            depth_mm = (bbox.Max.Z - bbox.Min.Z) * 304.8 if bbox is not None else 0.0
            lap_mm = standards.lap_length_mm(
                self._host_std(host), values['bar_dia'], False, 100.0, depth_mm <= 250.0,
                alpha3=standards.CONFINED_ALPHA3)
        except Exception:
            lap_mm = max(40.0 * values['bar_dia'], 15.0 * values['bar_dia'], 300.0)
        try:
            # anchorage into the columns, measured for the (poorer-bond) top bars
            anchorage_mm = standards.anchorage_length_mm(
                self._host_std(host), values['bar_dia'], depth_mm <= 250.0,
                alpha3=standards.CONFINED_ALPHA3)
        except Exception:
            anchorage_mm = None

        import nib_rebar
        from nosa_utils import nibs
        half = nib_rebar.half_joint_params(host)
        half_frame = None
        bottom_stop = (span or {}).get('bottom_stop_mm', (None, None))
        bottom_leg = (False, False)
        if half:
            # SMDSC 6.9 / EC2 Annex J: full-depth links only past the hanger links at each notch
            half_frame = nib_rebar.frame(host)
            stop = -(half[0] + cover_mm - half_frame['axis_offset'])
            bottom_stop, bottom_leg = (stop, stop), (True, True)
            hangers_end = (half[0] + cover_mm + values['stirrup_dia'] / 2.0
                           + (nibs.HANGER_LINKS - 1) * nibs.HANGER_PITCH_MM - half_frame['axis_offset'])
            values = dict(values, end_offset=max(values['end_offset'], hangers_end + 50.0))
        curves = beam_rebar.build_beam_rebar_curves(
            self.doc, host,
            cover_mm=cover_mm,
            bar_diameter_mm=values['bar_dia'],
            n_top_bars=values['n_top'],
            n_bottom_bars=values['n_bottom'],
            stirrup_spacing_mm=values['stirrup_spacing'],
            stirrup_bar_diameter_mm=values['stirrup_dia'],
            stirrup_start_offset_mm=values['end_offset'],
            stirrup_end_offset_mm=values['end_offset'],
            stock_length_mm=values['stock_length'],
            lap_length_mm=lap_mm,
            densify_ends=values.get('densify_ends', False),
            dense_spacing_mm=values.get('dense_spacing'),
            confine_length_mm=values.get('confine_length'),
            anchorage_mm=anchorage_mm,
            include_interior_ties=values.get('interior_ties', False),
            link_bend_diameter_mm=self._bend_diameter_mm(bar_types.get(values['stirrup_dia'])),
            continuous_ends=(span or {}).get('continuous_ends', (False, False)),
            internal_bottom_ext_mm=(span or {}).get('internal_bottom_ext_mm', (0.0, 0.0)),
            bottom_stop_mm=bottom_stop,
            bottom_stop_leg=bottom_leg,
            include_top=span is None,
            n_support_bars=values.get('n_support', 0),
            support_bar_diameter_mm=values.get('support_dia'),
            n_span_bars=values.get('n_span', 0),
            span_bar_diameter_mm=values.get('span_dia'))

        for w in curves.get('warnings', []):
            errors.append(u'Beam {}: {}'.format(get_id_value(host.Id), w))

        bar_type_long = bar_types.get(values['bar_dia'])
        first_long = len(created_rebars)
        long_normal = curves.get('long_bar_normal') or DB.XYZ.BasisZ

        def _create_bar_group_or_fallback(group, label, layer):
            """
            One entry from top_bar_sets/bottom_bar_sets: try ONE Rebar
            Set for `count` parallel bars (the optimisation — n
            individual elements become 1 countable Set), falling back
            to individual create_from_curves calls (all_curves) if the
            Set attempt fails, matching the same try/fallback shape
            already established for stirrup_sets above.
            """
            n = group.get('count', 1)
            if n > 1 and group.get('array_length_mm', 0) > 0:
                rebar = wrapper.create_rebar_set(
                    host, group['curves'], bar_type_long, group['spacing_mm'],
                    group['array_length_mm'], normal=group.get('normal', long_normal),
                    transaction_name=u'NOSA — Create {}'.format(group.get('label', label)))
                if rebar is None:
                    for chain in group.get('all_curves', [group['curves']]):
                        if not chain:
                            continue
                        rb = wrapper.create_from_curves(
                            host, chain, bar_type_long, normal=group.get('normal', long_normal),
                            transaction_name=u'NOSA — Create {}'.format(label))
                        if rb is None:
                            errors.append(u'Beam {}: {} — {}'.format(
                                get_id_value(host.Id), label, wrapper.last_error))
                        else:
                            self._stamp_layer(rb, layer)
                            created_rebars.append(rb)
                else:
                    self._stamp_layer(rebar, layer)
                    created_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Beam {}: {} — {}'.format(
                            get_id_value(host.Id), label, wrapper.last_error))
            else:
                for chain in group.get('all_curves', [group.get('curves')]):
                    if not chain:
                        continue
                    rb = wrapper.create_from_curves(
                        host, chain, bar_type_long, normal=group.get('normal', long_normal),
                        transaction_name=u'NOSA — Create {}'.format(label))
                    if rb is None:
                        errors.append(u'Beam {}: {} — {}'.format(
                            get_id_value(host.Id), label, wrapper.last_error))
                    else:
                        self._stamp_layer(rb, layer)
                        created_rebars.append(rb)

        if bar_type_long is not None:
            top_bar_sets = curves.get('top_bar_sets')
            if top_bar_sets:
                for group in top_bar_sets:
                    _create_bar_group_or_fallback(group, u'Beam Top Bar', u'top')
            else:
                # Legacy fallback — no grouped sets returned (e.g. an
                # older beam_rebar.py without this optimisation).
                for chain in curves.get('top_bars', []):
                    if not chain:
                        continue
                    rebar = wrapper.create_from_curves(
                        host, chain, bar_type_long, normal=long_normal,
                        transaction_name=u'NOSA — Create Beam Top Bar')
                    if rebar is None:
                        errors.append(u'Beam {}: top bar — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'top')
                        created_rebars.append(rebar)

            bottom_bar_sets = curves.get('bottom_bar_sets')
            if bottom_bar_sets:
                for group in bottom_bar_sets:
                    _create_bar_group_or_fallback(group, u'Beam Bottom Bar', u'bottom')
            else:
                for chain in curves.get('bottom_bars', []):
                    if not chain:
                        continue
                    rebar = wrapper.create_from_curves(
                        host, chain, bar_type_long, normal=long_normal,
                        transaction_name=u'NOSA — Create Beam Bottom Bar')
                    if rebar is None:
                        errors.append(u'Beam {}: bottom bar — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'bottom')
                        created_rebars.append(rebar)

        long_rebars = created_rebars[first_long:]
        support_type = bar_types.get(values.get('support_dia'))
        if support_type is not None:
            for group in curves.get('support_bar_sets') or []:
                self._create_long_group(wrapper, host, group, support_type, u'Beam Support Bar',
                                        u'top_support', errors, created_rebars)
        span_type = bar_types.get(values.get('span_dia'))
        if span_type is not None:
            for group in curves.get('span_bar_sets') or []:
                self._create_long_group(wrapper, host, group, span_type, u'Beam Span Bar',
                                        u'bottom_span', errors, created_rebars)
        self._create_spacers(wrapper, [(host, g) for g in curves.get('spacer_sets') or []], errors, created_rebars)
        side_groups = curves.get('side_bar_sets') or []
        if side_groups:
            # IStructE SMDSC 6.3: beams 1000 mm deep or more, H16 side bars at <= 250 mm
            side_type = re_engine.get_bar_type_by_diameter(self.doc, side_groups[0]['diameter_mm'])
            if side_type is None:
                errors.append(u'Beam {}: no H{:.0f} bar type for the side bars.'.format(
                    get_id_value(host.Id), float(side_groups[0]['diameter_mm'])))
            else:
                for group in side_groups:
                    self._create_long_group(wrapper, host, group, side_type, u'Beam Side Bar',
                                            u'side', errors, created_rebars)
        if len(curves.get('spans_mm') or []) > 1 and not values.get('n_support'):
            errors.append(u'Beam {}: runs over {} intermediate support(s) — links placed span by span; '
                          u'tick "Top support bars" for the hogging bars over them.'.format(
                              get_id_value(host.Id), len(curves['spans_mm']) - 1))


        bar_type_st = bar_types.get(values['stirrup_dia'])
        stirrup_sets = curves.get('stirrup_sets') or []
        if bar_type_st is not None and stirrup_sets:
            for sset in stirrup_sets:
                n = sset.get('count', 1)
                if n > 1 and sset.get('array_length_mm', 0) > 0:
                    rebar = wrapper.create_rebar_set(
                        host, sset['curves'], bar_type_st, sset['spacing_mm'],
                        sset['array_length_mm'], normal=sset['normal'],
                        style=DBS.RebarStyle.StirrupTie,
                        transaction_name=u'NOSA — Create Beam Stirrups ({})'.format(
                            sset.get('zone', u'')),
                        link_hook=re_engine.get_link_hook_type(self.doc))
                    if rebar is None:
                        for st_curves in sset.get('all_curves', [sset['curves']]):
                            rb = wrapper.create_from_curves(
                                host, st_curves, bar_type_st,
                                normal=sset.get('normal'),
                                style=DBS.RebarStyle.StirrupTie,
                                transaction_name=u'NOSA — Create Beam Stirrup')
                            if rb is None:
                                errors.append(u'Beam {}: stirrup — {}'.format(
                                    get_id_value(host.Id), wrapper.last_error))
                            else:
                                self._stamp_layer(rb, u'stirrup')
                                created_rebars.append(rb)
                    else:
                        self._stamp_layer(rebar, u'stirrup')
                        created_rebars.append(rebar)
                        if wrapper.last_error:
                            errors.append(u'Beam {}: stirrups {} — {}'.format(
                                get_id_value(host.Id), sset.get('zone', u''),
                                wrapper.last_error))
                else:
                    rebar = wrapper.create_from_curves(
                        host, sset['curves'], bar_type_st,
                        normal=sset.get('normal'),
                        style=DBS.RebarStyle.StirrupTie,
                        transaction_name=u'NOSA — Create Beam Stirrup')
                    if rebar is None:
                        errors.append(u'Beam {}: stirrup — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'stirrup')
                        created_rebars.append(rebar)
        elif bar_type_st is not None:
            # Legacy flat list fallback
            stirrup_normal = curves.get('long_bar_normal') or DB.XYZ.BasisZ
            for st_curves in curves.get('stirrups', []):
                rebar = wrapper.create_from_curves(
                    host, st_curves, bar_type_st, normal=stirrup_normal,
                    style=DBS.RebarStyle.StirrupTie,
                    transaction_name=u'NOSA — Create Beam Stirrup')
                if rebar is None:
                    errors.append(u'Beam {}: stirrup — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'stirrup')
                    created_rebars.append(rebar)

        if long_rebars and curves.get('bar_inset_mm'):
            # T2.10b: stirrups re-snap the longitudinals; pin them back to the design inset.
            try:
                with nosa_tx.guard(DB.Transaction(self.doc, u'NOSA — Pin Beam Longitudinal Bars')) as t:
                    t.Start()
                    for rebar in long_rebars:
                        re_engine.pin_rebar_to_host_faces(self.doc, rebar, host, curves['bar_inset_mm'])
                    t.Commit()
            except Exception as e:
                errors.append(u'Beam {}: longitudinal bars left where Revit snapped them '
                              u'(could not pin to the faces: {}).'.format(get_id_value(host.Id), e))

        # Interior links / crossties after the bars are pinned (see _process_column)
        if bar_type_st is not None:
            self._create_interior_tie_sets(
                host, curves.get('interior_tie_sets') or [], bar_type_st, wrapper, errors,
                created_rebars, u'Beam')
        if half:
            self._reinforce_half_joints(host, half, half_frame, values, cover_mm, bar_types, wrapper, errors,
                                        created_rebars)
        self._reinforce_nibs(host, values, cover_mm, bar_types, wrapper, errors, created_rebars)

    def _type_for(self, dia, bar_types):
        if bar_types.get(dia) is None:
            bar_types[dia] = re_engine.get_bar_type_by_diameter(self.doc, dia)
        return bar_types[dia]

    def _made(self, rebar, layer, label, wrapper, errors, created_rebars):
        try:
            if rebar is not None and not rebar.IsValidObject:
                rebar = None                     # Revit rejected and undid it
        except Exception:
            rebar = None
        if rebar is None:
            errors.append(u'{} — {}'.format(label, wrapper.last_error))
            return
        self._stamp_layer(rebar, layer)
        created_rebars.append(rebar)

    def _link_set(self, host, fr, xs, corners, bar_type, wrapper, label, layer, errors, created_rebars):
        """Closed links in the beam section at the even positions xs."""
        import nib_rebar
        xs = sorted(xs)
        curves = nib_rebar.section_loop(fr, xs[0], corners)
        if len(xs) > 1:
            rebar = wrapper.create_rebar_set(
                host, curves, bar_type, xs[1] - xs[0], xs[-1] - xs[0], normal=fr['ex'],
                style=DBS.RebarStyle.StirrupTie, transaction_name=u'NOSA — Create {}'.format(label),
                link_hook=re_engine.get_link_hook_type(self.doc))
        else:
            rebar = wrapper.create_from_curves(host, curves, bar_type, normal=fr['ex'], style=DBS.RebarStyle.StirrupTie,
                                               transaction_name=u'NOSA — Create {}'.format(label))
        self._made(rebar, layer, u'Beam {}: {}'.format(get_id_value(host.Id), label), wrapper, errors, created_rebars)

    def _reinforce_nibs(self, host, values, cover_mm, bar_types, wrapper, errors, created_rebars):
        """IStructE SMDSC MN1 (closed links) or MN2 (horizontal U-bars, shallow nibs) along the nibs of an 'RC Beam - Nib'."""
        import nib_rebar
        from nosa_utils import nibs
        info = nib_rebar.nib_sides(host)
        if info is None:
            return
        proj, depth, sides = info
        b, _h = nib_rebar.section_mm(host)
        fr = nib_rebar.frame(host)
        hid = get_id_value(host.Id)
        link_dia = min(values['stirrup_dia'], nibs.MAX_LINK_DIA_MM)
        mode, notes = nibs.nib_mode(depth, cover_mm, link_dia)
        errors.extend(u'Beam {}: {}'.format(hid, n) for n in notes)
        pitch = nibs.nib_pitch_mm(depth)
        x0, x1 = cover_mm + link_dia, fr['length'] - cover_mm - link_dia
        for n_side, side in enumerate(sides):
            def flip(pts):
                return [(x, side * y, z) for x, y, z in pts]
            if mode == 'MN1':
                corners = [(side * y, z) for y, z in nibs.mn1_link(b, proj, depth, cover_mm, link_dia)]
                xs = nibs.positions_mm(x0, x1, pitch)
                self._link_set(host, fr, xs, corners, self._type_for(link_dia, bar_types), wrapper, u'Nib Links',
                               u'nib_link', errors, created_rebars)
                bar_dia = 12.0
                bar_t = self._type_for(bar_dia, bar_types)
                for y, z in nibs.nib_bar_positions(b, proj, depth, cover_mm, link_dia, bar_dia):
                    line = nib_rebar.polyline(fr, [(cover_mm, side * y, z), (fr['length'] - cover_mm, side * y, z)])
                    self._made(wrapper.create_from_curves(host, line, bar_t, normal=fr['ey'],
                                                          transaction_name=u'NOSA — Create Nib Bar'),
                               u'nib_bar', u'Beam {}: nib bar'.format(hid), wrapper, errors, created_rebars)
                if not n_side:
                    errors.append(u'Beam {}: nib ({:.0f} x {:.0f}) to SMDSC MN1 — H{:.0f} closed links at {:.0f} round '
                              u'beam and nib, H{:.0f} bars in the nib corners; keep 60 mm overlap with the supported '
                              u'member\'s steel and size the beam links for the nib load.'.format(
                                  hid, proj, depth, link_dia, xs[1] - xs[0] if len(xs) > 1 else 0.0, bar_dia))
            else:
                dia = min(max(link_dia, 10.0), nibs.MAX_UBAR_DIA_MM)
                bar_t = self._type_for(dia, bar_types)
                anchorage = self._beam_lap_anchorage(host, dia)[1]
                xs = nibs.positions_mm(x0 + 30.0, x1 - 30.0, min(nibs.MAX_UBAR_PITCH_MM, pitch))
                chains, short = [], 0.0
                for x in xs:
                    pts, s = nibs.mn2_ubar(b, proj, depth, cover_mm, dia, anchorage, x)
                    short = max(short, s)
                    chains.append(nib_rebar.polyline(fr, flip(pts)))
                self._made(wrapper.create_freeform_group(host, chains, bar_t,
                                                         transaction_name=u'NOSA — Create Nib U-Bars'),
                           u'nib_ubar', u'Beam {}: nib U-bars'.format(hid), wrapper, errors, created_rebars)
                y, z = nibs.mn2_lacer(b, proj, depth, cover_mm, dia)
                line = nib_rebar.polyline(fr, [(cover_mm, side * y, z), (fr['length'] - cover_mm, side * y, z)])
                self._made(wrapper.create_from_curves(host, line, bar_t, normal=fr['ey'],
                                                      transaction_name=u'NOSA — Create Nib Lacer'),
                           u'nib_lacer', u'Beam {}: nib lacer'.format(hid), wrapper, errors, created_rebars)
                if not n_side:
                    errors.append(u'Beam {}: shallow nib ({:.0f} x {:.0f}) to SMDSC MN2 — {} horizontal H{:.0f} U-bars at '
                              u'{:.0f} with a lacer bar; wire each to at least two main bars.'.format(
                                  hid, proj, depth, len(xs), dia, xs[1] - xs[0] if len(xs) > 1 else 0.0))
                if short > 1.0:
                    errors.append(u'Beam {}: the nib U-bar legs reach the far side {:.0f} mm short of a tension '
                                  u'anchorage — bend them down or use smaller bars.'.format(hid, short))

    def _reinforce_half_joints(self, host, half, fr, values, cover_mm, bar_types, wrapper, errors, created_rebars):
        """IStructE SMDSC 6.9 / EC2 Annex J at both ends of an 'RC Beam - Half Joint'."""
        import nib_rebar
        from nosa_utils import nibs
        hid = get_id_value(host.Id)
        b, h = nib_rebar.section_mm(host)
        link_dia = values['stirrup_dia']
        ubar_dia = min(values['bar_dia'], nibs.MAX_UBAR_DIA_MM)
        anchorage = self._beam_lap_anchorage(host, ubar_dia)[1]
        lay = nibs.half_joint(half[0], half[1], h, b, cover_mm, link_dia, ubar_dia, anchorage)
        errors.extend(u'Beam {}: {}'.format(hid, n) for n in lay['notes'])
        link_t, u_t = self._type_for(link_dia, bar_types), self._type_for(ubar_dia, bar_types)
        c = cover_mm + link_dia / 2.0
        full = [(-b / 2.0 + c, c), (b / 2.0 - c, c), (b / 2.0 - c, h - c), (-b / 2.0 + c, h - c)]
        for end in (0, 1):
            def at(x):
                return x if end == 0 else fr['length'] - x
            self._link_set(host, fr, [at(x) for x in lay['hangers']], full, link_t, wrapper,
                           u'Half Joint Hanger Links', u'half_joint_hanger', errors, created_rebars)
            if lay['nib_links']:
                self._link_set(host, fr, [at(x) for x in lay['nib_links']], lay['nib_link'], link_t, wrapper,
                               u'Half Joint Nib Links', u'half_joint_link', errors, created_rebars)
            chains = [nib_rebar.polyline(fr, u if end == 0 else nib_rebar.mirror_x(fr, u)) for u in lay['ubars']]
            if chains:
                self._made(wrapper.create_freeform_group(host, chains, u_t,
                                                         transaction_name=u'NOSA — Create Half Joint U-Bars'),
                           u'half_joint_ubar', u'Beam {}: half joint U-bars'.format(hid), wrapper, errors,
                           created_rebars)

    @staticmethod
    def _bend_diameter_mm(bar_type):
        """Stirrup/Tie bend diameter (mm) of a bar type, or None."""
        try:
            return bar_type.StirrupTieBendDiameter * 304.8
        except Exception:
            return None

    def _create_interior_tie_sets(self, host, tie_sets, bar_type, wrapper, errors, created_rebars, kind):
        """Interior links and crossties as Sets with 135° Stirrup/Tie hooks; crossties take shape 99."""
        for iss in tie_sets:
            style = DBS.RebarStyle.StirrupTie if iss.get('style') == 'StirrupTie' else None
            rebar = wrapper.create_rebar_set(
                host, iss['curves'], bar_type, iss['spacing_mm'], iss['array_length_mm'],
                normal=iss['normal'], style=style,
                transaction_name=u'NOSA — Create {} Interior Links'.format(kind),
                link_hook=re_engine.get_link_hook_type(self.doc))
            layer = iss.get('layer', u'interior_stirrup')
            label = u'crosstie' if layer == u'crosstie' else u'interior link'
            if rebar is None:
                errors.append(u'{} {}: {} (set) — {}'.format(
                    kind, get_id_value(host.Id), label, wrapper.last_error))
                continue
            self._stamp_layer(rebar, layer)
            created_rebars.append(rebar)
            if wrapper.last_error:
                errors.append(u'{} {}: {} (set) — {}'.format(
                    kind, get_id_value(host.Id), label, wrapper.last_error))
            if layer == u'crosstie':
                # BS 8666 has no standard crosstie shape: code 99 (Revit had named it "Rebar Shape N")
                try:
                    with nosa_tx.guard(DB.Transaction(self.doc, u'NOSA — Name Crosstie Shape')) as t:
                        t.Start()
                        re_engine.name_auto_shape(self.doc, rebar, u'99')
                        t.Commit()
                except Exception as e:
                    errors.append(u'{} {}: crosstie shape left unnamed ({}).'.format(
                        kind, get_id_value(host.Id), e))

    def _run_beam_reinforcement(self, beams, values):
        errors = []
        diameters = {values['bar_dia'], values['stirrup_dia']}
        if values.get('n_support'):
            diameters.add(values['support_dia'])
        if values.get('n_span'):
            diameters.add(values['span_dia'])
        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []
        lines = beam_rebar.group_beam_lines(beams)
        if not values.get('continuous'):
            for line in lines:
                if len(line) > 1:
                    errors.append(u'Beams {} form one line over their supports but were reinforced as '
                                  u'separate spans: tick "Continuous beam over several spans" to detail them '
                                  u'as one (IStructE SMDSC 6.3).'.format(
                                      u', '.join(str(get_id_value(h.Id)) for h in line)))
            lines = [[b] for b in beams]
        for line in lines:
            if len(line) > 1:
                try:
                    self._process_beam_line(line, values, wrapper, bar_types, errors, created_rebars)
                    continue
                except Exception as e:
                    errors.append(u'Beams {}: not reinforced as one continuous line — {}. Each span '
                                  u'is reinforced on its own.'.format(
                                      u', '.join(str(get_id_value(h.Id)) for h in line), e))
            for host in line:
                try:
                    self._process_beam(host, values, wrapper, bar_types, errors, created_rebars)
                except Exception as e:
                    errors.append(u'Beam {}: {}'.format(get_id_value(host.Id), e))
        return created_rebars, {'created': len(created_rebars), 'errors': errors}


_OWN = set(globals())
