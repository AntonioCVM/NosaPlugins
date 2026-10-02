# -*- coding: utf-8 -*-
import os
import sys
from Autodesk.Revit import DB
import random
from nosa_utils.telemetry import log_swallowed
_LOG = u'viewoverrides'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value, element_id_from_int

_PALETTE = [
    (220, 60,  60),  (255, 130,  0),  (255, 200,  0),  (50,  180, 80),
    (0,  160, 200),  (80,  100, 220), (160, 60,  200), (220, 60,  140),
    (0,  180, 180),  (140, 180, 40),  (200, 100, 50),  (100, 130, 200),
    (80,  160, 80),  (220, 140, 60),  (60,  100, 160), (180, 80,  80),
]


def _color(r, g, b):
    return DB.Color(r, g, b)


def get_categories_in_view(doc, view):
    cats = set()
    col = DB.FilteredElementCollector(doc, view.Id) \
            .WhereElementIsNotElementType() \
            .ToElements()
    for el in col:
        try:
            c = el.Category
            if c is not None:
                cats.add((get_id_value(c.Id), c.Name))
        except Exception:
            log_swallowed(_LOG, u'get_categories_in_view')
    return sorted(cats, key=lambda x: x[1])


def get_instance_params_for_category(doc, view, category_id):
    """Return sorted list of parameter names available on elements in a category."""
    col = DB.FilteredElementCollector(doc, view.Id) \
            .OfCategoryId(element_id_from_int(category_id)) \
            .WhereElementIsNotElementType() \
            .ToElements()
    param_names = set()
    for el in list(col)[:20]:  # sample first 20
        for p in el.Parameters:
            try:
                if p.StorageType in (DB.StorageType.String, DB.StorageType.Integer,
                                     DB.StorageType.Double):
                    param_names.add(p.Definition.Name)
            except Exception:
                log_swallowed(_LOG, u'get_instance_params_for_category')
    return sorted(param_names)


def get_param_value_str(el, param_name):
    p = el.LookupParameter(param_name)
    if p is None or not p.HasValue:
        return u'<no value>'
    st = p.StorageType
    if st == DB.StorageType.String:
        v = p.AsString()
        return v if v else u'<empty>'
    if st == DB.StorageType.Integer:
        return str(p.AsInteger())
    if st == DB.StorageType.Double:
        return u'{:.2f}'.format(p.AsDouble())
    return u'<unknown>'


def collect_values_for_param(doc, view, category_id, param_name):
    col = DB.FilteredElementCollector(doc, view.Id) \
            .OfCategoryId(element_id_from_int(category_id)) \
            .WhereElementIsNotElementType() \
            .ToElements()
    value_map = {}  # value_str -> [element_ids]
    for el in col:
        v = get_param_value_str(el, param_name)
        if v not in value_map:
            value_map[v] = []
        value_map[v].append(el.Id)
    return value_map


def apply_overrides(doc, view, value_map, color_assignments):
    """Apply solid fill colour overrides per value group. Returns (ok, cleared)."""
    ogs_reset = DB.OverrideGraphicSettings()
    ok = 0
    # First clear all elements in view for the selected categories
    for ids in value_map.values():
        for eid in ids:
            view.SetElementOverrides(eid, ogs_reset)

    for val_str, ids in value_map.items():
        rgb = color_assignments.get(val_str)
        if rgb is None:
            continue
        r, g, b = rgb
        ogs = DB.OverrideGraphicSettings()
        col = _color(r, g, b)
        try:
            ogs.SetSurfaceForegroundPatternColor(col)
            ogs.SetSurfaceForegroundPatternVisible(True)
            pat_id = _get_solid_fill_pattern_id(doc)
            if pat_id:
                ogs.SetSurfaceForegroundPatternId(pat_id)
        except Exception:
            log_swallowed(_LOG, u'apply_overrides')
        try:
            ogs.SetProjectionLineColor(col)
        except Exception:
            log_swallowed(_LOG, u'apply_overrides')
        for eid in ids:
            view.SetElementOverrides(eid, ogs)
            ok += 1
    return ok


def _get_solid_fill_pattern_id(doc):
    try:
        fps = DB.FilteredElementCollector(doc) \
                .OfClass(DB.FillPatternElement) \
                .ToElements()
        for fp in fps:
            pat = fp.GetFillPattern()
            if pat.IsSolidFill:
                return fp.Id
    except Exception:
        log_swallowed(_LOG, u'_get_solid_fill_pattern_id')
    return None


def clear_overrides(doc, view, value_map):
    ogs_reset = DB.OverrideGraphicSettings()
    for ids in value_map.values():
        for eid in ids:
            view.SetElementOverrides(eid, ogs_reset)


def assign_colors(values):
    """Assign a palette colour (r,g,b) to each unique value string."""
    result = {}
    palette = list(_PALETTE)
    for i, v in enumerate(sorted(values)):
        result[v] = palette[i % len(palette)]
    return result
