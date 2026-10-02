# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'poursequenceplanner'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value

_POUR_PARAM_NAMES = ('Pour Phase', 'NOSA_POUR_PHASE', 'Comments')
_DEFAULT_PHASES = [u'Phase 1', u'Phase 2', u'Phase 3', u'Phase 4']

_PHASE_COLOURS = [
    (255, 95, 0), (50, 160, 220), (80, 180, 80), (200, 80, 80),
    (160, 80, 200), (220, 180, 40), (100, 130, 200), (180, 100, 60),
]


def _concrete_categories():
    return [
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_Walls,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]


def get_levels(doc):
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements())
    return sorted(levels, key=lambda l: l.Elevation)


def _find_pour_param(el):
    for name in _POUR_PARAM_NAMES:
        try:
            p = el.LookupParameter(name)
            if p and not p.IsReadOnly and p.StorageType == DB.StorageType.String:
                return p
        except Exception:
            log_swallowed(_LOG, u'_find_pour_param')
    return None


def collect_elements_on_level(doc, level_id, categories=None):
    cats = categories or _concrete_categories()
    elements = []
    for cat in cats:
        try:
            col = (DB.FilteredElementCollector(doc)
                   .OfCategory(cat)
                   .WhereElementIsNotElementType()
                   .ToElements())
            for el in col:
                try:
                    lvl = el.LevelId
                    if lvl and get_id_value(lvl) == get_id_value(level_id):
                        elements.append(el)
                except Exception:
                    log_swallowed(_LOG, u'collect_elements_on_level')
        except Exception:
            log_swallowed(_LOG, u'collect_elements_on_level')
    return elements


def assign_pour_phase(doc, level_id, phase_name, zone_filter=None):
    """Write pour phase to concrete elements on a level. Optional zone name filter in Mark."""
    assigned = skipped = 0
    zone_filter = (zone_filter or u'').strip().lower()

    with DB.Transaction(doc, u'NOSA — Pour Sequence') as t:
        t.Start()
        for el in collect_elements_on_level(doc, level_id):
            if zone_filter:
                try:
                    mark_p = el.LookupParameter('Mark')
                    mark = (mark_p.AsString() or u'').lower() if mark_p else u''
                    if zone_filter not in mark and zone_filter not in (el.Name or u'').lower():
                        skipped += 1
                        continue
                except Exception:
                    skipped += 1
                    continue
            p = _find_pour_param(el)
            if p is None:
                skipped += 1
                continue
            try:
                p.Set(phase_name)
                assigned += 1
            except Exception:
                skipped += 1
        t.Commit()
    return assigned, skipped


def _solid_pattern_id(doc):
    try:
        for pat in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement).ToElements():
            if pat.GetFillPattern().IsSolidFill:
                return pat.Id
    except Exception:
        log_swallowed(_LOG, u'_solid_pattern_id')
    return DB.ElementId.InvalidElementId


def apply_phase_colours(doc, view, phase_names):
    """Apply graphic overrides in view grouped by pour phase parameter value."""
    pat_id = _solid_pattern_id(doc)
    phase_set = set(phase_names)
    colour_map = {}
    for i, name in enumerate(phase_names):
        colour_map[name] = _PHASE_COLOURS[i % len(_PHASE_COLOURS)]

    updated = 0
    with DB.Transaction(doc, u'NOSA — Pour Sequence Colours') as t:
        t.Start()
        for cat in _concrete_categories():
            try:
                col = (DB.FilteredElementCollector(doc, view.Id)
                       .OfCategory(cat)
                       .WhereElementIsNotElementType()
                       .ToElements())
            except Exception:
                continue
            for el in col:
                p = _find_pour_param(el)
                if p is None or not p.HasValue:
                    continue
                val = (p.AsString() or u'').strip()
                if val not in phase_set:
                    continue
                r, g, b = colour_map[val]
                ogs = DB.OverrideGraphicSettings()
                col_obj = DB.Color(r, g, b)
                try:
                    ogs.SetSurfaceForegroundPatternColor(col_obj)
                    ogs.SetSurfaceForegroundPatternVisible(True)
                    if pat_id != DB.ElementId.InvalidElementId:
                        ogs.SetSurfaceForegroundPatternId(pat_id)
                    ogs.SetProjectionLineColor(col_obj)
                    view.SetElementOverrides(el.Id, ogs)
                    updated += 1
                except Exception:
                    log_swallowed(_LOG, u'apply_phase_colours')
        t.Commit()
    return updated


def summarise_phases(doc):
    counts = {}
    for cat in _concrete_categories():
        for el in (DB.FilteredElementCollector(doc)
                   .OfCategory(cat)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            p = _find_pour_param(el)
            if p and p.HasValue:
                val = (p.AsString() or u'<empty>').strip()
                counts[val] = counts.get(val, 0) + 1
    return counts
