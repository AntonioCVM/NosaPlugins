# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Columns tab: inputs, generation and preview of column reinforcement.
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


class ColumnsMixin(object):
    # ── Columns (Phase 3) ────────────────────────────────────────────────

    def ColumnDensify_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelColDensify.IsEnabled = self.ChkColDensify.IsChecked == True
        self._update_column_preview()

    def ColumnCrossties_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelColCrossties.IsEnabled = self.ChkColCrossties.IsChecked == True
        self._update_column_preview()

    def ColFoundationStarters_Click(self, sender, args):
        # PHASE F7.18 (2026-09-02) — no preview support yet (scope
        # disclosed to the user: this feature's own geometry depends on
        # a live foundation-detection query, not the illustrative-only
        # rebar_preview.py this window's other panels use) — just
        # enables/disables the length fields, matching every other
        # optional-panel checkbox's own convention.
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelColFoundationStarters.IsEnabled = self.ChkColFoundationStarters.IsChecked == True

    def ColumnPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_column_preview()

    def _update_column_preview(self):
        columns = self._selected_columns()
        col_host = columns[0] if columns else None

        # PHASE 3.5.3 item 4 — cover from the live selected column's
        # own native Rebar Cover, matching real generation exactly
        # (see _process_column) instead of a typed UI value.
        cover = self._preview_cover_mm(col_host, u'Exterior', u'column')
        try:
            bar_dia = float(self.TxtColBarDia.Text)
            bar_count = float(self.TxtColBarCount.Text)
            link_dia = float(self.TxtColLinkDia.Text)
        except (TypeError, ValueError):
            return
        if cover <= 0 or bar_dia <= 0 or bar_count < 4 or link_dia <= 0:
            return

        # Representative section — falls back to a fixed illustrative
        # 400x300mm rectangle when no column is selected or its
        # geometry can't be read; otherwise uses the REAL selected
        # host's own shape/aspect-ratio/diameter (Phase 3.4 item 4), so
        # the preview never shows a misleading rectangle for a round
        # column or the wrong proportions for a real rectangular one.
        width_mm, depth_mm = 400.0, 300.0
        shape, diameter_mm = 'rect', None
        try:
            if col_host is not None:
                geom = column_rebar.detect_column_geometry(self.doc, col_host)
                if geom is not None:
                    shape = geom['shape']
                    if shape == 'circle':
                        diameter_mm = geom['diameter_mm']
                    else:
                        width_mm, depth_mm = geom['width_mm'], geom['depth_mm']
        except Exception:
            shape, diameter_mm = 'rect', None
            width_mm, depth_mm = 400.0, 300.0

        crossties = self.ChkColCrossties.IsChecked == True
        crosstie_layout = ('alternate' if self.CboCrosstieLayout.SelectedIndex == 1
                            else 'all')

        try:
            data = rebar_preview.compute_column_section_preview(
                width_mm, depth_mm, cover, bar_dia, int(bar_count), link_dia,
                shape=shape, diameter_mm=diameter_mm,
                include_crossties=crossties, crosstie_layout=crosstie_layout)
        except ValueError:
            return

        positions = [(b['x_mm'], b['y_mm']) for b in data['bars']]
        starters = self.ChkColFoundationStarters.IsChecked == True
        self._draw_shapes(self.ColumnPreviewCanvas, preview_shapes.column_section_shapes(
            diameter_mm if shape == 'circle' else width_mm,
            diameter_mm if shape == 'circle' else depth_mm,
            cover, bar_dia, positions, link_dia, shape=shape, starters=starters,
            starter_dia=bar_dia, link_spacing=self._preview_number(self.TxtColLinkSpacing, None),
            crossties=[(t['x1_mm'], t['y1_mm'], t['x2_mm'], t['y2_mm']) for t in data['crossties']]))
        self._update_column_adopted_solution_label(cover, bar_dia, int(bar_count), link_dia)
        self._update_column_elevation_preview()

    def _update_column_elevation_preview(self):
        columns = self._selected_columns()
        col_host = columns[0] if columns else None

        # PHASE 3.5.3 item 4 — same live-host native cover as the plan
        # preview (_update_column_preview) — see that method's note.
        cover = self._preview_cover_mm(col_host, u'Exterior', u'column')
        try:
            bar_dia = float(self.TxtColBarDia.Text)
            bar_count = float(self.TxtColBarCount.Text)
            link_dia = float(self.TxtColLinkDia.Text)
            normal_spacing = float(self.TxtColLinkSpacing.Text)
        except (TypeError, ValueError):
            return
        if cover <= 0 or bar_dia <= 0 or bar_count < 4 or link_dia <= 0 or normal_spacing <= 0:
            return

        densify = self.ChkColDensify.IsChecked == True
        dense_spacing = normal_spacing
        if densify:
            try:
                dense_spacing = float(self.TxtColDenseSpacing.Text)
            except (TypeError, ValueError):
                return
            if dense_spacing <= 0:
                return

        starter_bars = self.ChkColStarterBars.IsChecked == True
        cranked_laps = self.ChkColCrankedLaps.IsChecked == True
        crossties = self.ChkColCrossties.IsChecked == True

        # Same illustrative section as the plan preview, plus a
        # representative column height — this module has no real
        # host height/width available at preview time UNLESS a real
        # column is currently selected, in which case its own axis/
        # floor intersections/real cross-section width are used so the
        # preview reflects the ACTUAL multi-story splits/starters/
        # aspect ratio that will be generated (Phase 3.2 item 5 /
        # Phase 3.4 item 4) — best-effort only, silently falling back
        # to the plain illustrative case for any failure (nothing
        # selected, a non-rectangular host, etc.), matching this
        # method's existing defensive convention.
        width_mm, height_mm = 400.0, 3000.0
        floor_splits_mm = None
        floor_bands_mm = None
        preview_crank_offset_mm = None
        try:
            if col_host is not None:
                host = col_host
                axis = column_rebar.get_column_axis(host)
                height_mm = axis.Length * 304.8
                geom = column_rebar.detect_column_geometry(self.doc, host)
                if geom is not None:
                    width_mm = geom['diameter_mm'] if geom['shape'] == 'circle' else geom['width_mm']
                floor_entries = column_rebar.find_floor_split_elevations_ft(self.doc, axis)
                base_z_ft = axis.GetEndPoint(0).Z
                floor_splits_mm = [(e['top_ft'] - base_z_ft) * 304.8 for e in floor_entries]
                floor_bands_mm = [((e['bottom_ft'] - base_z_ft) * 304.8,
                                    (e['top_ft'] - base_z_ft) * 304.8) for e in floor_entries]
                if cranked_laps:
                    # A REAL, representative crank offset (Phase 3.3):
                    # resolved against whatever column is actually
                    # found above the LAST split (or this column's own
                    # top, if none) — the same detection
                    # build_column_reinforcement itself uses, not the
                    # old fixed-heuristic default. Uses the 'v' edge as
                    # representative (the elevation preview shows one
                    # face, not all 4).
                    engine = re_engine
                    cover_mgr = engine.CoverGeometryManager(self.doc, host)
                    u_pos, u_neg, v_pos, v_neg, u_dir, v_dir = column_rebar._column_faces(
                        cover_mgr, axis.Direction)
                    bar_inset_mm = cover + link_dia + bar_dia / 2.0 +                         engine.link_corner_extra_inset_mm(bar_dia, link_dia)
                    bar_half_w_mm, bar_half_d_mm = column_rebar._cross_section_half_extents(
                        engine, axis, u_pos, u_neg, v_pos, v_neg, u_dir, v_dir, bar_inset_mm)
                    top_elevation_ft = floor_entries[-1]['top_ft'] if floor_entries else axis.GetEndPoint(1).Z
                    preview_crank_offset_mm = column_rebar.resolve_crank_offset_mm(
                        self.doc, host, axis, top_elevation_ft, 'v', engine, bar_inset_mm,
                        bar_half_w_mm, bar_half_d_mm)
        except Exception:
            floor_splits_mm = None
            floor_bands_mm = None
            height_mm = 3000.0
            preview_crank_offset_mm = None

        try:
            data = rebar_preview.compute_column_elevation_preview(
                width_mm, height_mm, cover, bar_dia, int(bar_count), link_dia,
                dense_spacing, normal_spacing, densify, starter_bars,
                floor_splits_mm=floor_splits_mm, use_cranked_laps=cranked_laps,
                crank_offset_mm=preview_crank_offset_mm,
                floor_bands_mm=floor_bands_mm, include_crossties=crossties)
        except ValueError:
            return

        base_levels = [y for y in (floor_splits_mm or []) if 0.0 < y < height_mm - 1.0]
        self._draw_shapes(self.ColumnElevationCanvas, preview_shapes.column_elevation_shapes(
            width_mm, height_mm, cover, bar_dia, link_dia, normal_spacing,
            dense_spacing=dense_spacing if densify else None,
            dense_zone_mm=max(width_mm, height_mm / 6.0, 450.0) if densify else None,
            top_starters=starter_bars, top_lap_mm=self._splice_mm(None, bar_dia, None),
            foundation_starters=self.ChkColFoundationStarters.IsChecked == True,
            starter_dia=bar_dia,
            starter_splice_mm=self._preview_splice(self.TxtColFoundationSplice, bar_dia),
            kicker_mm=self._kicker_mm(), floor_levels_mm=base_levels))

    def _draw_column_elevation_preview(self, data):
        canvas = self.ColumnElevationCanvas
        canvas.Children.Clear()

        section = data['section']
        w_mm = section['width_mm']
        h_mm = section['height_mm']
        starter_ext = data['starter_extension_mm']

        cw = canvas.Width
        ch = canvas.Height
        margin_x = 40.0
        margin_top = 16.0
        margin_bottom = 16.0
        total_h_mm = h_mm + starter_ext
        scale = min((cw - 2 * margin_x) / w_mm, (ch - margin_top - margin_bottom) / total_h_mm)
        off_x = cw / 2.0
        off_y = ch - margin_bottom

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        # Column outline (base to head, excluding starter projection)
        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 1.5
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        # Floor-split reference lines (Phase 3.2 item 5) — dashed,
        # drawn full-width, one per intermediate storey join detected
        # on the currently selected column's own axis.
        for split_mm in data.get('floor_splits_mm', []):
            line = SWS.Line()
            line.X1 = sx(-w_mm / 2.0 - 6.0)
            line.X2 = sx(w_mm / 2.0 + 6.0)
            line.Y1 = sy(split_mm)
            line.Y2 = sy(split_mm)
            line.Stroke = _PREVIEW_SECTION_STROKE
            line.StrokeThickness = 1.0
            line.StrokeDashArray = SWM.DoubleCollection([4.0, 3.0])
            canvas.Children.Add(line)

        # Vertical bar segments — one or more per bar position (a
        # straight run per storey, plus a straight or cranked starter
        # at each split/the head, if any — see
        # rebar_preview.compute_column_elevation_preview).
        for bar in data['bars']:
            line = SWS.Line()
            line.X1 = sx(bar['x0_mm'])
            line.X2 = sx(bar['x1_mm'])
            line.Y1 = sy(bar['y0_mm'])
            line.Y2 = sy(bar['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.5, bar['diameter_mm'] * scale)
            canvas.Children.Add(line)

        # Horizontal link/tie lines, illustrating densification at
        # nodes — excludes any Z inside a detected floor's own
        # thickness (Phase 3.4 item 2), matching the real generator.
        for link in data['links']:
            line = SWS.Line()
            line.X1 = sx(-link['half_w_mm'])
            line.X2 = sx(link['half_w_mm'])
            line.Y1 = sy(link['y_mm'])
            line.Y2 = sy(link['y_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.5
            canvas.Children.Add(line)

        # Interior crosstie lines (Phase 3.4 item 5) — shorter, dashed,
        # crossing only the core.
        for tie in data.get('crossties', []):
            line = SWS.Line()
            line.X1 = sx(-tie['half_w_mm'])
            line.X2 = sx(tie['half_w_mm'])
            line.Y1 = sy(tie['y_mm'])
            line.Y2 = sy(tie['y_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.0
            line.StrokeDashArray = SWM.DoubleCollection([3.0, 2.0])
            canvas.Children.Add(line)

    def _draw_column_preview(self, data):
        canvas = self.ColumnPreviewCanvas
        canvas.Children.Clear()

        section = data['section']
        w_mm = section['width_mm']
        h_mm = section['height_mm']

        cw = canvas.Width
        ch = canvas.Height
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        off_x = cw / 2.0
        off_y = ch / 2.0

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        # Concrete section outline — a circle for a round column
        # (Phase 3.4 item 4), a rectangle at its REAL aspect ratio
        # otherwise.
        is_circle = section.get('shape') == 'circle'
        outline = SWS.Ellipse() if is_circle else SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 1.5
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm / 2.0))
        canvas.Children.Add(outline)

        # Stirrup (Link/Tie) perimeter outline, cover-inset
        stirrup = data['stirrup']
        st_w = stirrup['half_w_mm'] * 2.0 * scale
        st_d = stirrup['half_d_mm'] * 2.0 * scale
        st_shape = SWS.Ellipse() if is_circle else SWS.Rectangle()
        st_shape.Width = st_w
        st_shape.Height = st_d
        st_shape.Stroke = _PREVIEW_BAR_FILL
        st_shape.StrokeThickness = 1.5
        st_shape.Fill = SWM.Brushes.Transparent
        SWC.Canvas.SetLeft(st_shape, sx(-stirrup['half_w_mm']))
        SWC.Canvas.SetTop(st_shape, sy(stirrup['half_d_mm']))
        canvas.Children.Add(st_shape)

        # Vertical bar dots
        for bar in data['bars']:
            dot_d = max(4.0, bar['diameter_mm'] * scale)
            dot = SWS.Ellipse()
            dot.Width = dot_d
            dot.Height = dot_d
            dot.Fill = _PREVIEW_BAR_FILL
            SWC.Canvas.SetLeft(dot, sx(bar['x_mm']) - dot_d / 2.0)
            SWC.Canvas.SetTop(dot, sy(bar['y_mm']) - dot_d / 2.0)
            canvas.Children.Add(dot)

        # PHASE 3.5.1 item 4 — interior crosstie lines, plan view: each
        # line connects an intermediate bar to its direct mirror across
        # the section, the exact same (x1,y1)-(x2,y2) pairing
        # column_rebar.build_crosstie_sets computes for real creation
        # (see compute_column_section_preview/_crosstie_lines_preview).
        for tie in data.get('crossties', []):
            line = SWS.Line()
            line.X1 = sx(tie['x1_mm'])
            line.Y1 = sy(tie['y1_mm'])
            line.X2 = sx(tie['x2_mm'])
            line.Y2 = sy(tie['y2_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.0
            line.StrokeDashArray = SWM.DoubleCollection([3.0, 2.0])
            canvas.Children.Add(line)

    def _update_column_adopted_solution_label(self, cover, bar_dia, bar_count, link_dia):
        text = (u'Adopted Solution — {} x Ø{:.0f}mm verticals, Ø{:.0f}mm links, '
                u'{:.0f}mm cover').format(bar_count, bar_dia, link_dia, cover)
        self.TxtColumnAdoptedSolution.Text = text

    def _selected_columns(self):
        ids = self.uidoc.Selection.GetElementIds()
        columns = []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            if get_id_value(elem.Category.Id) == _cat_id('OST_StructuralColumns'):
                columns.append(elem)
        return columns

    def _selected_beams(self):
        ids = self.uidoc.Selection.GetElementIds()
        beams = []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            if get_id_value(elem.Category.Id) == _cat_id('OST_StructuralFraming') or is_ground_beam(elem):
                beams.append(elem)
        return beams

    def _selected_walls(self):
        ids = self.uidoc.Selection.GetElementIds()
        walls = []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            if get_id_value(elem.Category.Id) == _cat_id('OST_Walls'):
                walls.append(elem)
        return walls

    def _read_column_inputs(self):
        errors = []
        values = {}

        # PHASE 3.5.3 item 4 — cover is no longer read here: it's
        # resolved per-host from native Rebar Cover in _process_column.
        values['bar_dia'] = self._read_number(self.TxtColBarDia.Text, u'Vertical bar diameter', errors)
        try:
            values['bar_count'] = int(float(self.TxtColBarCount.Text))
            if values['bar_count'] < 4:
                errors.append(u'"Quantity" must be at least 4.')
        except (TypeError, ValueError):
            errors.append(u'"Quantity" must be a number.')
            values['bar_count'] = None
        values['link_dia'] = self._read_number(self.TxtColLinkDia.Text, u'Link diameter', errors)
        values['link_spacing'] = self._read_number(
            self.TxtColLinkSpacing.Text, u'Link centre spacing', errors)
        values['densify'] = self.ChkColDensify.IsChecked == True
        if values['densify']:
            values['dense_spacing'] = self._read_number(
                self.TxtColDenseSpacing.Text, u'Densified spacing at nodes', errors)
        values['starter_bars'] = self.ChkColStarterBars.IsChecked == True
        values['cranked_laps'] = self.ChkColCrankedLaps.IsChecked == True
        values['crossties'] = self.ChkColCrossties.IsChecked == True
        values['helical'] = self.ChkColHelical.IsChecked == True
        values['crosstie_layout'] = ('alternate' if self.CboCrosstieLayout.SelectedIndex == 1
                                      else 'all')

        # PHASE F7.18 (2026-09-02, explicit request) — L-shaped starters
        # into whatever foundation (isolated/strip footing or floor/mat
        # slab) is detected below the column, distinct from starter_bars
        # above (which extends the column's OWN top, for future storeys).
        values['foundation_starters'] = self.ChkColFoundationStarters.IsChecked == True
        if values['foundation_starters']:
            values['foundation_anchor_mm'] = self._read_number(
                self.TxtColFoundationAnchor.Text, u'Foundation starter anchor length', errors)
            values['foundation_splice_mm'] = self._read_splice(
                self.TxtColFoundationSplice.Text, u'Foundation starter splice length', errors)

        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def RunColumnReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_column_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'columns', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_column_result(self, columns, summary):
        lines = [
            u'{} column(s) processed.'.format(len(columns)),
            u'{} Rebar element(s) created (sets count as one each).'.format(summary['created']),
        ]
        if summary['errors']:
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — same fix as _show_reinforcement_result.
            lines.extend(summary['errors'])
        self.TxtColumnResult.Text = u'\n'.join(lines)

    def _process_column(self, host, values, wrapper, bar_types, errors, created_rebars):
        """
        PHASE 3.2 — vertical bars are now Rebar SETS, one per column
        face per storey segment (SetLayoutAsFixedNumber — see
        column_rebar.build_column_reinforcement's own docstring for why
        this is now a Set, and for the multi-story splitting/cranked-lap
        behaviour); the rare face reduced to a single bar position
        (e.g. a V-edge on a small column) stays an individual element,
        since a Set has nothing to propagate for a count of 1.
        Links/ties remain Rebar Sets (1 zone, or 3 if
        densify_at_nodes, now split further wherever they'd otherwise
        run through a detected floor — Phase 3.4 item 2), the same
        create_rebar_set mechanism footing_rebar.build_side_rebar_set
        already proved live for a vertically-propagated closed
        rectangle. Interior links and crossties, if requested, are Sets
        too (column_rebar.interior_tie_layout), created after the
        verticals are pinned to the faces.
        """
        # PHASE 3.5.3 item 4 — cover read from THIS host's own native
        # Rebar Cover ('Exterior' face — a column's cover is uniform
        # across all 4 side faces in this plugin's model), not a UI
        # text field.
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Exterior', self._standard_default_cover_mm(u'column'))
        try:
            # T8.47, SMDSC 5.2/5.3: do the bars fit inside the links at their actual size?
            import fit_checks
            geom = column_rebar.detect_column_geometry(self.doc, host)
            per_face = (0, 0)
            if geom and geom.get('shape') == 'rect':
                per_face = column_rebar.distribute_bar_count(
                    values['bar_count'], geom['width_mm'] / 2.0, geom['depth_mm'] / 2.0)
            errors.extend(fit_checks.column_notes(
                geom, cover_mm, values['link_dia'], values['bar_dia'], values['bar_count'], per_face,
                label=u'Column {}'.format(get_id_value(host.Id))))
            # T8.38, SMDSC 6.4: link pitch (x 0.6 next to beams, slabs and laps), sizes, restraint
            from nosa_utils import links
            pitch, dense, link_notes = links.column_review(
                geom, cover_mm, values['link_dia'], values['bar_dia'], values['bar_count'], per_face,
                values['link_spacing'], values.get('dense_spacing'), values.get('densify'),
                values.get('crossties'), label=u'Column {}'.format(get_id_value(host.Id)))
            errors.extend(link_notes)
            # SMDSC 6.4 / 5.4.3: links against bursting at laps of H20 and over (sum Ast >= As)
            from nosa_utils import laps
            lap_mm = column_rebar.default_lap_length_mm(values['bar_dia'], std=self._host_std(host))
            # SMDSC 6.4 / Fig. 6.25: along every lap the links are at the dense pitch, closer for
            # H20 and over so each outer third holds the area of one lapped bar
            lap_pitch = dense or pitch
            burst = laps.lap_link_pitch_mm(values['bar_dia'], lap_mm, values['link_dia'], 2)
            if burst is not None and burst < lap_pitch:
                lap_pitch = burst
                errors.append(u'Column {}: links at {:.0f} along the H{:.0f} laps ({:.0f} mm) so each outer '
                              u'third holds the area of one bar (SMDSC 6.4, Fig. 6.25).'.format(
                                  get_id_value(host.Id), float(burst), float(values['bar_dia']), float(lap_mm)))
            values = dict(values, lap_link_spacing=lap_pitch)
            if pitch != values['link_spacing'] or dense != values.get('dense_spacing'):
                values = dict(values, link_spacing=pitch, dense_spacing=dense)
        except Exception:
            log_swallowed(_LOG, u'column fit check')
        try:
            link_bend_mm = bar_types[values['link_dia']].StirrupTieBendDiameter * 304.8
        except Exception:
            link_bend_mm = None
        reinforcement = column_rebar.build_column_reinforcement(
            self.doc, host,
            cover_mm=cover_mm,
            bar_diameter_mm=values['bar_dia'],
            bar_count=values['bar_count'],
            stirrup_diameter_mm=values['link_dia'],
            dense_spacing_mm=values.get('dense_spacing', values['link_spacing']),
            normal_spacing_mm=values['link_spacing'],
            densify_at_nodes=values['densify'],
            include_starter_bars=values['starter_bars'],
            use_cranked_laps=values['cranked_laps'],
            include_crossties=values['crossties'],
            crosstie_layout=values['crosstie_layout'], link_bend_diameter_mm=link_bend_mm,
            std=self._host_std(host), kicker_mm=self._kicker_mm(),
            lap_link_spacing_mm=values.get('lap_link_spacing'),
            slab_top_mat_mm=self._preview_number(self.TxtTopDiaX, 12.0)
            + self._preview_number(self.TxtTopDiaY, 12.0))

        for w in reinforcement.get('warnings', []):
            errors.append(u'Column {}: {}'.format(get_id_value(host.Id), w))

        # DIAGNOSTIC HARDENING (2026-09-01) — a circular column was
        # reported creating ZERO rebar with NO error at all, which
        # should be impossible if a caught exception was the cause (see
        # this file's outer try/except in _run_column_reinforcement).
        # The remaining explanation is build_column_reinforcement
        # itself returning normally with every list empty — nothing to
        # create, nothing to fail, hence silence. Surface that
        # explicitly so it is never silent again.
        if not any(reinforcement.get(k) for k in (
                'vertical_bars', 'vertical_bar_sets', 'stirrup_sets',
                'interior_stirrup_sets', 'crosstie_sets')):
            errors.append(
                u'Column {}: build_column_reinforcement returned with NO curves '
                u'at all (no exception, no warnings) — nothing to create. This '
                u'points at generate_column_stirrup_zones/_subtract_floor_bands '
                u'or build_story_segment_chains producing empty output for this '
                u'host\'s specific geometry (e.g. a multi-storey split); please '
                u'report this exact column/model to investigate further.'.format(
                    get_id_value(host.Id)))

        bar_type_vert = bar_types.get(values['bar_dia'])
        first_vertical = len(created_rebars)
        if bar_type_vert is not None:
            for vs in reinforcement['vertical_bar_sets']:
                rebar = wrapper.create_rebar_set_fixed_number(
                    host, vs['curves'], bar_type_vert, vs['count'], vs['array_length_mm'],
                    normal=vs['normal'],
                    transaction_name=u'NOSA — Create Column Vertical Bars',
                    shape_name=vs.get('shape'))
                if getattr(wrapper, 'shape_warning', None):
                    errors.append(u'Column {}: cranked bars — {}'.format(
                        get_id_value(host.Id), wrapper.shape_warning))
                if rebar is None:
                    errors.append(u'Column {}: vertical bars (set) — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'vertical')
                    created_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Column {}: vertical bars (set) — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
            for vb in reinforcement['vertical_bars']:
                rebar = wrapper.create_from_curves(
                    host, vb['curves'], bar_type_vert, normal=vb['normal'],
                    transaction_name=u'NOSA — Create Column Vertical Bar',
                    shape_name=vb.get('shape'))
                if getattr(wrapper, 'shape_warning', None):
                    errors.append(u'Column {}: cranked bar — {}'.format(
                        get_id_value(host.Id), wrapper.shape_warning))
                if rebar is None:
                    errors.append(u'Column {}: vertical bar — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'vertical')
                    created_rebars.append(rebar)

        vertical_rebars = created_rebars[first_vertical:]
        if bar_type_vert is not None:
            for us in reinforcement.get('top_ubar_sets', []):
                if us['count'] > 1:
                    rebar = wrapper.create_rebar_set_fixed_number(
                        host, us['curves'], bar_type_vert, us['count'], us['array_length_mm'],
                        normal=us['normal'], transaction_name=u'NOSA — Create Column Top U-Bars')
                else:
                    rebar = wrapper.create_from_curves(
                        host, us['curves'], bar_type_vert, normal=us['normal'],
                        transaction_name=u'NOSA — Create Column Top U-Bar')
                if rebar is None:
                    errors.append(u'Column {}: top U-bars (SMDSC MC4) — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'top_ubar')
                    created_rebars.append(rebar)

        bar_type_link = bar_types.get(values['link_dia'])
        link_rebars = []
        if bar_type_link is not None:
            for s in reinforcement['stirrup_sets']:
                style = DBS.RebarStyle.StirrupTie if s.get('style') == 'StirrupTie' else None
                rebar = None
                circle = s.get('circle')
                if circle and values.get('helical') and self._create_helix(
                        host, bar_type_link, circle, s, errors, created_rebars, link_rebars):
                    continue
                if circle:
                    rebar = wrapper.create_lapped_circle_set(
                        host, bar_type_link, circle['centre'], circle['radius_mm'],
                        circle['lap_mm'], s['spacing_mm'], s['array_length_mm'])
                    if rebar is None:
                        errors.append(u'Column {}: circular links drawn as a polygon — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                if rebar is None:
                    rebar = wrapper.create_rebar_set(
                        host, s['curves'], bar_type_link, s['spacing_mm'], s['array_length_mm'],
                        normal=s['normal'], style=style,
                        transaction_name=u'NOSA — Create Column Links',
                        link_hook=re_engine.get_link_hook_type(self.doc))
                if rebar is None:
                    errors.append(u'Column {}: links (set) — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'stirrup')
                    created_rebars.append(rebar)
                    link_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Column {}: links (set) — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))

        if bar_type_link is not None:
            self._crank_knuckle_links(host, reinforcement, bar_type_link, wrapper, errors, created_rebars)

        # PHASE F7.18 (2026-09-02, explicit request — "Starter bars con
        # forma de L en columnas y muros... unidas a la cimentación") —
        # a representative 4-corner starter cage (n_u=n_v=2, matching
        # footing_rebar's own Dowels default of 4) reaching down into
        # whatever foundation is detected below this column, distinct
        # from values['starter_bars'] above (the column's OWN top, for
        # future storeys — unrelated direction/purpose).
        if vertical_rebars and reinforcement.get('bar_inset_mm'):
            # T2.10b: links re-snap the verticals; pin them back to the design inset.
            try:
                with nosa_tx.guard(DB.Transaction(self.doc, u'NOSA — Pin Column Vertical Bars')) as t:
                    t.Start()
                    for rebar in link_rebars:     # off the cover of a beam joined through the column
                        # cover + link diameter: the distance Revit itself keeps on the hooked sides,
                        # so a column with a beam through it matches its neighbours in the BBS
                        re_engine.pin_rebar_to_host_faces(self.doc, rebar, host, cover_mm + values['link_dia'],
                                                         foreign_handles=('Edge',))
                    if link_rebars:
                        self.doc.Regenerate()
                    for rebar in vertical_rebars:
                        re_engine.pin_rebar_to_host_faces(
                            self.doc, rebar, host, reinforcement['bar_inset_mm'])
                        if link_rebars:
                            self.doc.Regenerate()
                    t.Commit()
            except Exception as e:
                errors.append(u'Column {}: vertical bars left where Revit snapped them '
                              u'(could not pin to the faces: {}).'.format(get_id_value(host.Id), e))

        # Interior links and crossties (column_rebar.interior_tie_layout) are Sets laid out like
        # the main links, created AFTER the verticals are pinned: pinning re-targets the handles
        # Revit snapped to other bars, so ties present by then dragged verticals to a wrong face.
        if bar_type_link is not None:
            self._create_interior_tie_sets(
                host, reinforcement.get('interior_stirrup_sets', []), bar_type_link, wrapper, errors,
                created_rebars, u'Column')

        if values.get('foundation_starters') and bar_type_vert is not None and \
                re_engine.nosa_bars_in_footprint(self.doc, host, (u'dowel', u'foundation_starter')):
            errors.append(u'Column {}: foundation starters skipped — the footing below already '
                          u'has NOSA dowels (or starters) under this column.'.format(get_id_value(host.Id)))
        elif values.get('foundation_starters') and bar_type_vert is not None:
            points = re_engine.unique_plan_points(
                [p for r in vertical_rebars for p in re_engine.rebar_bar_plan_points(r)])
            starters = column_rebar.build_column_foundation_starters(
                self.doc, host, points, values['bar_dia'], values['bar_dia'],
                values['foundation_anchor_mm'],
                self._foundation_starter_mm(values['foundation_splice_mm'], values['bar_dia'], host, errors),
                foundation_cover_mm=cover_mm)
            hook_90 = re_engine.get_hook_type_by_angle(self.doc, 90.0)
            if hook_90 is None:
                errors.append(u'Column {}: foundation starters — no 90° RebarHookType '
                              u'found in this project; created WITHOUT hooks (not '
                              u'normative anchorage).'.format(get_id_value(host.Id)))
            self._create_foundation_starter_bars(
                wrapper, host, starters, bar_type_vert, hook_90, u'Column',
                errors, created_rebars)
            try:
                hand = DB.XYZ(host.HandOrientation.X, host.HandOrientation.Y, 0.0)
            except Exception:
                hand = DB.XYZ.BasisX
            by_foundation = {}
            for line, foundation in zip(starters.get('bars', []), starters.get('hosts', [])):
                by_foundation.setdefault(get_id_value(foundation.Id), (foundation, []))[1].append(line)
            self._create_starter_links(
                wrapper, [{'bars': lines, 'hand': hand, 'foundation': foundation}
                          for foundation, lines in by_foundation.values()],
                values['bar_dia'], cover_mm, errors, created_rebars, u'Column', host)

    def _create_helix(self, host, bar_type, circle, zone, errors, created_rebars, link_rebars):
        """IStructE SMDSC MC6: the zone's circular links as helical binding, 12 m pieces lapped one turn."""
        from nosa_utils import links
        shape = re_engine.find_rebar_shape(self.doc, u'77')
        if shape is None:
            errors.append(u'Column {}: no spiral shape 77 in the project — circular links used '
                          u'instead of a helix.'.format(get_id_value(host.Id)))
            return False
        pieces = links.helix_pieces_mm(zone['array_length_mm'], zone['spacing_mm'], circle['radius_mm'])
        made = []
        try:
            with nosa_tx.guard(DB.Transaction(self.doc, u'NOSA — Create Helical Links')) as t:
                t.Start()
                for z0, height in pieces:
                    centre = circle['centre'] + DB.XYZ(0.0, 0.0, z0 / 304.8)
                    rebar = re_engine.create_helix(self.doc, host, bar_type, shape, centre,
                                                   circle['radius_mm'], height, zone['spacing_mm'])
                    if rebar is None:
                        raise ValueError(u'the spiral shape would not take r / Height / Pitch')
                    made.append(rebar)
                t.Commit()
        except Exception as e:
            errors.append(u'Column {}: helical links — {}; circular links used instead.'.format(
                get_id_value(host.Id), e))
            return False
        for rebar in made:
            self._stamp_layer(rebar, u'stirrup')
            created_rebars.append(rebar)
            link_rebars.append(rebar)
        if len(made) > 1:
            errors.append(u'Column {}: helical links in {} pieces of up to 12 m of bar, lapped one turn '
                          u'(SMDSC MC6).'.format(get_id_value(host.Id), len(made)))
        return True

    def _crank_knuckle_links(self, host, reinforcement, bar_type_link, wrapper, errors, created_rebars):
        """IStructE SMDSC MC2: one more link at the knuckle of each crank, where the bars push outwards."""
        rect = [s for s in reinforcement.get('stirrup_sets', []) if not s.get('circle')]
        knuckles = reinforcement.get('crank_knuckles_ft') or []
        if not rect or not knuckles:
            return
        template = rect[0]
        z0 = template['curves'][0].GetEndPoint(0).Z
        for z in knuckles:
            shift = DB.Transform.CreateTranslation(DB.XYZ(0.0, 0.0, z - z0))
            curves = [c.CreateTransformed(shift) for c in template['curves']]
            rebar = wrapper.create_rebar_set(
                host, curves, bar_type_link, template['spacing_mm'], 0.0, normal=template['normal'],
                style=DBS.RebarStyle.StirrupTie, transaction_name=u'NOSA — Create Crank Link',
                link_hook=re_engine.get_link_hook_type(self.doc))
            if rebar is None:
                errors.append(u'Column {}: link at the crank knuckle — {}'.format(
                    get_id_value(host.Id), wrapper.last_error))
                continue
            self._stamp_layer(rebar, u'crank_link')
            created_rebars.append(rebar)

    def _run_column_reinforcement(self, columns, values):
        """
        PHASE F1 — see _run_reinforcement's own docstring for why the
        TransactionGroup that used to wrap this loop moved up into
        rebar_batch.RebarBatch.run instead (Revit doesn't support a
        nested/concurrent TransactionGroup, and the outer one now also
        needs to cover the provenance-stamping pass). Geometry
        generation itself is unchanged.

        Returns:
            (created_rebars, summary) — see _run_reinforcement's own
            docstring for the same PHASE F1 return-shape change.
        """
        errors = []
        diameters = {values['bar_dia'], values['link_dia']}
        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []

        for host in columns:
            try:
                self._process_column(host, values, wrapper, bar_types, errors, created_rebars)
            except Exception as e:
                # DIAGNOSTIC HARDENING (2026-09-01) — a circular column
                # was reported creating ZERO rebar with NO error message
                # at all, which should be impossible if an exception is
                # what stopped it (this except already appends one).
                # Capture the full traceback so a genuine silent-failure
                # report always has an exact line to act on next time —
                # a bare `{}`.format(e) can render as an empty string
                # for some exception types, which would itself look like
                # "no error" even though this branch DID run.
                import traceback
                detail = u'{}'.format(e) or u'(empty exception message)'
                try:
                    detail = u'{}\n{}'.format(detail, traceback.format_exc())
                except Exception:
                    log_swallowed(_LOG, u'RebarAutomateWindow._run_column_reinforcement')
                errors.append(u'Column {}: {}'.format(get_id_value(host.Id), detail))

        return created_rebars, {'created': len(created_rebars), 'errors': errors}


_OWN = set(globals())
