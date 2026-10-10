# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Detailing & Tools tab: batches, partitions, detailing, views, schedules, exports.
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


class ToolsMixin(object):
    # ── Detailing & Tools — dashboard (Phase 1 placeholders) ────────────────
    # Every handler below is wired (not disabled) so the button gives real
    # feedback when clicked, but does nothing yet — each one's actual logic
    # is a Phase 5 (Modify/Detailing Tools) or later deliverable. Kept as
    # one line per handler here deliberately: there is no shared behaviour
    # to factor out yet, and pre-building an abstraction for behaviour that
    # doesn't exist yet would be exactly the speculative generality this
    # project avoids elsewhere.

    # ── Batch Manager (Phase F1) ─────────────────────────────────────────

    def _refresh_batch_list(self):
        """Repopulates LstBatches from rebar_batch.RebarBatch.list_batches
        — one formatted row per distinct batch_id, storing the RAW
        batch_id string as each ListBoxItem's own Tag so Select/Delete
        don't need to re-parse the displayed text."""
        self.LstBatches.Items.Clear()
        try:
            batches = rebar_batch.RebarBatch.list_batches(self.doc)
        except Exception as e:
            forms.alert(u'Could not list batches:\n{}'.format(e))
            return
        if not batches:
            item = SWC.ListBoxItem()
            item.Content = u'(no NOSA RebarAutomate batches found in this document)'
            item.IsEnabled = False
            self.LstBatches.Items.Add(item)
            return
        for b in batches:
            item = SWC.ListBoxItem()
            item.Content = u'{}   —   {} bar(s)   —   {}'.format(
                b['batch_id'], b['count'], b.get('standard_code') or u'?')
            item.Tag = b['batch_id']
            self.LstBatches.Items.Add(item)

    def _selected_batch_id(self):
        selected = self.LstBatches.SelectedItem
        if selected is None:
            return None
        return getattr(selected, 'Tag', None)

    def _same_document(self, uiapp):
        """The window stays bound to the model it was opened on; refuse to act on another."""
        uidoc = uiapp.ActiveUIDocument
        try:
            if self.doc.IsValidObject and uidoc is not None and uidoc.Document.Equals(self.doc):
                return True
            title = self.doc.Title if self.doc.IsValidObject else u'a closed model'
        except Exception:
            title = u'a closed model'
        forms.alert(u'RebarAutomate is open for "{}". Switch back to that model, or close '
                    u'and reopen RebarAutomate for the current one.'.format(title),
                    title=u'RebarAutomate')
        return False

    def _in_revit(self, action):
        """Queue a model change for Revit's next API call (the window is modeless)."""
        self._model_action_handler.pending = action
        self._model_action_event.Raise()

    def RenumberPartition_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._renumber_partition)

    def _renumber_partition(self):
        partition = self._partition()
        confirmed = forms.alert(
            u'Renumber every non-finalized NOSA bar of partition "{}" with BS 8666 marks '
            u'(01, 02 ...)? Bar tags and schedules will show the new marks.'.format(
                partition or u'(none)'),
            title=u'RebarAutomate — Renumber Partition', yes=True, no=True)
        if not confirmed:
            return
        ctx = {'standard': self.ra_standard, 'mark_prefix': partition}
        with nosa_tx.revit_transaction(u'NOSA — Renumber Partition'):
            summary = rebar_marking.renumber_partition(self.doc, ctx)
        forms.alert(u'{} bar mark(s) given to {} Rebar element(s); {} varying set(s).'.format(
            summary.get('total_positions', 0), summary.get('total_bars', 0),
            summary.get('varying_sets', 0)), title=u'RebarAutomate — Renumber Partition')

    def Partitions_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._open_partitions)

    def _open_partitions(self):
        partitions_window = load_module('partitions_window', os.path.join(_HERE, 'partitions_window.py'))
        dialog = partitions_window.PartitionsWindow(self.doc, {'standard': self.ra_standard})
        if not dialog.rows:
            forms.alert(u'No host carries RebarAutomate bars yet.', title=u'RebarAutomate — Partitions')
            return
        dialog.ShowDialog()
        summary = dialog.summary
        if not summary:
            return
        message = (u'{} partition(s) written; {} bar mark(s) given. {} Rebar element(s) of identical '
                   u'hosts set to Show In Schedule = No.'.format(
                       summary['partitions'], summary['positions'], summary['hidden']))
        if summary['finalized_skipped']:
            message += u'\n{} finalized Rebar element(s) left unchanged.'.format(summary['finalized_skipped'])
        message += (u'\n\nThe template BBS schedule needs the filter '
                    u'"NOSA_Rebar_Show_In_Schedule equals Yes" to leave the copies out.')
        forms.alert(message, title=u'RebarAutomate — Partitions')

    def RefreshBatches_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._refresh_batch_list()

    def SelectBatch_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._select_batch)

    def _select_batch(self):
        batch_id = self._selected_batch_id()
        if not batch_id:
            forms.alert(u'Select a batch from the list first.')
            return
        try:
            ids = rebar_batch.RebarBatch.select_batch(self.doc, batch_id)
        except Exception as e:
            forms.alert(u'Could not select batch {}:\n{}'.format(batch_id, e))
            return
        if not ids:
            forms.alert(u'No elements found for batch {} — it may already be deleted.'.format(
                batch_id))
            return
        self.uidoc.Selection.SetElementIds(List[DB.ElementId](ids))
        forms.alert(u'{} element(s) from batch {} selected in the model.'.format(
            len(ids), batch_id))

    def DeleteBatch_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._delete_batch)

    def _delete_batch(self):
        batch_id = self._selected_batch_id()
        if not batch_id:
            forms.alert(u'Select a batch from the list first.')
            return
        confirmed = forms.alert(
            u'Delete every element from batch {}? Elements marked '
            u'"Finalized" are protected and will be skipped.'.format(batch_id),
            title=u'NOSA RebarAutomate — Delete Batch', yes=True, no=True)
        if not confirmed:
            return
        try:
            result = rebar_batch.RebarBatch.delete_batch(self.doc, batch_id)
        except Exception as e:
            forms.alert(u'Delete batch failed:\n{}'.format(e))
            return
        lines = [
            u'{} element(s) deleted.'.format(len(result['deleted'])),
            u'{} element(s) protected (Finalized) and kept.'.format(len(result['protected'])),
        ]
        if result['errors']:
            lines.append(u'{} error(s):'.format(len(result['errors'])))
            lines.extend(result['errors'][:10])
        forms.alert(u'\n'.join(lines))
        self._refresh_batch_list()

    def GenerateSchedule_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Rebar schedule generation is not implemented yet — planned for Phase 5.')

    def Split_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._split_selected)

    def _split_selected(self):
        """T7.7 — cut the selected straight bars to the stock length, laps staggered (T7.6)."""
        errors = []
        stock_mm = self._read_number(self.TxtModifyStockLength.Text, u'Stock length', errors)
        if errors or stock_mm is None or stock_mm < 1000.0:
            forms.alert(u'Enter a stock length of at least 1000 mm.', title=u'RebarAutomate — Split')
            return
        rebars = self._selected_rebars()
        if not rebars:
            forms.alert(u'Select the bars to split in the model first.', title=u'RebarAutomate — Split')
            return
        if not self._ensure_shared_params():
            return
        skipped = []
        jobs = []
        for rebar in rebars:
            rid = get_id_value(rebar.Id)
            if rebar_partitions.is_finalized(rebar):
                skipped.append(u'{}: Finalized'.format(rid))
                continue
            geometry = rebar_modify.straight_set_geometry(rebar)
            if geometry is None:
                skipped.append(u'{}: not a set of straight bars'.format(rid))
                continue
            if geometry['line'].Length * 304.8 <= stock_mm + 1.0:
                skipped.append(u'{}: already within the stock length'.format(rid))
                continue
            host = self.doc.GetElement(rebar.GetHostId())
            dia = rebar_modify.bar_diameter_mm(self.doc, rebar)
            try:
                lap = standards.lap_length_mm(self._host_std(host), dia, False,
                                              wall_rebar.STAGGERED_PCT_LAPPED, True)
            except Exception:
                lap = max(40.0 * dia, 300.0)
            if lap >= stock_mm:
                skipped.append(u'{}: lap {:.0f} mm is not shorter than the stock length'.format(rid, lap))
                continue
            jobs.append((rebar, host, geometry, lap))
        if not jobs:
            forms.alert(u'Nothing to split.\n' + u'\n'.join(skipped[:15]), title=u'RebarAutomate — Split')
            return

        def _generate():
            wrapper = re_engine.RebarWrapper(self.doc)
            created, errs = [], []
            for rebar, host, geometry, lap in jobs:
                bar_type = self.doc.GetElement(rebar.GetTypeId())
                layer = shared_params.read(rebar, u'NOSA_Rebar_Layer', u'') or None
                comment = rebar.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                location = (comment.AsString() if comment else None) or None
                new = []
                for spec in rebar_modify.split_specs(geometry, stock_mm, lap):
                    if spec['count'] > 1:
                        bar = wrapper.create_rebar_set(
                            host, spec['curves'], bar_type, spec['spacing_mm'], spec['array_length_mm'],
                            normal=spec['normal'], transaction_name=u'NOSA — Split Rebar')
                    else:
                        bar = wrapper.create_from_curves(host, spec['curves'], bar_type, normal=spec['normal'],
                                                         transaction_name=u'NOSA — Split Rebar')
                    if bar is None:
                        errs.append(u'{}: {}'.format(get_id_value(rebar.Id), wrapper.last_error))
                        break
                    self._stamp_layer(bar, layer)
                    self._stamp_location(bar, location)
                    new.append(bar)
                else:
                    with nosa_tx.revit_transaction(u'NOSA — Split Rebar (remove original)'):
                        self.doc.Delete(rebar.Id)
                    created.extend(new)
                    continue
                if new:
                    with nosa_tx.revit_transaction(u'NOSA — Split Rebar (undo partial)'):
                        for bar in new:
                            self.doc.Delete(bar.Id)
            return created, {'created': len(created), 'errors': errs, 'split': len(jobs) - len(errs)}

        batch = rebar_batch.RebarBatch(
            self.doc, standard=self.ra_standard, generator_version=self.ra_generator_version,
            standard_code=self.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE),
            layers=self._pending_layers, locations=self._pending_locations, mark_prefix=self._partition())
        result = batch.run(_generate)
        lines = [u'{} bar set(s) split into {} set(s).'.format(result.summary.get('split', 0), len(result.created))]
        if skipped:
            lines.append(u'Skipped: ' + u'; '.join(skipped[:10]))
        lines.extend(result.errors[:10])
        self.TxtDetailingStatus.Text = u'\n'.join(lines)
        forms.alert(u'\n'.join(lines), title=u'RebarAutomate — Split')

    def DeleteHostRebars_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._delete_host_rebars)

    def _delete_host_rebars(self):
        """T7.7 — delete the free bars of the selected hosts; Finalized bars stay."""
        hosts = []
        for eid in self.uidoc.Selection.GetElementIds():
            elem = self.doc.GetElement(eid)
            if elem is not None and _is_valid_rebar_host(elem) and not isinstance(elem, DBS.Rebar):
                hosts.append(elem)
        if not hosts:
            forms.alert(u'Select the hosts (columns, beams, walls, floors, foundations, stairs) first.',
                        title=u'RebarAutomate — Delete Host Rebars')
            return
        rebars = rebar_modify.host_rebars(self.doc, hosts)
        kept = [r for r in rebars if rebar_partitions.is_finalized(r)]
        doomed = [r for r in rebars if r not in kept]
        if not doomed:
            forms.alert(u'The selected hosts have no bars to delete ({} Finalized kept).'.format(len(kept)),
                        title=u'RebarAutomate — Delete Host Rebars')
            return
        if not forms.alert(u'Delete {} bar element(s) from {} host(s)? {} Finalized bar(s) are kept.'.format(
                len(doomed), len(hosts), len(kept)), title=u'RebarAutomate — Delete Host Rebars',
                yes=True, no=True):
            return
        with nosa_tx.revit_transaction(u'NOSA — Delete Host Rebars'):
            self.doc.Delete(List[DB.ElementId]([r.Id for r in doomed]))
        msg = u'{} bar element(s) deleted from {} host(s); {} Finalized kept.'.format(len(doomed), len(hosts),
                                                                                     len(kept))
        self.TxtDetailingStatus.Text = msg
        self._refresh_batch_list()

    def ToggleSolids_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._toggle_solids)

    def _toggle_solids(self):
        """T7.7 — selected bars (or every bar in the active 3D view) as solids, or back to wires."""
        view = self.doc.ActiveView
        if not isinstance(view, DB.View3D):
            forms.alert(u'Open a 3D view first: Revit only shows bars as solids in 3D views.',
                        title=u'RebarAutomate — Rebar as Solids')
            return
        rebars = self._selected_rebars() or rebar_modify.view_rebars(self.doc, view)
        if not rebars:
            forms.alert(u'No bars in this view.', title=u'RebarAutomate — Rebar as Solids')
            return
        with nosa_tx.revit_transaction(u'NOSA — Rebar as Solids'):
            shown = rebar_modify.toggle_solids(view, rebars)
        self.TxtDetailingStatus.Text = u'{} bar element(s) shown as {} in "{}".'.format(
            len(rebars), u'solids' if shown else u'wires', element_name(view))

    # ── Detailing (Phase F6) ─────────────────────────────────────────────

    def _populate_detailing_combos(self):
        """Fill CmbRebarTagType / CmbMraType from families loaded in the project."""
        # Rebar tag types
        self.CmbRebarTagType.Items.Clear()
        tag_types = []
        try:
            tag_types = rebar_detailing.list_rebar_tag_types(self.doc)
        except Exception:
            tag_types = []
        if not tag_types:
            item = SWC.ComboBoxItem()
            item.Content = u'(no rebar tag types loaded)'
            item.IsEnabled = False
            self.CmbRebarTagType.Items.Add(item)
        else:
            # IronPython: do NOT use lambda t: t.Name — free-var lookup
            # raises NameError: Name.
            for tt in sorted(tag_types, key=element_name):
                item = SWC.ComboBoxItem()
                item.Content = element_name(tt)
                item.Tag = tt.Id
                self.CmbRebarTagType.Items.Add(item)
            self.CmbRebarTagType.SelectedIndex = 0

        # Multi-rebar annotation types
        self.CmbMraType.Items.Clear()
        mra_types = []
        try:
            mra_types = rebar_detailing.list_mra_types(self.doc)
        except Exception:
            mra_types = []
        if not mra_types:
            item = SWC.ComboBoxItem()
            item.Content = u'(no multi-rebar annotation types loaded)'
            item.IsEnabled = False
            self.CmbMraType.Items.Add(item)
        else:
            for mt in sorted(mra_types, key=element_name):
                item = SWC.ComboBoxItem()
                item.Content = element_name(mt)
                item.Tag = mt.Id
                self.CmbMraType.Items.Add(item)
            self.CmbMraType.SelectedIndex = 0

    def _refresh_content_status(self):
        """Warn on the Detailing card when a NOSA family is missing or out of date (T4.3)."""
        try:
            self._content_report = rebar_content.check(self.doc)
            lines = rebar_content.status_lines(self._content_report)
        except Exception as e:
            self._content_report = []
            lines = [u'Could not read data/content_manifest.json: {}'.format(e)]
        self.TxtContentStatus.Text = u'\n'.join(lines)

    def LoadContent_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._load_content)

    def _load_content(self):
        report = rebar_content.check(self.doc)
        with nosa_tx.revit_transaction(u'NOSA — Load NOSA Families'):
            loaded, skipped = rebar_content.load_packaged(self.doc, report)
        self._populate_detailing_combos()
        self._refresh_content_status()
        lines = [u'{} family(ies) loaded: {}'.format(len(loaded), u', '.join(loaded) or u'none')]
        if skipped:
            lines.append(u'Not found in the extension content folder: {}'.format(u', '.join(skipped)))
        forms.alert(u'\n'.join(lines), title=u'RebarAutomate — NOSA Families')

    def _combo_selected_element_id(self, combo):
        selected = combo.SelectedItem
        if selected is None:
            return None
        return getattr(selected, 'Tag', None)

    def _selected_rebars(self):
        """Rebars currently selected in the model (OST_Rebar only)."""
        rebars = []
        try:
            for eid in self.uidoc.Selection.GetElementIds():
                elem = self.doc.GetElement(eid)
                if elem is None:
                    continue
                try:
                    if elem.Category and get_id_value(elem.Category.Id) == get_id_value(
                            DB.ElementId(DB.BuiltInCategory.OST_Rebar)):
                        rebars.append(elem)
                except Exception:
                    continue
        except Exception:
            log_swallowed(_LOG, u'RebarAutomateWindow._selected_rebars')
        return rebars

    def _selected_detail_hosts(self):
        """Footings / floors / columns currently selected (for detail sections)."""
        hosts = []
        allowed = set([_cat_id('OST_StructuralFoundation'), _cat_id('OST_Floors'), _cat_id('OST_StructuralColumns')])
        try:
            for eid in self.uidoc.Selection.GetElementIds():
                elem = self.doc.GetElement(eid)
                if elem is None or elem.Category is None:
                    continue
                try:
                    if get_id_value(elem.Category.Id) in allowed:
                        hosts.append(elem)
                except Exception:
                    continue
        except Exception:
            log_swallowed(_LOG, u'RebarAutomateWindow._selected_detail_hosts')
        return hosts

    def CreateViews_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._create_views)

    def _create_views(self):
        """T7.3 — the views, tags and sheets of every selected reinforced element."""
        hosts = []
        for eid in self.uidoc.Selection.GetElementIds():
            elem = self.doc.GetElement(eid)
            if rebar_views.host_kind(elem) and rebar_views.host_rebars(elem):
                hosts.append(elem)
        if not hosts:
            forms.alert(u'Select reinforced columns, beams, foundations, slabs, walls or stairs first.',
                        title=u'NOSA — Create Views')
            return
        beams = [h for h in hosts if rebar_views.host_kind(h) == 'beam']
        groups = [[h] for h in hosts if rebar_views.host_kind(h) != 'beam']
        groups += beam_rebar.group_beam_lines(beams) if beams else []
        existing = [s.SheetNumber for s in DB.FilteredElementCollector(self.doc).OfClass(DB.ViewSheet)]
        numbers = view_plan.next_sheet_numbers(existing, 10 * len(groups) + 5)
        views = sheets = tags = 0
        errors = []
        self.SetLoading(True, u'Creating views…')
        try:
            for group in groups:
                report = rebar_views.build_element_views(
                    self.doc, group, re_engine, rebar_detailing, view_plan, numbers,
                    beam_rebar=beam_rebar, stair_host=stair_host,
                    place_on_sheets=self.ChkViewsSheets.IsChecked == True,
                    tag=self.ChkViewsTags.IsChecked == True)
                views += len(report['views'])
                sheets += len(report['sheets'])
                tags += report['tags']
                errors.extend(report['errors'])
        finally:
            self.SetLoading(False)
        msg = u'{} view(s), {} sheet(s) and {} tag(s) created for {} element(s).'.format(
            views, sheets, tags, len(groups))
        if errors:
            msg += u'\n\n{} issue(s):\n{}'.format(len(errors), u'\n'.join(errors[:10]))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Create Views')

    def AutoTag_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._auto_tag)

    def _auto_tag(self):
        rebars = self._selected_rebars()
        if not rebars:
            forms.alert(u'Select one or more rebar elements in the model first.',
                        title=u'NOSA — Auto Tag')
            return

        view = self.doc.ActiveView
        if view is None or getattr(view, 'IsTemplate', False):
            forms.alert(u'Switch to a model view (not a template) before tagging.',
                        title=u'NOSA — Auto Tag')
            return

        tag_type_id = rebar_detailing.tag_type_for_view(
            self.doc, view, self._combo_selected_element_id(self.CmbRebarTagType))
        try:
            with nosa_tx.revit_transaction(u'NOSA — Auto Tag Rebar'):
                tags, errors = rebar_detailing.create_rebar_tags_smart(
                    self.doc, view, rebars,
                    use_param_offsets=True,
                    tag_type_id=tag_type_id,
                    add_leader=False)
                moved = rebar_detailing.resolve_tag_overlaps(self.doc, view, tags)
        except Exception as e:
            forms.alert(u'Auto Tag failed:\n{}'.format(e), title=u'NOSA — Auto Tag')
            return

        msg = u'Created {} tag(s) for {} selected rebar(s); {} moved clear of other tags.'.format(
            len(tags), len(rebars), moved)
        if errors:
            msg += u'\n\n{} warning(s):\n{}'.format(
                len(errors), u'\n'.join(errors[:8]))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Auto Tag')

    def AutoMRA_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._auto_mra)

    def _auto_mra(self):
        rebars = self._selected_rebars()
        if len(rebars) < 1:
            forms.alert(
                u'Select one or more rebar elements (typically a parallel set) '
                u'in the model first.',
                title=u'NOSA — Auto MRA')
            return

        view = self.doc.ActiveView
        if view is None or getattr(view, 'IsTemplate', False):
            forms.alert(u'Switch to a model view (not a template) before creating an MRA.',
                        title=u'NOSA — Auto MRA')
            return

        mra_type_id = self._combo_selected_element_id(self.CmbMraType)
        mra_type = self.doc.GetElement(mra_type_id) if mra_type_id else None
        if mra_type is None:
            forms.alert(
                u'No Multi-Rebar Annotation type is available in this project.\n'
                u'Load a Multi-Rebar Annotation family first (Project Browser → '
                u'Families → Annotation Symbols → Multi-Rebar Annotations).',
                title=u'NOSA — Auto MRA')
            return

        try:
            with nosa_tx.revit_transaction(u'NOSA — Auto Multi-Rebar Annotation'):
                mra = rebar_detailing.create_multi_rebar_annotation(
                    self.doc, view, rebars, mra_type=mra_type, dim_offset_mm=300.0)
        except Exception as e:
            forms.alert(u'Auto MRA failed:\n{}'.format(e), title=u'NOSA — Auto MRA')
            return

        if mra is None:
            msg = (u'Could not create Multi-Rebar Annotation for {} selected bar(s).\n'
                   u'Check that they are the same category, roughly parallel, and '
                   u'visible in the active view.'.format(len(rebars)))
            self.TxtDetailingStatus.Text = msg
            forms.alert(msg, title=u'NOSA — Auto MRA')
            return

        msg = u'Multi-Rebar Annotation created for {} bar(s).'.format(len(rebars))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Auto MRA')

    def AutoSections_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._auto_sections)

    def _auto_sections(self):
        hosts = self._selected_detail_hosts()
        if not hosts:
            forms.alert(
                u'Select one or more footings, floors, or columns in the model first.',
                title=u'NOSA — Auto Sections')
            return

        created = 0
        errors = []
        try:
            with nosa_tx.revit_transaction(u'NOSA — Auto Detail Sections'):
                for host in hosts:
                    sections, host_errors = rebar_detailing.create_orthogonal_detail_sections(
                        self.doc, host)
                    created += len(sections)
                    for err in host_errors:
                        errors.append(u'{}: {}'.format(get_id_value(host.Id), err))
        except Exception as e:
            forms.alert(u'Auto Sections failed:\n{}'.format(e),
                        title=u'NOSA — Auto Sections')
            return

        msg = u'Created {} detail section(s) for {} host(s).'.format(created, len(hosts))
        if errors:
            msg += u'\n\n{} warning(s):\n{}'.format(
                len(errors), u'\n'.join(errors[:8]))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Auto Sections')


    def BarSchedules_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._create_bar_schedules)

    def _create_bar_schedules(self):
        """T8.33/T8.34 — A4 bar schedules per drawing (IStructE SMDSC 4.5.1)."""
        import bar_schedules
        try:
            bar_schedules.bind(self.doc)
        except Exception as e:
            forms.alert(u'The bar schedule sheet parameters could not be added:\n{}'.format(e),
                        title=u'NOSA — Bar Schedules')
            return
        with nosa_tx.revit_transaction(u'NOSA — A4 Bar Schedules'):
            report = bar_schedules.create(self.doc)
        if not report['schedules'] and not report['errors']:
            msg = (u'No bar has a drawing yet: run Create Views (with sheets) on the reinforced '
                   u'elements first, then create their schedules.')
        else:
            msg = u'{} bar schedule(s): {}.\n{} new A4 sheet(s) in the {} series.'.format(
                len(report['schedules']), u', '.join(report['schedules']),
                len(report['new_sheets']), bar_schedules.SHEET_SERIES)
        if report['errors']:
            msg += u'\n\n{} issue(s):\n{}'.format(len(report['errors']), u'\n'.join(report['errors'][:10]))
        self.TxtScheduleSummary.Text = msg
        forms.alert(msg, title=u'NOSA — Bar Schedules')

    def RebarHub_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._open_rebar_hub)

    def _open_rebar_hub(self):
        """T8.6 — the former Rebar Hub, opened in Revit's API context (it renumbers marks)."""
        from nosa_utils.base_window import launch_nosa_window
        hub_lib = os.path.join(_HERE, 'rebar_hub')
        if hub_lib not in sys.path:
            sys.path.insert(0, hub_lib)
        hub = load_module('rebarhub_ui', os.path.join(hub_lib, 'ui.py'))
        launch_nosa_window(hub.RebarHubWindow, self.doc, self.uidoc)

    def RebarQA_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._open_rebar_qa)

    def TypeSchedules_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._type_schedules)

    def _type_schedules(self):
        """T8.54 — SMDSC 4.1.1 / 6.4.4 / 6.7.4 tabular method: column and base schedules by type."""
        import tabular_schedules
        from pyrevit import forms
        try:
            tabular_schedules.bind(self.doc)
            with nosa_tx.revit_transaction(u'NOSA — Column and Base Schedules'):
                n_cols, n_bases, n_groups = tabular_schedules.update(self.doc)
                tabular_schedules.ensure_schedules(self.doc)
        except Exception as e:
            forms.alert(u'Column and base schedules not made: {}'.format(e), title=u'RebarAutomate')
            return
        forms.alert(u'{} column(s) and {} base(s) with bars, in {} type(s): see the schedules "{}" and "{}" '
                    u'(IStructE SMDSC 6.4.4 / 6.7.4). Run it again after changing any reinforcement.'.format(
                        n_cols, n_bases, n_groups, tabular_schedules.COLUMN_SCHEDULE,
                        tabular_schedules.BASE_SCHEDULE), title=u'RebarAutomate')

    def Robustness_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._open_robustness)

    def _open_robustness(self):
        """T8.50 — the QA Hub's robustness ties window (SMDSC 5.1.9)."""
        from nosa_utils.base_window import launch_nosa_window
        path = os.path.join(_HERE, '..', '..', '..', 'Structures.panel', 'QAHub.pushbutton', 'lib', 'robustness',
                            'ui.py')
        mod = load_module('robustness_ui', os.path.abspath(path))
        launch_nosa_window(mod.RobustnessWindow, self.doc)

    def _open_rebar_qa(self):
        """T8.48 — the QA Hub's Rebar QA window (SMDSC 4.4 / 4.6 checks), shared with the hub."""
        from nosa_utils.base_window import launch_nosa_window
        path = os.path.join(_HERE, '..', '..', '..', 'Structures.panel', 'QAHub.pushbutton', 'lib', 'rebar_qa',
                            'ui.py')
        qa = load_module('rebarqa_ui', os.path.abspath(path))
        launch_nosa_window(qa.RebarQAWindow, self.doc)


_OWN = set(globals())
