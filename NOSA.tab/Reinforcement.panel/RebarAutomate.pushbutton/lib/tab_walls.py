# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Walls tab: straight and curved walls (T7.6, T7.9).
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


class WallsMixin(object):
    # ── Walls (Phase F7) ─────────────────────────────────────────────────

    def _read_wall_inputs(self):
        errors = []
        values = {}
        values['vert_dia'] = self._read_number(self.TxtWallVertDia.Text, u'Vertical diameter', errors)
        values['vert_spacing'] = self._read_number(
            self.TxtWallVertSpacing.Text, u'Vertical spacing', errors)
        values['horiz_dia'] = self._read_number(
            self.TxtWallHorizDia.Text, u'Horizontal diameter', errors)
        values['horiz_spacing'] = self._read_number(
            self.TxtWallHorizSpacing.Text, u'Horizontal spacing', errors)
        values['both_faces'] = self.ChkWallBothFaces.IsChecked == True
        values['stagger_laps'] = self.ChkWallStaggerLaps.IsChecked == True
        # BUG FIX (2026-09-01) — reported live: End/Top U-bars (and the
        # main mesh) always assumed vertical = outer layer, no way to
        # flip it. This selector controls both.
        values['vert_is_outer'] = self.ChkWallVertOuter.IsChecked == True
        values['retaining'] = self.ChkWallRetaining.IsChecked == True
        values['earth_interior'] = self.ChkWallEarthInterior.IsChecked == True
        values['include_ties'] = self.ChkWallTies.IsChecked == True
        if values['include_ties']:
            values['tie_dia'] = self._read_number(
                self.TxtWallTieDia.Text, u'Tie diameter', errors)
            values['tie_spacing'] = self._read_number(
                self.TxtWallTieSpacing.Text, u'Tie spacing', errors)
        values['include_end_ubars'] = self.ChkWallEndUBars.IsChecked == True
        if values['include_end_ubars']:
            values['ubar_dia'] = self._read_number(
                self.TxtWallUBarDia.Text, u'U-bar diameter', errors)
            values['ubar_spacing'] = self._read_number(
                self.TxtWallUBarSpacing.Text, u'U-bar spacing', errors)
        values['include_starter_bars'] = self.ChkWallStarters.IsChecked == True
        if values['include_starter_bars']:
            values['starter_length'] = self._read_splice(
                self.TxtWallStarterLength.Text, u'Starter length', errors)
        # PHASE F7.18 (2026-09-02, explicit request) — L-shaped starters
        # into whatever foundation (isolated/strip footing or floor/mat
        # slab) is detected below the wall, distinct from include_
        # starter_bars above (a plain straight extension, no foundation
        # detection or hook).
        values['foundation_starters'] = self.ChkWallFoundationStarters.IsChecked == True
        if values['foundation_starters']:
            values['foundation_anchor_mm'] = self._read_number(
                self.TxtWallFoundationAnchor.Text, u'Foundation starter anchor length', errors)
            values['foundation_splice_mm'] = self._read_splice(
                self.TxtWallFoundationSplice.Text, u'Foundation starter splice length', errors)
        values['stock_length'] = self._read_number(
            self.TxtWallStockLength.Text, u'Max stock length', errors)
        if values.get('stock_length') is not None and values['stock_length'] < 1000.0:
            errors.append(u'"Max stock length" must be at least 1000 mm.')
        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def WallTies_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallTies.IsEnabled = self.ChkWallTies.IsChecked == True
        self._update_wall_preview()

    def WallEndUBars_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallEndUBars.IsEnabled = self.ChkWallEndUBars.IsChecked == True
        self._update_wall_preview()

    def WallStarters_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallStarters.IsEnabled = self.ChkWallStarters.IsChecked == True
        self._update_wall_preview()

    def WallFoundationStarters_Click(self, sender, args):
        # PHASE F7.18 (2026-09-02) — no preview support yet, same
        # reasoning as ColFoundationStarters_Click.
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallFoundationStarters.IsEnabled = self.ChkWallFoundationStarters.IsChecked == True

    def WallPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_wall_preview()

    def RunWallReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_wall_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'walls', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_wall_result(self, walls, summary):
        lines = [
            u'{} wall(s) processed.'.format(len(walls)),
            u'{} Rebar element(s) created.'.format(summary.get('created', 0)),
        ]
        if summary.get('errors'):
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — same fix as _show_beam_result.
            lines.extend(summary['errors'])
        self.TxtWallResult.Text = u'\n'.join(lines)

    def _process_wall(self, host, values, wrapper, bar_types, errors, created_rebars):
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Exterior', self._standard_default_cover_mm(u'wall'))
        try:
            # T8.40, IStructE SMDSC 6.5: pitches within min(3t, 400), minimum steel, links over 2 %
            from nosa_utils import wall_rules
            vs, hs, wall_notes = wall_rules.review(
                host.Width * 304.8, values['vert_dia'], values['vert_spacing'], values['horiz_dia'],
                values['horiz_spacing'], values.get('both_faces', True), values.get('include_ties'),
                values.get('tie_spacing'), label=u'Wall {}'.format(get_id_value(host.Id)))
            errors.extend(wall_notes)
            if vs != values['vert_spacing'] or hs != values['horiz_spacing']:
                values = dict(values, vert_spacing=vs, horiz_spacing=hs)
        except Exception:
            log_swallowed(_LOG, u'wall SMDSC review')
        lap_mm = None
        # staggered laps: half the bars lapped at a section (alpha6 1.4); otherwise all (1.5)
        pct_lapped = wall_rebar.STAGGERED_PCT_LAPPED if values.get('stagger_laps') else 100.0
        try:
            lap_mm = standards.lap_length_mm(
                self._host_std(host), values['vert_dia'], False, pct_lapped, True)
        except Exception:
            lap_mm = max(40.0 * values['vert_dia'], 15.0 * values['vert_dia'], 300.0)
        # BUG FIX (2026-09-01) — horiz_dia's own lap, not vert_dia's
        # reused unchanged (see wall_rebar.build_wall_reinforcement's
        # own docstring note on horiz_lap_length_mm).
        horiz_lap_mm = None
        try:
            horiz_lap_mm = standards.lap_length_mm(
                self._host_std(host), values['horiz_dia'], False, pct_lapped, True)
        except Exception:
            horiz_lap_mm = max(40.0 * values['horiz_dia'], 15.0 * values['horiz_dia'], 300.0)

        earth_normal = None
        if values.get('retaining'):
            from nosa_utils import wall_rules
            try:
                length_mm = host.Location.Curve.Length * 304.8
                earth_normal = DB.XYZ(host.Orientation.X, host.Orientation.Y, 0.0).Normalize()
                if values.get('earth_interior'):
                    earth_normal = earth_normal.Negate()
            except Exception:
                length_mm = 0.0
            vs, hs, notes = wall_rules.retaining_review(
                length_mm, values['vert_spacing'], values['horiz_spacing'], cover_mm,
                label=u'Wall {}'.format(get_id_value(host.Id)))
            errors.extend(notes)
            values = dict(values, vert_spacing=vs, horiz_spacing=hs)
        reinforcement = wall_rebar.build_wall_reinforcement(
            self.doc, host,
            earth_normal=earth_normal,
            cover_mm=cover_mm,
            vert_dia_mm=values['vert_dia'],
            vert_spacing_mm=values['vert_spacing'],
            horiz_dia_mm=values['horiz_dia'],
            horiz_spacing_mm=values['horiz_spacing'],
            both_faces=values['both_faces'],
            include_ties=values.get('include_ties', False),
            tie_dia_mm=values.get('tie_dia'),
            tie_spacing_mm=values.get('tie_spacing', 400.0),
            include_end_ubars=values.get('include_end_ubars', False),
            ubar_dia_mm=values.get('ubar_dia'),
            ubar_spacing_mm=values.get('ubar_spacing'),
            include_top_ubars=values.get('include_end_ubars', False),
            include_starter_bars=values.get('include_starter_bars', False),
            starter_length_mm=self._splice_mm(values.get('starter_length'), values['vert_dia'],
                                              host, errors, u'Wall starter length'),
            stock_length_mm=values.get('stock_length', 12000.0),
            lap_length_mm=lap_mm,
            horiz_lap_length_mm=horiz_lap_mm,
            vert_is_outer=values.get('vert_is_outer', False),
            end_conditions=(values.get('_wall_joints') or {}).get(get_id_value(host.Id)),
            ubar_lap_length_mm=self._splice_mm(
                None, values.get('ubar_dia') or values['vert_dia'], host),
            anchorage_mm=self._anchorage_mm(host, values['vert_dia']),
            stagger_laps=values.get('stagger_laps', False))

        for w in reinforcement.get('warnings', []):
            errors.append(u'Wall {}: {}'.format(get_id_value(host.Id), w))

        def _create_curves(curves, bar_type, normal, label, style=None, layer=None,
                           location=None, host_id=None):
            if bar_type is None or not curves:
                return
            bar_host = host
            if host_id is not None:
                # MW2 corner bars stand in the concrete of the wall met, not this one
                from nosa_utils.revit_helpers import element_id_from_int
                bar_host = self.doc.GetElement(element_id_from_int(host_id)) or host
            rebar = wrapper.create_from_curves(
                bar_host, curves, bar_type, normal=normal, style=style,
                transaction_name=u'NOSA — Create {}'.format(label))
            if rebar is None:
                errors.append(u'Wall {}: {} — {}'.format(
                    get_id_value(host.Id), label, wrapper.last_error))
            else:
                self._stamp_layer(rebar, layer)
                self._stamp_location(rebar, location)
                created_rebars.append(rebar)

        bar_type_v = bar_types.get(values['vert_dia'])
        first_vertical = len(created_rebars)
        if bar_type_v is not None:
            for vs in reinforcement.get('vertical_sets', []):
                if vs.get('freeform_bars'):
                    # curved wall (T7.9): radial bars a Set cannot rotate into — one FreeForm per face
                    rebar = wrapper.create_freeform_group(
                        host, vs['freeform_bars'], bar_type_v,
                        transaction_name=u'NOSA — Create Wall Vertical Mesh')
                    if rebar is None:
                        errors.append(u'Wall {}: vertical — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'vertical')
                        self._stamp_location(rebar, vs.get('location'))
                        created_rebars.append(rebar)
                elif vs.get('count', 1) > 1 and vs.get('array_length_mm', 0) > 0:
                    rebar = wrapper.create_rebar_set(
                        host, vs['curves'], bar_type_v, vs['spacing_mm'],
                        vs['array_length_mm'], normal=vs['normal'],
                        transaction_name=u'NOSA — Create Wall Vertical Mesh')
                    if rebar is None:
                        errors.append(u'Wall {}: vertical — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'vertical')
                        self._stamp_location(rebar, vs.get('location'))
                        created_rebars.append(rebar)
                else:
                    _create_curves(vs['curves'], bar_type_v, vs.get('normal'),
                                   vs.get('label', u'Wall Vertical'), layer=u'vertical',
                                   location=vs.get('location'), host_id=vs.get('host_id'))

        vertical_rebars = created_rebars[first_vertical:]

        bar_type_h = bar_types.get(values['horiz_dia'])
        if bar_type_h is not None:
            for hs in reinforcement.get('horizontal_sets', []):
                if hs.get('count', 1) > 1 and hs.get('array_length_mm', 0) > 0:
                    rebar = wrapper.create_rebar_set(
                        host, hs['curves'], bar_type_h, hs['spacing_mm'],
                        hs['array_length_mm'], normal=hs['normal'],
                        transaction_name=u'NOSA — Create Wall Horizontal Mesh')
                    if rebar is None:
                        errors.append(u'Wall {}: horizontal — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'horizontal')
                        self._stamp_location(rebar, hs.get('location'))
                        created_rebars.append(rebar)
                else:
                    _create_curves(hs['curves'], bar_type_h, hs.get('normal'),
                                   hs.get('label', u'Wall Horizontal'), layer=u'horizontal',
                                   location=hs.get('location'))

        tie_dia = values.get('tie_dia') or values['horiz_dia']
        bar_type_t = bar_types.get(tie_dia)
        if bar_type_t is not None:
            for tie in reinforcement.get('ties', []):
                _create_curves(tie['curves'], bar_type_t, tie.get('normal'),
                               tie.get('label', u'Wall Tie'),
                               style=DBS.RebarStyle.StirrupTie, layer=u'tie')

        # BUG FIX (2026-09-01) — End/Top U-bars now come back from
        # wall_rebar.py as {'sets':[...],'bars':[...]} (grouped by end/
        # position — every height/position along one end or the wall
        # head shares an identical shape), routed through the same
        # _create_grouped_bars helper footings/floors already use for
        # this exact open leg-back-leg U topology: Set first, FreeForm-
        # group fallback, individual bars only as the true last resort
        # — instead of always creating N loose individual elements.
        ubar_dia = values.get('ubar_dia') or values['vert_dia']
        bar_type_u = bar_types.get(ubar_dia)
        holes = reinforcement.get('opening_bars') or {}
        # IStructE SMDSC MW4: U-bars of the horizontal size and trimmer bars one size up
        hole_ubars = holes.get('ubars') or {'sets': [], 'bars': []}
        if hole_ubars['sets'] or hole_ubars['bars']:
            self._create_grouped_bars(
                wrapper, host, hole_ubars, bar_types.get(values['horiz_dia']), errors, created_rebars,
                u'Wall Hole U-Bar', layer=u'opening_ubar')
        for bar in holes.get('trimmers', []):
            _create_curves(bar['curves'], re_engine.get_bar_type_by_diameter(self.doc, bar['dia_mm']),
                           bar['normal'], u'Wall Trimmer Bar', layer=u'trimmer')
        corner = reinforcement.get('corner_ubars') or {'sets': [], 'bars': []}
        if corner['sets'] or corner['bars']:
            # IStructE SMDSC MW2: U-bars of the horizontal size and pitch round the corner
            self._create_grouped_bars(
                wrapper, host, corner, bar_types.get(values['horiz_dia']), errors, created_rebars,
                u'Wall Corner U-Bar', layer=u'corner_ubar')
        if bar_type_u is not None:
            self._create_grouped_bars(
                wrapper, host, reinforcement.get('end_ubars', {'sets': [], 'bars': []}),
                bar_type_u, errors, created_rebars, u'Wall End U-Bar', layer=u'end_ubar')
            self._create_grouped_bars(
                wrapper, host, reinforcement.get('top_ubars', {'sets': [], 'bars': []}),
                bar_type_u, errors, created_rebars, u'Wall Top U-Bar', layer=u'top_ubar')

        # PHASE F7.18 (2026-09-02, explicit request — "Starter bars con
        # forma de L en columnas y muros... unidas a la cimentación") —
        # one starter per vertical-bar position along the wall's own
        # length, reaching down into whatever foundation is detected
        # below it.
        if values.get('foundation_starters') and bar_type_v is not None:
            points = re_engine.unique_plan_points(
                [p for r in vertical_rebars for p in re_engine.rebar_bar_plan_points(r)])
            starters = wall_rebar.build_wall_foundation_starters(
                self.doc, host, points, values['vert_dia'], values['vert_dia'],
                values['foundation_anchor_mm'],
                self._foundation_starter_mm(values['foundation_splice_mm'], values['vert_dia'], host, errors,
                                            min_kicker_mm=150.0 if values.get('retaining') else 0.0),
                foundation_cover_mm=cover_mm)
            hook_90 = re_engine.get_hook_type_by_angle(self.doc, 90.0)
            if hook_90 is None:
                errors.append(u'Wall {}: foundation starters — no 90° RebarHookType '
                              u'found in this project; created WITHOUT hooks (not '
                              u'normative anchorage).'.format(get_id_value(host.Id)))
            self._create_foundation_starter_bars(
                wrapper, host, starters, bar_type_v, hook_90, u'Wall',
                errors, created_rebars)

    def _wall_joints(self, walls):
        """IStructE SMDSC MW2: how each end of the selected straight walls meets the others."""
        import wall_joints
        plan = []
        for host in walls:
            try:
                line = host.Location.Curve
                if not isinstance(line, DB.Line):
                    continue
                a, b = line.GetEndPoint(0), line.GetEndPoint(1)
                plan.append({'id': get_id_value(host.Id), 'p0': (a.X * 304.8, a.Y * 304.8),
                             'p1': (b.X * 304.8, b.Y * 304.8), 'thickness_mm': host.Width * 304.8})
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._wall_joints')
        return wall_joints.classify(plan)

    def _run_wall_reinforcement(self, walls, values):
        errors = []
        diameters = {values['vert_dia'], values['horiz_dia']}
        if values.get('include_ties'):
            diameters.add(values.get('tie_dia') or values['horiz_dia'])
        if values.get('include_end_ubars'):
            diameters.add(values.get('ubar_dia') or values['vert_dia'])
        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []
        values = dict(values, _wall_joints=self._wall_joints(walls))
        for host in walls:
            try:
                self._process_wall(host, values, wrapper, bar_types, errors, created_rebars)
            except Exception as e:
                errors.append(u'Wall {}: {}'.format(get_id_value(host.Id), e))
        return created_rebars, {'created': len(created_rebars), 'errors': errors}


_OWN = set(globals())
