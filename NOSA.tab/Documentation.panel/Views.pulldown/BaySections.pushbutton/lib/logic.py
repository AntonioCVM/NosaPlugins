# -*- coding: utf-8 -*-
import os
import sys
from Autodesk.Revit import DB
import math

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value


def get_grids(doc):
    grids = DB.FilteredElementCollector(doc) \
               .OfClass(DB.Grid) \
               .WhereElementIsNotElementType() \
               .ToElements()
    result = []
    for g in grids:
        try:
            curve = g.Curve
            result.append({
                'id':   g.Id,
                'name': g.Name,
                'curve': curve,
                'is_arc': isinstance(curve, DB.Arc),
            })
        except Exception:
            pass
    return sorted(result, key=lambda x: x['name'])


def safe_element_name(el):
    """Get element name with Revit 2026+ fallback (Element.Name throws AttributeError)."""
    try:
        n = el.Name
        if n:
            return n
    except Exception:
        pass
    for bip in (DB.BuiltInParameter.SYMBOL_NAME_PARAM,
                DB.BuiltInParameter.ALL_MODEL_TYPE_NAME,
                DB.BuiltInParameter.VIEW_NAME):
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                v = p.AsString()
                if v:
                    return v
        except Exception:
            pass
    return u'Type {}'.format(get_id_value(el.Id))


def get_view_family_types(doc):
    vfts = DB.FilteredElementCollector(doc) \
              .OfClass(DB.ViewFamilyType) \
              .ToElements()
    section_types = [vft for vft in vfts if vft.ViewFamily == DB.ViewFamily.Section]
    return section_types


def get_3d_view_type(doc):
    vfts = DB.FilteredElementCollector(doc) \
              .OfClass(DB.ViewFamilyType) \
              .ToElements()
    for vft in vfts:
        if vft.ViewFamily == DB.ViewFamily.ThreeDimensional:
            return vft
    return None


def _grid_midpoint(curve):
    try:
        return curve.Evaluate(0.5, True)
    except Exception:
        try:
            return (curve.GetEndPoint(0) + curve.GetEndPoint(1)) / 2.0
        except Exception:
            return DB.XYZ.Zero


def _grid_direction(curve):
    try:
        p0 = curve.GetEndPoint(0)
        p1 = curve.GetEndPoint(1)
        return (p1 - p0).Normalize()
    except Exception:
        return DB.XYZ.BasisX


def _perpendicular(direction):
    return DB.XYZ(-direction.Y, direction.X, 0).Normalize()


def _get_model_extents(doc):
    """Approximate model extents for section depth."""
    try:
        collector = DB.FilteredElementCollector(doc) \
                      .WhereElementIsNotElementType() \
                      .ToElements()
        mins, maxs = [], []
        count = 0
        for el in collector:
            if count > 500:
                break
            try:
                bb = el.get_BoundingBox(None)
                if bb:
                    mins.append(bb.Min)
                    maxs.append(bb.Max)
                    count += 1
            except Exception:
                pass
        if not mins:
            return -100, 100, -100, 100, -10, 50  # defaults in feet
        min_x = min(p.X for p in mins)
        min_y = min(p.Y for p in mins)
        min_z = min(p.Z for p in mins)
        max_x = max(p.X for p in maxs)
        max_y = max(p.Y for p in maxs)
        max_z = max(p.Z for p in maxs)
        return min_x, max_x, min_y, max_y, min_z, max_z
    except Exception:
        return -100, 100, -100, 100, -10, 50


def create_section_view(doc, view_type_id, origin, look_dir, up_dir,
                        far_clip, width, height, view_name):
    """
    Create a single section view.
    look_dir: direction the section looks at (X of the right-hand frame).
    up_dir:   vertical (Z of the section frame) — typically BasisZ.
    """
    right_dir = look_dir.CrossProduct(up_dir).Normalize()

    transform = DB.Transform.Identity
    transform.BasisX = right_dir
    transform.BasisY = up_dir
    transform.BasisZ = look_dir.Negate()
    transform.Origin = origin

    bb = DB.BoundingBoxXYZ()
    bb.Transform = transform
    bb.Min = DB.XYZ(-width / 2.0, -height / 2.0, 0)
    bb.Max = DB.XYZ( width / 2.0,  height / 2.0, far_clip)

    view = DB.ViewSection.CreateSection(doc, view_type_id, bb)
    try:
        view.Name = view_name[:60]
    except Exception:
        pass
    return view


def create_bay_sections(doc, grid_a_id, grid_b_id, section_type_id,
                        depth_offset_ft=10.0, height_offset_ft=5.0,
                        view_name_prefix=u'S', model_extents=None):
    """
    Create longitudinal and transverse sections between two grids.
    Returns list of created view Ids.

    model_extents: pre-computed (min_x, max_x, min_y, max_y, min_z, max_z)
    tuple from _get_model_extents(doc) — the model's own extents don't
    depend on which grid pair is selected, so callers looping over many
    grid pairs should compute this once and pass it in, instead of
    re-scanning the whole document on every call.
    """
    grid_a = doc.GetElement(grid_a_id)
    grid_b = doc.GetElement(grid_b_id)
    if grid_a is None or grid_b is None:
        return []

    if model_extents is None:
        model_extents = _get_model_extents(doc)
    min_x, max_x, min_y, max_y, min_z, max_z = model_extents
    model_height = max_z - min_z + height_offset_ft
    model_width  = math.sqrt((max_x - min_x)**2 + (max_y - min_y)**2) + depth_offset_ft * 2

    mid_a = _grid_midpoint(grid_a.Curve)
    mid_b = _grid_midpoint(grid_b.Curve)
    origin = DB.XYZ(
        (mid_a.X + mid_b.X) / 2.0,
        (mid_a.Y + mid_b.Y) / 2.0,
        min_z - height_offset_ft / 2.0,
    )

    dir_a = _grid_direction(grid_a.Curve)
    dir_b = _grid_direction(grid_b.Curve)
    up = DB.XYZ.BasisZ

    name_ab = u'{}-{}-{}'.format(view_name_prefix, grid_a.Name, grid_b.Name)

    created = []
    # Longitudinal section (along grid A direction)
    try:
        v1 = create_section_view(doc, section_type_id, origin, dir_a, up,
                                 model_width, model_width, model_height,
                                 u'{} Long'.format(name_ab))
        created.append(v1.Id)
    except Exception:
        pass

    # Transverse section (perpendicular to grid A)
    try:
        perp = _perpendicular(dir_a)
        v2 = create_section_view(doc, section_type_id, origin, perp, up,
                                 model_width, model_width, model_height,
                                 u'{} Trans'.format(name_ab))
        created.append(v2.Id)
    except Exception:
        pass

    return created
