# -*- coding: utf-8 -*-
"""Dedicated 3D view for reviewing clashes: section box, isolation and colour overrides."""
import os
import re
from Autodesk.Revit import DB
from System.Collections.Generic import List

from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.telemetry import log_swallowed
from nosa_utils.transactions import nosa_transaction

_LOG = u'ClashViewer.view'
_MM_TO_FT = 1.0 / 304.8
_MAX_DIMMED = 20000

DEFAULT_COLOUR_1 = u'#FF0000'
DEFAULT_COLOUR_2 = u'#0066FF'


class ViewOptions(object):
    """Settings the window passes to every 'go to clash' request."""

    def __init__(self):
        self.isolate = True
        self.permanent = False
        self.dim_rest = False
        self.keep_camera = False
        self.margin_mm = 1000.0
        self.crop_radius_mm = 0.0
        self.colour1 = DEFAULT_COLOUR_1
        self.colour2 = DEFAULT_COLOUR_2


def parse_colour(text, fallback):
    m = re.match(r'^\s*#?([0-9a-fA-F]{6})\s*$', text or u'')
    value = m.group(1) if m else fallback.lstrip(u'#')
    return DB.Color(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _id_list(ids):
    out = List[DB.ElementId]()
    for i in ids:
        out.Add(i)
    return out


class ClashView(object):
    """Owns the dedicated view and remembers everything it overrode there."""

    def __init__(self):
        self._painted = {}          # doc title -> [ElementId] with overrides set by us
        self._permanent = set()     # doc titles where isolation was made permanent
        self._origin = {}           # doc title -> ElementId of the view the user came from
        self._solid = {}            # doc title -> solid fill pattern ElementId

    # ------------------------------------------------------------------ view

    @staticmethod
    def view_name():
        user = re.sub(r'[^A-Za-z0-9_-]', u'_', os.getenv('USERNAME') or u'user')
        return u'CLASH_VIEWER_%s' % user

    def find_view(self, doc):
        name = self.view_name()
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
            if not v.IsTemplate and element_name(v) == name:
                return v
        return None

    def ensure_view(self, doc):
        view = self.find_view(doc)
        if view is not None:
            return view
        vft = None
        for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
            if t.ViewFamily == DB.ViewFamily.ThreeDimensional:
                vft = t
                break
        if vft is None:
            raise RuntimeError(u'This project has no 3D view type.')
        with nosa_transaction(doc, u'NOSA — Clash Viewer: create view'):
            view = DB.View3D.CreateIsometric(doc, vft.Id)
            view.Name = self.view_name()
            view.DetailLevel = DB.ViewDetailLevel.Medium
            view.DisplayStyle = DB.DisplayStyle.Shading
        return view

    def activate(self, uidoc, view):
        current = uidoc.ActiveView
        if get_id_value(current.Id) == get_id_value(view.Id):
            return
        title = uidoc.Document.Title
        if title not in self._origin:
            self._origin[title] = current.Id
        uidoc.ActiveView = view

    # -------------------------------------------------------------- overrides

    def _solid_fill(self, doc):
        title = doc.Title
        if title not in self._solid:
            found = None
            for fpe in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
                pat = fpe.GetFillPattern()
                if pat.IsSolidFill:
                    if pat.Target == DB.FillPatternTarget.Drafting:
                        found = fpe.Id
                        break
                    found = found or fpe.Id
            self._solid[title] = found
        return self._solid[title]

    def _highlight(self, doc, colour):
        ogs = DB.OverrideGraphicSettings()
        ogs.SetProjectionLineColor(colour)
        ogs.SetProjectionLineWeight(6)
        ogs.SetCutLineColor(colour)
        ogs.SetCutLineWeight(6)
        solid = self._solid_fill(doc)
        if solid is not None:
            ogs.SetSurfaceForegroundPatternId(solid)
            ogs.SetSurfaceForegroundPatternColor(colour)
            ogs.SetCutForegroundPatternId(solid)
            ogs.SetCutForegroundPatternColor(colour)
        ogs.SetSurfaceTransparency(0)
        return ogs

    def _paint(self, doc, view, element_id, ogs):
        view.SetElementOverrides(element_id, ogs)
        self._painted.setdefault(doc.Title, []).append(element_id)

    def _clear_overrides(self, doc, view):
        blank = DB.OverrideGraphicSettings()
        for eid in self._painted.pop(doc.Title, []):
            try:
                view.SetElementOverrides(eid, blank)
            except Exception:
                log_swallowed(_LOG, u'_clear_overrides')
        try:
            view.DisableTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate)
        except Exception:
            log_swallowed(_LOG, u'_clear_overrides.isolate')

    # ------------------------------------------------------------------ show

    @staticmethod
    def region(located, opts):
        """(min, max) XYZ in host feet for the section box, or None when nothing is known."""
        box = None
        for li in located.found_items:
            if li.bbox is None:
                continue
            mn, mx = li.bbox
            if box is None:
                box = [mn, mx]
            else:
                box = [DB.XYZ(min(box[0].X, mn.X), min(box[0].Y, mn.Y), min(box[0].Z, mn.Z)),
                       DB.XYZ(max(box[1].X, mx.X), max(box[1].Y, mx.Y), max(box[1].Z, mx.Z))]
        pt = located.point
        if pt is not None:
            if box is None:
                box = [pt, pt]
            elif opts.crop_radius_mm > 0:
                r = opts.crop_radius_mm * _MM_TO_FT
                lo = DB.XYZ(max(box[0].X, pt.X - r), max(box[0].Y, pt.Y - r), max(box[0].Z, pt.Z - r))
                hi = DB.XYZ(min(box[1].X, pt.X + r), min(box[1].Y, pt.Y + r), min(box[1].Z, pt.Z + r))
                if lo.X <= hi.X and lo.Y <= hi.Y and lo.Z <= hi.Z:
                    box = [lo, hi]
        if box is None:
            return None
        m = max(opts.margin_mm, 0.0) * _MM_TO_FT
        if m == 0 and box[0].IsAlmostEqualTo(box[1]):
            m = 1.0
        return (DB.XYZ(box[0].X - m, box[0].Y - m, box[0].Z - m),
                DB.XYZ(box[1].X + m, box[1].Y + m, box[1].Z + m))

    @staticmethod
    def _orientation(lo, hi):
        centre = (lo + hi) * 0.5
        size = max(hi.X - lo.X, hi.Y - lo.Y, hi.Z - lo.Z, 3.0)
        eye = centre + DB.XYZ(1.0, -1.0, 0.8).Normalize() * (size * 1.5)
        forward = (centre - eye).Normalize()
        right = forward.CrossProduct(DB.XYZ.BasisZ).Normalize()
        up = right.CrossProduct(forward).Normalize()
        return DB.ViewOrientation3D(eye, up, forward)

    def show(self, uidoc, located, opts):
        """Show one located clash in the dedicated view; returns a status message."""
        doc = uidoc.Document
        found = located.found_items
        reg = self.region(located, opts)
        if reg is None:
            return u'Nothing to show: no element was found and the clash has no usable point.'
        old = self.find_view(doc)
        if old is not None and doc.Title in self._permanent:
            self._drop_view(uidoc, old)          # start from a clean view: hidden elements are permanent
        view = self.ensure_view(doc)
        self.activate(uidoc, view)

        c1 = parse_colour(opts.colour1, DEFAULT_COLOUR_1)
        c2 = parse_colour(opts.colour2, DEFAULT_COLOUR_2)
        host_ids, isolate_ids, painted = [], [], set()
        with nosa_transaction(doc, u'NOSA — Clash Viewer: show clash'):
            self._clear_overrides(doc, view)
            box = DB.BoundingBoxXYZ()
            box.Min, box.Max = reg
            view.SetSectionBox(box)
            view.IsSectionBoxActive = True
            if not opts.keep_camera:
                view.SetOrientation(self._orientation(reg[0], reg[1]))
            for li, colour in ((located.first, c1), (located.second, c2)):
                if not li.is_found:
                    continue
                if li.model.is_link:
                    isolate_ids.append(li.model.instance.Id)
                    continue
                self._paint(doc, view, li.element.Id, self._highlight(doc, colour))
                host_ids.append(li.element.Id)
                isolate_ids.append(li.element.Id)
                painted.add(get_id_value(li.element.Id))
            if opts.isolate and isolate_ids and view.CanUseTemporaryVisibilityModes():
                view.IsolateElementsTemporary(_id_list(isolate_ids))
                if opts.permanent:
                    view.ConvertTemporaryHideIsolateToPermanent()
                    self._permanent.add(doc.Title)
            elif opts.dim_rest:
                self._dim_rest(doc, view, painted)
        self._select(uidoc, found)
        self._zoom(uidoc, view, reg)
        return self._summary(located)

    def _dim_rest(self, doc, view, skip):
        ogs = DB.OverrideGraphicSettings()
        ogs.SetHalftone(True)
        ogs.SetSurfaceTransparency(60)
        count = 0
        for eid in DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType().ToElementIds():
            if get_id_value(eid) in skip:
                continue
            self._paint(doc, view, eid, ogs)
            count += 1
            if count >= _MAX_DIMMED:
                break

    @staticmethod
    def _select(uidoc, found):
        refs, ids = List[DB.Reference](), List[DB.ElementId]()
        for li in found:
            if li.model.is_link:
                ids.Add(li.model.instance.Id)
                refs.Add(DB.Reference(li.element).CreateLinkReference(li.model.instance))
            else:
                ids.Add(li.element.Id)
                refs.Add(DB.Reference(li.element))
        try:
            if any(li.model.is_link for li in found):
                uidoc.Selection.SetReferences(refs)
            else:
                uidoc.Selection.SetElementIds(ids)
        except Exception:
            log_swallowed(_LOG, u'_select')
            uidoc.Selection.SetElementIds(ids)

    @staticmethod
    def _zoom(uidoc, view, reg):
        try:
            for uv in uidoc.GetOpenUIViews():
                if get_id_value(uv.ViewId) == get_id_value(view.Id):
                    uv.ZoomAndCenterRectangle(reg[0], reg[1])
                    return
        except Exception:
            log_swallowed(_LOG, u'_zoom')

    @staticmethod
    def _summary(located):
        parts = [u'%s: %s' % (u'Item %d' % n, li.text)
                 for n, li in ((1, located.first), (2, located.second))]
        return u'  |  '.join(parts + located.warnings)

    # ----------------------------------------------------------------- reset

    def reset(self, uidoc):
        """Remove overrides, isolation and the section box; returns a status message."""
        doc = uidoc.Document
        view = self.find_view(doc)
        if view is None:
            return u'There is nothing to reset: the clash view does not exist yet.'
        if doc.Title in self._permanent:
            if not self._drop_view(uidoc, view):
                return (u'Permanent isolation was used and no other view could be opened: '
                        u'open another view and press Reset again.')
            uidoc.Selection.SetElementIds(List[DB.ElementId]())
            return u'View rebuilt: permanent isolation removed.'
        with nosa_transaction(doc, u'NOSA — Clash Viewer: reset view'):
            self._clear_overrides(doc, view)
            view.IsSectionBoxActive = False
        uidoc.Selection.SetElementIds(List[DB.ElementId]())
        return u'View reset.'

    def _drop_view(self, uidoc, view):
        """Permanent isolation cannot be undone: switch to another view and delete the clash view."""
        doc = uidoc.Document
        origin = self._origin.get(doc.Title)
        back = doc.GetElement(origin) if origin is not None else None
        if back is None or get_id_value(back.Id) == get_id_value(view.Id):
            back = None
            for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
                if not v.IsTemplate:
                    back = v
                    break
        if back is None:
            return False
        uidoc.ActiveView = back
        with nosa_transaction(doc, u'NOSA — Clash Viewer: rebuild view'):
            doc.Delete(view.Id)
        self._painted.pop(doc.Title, None)
        self._permanent.discard(doc.Title)
        return True
