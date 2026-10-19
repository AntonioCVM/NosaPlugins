# -*- coding: utf-8 -*-
"""Find the elements of a clash in the open Revit document and in its Revit links."""
import re
from Autodesk.Revit import DB

from nosa_utils.revit_helpers import get_id_value, element_id_from_int, element_name
from nosa_utils.telemetry import log_swallowed

_LOG = u'ClashViewer.locator'
_MM_TO_FT = 1.0 / 304.8

FOUND_HOST = u'host'
FOUND_LINK = u'link'
NOT_FOUND = u'missing'
UNLOADED = u'unloaded'
MISMATCH = u'mismatch'
NOT_IN_REVIT = u'plant'
NO_DATA = u'empty'

_RE_MODEL_CODE = re.compile(r'[a-z0-9]+-[a-z0-9]+-\d{2}-[a-z]{2}-[a-z]{2,3}-\d{5}')
_PLANT_PARAMS = (u'Tag', u'PnPGuid', u'PnPID', u'Mark')


def _strip_model_name(name):
    base = re.split(r'[\\/]', name or u'')[-1]
    base = re.sub(r'\s*:.*$', u'', base)                     # "X.rvt : 1 : location ..."
    return re.sub(r'\.(rvt|nwc|nwd|ifc)$', u'', base, flags=re.I).strip().lower()


def _model_code(name):
    m = _RE_MODEL_CODE.search(_strip_model_name(name))
    return m.group(0) if m else None


def names_match(a, b):
    """True when two model names are the same model (equal, same code, or one extends the other)."""
    a, b = _strip_model_name(a), _strip_model_name(b)
    if not a or not b:
        return False
    if a == b:
        return True
    ca, cb = _model_code(a), _model_code(b)
    if ca and cb:
        return ca == cb
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 12 and long_.startswith(short)


def _words(text):
    text = re.sub(r'^OST_', u'', text or u'')
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    out = set()
    for w in re.split(r'[^A-Za-z0-9]+', text.lower()):
        if w:
            out.add(w[:-1] if len(w) > 3 and w.endswith('s') else w)
    return frozenset(out)


def _category_keys(element):
    """Normalised word-sets for the element's category: localised name and OST_ enum name."""
    keys = set()
    cat = element.Category
    if cat is None:
        return keys
    keys.add(_words(cat.Name))
    try:
        import clr
        import System
        enum_name = str(System.Enum.ToObject(clr.GetClrType(DB.BuiltInCategory),
                                             get_id_value(cat.Id)))
        if enum_name.startswith('OST_'):
            keys.add(_words(enum_name))
    except Exception:
        log_swallowed(_LOG, u'_category_keys')
    keys.discard(frozenset())
    return keys


class ModelRef(object):
    """The host model or one Revit link instance."""

    def __init__(self, doc, instance, names):
        self.doc = doc
        self.instance = instance
        self.names = [n for n in names if n]
        self.transform = None
        if instance is not None:
            try:
                self.transform = instance.GetTotalTransform()
            except Exception:
                log_swallowed(_LOG, u'ModelRef.transform')

    @property
    def is_link(self):
        return self.instance is not None

    @property
    def label(self):
        return self.names[0] if self.names else u'?'

    def matches(self, nwc_name, extra_names=()):
        for candidate in list(extra_names) + [nwc_name]:
            for mine in self.names:
                if names_match(candidate, mine):
                    return True
        return False


def collect_models(host_doc):
    """Host first, then every Revit link instance (loaded or not)."""
    host_names = [host_doc.Title, host_doc.PathName]
    models = [ModelRef(host_doc, None, host_names)]
    for inst in DB.FilteredElementCollector(host_doc).OfClass(DB.RevitLinkInstance):
        ldoc = None
        try:
            ldoc = inst.GetLinkDocument()
        except Exception:
            log_swallowed(_LOG, u'collect_models.GetLinkDocument')
        names = []
        try:
            names.append(element_name(host_doc.GetElement(inst.GetTypeId())))
        except Exception:
            log_swallowed(_LOG, u'collect_models.type_name')
        if ldoc is not None:
            names.extend([ldoc.Title, ldoc.PathName])
        names.append(element_name(inst))
        models.append(ModelRef(ldoc, inst, names))
    return models


