# -*- coding: utf-8 -*-
"""
T12.9 (user 2026-10-24): "Update drawings". Each view and sheet RebarAutomate draws keeps a record (Extensible
Storage) of what the plugin put there; an update snapshots the drawings, has them drawn again into the same
sheets, then puts back what the user did: viewport positions, crop and scale, their own annotations and the tags
they moved whose bars did not change. "Regenerate" replaces the drawings, sheets and their title block data kept.
"""
import re

from nosa_utils import drawing_update as du

SCHEMA_GUID = u'5f0d3a52-8c1e-4b7e-9f26-1d4c7a9e2b61'
FIELD = u'Record'
UPDATE, REGENERATE = 'update', 'regenerate'
_OLD_SUFFIX = u' (updating)'
_TEMP_PREFIX = u'UPDATING-'
_FT = 304.8
_OWN_VIEW = re.compile(u'^(Beam|Column|Slab|Wall|Foundation|Stair)s? .* - ')


def _schema():
    import System
    from Autodesk.Revit.DB import ExtensibleStorage as es
    guid = System.Guid(SCHEMA_GUID)
    schema = es.Schema.Lookup(guid)
    if schema is not None:
        return schema
    b = es.SchemaBuilder(guid)
    b.SetSchemaName(u'NOSA_RA_Drawing')
    b.SetReadAccessLevel(es.AccessLevel.Public)
    b.SetWriteAccessLevel(es.AccessLevel.Public)
    b.AddSimpleField(FIELD, System.String)
    return b.Finish()


def read(element):
    """The record an element carries; {} without one."""
    import System
    from Autodesk.Revit.DB import ExtensibleStorage as es
    try:
        schema = es.Schema.Lookup(System.Guid(SCHEMA_GUID))
        if schema is None:
            return {}
        entity = element.GetEntity(schema)
        if entity is None or not entity.IsValid():
            return {}
        return du.decode(entity.Get[System.String](FIELD))
    except Exception:  # nosa-lint: disable=NOSA006 - an unreadable record reads as none
        return {}


def write(element, record):
    """In a transaction."""
    import System
    from Autodesk.Revit.DB import ExtensibleStorage as es
    entity = es.Entity(_schema())
    entity.Set[System.String](FIELD, du.encode(record))
    element.SetEntity(entity)


def _xy(view, p):
    return (p.DotProduct(view.RightDirection) * _FT, p.DotProduct(view.UpDirection) * _FT)


def _id(eid):
    from nosa_utils.revit_helpers import get_id_value
    return get_id_value(eid)


def _annotations(doc, view):
    """The annotation and detail elements drawn in a view, a Multi-Rebar Annotation's own tag and dimension aside."""
    from Autodesk.Revit import DB  # Lazy import
    out, inner = [], set()
    for e in DB.FilteredElementCollector(doc, view.Id).OwnedByView(view.Id):
        if isinstance(e, DB.MultiReferenceAnnotation):
            inner.update((_id(e.TagId), _id(e.DimensionId)))
    for e in DB.FilteredElementCollector(doc, view.Id).OwnedByView(view.Id):
        cat = e.Category
        if cat is None or _id(e.Id) in inner or _id(cat.Id) == int(DB.BuiltInCategory.OST_Viewers):
            continue
        if cat.CategoryType == DB.CategoryType.Annotation or isinstance(e, (DB.DetailCurve, DB.FilledRegion)) or \
                _id(cat.Id) == int(DB.BuiltInCategory.OST_DetailComponents):
            out.append(e)
    return out


def _tagged(doc, e):
    """The bars an annotation calls up."""
    from Autodesk.Revit import DB  # Lazy import
    tag = doc.GetElement(e.TagId) if isinstance(e, DB.MultiReferenceAnnotation) else e
    if not isinstance(tag, DB.IndependentTag):
        return []
    try:
        return sorted(_id(i) for i in tag.GetTaggedLocalElementIds())
    except Exception:  # nosa-lint: disable=NOSA006 - a tag of nothing calls up no bar
        return []


