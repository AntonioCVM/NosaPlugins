# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Stairs tab (T7.8).
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


class StairsMixin(object):
    # ── Stairs (T7.8) ──────────────────────────────────────────────────────

    _STAIR_LOCATIONS = {u'Stair Flight Bottom': u'B1', u'Stair Flight Top': u'T1',
                        u'Stair Upper Knee': u'B1', u'Stair Lower Knee': u'T1',
                        u'Stair Flight Distribution Bottom': u'B2',
                        u'Stair Flight Distribution Top': u'T2',
                        u'Stair Landing Transverse Top': u'T2', u'Stair Landing Transverse Bottom': u'B2',
                        u'Stair Landing Top': u'T1', u'Stair Landing Bottom': u'B1',
                        u'Stair Starter Bottom': u'B1', u'Stair Starter Top': u'T1'}

    def _read_stair_inputs(self):
        errors = []
        values = {
            'main_dia': self._read_number(self.TxtStairMainDia.Text, u'Bottom bar diameter', errors),
            'main_spacing': self._read_number(self.TxtStairMainSpacing.Text, u'Bottom bar spacing', errors),
            'top_dia': self._read_number(self.TxtStairTopDia.Text, u'Top bar diameter', errors),
            'top_spacing': self._read_number(self.TxtStairTopSpacing.Text, u'Top bar spacing', errors),
            'dist_dia': self._read_number(self.TxtStairDistDia.Text, u'Distribution bar diameter', errors),
            'dist_spacing': self._read_number(self.TxtStairDistSpacing.Text, u'Distribution bar spacing', errors),
            'slab_anchor': self.ChkStairSlabAnchor.IsChecked == True,
            'starters': self.ChkStairStarters.IsChecked == True,
            'starter_mode': 'post' if self.CboStairStarterType.SelectedIndex == 1 else 'cast',
            'landing_ubars': self.ChkStairLandingUBars.IsChecked == True,
            'curtail_top': self.ChkStairCurtailTop.IsChecked == True,
            'no_finish': self.ChkStairNoFinish.IsChecked == True,
        }
        if values['starters']:
            values['starter_dia'] = self._read_number(self.TxtStairStarterDia.Text, u'Starter diameter', errors)
            values['starter_lap'] = self._read_splice(self.TxtStairStarterLap.Text, u'Starter lap length', errors)
            values['starter_embed'] = self._read_splice(self.TxtStairStarterEmbed.Text,
                                                        u'Drilled embedment', errors)
        if values['landing_ubars']:
            values['ubar_dia'] = self._read_number(self.TxtStairUBarDia.Text, u'U-bar diameter', errors)
        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def RunStairReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_stair_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'stairs', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def StairPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_stair_preview()

    def _selected_stairs(self):
        stairs = []
        for eid in self.uidoc.Selection.GetElementIds():
            elem = self.doc.GetElement(eid)
            if elem is not None and elem.Category is not None and \
                    get_id_value(elem.Category.Id) == _cat_id('OST_Stairs') and \
                    stair_host.is_cast_in_place(elem):
                stairs.append(elem)
        return stairs

    def _update_stair_preview(self):
        """Longitudinal section of the selected stair's first flight, else a typical flight."""
        try:
            main_dia = float(self.TxtStairMainDia.Text)
            main_spacing = float(self.TxtStairMainSpacing.Text)
            top_dia = float(self.TxtStairTopDia.Text)
            top_spacing = float(self.TxtStairTopSpacing.Text)
            dist_dia = float(self.TxtStairDistDia.Text)
            dist_spacing = float(self.TxtStairDistSpacing.Text)
        except (TypeError, ValueError, AttributeError):
            return
        if min(main_dia, main_spacing, top_dia, top_spacing, dist_dia, dist_spacing) <= 0:
            return
        run, cover, note = None, 40.0, u'Typical flight — select a cast-in-place stair to see its own.'
        try:
            selected = self._selected_stairs()
            if selected:
                data = stair_host.read_stairs(self.doc, selected[0])
                if data['runs']:
                    run = data['runs'][0]
                    cover = stair_host.host_cover_mm(selected[0], cover)
                    note = u'First flight of stair {}.'.format(get_id_value(selected[0].Id))
        except Exception:
            log_swallowed(_LOG, u'_update_stair_preview')
        if run is None:
            run = preview_shapes.typical_stair_flight()
        ubar_dia = starter_dia = None
        if self.ChkStairLandingUBars.IsChecked == True:
            ubar_dia = self._preview_number(self.TxtStairUBarDia, 10.0)
        if self.ChkStairStarters.IsChecked == True:
            starter_dia = self._preview_number(self.TxtStairStarterDia, main_dia)
        a_mm = None
        if self.ChkStairCurtailTop.IsChecked == True:
            lo = run['lower']['s_far'] if run['lower']['kind'] == 'landing' else 0.0
            hi = run['upper']['s_far'] if run['upper']['kind'] == 'landing' else run['length']
            a_mm = stair_rebar.a_length_mm(abs(hi - lo), self._anchorage_mm(None, top_dia))
        try:
            shapes = preview_shapes.stair_section_shapes(
                run, cover, main_dia, main_spacing, top_dia, top_spacing, dist_dia, dist_spacing,
                self._anchorage_mm(None, main_dia),
                slab_anchor=self.ChkStairSlabAnchor.IsChecked == True, ubar_dia=ubar_dia,
                starter_dia=starter_dia,
                starter_mode='post' if self.CboStairStarterType.SelectedIndex == 1 else 'cast',
                starter_lap=self._splice_mm(None, starter_dia or main_dia, None), a_mm=a_mm)
        except Exception:
            log_swallowed(_LOG, u'_update_stair_preview shapes')
            return
        self._draw_shapes(self.StairSectionCanvas, shapes)
        self.TxtStairPreviewNote.Text = note

    def _show_stair_result(self, stairs, summary):
        lines = [u'{} stair(s) processed.'.format(len(stairs)),
                 u'{} Rebar element(s) created (sets count as one each).'.format(summary.get('created', 0))]
        if summary.get('errors'):
            lines += [u'', u'{} issue(s):'.format(len(summary['errors']))] + list(summary['errors'])
        self.TxtStairResult.Text = u'\n'.join(lines)

    def _smdsc_stair_review(self, host, run, cover, values, errors):
        """T8.42 — IStructE SMDSC 6.8 on this flight's waist: pitches over the maxima come down, the rest is reported."""
        try:
            import math
            from nosa_utils import mesh_rules, standards
            throat = (run['pitch_z0'] - run['soffit_z0']) * math.cos(math.atan(run['slope']))
            try:
                fck = standards.concrete_fck_mpa(self._host_std(host))
            except Exception:
                fck = 30.0
            main, dist, top, notes = mesh_rules.stair_review(
                throat, cover, values['main_dia'], values['main_spacing'], values['dist_dia'],
                values['dist_spacing'], fck, top_dia=values.get('top_dia'), top_spacing=values.get('top_spacing'),
                label=u'Stair {}'.format(get_id_value(host.Id)))
            errors.extend(n for n in notes if n not in errors)
            return dict(values, main_spacing=main, dist_spacing=dist,
                        top_spacing=top if top is not None else values.get('top_spacing'))
        except Exception:
            log_swallowed(_LOG, u'stair SMDSC review')
            return values

    def _run_stair_reinforcement(self, stairs, values):
        errors = []
        bar_types = {}
        if values['landing_ubars']:
            u_dia = stair_rebar.landing_ubar_dia_mm(values['ubar_dia'], values['top_spacing'],
                                                    values['main_dia'], values['main_spacing'])
            if u_dia > values['ubar_dia']:
                errors.append(u'Landing U-bars H{:g} raised to H{:g}: SMDSC MST1 asks for 50 % of the area '
                              u'of the main bottom bars (H{:g} at {:g}).'.format(
                                  values['ubar_dia'], u_dia, values['main_dia'], values['main_spacing']))
                values = dict(values, ubar_dia=u_dia)
        diameters = {values['main_dia'], values['top_dia'], values['dist_dia']}
        if values['starters']:
            diameters.add(values['starter_dia'])
        if values['landing_ubars']:
            diameters.add(values['ubar_dia'])
        for dia in diameters:
            bar_types[dia] = re_engine.get_bar_type_by_diameter(self.doc, dia)
            if bar_types[dia] is None:
                errors.append(u'No RebarBarType found for {:g} mm — those bars are skipped.'.format(dia))
        wrapper = re_engine.RebarWrapper(self.doc)
        created = []
        for host in stairs:
            hid = get_id_value(host.Id)
            try:
                data = stair_host.read_stairs(self.doc, host)
            except Exception as e:
                errors.append(u'Stair {}: could not read its geometry — {}'.format(hid, e))
                continue
            errors.extend(u'Stair {}: {}'.format(hid, w) for w in data['warnings'])
            cover = stair_host.host_cover_mm(host, self._standard_default_cover_mm(u'slab'))
            anchorage = self._anchorage_mm(host, values['main_dia'])
            if values.get('no_finish'):
                data['runs'], data['landings'] = stair_rebar.lower_tops(
                    data['runs'], data['landings'], stair_rebar.NO_FINISH_TOP_COVER_MM)
                errors.append(u'Stair {}: no finish — top cover {:.0f} + {:.0f} mm (SMDSC 6.8).'.format(
                    hid, cover, stair_rebar.NO_FINISH_TOP_COVER_MM))
            if values['landing_ubars']:
                errors.extend(u'Stair {}: {}'.format(hid, note) for note in stair_host.apply_landing_ubars(
                    data, values['ubar_dia'], cover, values['main_dia']))
            jobs = []
            for run in data['runs']:
                run_values = self._smdsc_stair_review(host, run, cover, values, errors)
                a_mm = None
                if values.get('curtail_top'):
                    lo = run['lower']['s_far'] if run['lower']['kind'] == 'landing' else 0.0
                    hi = run['upper']['s_far'] if run['upper']['kind'] == 'landing' else run['length']
                    a_mm = stair_rebar.a_length_mm(
                        abs(hi - lo), self._anchorage_mm(host, run_values['top_dia']))
                starters, starter_host = self._stair_starters(host, run, cover, anchorage, values, errors)
                for bar_set in stair_rebar.build_flight(
                        run, cover, run_values['main_dia'], run_values['main_spacing'], run_values['dist_dia'],
                        run_values['dist_spacing'], anchorage, top_dia=run_values['top_dia'],
                        top_spacing=run_values['top_spacing'], slab_anchor=values['slab_anchor'],
                        starters=starters, a_mm=a_mm):
                    jobs.append((run['frame'], bar_set,
                                 starter_host if bar_set['layer'] == u'stair_starter' else host))
                if run['upper']['kind'] == 'floor' and values['slab_anchor']:
                    errors.append(u'Stair {}: a flight ends without a landing — its bars are lapped '
                                  u'{:.0f} mm into the floor slab beyond.'.format(hid, anchorage))
            for landing in data['landings']:
                for bar_set in stair_rebar.build_landing(
                        landing, cover, values['main_dia'], values['dist_dia'], values['dist_spacing'],
                        values['main_spacing'], landing['strips'], landing['parallel'],
                        u_dia=values.get('ubar_dia') if values['landing_ubars'] else None,
                        u_edges=landing.get('u_edges', ()), top_dia=values['top_dia'],
                        top_spacing=values['top_spacing']):
                    jobs.append((landing['frame'], bar_set, host))
            for frame, bar_set, bar_host in jobs:
                bar_type = bar_types.get(bar_set['dia'])
                if bar_type is None:
                    continue
                rebar = stair_host.create_set(wrapper, bar_host, frame, bar_set, bar_type)
                if rebar is None:
                    errors.append(u'Stair {}: {} — {}'.format(hid, bar_set['label'], wrapper.last_error))
                    continue
                self._stamp_layer(rebar, bar_set['layer'])
                self._stamp_location(rebar, self._STAIR_LOCATIONS.get(bar_set['label']))
                created.append(rebar)
        return created, {'created': len(created), 'errors': errors}

    def _stair_starters(self, host, run, cover, anchorage, values, errors):
        """(starters for stair_rebar.build_flight, host of the starter bars) — (None, None) if none."""
        if not values['starters'] or run['lower']['kind'] != 'floor':
            return None, None
        hid = get_id_value(host.Id)
        dia = values['starter_dia']
        embed = values.get('starter_embed')
        if values['starter_mode'] == 'post' and embed is None:
            embed = max(self._anchorage_mm(host, dia), 10.0 * dia, 100.0)
        info = stair_host.starter_support(self.doc, re_engine, run, cover, dia,
                                          values['starter_mode'], embed)
        if info is None:
            errors.append(u'Stair {}: no foundation, slab or beam found under a flight base — '
                          u'its cast-in starters were skipped (choose post-installed for an '
                          u'existing support).'.format(hid))
            return None, None
        lap = self._splice_mm(values.get('starter_lap'), dia, host, errors, u'Starter lap')
        anchor = self._anchorage_mm(info['host'] or host, dia)
        if info['source'] != 'post' and info['embedded_mm'] < anchor:
            errors.append(u'Stair {}: the support is only {:.0f} mm deep below the base — less than '
                          u'the {:.0f} mm anchorage of the starters (the foot helps; check it).'.format(
                              hid, info['embedded_mm'], anchor))
        if info['source'] == 'post':
            errors.append(u'Stair {}: post-installed starters bonded {:.0f} mm into the support — '
                          u'confirm the resin system and edge distances.'.format(hid, embed))
        return {'dia': dia, 'lap': lap, 'support': info['support']}, info['host'] or host


_OWN = set(globals())