class LocatedItem(object):
    """Result of looking one clash item up in Revit."""

    def __init__(self, item, status, note=u''):
        self.item = item
        self.status = status
        self.note = note
        self.element = None
        self.model = None
        self.bbox = None            # (min XYZ, max XYZ) in host coordinates, feet

    @property
    def is_found(self):
        return self.status in (FOUND_HOST, FOUND_LINK)

    @property
    def element_id(self):
        return get_id_value(self.element.Id) if self.element is not None else None

    @property
    def text(self):
        if self.status == FOUND_HOST:
            return u'Found in the active model'
        if self.status == FOUND_LINK:
            return u'Found in link %s' % self.model.label
        if self.status == UNLOADED:
            return u'Link not loaded: %s' % self.note
        if self.status == MISMATCH:
            return u'Id found but category differs (%s)' % self.note
        if self.status == NOT_IN_REVIT:
            return u'AutoCAD Plant item - not present in Revit'
        if self.status == NO_DATA:
            return u'No element data in the report'
        return u'Not found%s' % (u' (%s)' % self.note if self.note else u'')


class LocatedClash(object):
    def __init__(self, clash, first, second, point, warnings):
        self.clash = clash
        self.first = first
        self.second = second
        self.point = point          # XYZ in host internal coordinates, feet (or None)
        self.warnings = warnings

    @property
    def found_items(self):
        return [i for i in (self.first, self.second) if i.is_found]

    @property
    def state_text(self):
        found = len(self.found_items)
        if found == 2:
            return u'Both found'
        if found == 1:
            return u'One of two found'
        return u'Not found'


def point_to_internal(doc, point_mm):
    """Shared-coordinate point in mm -> host internal coordinates in feet."""
    p = DB.XYZ(point_mm[0] * _MM_TO_FT, point_mm[1] * _MM_TO_FT, point_mm[2] * _MM_TO_FT)
    loc = doc.ActiveProjectLocation
    total = loc.GetTotalTransform()
    pos = loc.GetProjectPosition(DB.XYZ.Zero)
    origin = total.OfPoint(DB.XYZ.Zero)
    shared_of_origin = DB.XYZ(pos.EastWest, pos.NorthSouth, pos.Elevation)
    if origin.DistanceTo(shared_of_origin) < 1e-6:        # transform goes internal -> shared
        return total.Inverse.OfPoint(p)
    return total.OfPoint(p)