def fingerprint(doc, view, e):
    """Where an annotation stands: a tag's head, elbows and leader ends; otherwise its box (view mm)."""
    from Autodesk.Revit import DB  # Lazy import
    pts = []
    try:
        tag = doc.GetElement(e.TagId) if isinstance(e, DB.MultiReferenceAnnotation) else e
        if isinstance(tag, DB.IndependentTag):
            pts.append(_xy(view, tag.TagHeadPosition))
            if tag.HasLeader:
                for ref in tag.GetTaggedReferences():
                    if tag.HasLeaderElbow(ref):
                        pts.append(_xy(view, tag.GetLeaderElbow(ref)))
                    if tag.LeaderEndCondition == DB.LeaderEndCondition.Free:
                        pts.append(_xy(view, tag.GetLeaderEnd(ref)))
        if isinstance(e, DB.MultiReferenceAnnotation):
            dim = doc.GetElement(e.DimensionId)
            if dim is not None and dim.Curve is not None:
                pts.append(_xy(view, dim.Origin))
        if not pts:
            bb = e.get_BoundingBox(view)
            if bb is not None:
                pts = [_xy(view, bb.Min), _xy(view, bb.Max)]
    except Exception:  # nosa-lint: disable=NOSA006 - unreadable: no fingerprint, never taken as moved
        return None
    return [(round(x, 2), round(y, 2)) for x, y in pts]


def signatures(doc):
    """{bar id: signature} of every NOSA bar in the model."""
    from Autodesk.Revit import DB  # Lazy import
    out = {}
    for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
        try:
            p = r.LookupParameter(u'NOSA_Rebar_Is_Variable')
            out[u'{}'.format(_id(r.Id))] = du.bar_signature(
                r.NumberOfBarPositions, r.TotalLength * _FT, _id(r.GetShapeId()), _id(r.GetTypeId()),
                p is not None and p.AsInteger() == 1)
        except Exception:
            continue
    return out


def _crop(view):
    try:
        b = view.CropBox
        return [round(b.Min.X * _FT, 1), round(b.Min.Y * _FT, 1), round(b.Max.X * _FT, 1), round(b.Max.Y * _FT, 1)]
    except Exception:  # nosa-lint: disable=NOSA006 - a view without a crop records none
        return None


def _port_of(doc, view):
    """(sheet, viewport) the view is placed on, (None, None) when on none."""
    from Autodesk.Revit import DB  # Lazy import
    for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        for pid in sheet.GetAllViewports():
            port = doc.GetElement(pid)
            if port is not None and port.ViewId == view.Id:
                return sheet, port
    return None, None


def _centre(port, view, point=None):
    """
    Where a model point of the view (its origin unless given) lands on the sheet (mm): the view's place there, not
    moved by a note or a crop that only resizes the viewport (2026-10-24 Revit test: the box centre was).
    """
    try:
        p = point if point is not None else view.Origin
        local = view.CropBox.Transform.Inverse.OfPoint(p)
        c = port.GetProjectionToSheetTransform().OfPoint(local.Divide(view.Scale))
    except Exception:  # nosa-lint: disable=NOSA006 - no projection: the box centre
        c = port.GetBoxCenter()
    return [round(c.X * _FT, 1), round(c.Y * _FT, 1)]


def own_views(doc, kinds):
    """The views RebarAutomate drew for these kinds: by their record, or by name for drawings made before records."""
    from Autodesk.Revit import DB  # Lazy import
    import rebar_views
    titles = tuple(rebar_views._TITLES[k] for k in kinds if k in rebar_views._TITLES)
    out = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        # a sheet is a View too: 'Slabs reinforcement - S1, S3' read as a slab's view (2026-10-24 Revit test)
        if v.IsTemplate or v.ViewType in (DB.ViewType.DrawingSheet, DB.ViewType.Schedule, DB.ViewType.Legend,
                                          DB.ViewType.DraftingView):
            continue
        rec = read(v)
        if rec:
            if rec.get('kind') in kinds:
                out.append(v)
        elif _OWN_VIEW.match(v.Name or u'') and (v.Name or u'').startswith(titles):
            out.append(v)
    return out


