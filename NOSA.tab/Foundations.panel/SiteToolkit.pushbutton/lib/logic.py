# -*- coding: utf-8 -*-
"""
Site Toolkit — Logic

Three read-only inventories that Survey.pulldown doesn't cover (which is
setting-out tables and pile coordinate export, not site-scale data):
  - Topography: every TopographySurface / Toposolid in the model.
  - Property lines: every PropertyLine, with perimeter length.
  - Site reference: Project Base Point / Survey Point position and angle
    to true north.
"""
import os, sys, math

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value, element_name

_FT_TO_MM = 304.8


def _bbox_elevation_range_mm(el):
    try:
        bbox = el.get_BoundingBox(None)
        if bbox is None:
            return None, None
        return bbox.Min.Z * _FT_TO_MM, bbox.Max.Z * _FT_TO_MM
    except Exception:
        return None, None


def _bbox_footprint_sqm(el):
    """Bounding-box footprint area — an approximation, not the true surface
    area (which needs a parameter that isn't reliably named the same way
    across TopographySurface and Toposolid)."""
    try:
        bbox = el.get_BoundingBox(None)
        if bbox is None:
            return None
        dx_mm = (bbox.Max.X - bbox.Min.X) * _FT_TO_MM
        dy_mm = (bbox.Max.Y - bbox.Min.Y) * _FT_TO_MM
        return (dx_mm * dy_mm) / 1.0e6
    except Exception:
        return None


def get_topography(doc):
    """Every TopographySurface (legacy) and Toposolid (2024+) in the model."""
    rows = []

    try:
        legacy = list(
            DB.FilteredElementCollector(doc)
            .OfClass(DB.Architecture.TopographySurface)
            .WhereElementIsNotElementType()
            .ToElements()
        )
    except Exception:
        legacy = []
    for el in legacy:
        z_min, z_max = _bbox_elevation_range_mm(el)
        name = element_name(el) or u'—'
        rows.append({
            'id': get_id_value(el.Id), 'kind': u'TopographySurface',
            'name': name, 'z_min': z_min, 'z_max': z_max,
            'footprint_sqm': _bbox_footprint_sqm(el),
        })

    try:
        toposolids = list(
            DB.FilteredElementCollector(doc)
            .OfClass(DB.Toposolid)
            .WhereElementIsNotElementType()
            .ToElements()
        )
    except Exception:
        toposolids = []
    for el in toposolids:
        z_min, z_max = _bbox_elevation_range_mm(el)
        name = element_name(el) or u'—'
        rows.append({
            'id': get_id_value(el.Id), 'kind': u'Toposolid',
            'name': name, 'z_min': z_min, 'z_max': z_max,
            'footprint_sqm': _bbox_footprint_sqm(el),
        })

    rows.sort(key=lambda r: (r['kind'], r['id']))
    return rows


def get_property_lines(doc):
    """Every PropertyLine, with segment count and perimeter length."""
    rows = []
    try:
        lines = list(
            DB.FilteredElementCollector(doc)
            .OfClass(DB.PropertyLine)
            .WhereElementIsNotElementType()
            .ToElements()
        )
    except Exception:
        lines = []

    for el in lines:
        try:
            curves = list(el.GetProfile())
        except Exception:
            curves = []
        total_len_mm = 0.0
        for c in curves:
            try:
                total_len_mm += c.Length * _FT_TO_MM
            except Exception:
                pass
        name = element_name(el) or u'—'
        rows.append({
            'id': get_id_value(el.Id), 'name': name,
            'segments': len(curves), 'perimeter_mm': total_len_mm,
        })

    rows.sort(key=lambda r: r['id'])
    return rows


def _base_point_row(doc, label, getter):
    try:
        bp = getter(doc)
    except Exception:
        bp = None
    if bp is None:
        return {'label': label, 'found': False, 'ew_mm': None, 'ns_mm': None,
                'elev_mm': None, 'angle_deg': None}

    def _param_mm(bip):
        try:
            p = bp.get_Parameter(bip)
            return p.AsDouble() * _FT_TO_MM if p else None
        except Exception:
            return None

    def _angle_deg():
        try:
            p = bp.get_Parameter(DB.BuiltInParameter.BASEPOINT_ANGLETON_PARAM)
            return math.degrees(p.AsDouble()) if p else None
        except Exception:
            return None

    return {
        'label': label, 'found': True,
        'ew_mm': _param_mm(DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM),
        'ns_mm': _param_mm(DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM),
        'elev_mm': _param_mm(DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM),
        'angle_deg': _angle_deg(),
    }


def get_site_reference(doc):
    """Project Base Point and Survey Point — position and angle to true
    north, read straight from the model (no assumptions/defaults)."""
    return [
        _base_point_row(doc, u'Project Base Point', DB.BasePoint.GetProjectBasePoint),
        _base_point_row(doc, u'Survey Point', DB.BasePoint.GetSurveyPoint),
    ]