class Locator(object):
    """Resolves clash items against one host document; results are cached per item."""

    def __init__(self, host_doc, model_map=None):
        self.doc = host_doc
        self.models = collect_models(host_doc)
        self.model_map = dict((_strip_model_name(k), v if isinstance(v, (list, tuple)) else [v])
                              for k, v in (model_map or {}).items())
        self._cache = {}
        self._plant = None

    # ---------------------------------------------------------------- public

    def link_names(self):
        return [m.label for m in self.models if m.is_link]

    def locate_clash(self, clash):
        first = self.locate_item(clash.item1)
        second = self.locate_item(clash.item2)
        warnings = []
        point = None
        pt_mm = clash.point_mm
        if pt_mm is not None:
            try:
                point = point_to_internal(self.doc, pt_mm)
            except Exception:
                log_swallowed(_LOG, u'locate_clash.point')
                warnings.append(u'The clash point could not be converted to model coordinates.')
        if point is not None:
            box = self.union_bbox([first, second])
            if box is not None:
                centre = (box[0] + box[1]) * 0.5
                if centre.DistanceTo(point) > 1640.0:       # ~500 m
                    warnings.append(u'The clash point is far from the elements: check that '
                                    u'shared coordinates are set in this model.')
        return LocatedClash(clash, first, second, point, warnings)

    def locate_item(self, item):
        key = (item.path, item.category, item.element_id_raw, item.unique_id,
               item.acad_tag, item.pnp_guid)
        if key not in self._cache:
            try:
                self._cache[key] = self._locate(item)
            except Exception:
                log_swallowed(_LOG, u'locate_item')
                self._cache[key] = LocatedItem(item, NOT_FOUND, u'lookup failed')
        return self._cache[key]

    @staticmethod
    def union_bbox(located_items):
        lo = hi = None
        for li in located_items:
            if li.bbox is None:
                continue
            mn, mx = li.bbox
            if lo is None:
                lo, hi = mn, mx
            else:
                lo = DB.XYZ(min(lo.X, mn.X), min(lo.Y, mn.Y), min(lo.Z, mn.Z))
                hi = DB.XYZ(max(hi.X, mx.X), max(hi.Y, mx.Y), max(hi.Z, mx.Z))
        return (lo, hi) if lo is not None else None

    # --------------------------------------------------------------- internals

    def _locate(self, item):
        if item.is_empty:
            return LocatedItem(item, NO_DATA)
        if not item.is_revit:
            return self._locate_plant(item)

        model = self._resolve_model(item)
        if model is not None and model.doc is None:
            return LocatedItem(item, UNLOADED, model.label)
        candidates = [model] if model is not None else [m for m in self.models if m.doc is not None]
        strict = model is None            # unknown model: only accept a category-checked hit
        mismatch_note = u''
        for m in candidates:
            element, how = self._find(m.doc, item, strict)
            if element is None:
                continue
            if how == u'mismatch':
                mismatch_note = u'%s in report' % item.category
                continue
            return self._found(item, element, m)
        if mismatch_note:
            return LocatedItem(item, MISMATCH, mismatch_note)
        if model is None:
            return LocatedItem(item, NOT_FOUND, u'model %s is not loaded' % (item.model_base or u'?'))
        return LocatedItem(item, NOT_FOUND)

    def _resolve_model(self, item):
        extra = self.model_map.get(_strip_model_name(item.path), [])
        for m in self.models:
            if m.matches(item.path, extra):
                return m
        return None

    def _find(self, doc, item, strict):
        """(element, how) where how is 'uid', 'id' or 'mismatch'; (None, None) when absent."""
        wrong = None
        if item.unique_id:
            el = doc.GetElement(item.unique_id)
            if el is not None:
                if self._category_ok(el, item):
                    return el, u'uid'
                wrong = el
        eid = item.element_id
        if eid is not None:
            el = doc.GetElement(element_id_from_int(eid))
            if el is not None and not isinstance(el, DB.ElementType):
                if self._category_ok(el, item):
                    return el, u'id'
                wrong = wrong or el
        if wrong is not None and not strict:
            return wrong, u'mismatch'
        return None, None

    @staticmethod
    def _category_ok(element, item):
        if not item.category:
            return True
        wanted = _words(item.category)
        have = _category_keys(element)
        return not have or wanted in have

    def _found(self, item, element, model):
        li = LocatedItem(item, FOUND_LINK if model.is_link else FOUND_HOST)
        li.element = element
        li.model = model
        li.bbox = self._bbox(element, model)
        return li

    def _bbox(self, element, model):
        box = element.get_BoundingBox(None)
        if box is None:
            return None
        corners = []
        for x in (box.Min.X, box.Max.X):
            for y in (box.Min.Y, box.Max.Y):
                for z in (box.Min.Z, box.Max.Z):
                    pt = DB.XYZ(x, y, z)
                    if box.Transform is not None:
                        pt = box.Transform.OfPoint(pt)
                    if model.transform is not None:
                        pt = model.transform.OfPoint(pt)
                    corners.append(pt)
        return (DB.XYZ(min(p.X for p in corners), min(p.Y for p in corners),
                       min(p.Z for p in corners)),
                DB.XYZ(max(p.X for p in corners), max(p.Y for p in corners),
                       max(p.Z for p in corners)))

    def _locate_plant(self, item):
        wanted = [v for v in (item.pnp_guid, item.acad_tag) if v]
        index = self._plant_index()
        for value in wanted:
            el = index.get(value.lower())
            if el is not None:
                return self._found(item, el, self.models[0])
        return LocatedItem(item, NOT_IN_REVIT)

    def _plant_index(self):
        """Tag / PnPGuid values on DirectShapes of the host model (built once)."""
        if self._plant is None:
            self._plant = {}
            for el in DB.FilteredElementCollector(self.doc).OfClass(DB.DirectShape):
                for pname in _PLANT_PARAMS:
                    p = el.LookupParameter(pname)
                    if p is not None and p.HasValue and p.StorageType == DB.StorageType.String:
                        val = p.AsString()
                        if val:
                            self._plant.setdefault(val.lower(), el)
        return self._plant
