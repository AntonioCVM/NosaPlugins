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
_PROXY_APP = u'NOSA.ClashViewer.proxy'


class ViewOptions(object):
    """Settings the window passes to every 'go to clash' request."""

    def __init__(self):
        self.isolate = True
        self.permanent = False
        self.dim_rest = False
        self.keep_camera = False
        self.quiet = False            # report mode: no selection, no zoom
        self.proxies = True           # temporary coloured copies of linked / CAD items
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
        self.proxy_docs = set()     # titles of the documents where temporary copies were made

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

    def _remove_proxies(self, doc):
        """Delete every temporary copy this tool made (also leftovers of a crashed session)."""
        ids = self._proxy_ids(doc)
        if ids:
            doc.Delete(_id_list(ids))
        self.proxy_docs.discard(doc.Title)

    @staticmethod
    def _proxy_ids(doc):
        """Our temporary copies that this user may delete (not those another user has checked out)."""
        ids = [ds.Id for ds in DB.FilteredElementCollector(doc).OfClass(DB.DirectShape)
               if ds.ApplicationId == _PROXY_APP]
        if doc.IsWorkshared:
            ids = [i for i in ids
                   if DB.WorksharingUtils.GetCheckoutStatus(doc, i) != DB.CheckoutStatus.OwnedByOtherUser]
        return ids

    def has_proxies(self, doc):
        return doc.Title in self.proxy_docs

    def sweep(self, doc):
        """Remove leftover temporary copies (transaction included); True when something was removed."""
        found = bool(self._proxy_ids(doc))
        if found:
            with nosa_transaction(doc, u'NOSA — Clash Viewer: remove temporary copies'):
                self._remove_proxies(doc)
        return found

    def _make_proxy(self, doc, shapes, label):
        """DirectShape copy of ``shapes`` (host coordinates), or None when Revit refuses the geometry."""
        category = DB.Category.GetCategory(doc, DB.BuiltInCategory.OST_GenericModel)
        shape = DB.DirectShape.CreateElement(doc, category.Id)
        shape.ApplicationId = _PROXY_APP
        shape.ApplicationDataId = label
        geometry = List[DB.GeometryObject]()
        for g in shapes:
            geometry.Add(g)
        try:
            shape.SetShape(geometry)
        except Exception:
            log_swallowed(_LOG, u'_make_proxy')
            doc.Delete(shape.Id)
            return None
        self.proxy_docs.add(doc.Title)
        return shape

    def _clear_overrides(self, doc, view):
        self._remove_proxies(doc)
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
        for li in located.boxed_items:
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
            for number, (li, colour) in enumerate(((located.first, c1), (located.second, c2)), 1):
                if li.is_found and not li.model.is_link:
                    self._paint(doc, view, li.element.Id, self._highlight(doc, colour))
                    host_ids.append(li.element.Id)
                    isolate_ids.append(li.element.Id)
                    painted.add(get_id_value(li.element.Id))
                elif li.is_found or li.is_present:
                    copy_ = None
                    if opts.proxies and li.is_shown:
                        copy_ = self._make_proxy(doc, li.proxy_geometry(), u'clash item %d' % number)
                    if copy_ is not None:
                        self._paint(doc, view, copy_.Id, self._highlight(doc, colour))
                        isolate_ids.append(copy_.Id)
                        painted.add(get_id_value(copy_.Id))
                    elif li.element is not None:
                        isolate_ids.append(li.model.instance.Id if li.is_found else li.element.Id)
                        if li.is_present:
                            self._paint(doc, view, li.element.Id, self._highlight(doc, colour))
            if opts.isolate and isolate_ids and view.CanUseTemporaryVisibilityModes():
                view.IsolateElementsTemporary(_id_list(isolate_ids))
                if opts.permanent:
                    view.ConvertTemporaryHideIsolateToPermanent()
                    self._permanent.add(doc.Title)
            elif opts.dim_rest:
                self._dim_rest(doc, view, painted)
        if not opts.quiet:
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

    # ---------------------------------------------------------------- image

    def frame_of(self, located, opts):
        """(min, max) the picture should be about: what is visible of the elements inside the clash window.

        The window is the section-box region, narrowed to the clash surroundings when the elements are long;
        the box of each element is clipped to it, so a 40 m beam does not turn the clash into a speck."""
        region = self.region(located, opts)
        if region is None:
            return None
        lo, hi = region
        point = located.point
        sizes = [li.bbox[0].DistanceTo(li.bbox[1]) for li in located.boxed_items]
        if point is not None and sizes:
            reach = max(6.5, 0.8 * min(sizes))                              # feet (about 2 m minimum)
            if lo.DistanceTo(hi) > 2.0 * reach:
                lo = DB.XYZ(max(lo.X, point.X - reach), max(lo.Y, point.Y - reach), max(lo.Z, point.Z - reach))
                hi = DB.XYZ(min(hi.X, point.X + reach), min(hi.Y, point.Y + reach), min(hi.Z, point.Z + reach))
        pieces = []
        for li in located.boxed_items:
            mn, mx = li.bbox
            a_ = DB.XYZ(max(mn.X, lo.X), max(mn.Y, lo.Y), max(mn.Z, lo.Z))
            b_ = DB.XYZ(min(mx.X, hi.X), min(mx.Y, hi.Y), min(mx.Z, hi.Z))
            if a_.X <= b_.X and a_.Y <= b_.Y and a_.Z <= b_.Z:
                pieces.extend((a_, b_))
        if not pieces:
            return lo, hi
        return (DB.XYZ(min(p.X for p in pieces), min(p.Y for p in pieces), min(p.Z for p in pieces)),
                DB.XYZ(max(p.X for p in pieces), max(p.Y for p in pieces), max(p.Z for p in pieces)))

    def _crop_to(self, doc, view, frame, margin=0.07):
        """Crop the clash view tightly around ``frame`` so the exported picture is not mostly empty."""
        lo, hi = frame
        diag = lo.DistanceTo(hi)
        pad = max(diag * margin, 0.4)
        crop = view.CropBox
        inverse = crop.Transform.Inverse
        pts = []
        for x in (lo.X, hi.X):
            for y in (lo.Y, hi.Y):
                for z in (lo.Z, hi.Z):
                    pts.append(inverse.OfPoint(DB.XYZ(x, y, z)))
        crop.Min = DB.XYZ(min(p.X for p in pts) - pad, min(p.Y for p in pts) - pad, min(p.Z for p in pts) - diag - pad)
        crop.Max = DB.XYZ(max(p.X for p in pts) + pad, max(p.Y for p in pts) + pad, max(p.Z for p in pts) + diag + pad)
        with nosa_transaction(doc, u'NOSA — Clash Viewer: frame picture'):
            view.CropBox = crop
            view.CropBoxActive = True
            view.CropBoxVisible = False

    def _uncrop(self, doc, view):
        with nosa_transaction(doc, u'NOSA — Clash Viewer: unframe picture'):
            view.CropBoxActive = False

    def export_image(self, doc, folder, pixels=1600, frame=None):
        """PNG of the clash view into ``folder``; returns the file path or None."""
        view = self.find_view(doc)
        if view is None:
            return None
        opts = DB.ImageExportOptions()
        opts.ExportRange = DB.ExportRange.SetOfViews
        opts.SetViewsAndSheets(_id_list([view.Id]))
        opts.FilePath = os.path.join(folder, u'clash')
        opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
        opts.ShadowViewsFileType = DB.ImageFileType.PNG
        opts.ImageResolution = DB.ImageResolution.DPI_150
        opts.ZoomType = DB.ZoomFitType.FitToPage
        opts.PixelSize = pixels
        for stale in os.listdir(folder):
            os.remove(os.path.join(folder, stale))      # Revit reuses the file name for the same view
        framed = False
        if frame is not None:
            try:
                self._crop_to(doc, view, frame)
                framed = True
            except Exception:
                log_swallowed(_LOG, u'export_image.crop')
        try:
            doc.ExportImage(opts)
        finally:
            if framed:
                self._uncrop(doc, view)
        fresh = sorted(os.listdir(folder))
        return os.path.join(folder, fresh[0]) if fresh else None

    def select_item(self, uidoc, li, zoom=True):
        """Select just one element of the clash (host element, linked element or CAD link); returns a message."""
        if li.is_found and li.model.is_link:
            ref = DB.Reference(li.element).CreateLinkReference(li.model.instance)
            refs = List[DB.Reference]()
            refs.Add(ref)
            uidoc.Selection.SetReferences(refs)
        elif li.is_found or li.is_present:
            ids = List[DB.ElementId]()
            ids.Add(li.element.Id)
            uidoc.Selection.SetElementIds(ids)
        else:
            return u'This item is not in the model, so there is nothing to select.'
        if zoom and li.bbox is not None:
            lo, hi = li.bbox
            pad = max(lo.DistanceTo(hi) * 0.5, 1.0)
            try:
                view = uidoc.ActiveView
                for uv in uidoc.GetOpenUIViews():
                    if get_id_value(uv.ViewId) == get_id_value(view.Id):
                        uv.ZoomAndCenterRectangle(DB.XYZ(lo.X - pad, lo.Y - pad, lo.Z - pad),
                                                  DB.XYZ(hi.X + pad, hi.Y + pad, hi.Z + pad))
                        break
            except Exception:
                log_swallowed(_LOG, u'select_item.zoom')
        return u'Selected: %s' % li.text

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
            self._remove_proxies(doc)
            doc.Delete(view.Id)
        self._painted.pop(doc.Title, None)
        self._permanent.discard(doc.Title)
        return True