class Updater(object):
    """One run of Create drawings over drawings already made: prepare() before, finish() after build_drawings."""

    def __init__(self, doc, mode=UPDATE):
        self.doc = doc
        self.mode = mode
        self.old = {}            # view name -> snapshot
        self.sheets = {}         # old sheet number -> sheet (renumbered while the drawing is redrawn)
        self.by_kind = {}        # kind -> [old sheet numbers]
        self.log = {'kept': [], 'updated': [], 'removed': [], 'warnings': []}
        self.users = {}          # view name -> {'user_crop', 'user_scale', 'user_place'} kept as the user's

    # -- before -------------------------------------------------------------------------------------------------
    def prepare(self, kinds):
        """Snapshot and clear the old drawings of these kinds, their sheets kept for the new ones. In a transaction."""
        from Autodesk.Revit import DB  # Lazy import
        doc = self.doc
        sigs = signatures(doc)
        views = own_views(doc, kinds)
        for v in views:
            rec = read(v)
            sheet, port = _port_of(doc, v)
            snap = {'view': v, 'record': rec, 'crop': _crop(v), 'scale': v.Scale,
                    'sheet': sheet.SheetNumber if sheet is not None else None,
                    'centre': _centre(port, v) if port is not None else None, 'origin': v.Origin,
                    'user': [], 'keep': []}
            notes = rec.get('notes') or {}
            for e in _annotations(doc, v):
                key = u'{}'.format(_id(e.Id))
                if key not in notes:
                    if rec:                      # a drawing made before records: everything in it was the plugin's
                        snap['user'].append(e.Id)
                    continue
                now = fingerprint(doc, v, e)
                action = du.tag_action(notes[key], now, sigs, v.Scale)
                if action == du.KEEP:
                    snap['keep'].append((e.Id, notes[key]))
                elif action == du.RELAY and now is not None and du.moved(now, notes[key].get('points'), v.Scale):
                    self.log['updated'].append(u'{}: bar {} changed - the calling-up you moved is laid out again.'
                                               .format(v.Name, u', '.join(u'{}'.format(b)
                                                                          for b in notes[key].get('bars') or [])))
                elif action == du.GONE_MOVED:
                    self.log['warnings'].append(u'{}: a calling-up you moved belonged to a deleted bar; removed.'
                                                .format(v.Name))
            self.old[v.Name] = snap
            if sheet is not None:
                kind = rec.get('kind') or next((k for k in kinds if v.Name.startswith(self._title(k))), None)
                self.by_kind.setdefault(kind, [])
                if sheet.SheetNumber not in self.by_kind[kind]:
                    self.by_kind[kind].append(sheet.SheetNumber)
                self.sheets[sheet.SheetNumber] = sheet
        for number, sheet in self.sheets.items():
            self._clear_sheet(sheet, [s['view'] for s in self.old.values()])
            sheet.SheetNumber = _TEMP_PREFIX + number
        for name, snap in self.old.items():
            snap['view'].Name = name + _OLD_SUFFIX
        for numbers in self.by_kind.values():
            numbers.sort()
        import rebar_views
        rebar_views.REUSE_SHEETS = dict((n, s) for n, s in self.sheets.items())
        rebar_views.UPDATE = self if self.mode == UPDATE else None
        return self

    @staticmethod
    def _title(kind):
        import rebar_views
        return rebar_views._TITLES.get(kind, u'~')

    def _clear_sheet(self, sheet, views):
        """The plugin's viewports and notes off a sheet; the user's own things stay."""
        from Autodesk.Revit import DB  # Lazy import
        doc = self.doc
        rec = read(sheet)
        ours = set(rec.get('ports') or [])
        own_ids = set(_id(v.Id) for v in views)
        for pid in list(sheet.GetAllViewports()):
            port = doc.GetElement(pid)
            if port is None:
                continue
            vid = _id(port.ViewId)
            if vid in own_ids or vid in ours or not rec:
                doc.Delete(pid)
        for note in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.TextNote):
            if (note.Text or u'').startswith(u'REINFORCEMENT NOTES'):
                doc.Delete(note.Id)

    def numbers(self, kind, shared):
        """The sheet numbers a drawing takes: its old ones first."""
        return du.NumberPool(self.by_kind.get(kind, []), shared)

    def free(self, shared):
        """The shared free numbers without the old drawings' own."""
        old = set(self.sheets)
        return [n for n in shared if n not in old]

    def view_made(self, view):
        """A view just drawn again: the user's crop and scale back on it, before its calling-up is laid out."""
        snap = self.old.get(view.Name)
        if snap is None:
            return
        crop_changed, scale_changed = du.view_changed(snap['record'], snap['crop'], snap['scale'])
        try:
            if scale_changed:
                view.Scale = snap['scale']
                self.users.setdefault(view.Name, {})['user_scale'] = True
                self.log['kept'].append(u'{}: your scale 1:{}'.format(view.Name, snap['scale']))
            if crop_changed:
                old = snap['view'].CropBox
                box = view.CropBox
                box.Min, box.Max = old.Min, old.Max
                view.CropBox = box
                self.users.setdefault(view.Name, {})['user_crop'] = True
                self.log['kept'].append(u'{}: your crop'.format(view.Name))
        except Exception as e:
            self.log['warnings'].append(u'{}: your crop or scale could not be kept ({}).'.format(view.Name, e))

    # -- after --------------------------------------------------------------------------------------------------
    def finish(self, report):
        """The user's work put back, the old views gone and every drawing recorded. In a transaction."""
        from Autodesk.Revit import DB  # Lazy import
        doc = self.doc
        import rebar_views
        rebar_views.REUSE_SHEETS = {}
        rebar_views.UPDATE = None
        sigs = signatures(doc)
        numbers = set(report.get('sheets') or [])
        drawn = []
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
            if sheet.SheetNumber in numbers:
                for pid in sheet.GetAllViewports():
                    port = doc.GetElement(pid)
                    view = doc.GetElement(port.ViewId) if port is not None else None
                    if view is not None and view.ViewType not in (DB.ViewType.Legend, DB.ViewType.DraftingView):
                        drawn.append((view, sheet, port))
        names = dict((v.Name, (v, s, p)) for v, s, p in drawn)
        records = {}
        for view, sheet, port in drawn:
            records[_id(view.Id)] = self._record(view, sheet, port, sigs, report)
        if self.mode == UPDATE:
            for name, snap in self.old.items():
                new = names.get(name)
                if new is None:
                    if snap['user'] or snap['keep']:
                        self.log['warnings'].append(u'{}: no longer drawn - your annotations on it are lost.'
                                                    .format(name))
                    self.log['removed'].append(name)
                    continue
                view, sheet, port = new
                self._restore(snap, view, sheet, port, records[_id(view.Id)])
        for snap in self.old.values():
            try:
                doc.Delete(snap['view'].Id)
            except Exception as e:
                self.log['warnings'].append(u'{}: old view not deleted ({}).'.format(snap['view'].Name, e))
        for number, sheet in self.sheets.items():
            if sheet.IsValidObject and sheet.SheetNumber.startswith(_TEMP_PREFIX):
                # a sheet the drawing no longer needs: gone when empty, back under its number otherwise
                if list(sheet.GetAllViewports()) or self._user_items(sheet):
                    sheet.SheetNumber = number
                    self.log['warnings'].append(u'Sheet {} no longer needed by the drawing: kept, it holds your '
                                                u'own work.'.format(number))
                else:
                    doc.Delete(sheet.Id)
                    self.log['removed'].append(u'Sheet {}'.format(number))
        for view, sheet, port in drawn:
            write(view, records[_id(view.Id)])
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
            if sheet.SheetNumber not in numbers:
                continue
            kinds = [records[_id(v.Id)].get('kind') for v, s, _p in drawn if s.Id == sheet.Id]
            ports = [doc.GetElement(p) for p in sheet.GetAllViewports()]
            write(sheet, {'kind': kinds[0] if kinds else None,
                          'ports': [_id(p.ViewId) for p in ports if p is not None and self._plugin_port(p, drawn)]})
        return self.log

    def _plugin_port(self, port, drawn):
        from Autodesk.Revit import DB  # Lazy import
        view = self.doc.GetElement(port.ViewId)
        return any(v.Id == port.ViewId for v, _s, _p in drawn) or \
            (view is not None and view.ViewType in (DB.ViewType.Legend, DB.ViewType.DraftingView))

    def _user_items(self, sheet):
        from Autodesk.Revit import DB  # Lazy import
        return [e for e in DB.FilteredElementCollector(self.doc, sheet.Id).OwnedByView(sheet.Id)
                if e.Category is not None and _id(e.Category.Id) != int(DB.BuiltInCategory.OST_TitleBlocks)
                and not isinstance(e, DB.Viewport)]

    def _record(self, view, sheet, port, sigs, report):
        doc = self.doc
        notes = {}
        for e in _annotations(doc, view):
            bars = _tagged(doc, e)
            notes[u'{}'.format(_id(e.Id))] = {'bars': bars, 'points': fingerprint(doc, view, e),
                                              'sig': dict((u'{}'.format(b), sigs.get(u'{}'.format(b))) for b in bars),
                                              'type': _id(e.GetTypeId())}
        kind = None
        for k, title in __import__('rebar_views')._TITLES.items():
            if view.Name.startswith(title):
                kind = k
        out = {'kind': kind, 'crop': _crop(view), 'scale': view.Scale, 'sheet': sheet.SheetNumber,
               'centre': _centre(port, view), 'notes': notes}
        out.update(self.users.get(view.Name, {}))
        return out

    def _restore(self, snap, view, sheet, port, record):
        from Autodesk.Revit import DB  # Lazy import
        from System.Collections.Generic import List
        doc = self.doc
        old = snap['view']
        if du.viewport_moved(snap['record'], snap['centre']) and snap['sheet'] == sheet.SheetNumber:
            doc.Regenerate()
            now = _centre(port, view, snap['origin'])
            shift = DB.XYZ((snap['centre'][0] - now[0]) / _FT, (snap['centre'][1] - now[1]) / _FT, 0.0)
            port.SetBoxCenter(port.GetBoxCenter() + shift)
            doc.Regenerate()
            record['centre'] = _centre(port, view)
            record['user_place'] = True
            self.log['kept'].append(u'{}: its place on sheet {}'.format(view.Name, sheet.SheetNumber))
        for eid, entry in snap['keep']:
            twin = self._twin(view, entry, record)
            try:
                copied = DB.ElementTransformUtils.CopyElements(old, List[DB.ElementId]([eid]), view,
                                                               DB.Transform.Identity, DB.CopyPasteOptions())
            except Exception as ex:
                self.log['warnings'].append(u'{}: a calling-up you moved could not be kept ({}).'.format(view.Name, ex))
                continue
            if twin is not None:
                record['notes'].pop(twin, None)
                doc.Delete(_element_id(twin))
            for cid in copied:
                c = doc.GetElement(cid)
                if c is not None:
                    record['notes'][u'{}'.format(_id(cid))] = dict(entry, kept=True,
                                                                   points=fingerprint(doc, view, c))
            self.log['kept'].append(u'{}: calling-up of bar {} where you put it'.format(
                view.Name, u', '.join(u'{}'.format(b) for b in entry.get('bars') or []) or u'-'))
        if snap['user']:
            try:
                DB.ElementTransformUtils.CopyElements(old, List[DB.ElementId](snap['user']), view,
                                                      DB.Transform.Identity, DB.CopyPasteOptions())
                self.log['kept'].append(u'{}: {} annotation(s) of your own'.format(view.Name, len(snap['user'])))
            except Exception as ex:
                self.log['warnings'].append(u'{}: your own annotations could not be carried over ({}).'
                                            .format(view.Name, ex))

    @staticmethod
    def _twin(view, entry, record):
        """The new annotation standing for a kept one: same type and bars, nearest its old place."""
        best, dist = None, None
        head = (entry.get('points') or [None])[0]
        for key, e in record['notes'].items():
            if e.get('type') != entry.get('type') or e.get('bars') != entry.get('bars') or not e.get('points'):
                continue
            if head is None:
                return key
            d = (e['points'][0][0] - head[0]) ** 2 + (e['points'][0][1] - head[1]) ** 2
            if dist is None or d < dist:
                best, dist = key, d
        return best


def _element_id(value):
    from nosa_utils.revit_helpers import element_id_from_int
    return element_id_from_int(int(value))


def summary(log):
    """The update's own lines for the review: what was kept, updated and removed."""
    out = []
    if log.get('kept'):
        out.append(u'Kept ({}):'.format(len(log['kept'])))
        out.extend(u'  - ' + m for m in log['kept'])
    if log.get('updated'):
        out.append(u'Updated ({}):'.format(len(log['updated'])))
        out.extend(u'  - ' + m for m in log['updated'])
    if log.get('removed'):
        out.append(u'Removed ({}):'.format(len(log['removed'])))
        out.extend(u'  - ' + m for m in log['removed'])
    if log.get('warnings'):
        out.append(u'Check ({}):'.format(len(log['warnings'])))
        out.extend(u'  - ' + m for m in log['warnings'])
    return u'\n'.join(out)
