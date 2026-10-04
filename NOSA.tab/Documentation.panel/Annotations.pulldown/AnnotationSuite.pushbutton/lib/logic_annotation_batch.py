# -*- coding: utf-8 -*-
"""
AnnotationBatch Logic — Batch-apply spot elevations, structural beam tags,
column marks and grid bubbles to structural views based on configurable rules.
"""
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils import unit_conversion as _uc10
from nosa_utils.telemetry import log_swallowed
_LOG = u'annotationsuite.logic_annotation_batch'
_FT_TO_MM = _uc10.FT_TO_MM




def _collect(doc, bic, view=None):
    if view:
        return list(DB.FilteredElementCollector(doc, view.Id)
                      .OfCategory(bic).WhereElementIsNotElementType().ToElements())
    return list(DB.FilteredElementCollector(doc)
                  .OfCategory(bic).WhereElementIsNotElementType().ToElements())


def get_structural_views(doc):
    """Return all taggable views (plans, sections, details, elevations)."""
    # Use int comparison to avoid IronPython enum equality issues
    _VALID = {
        int(DB.ViewType.FloorPlan),
        int(DB.ViewType.Section),
        int(DB.ViewType.Detail),
        int(DB.ViewType.Elevation),
        int(DB.ViewType.CeilingPlan),
        int(DB.ViewType.AreaPlan),
        int(DB.ViewType.EngineeringPlan),
    }
    result = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate: continue
            if int(v.ViewType) in _VALID:
                result.append(v)
        except Exception:
            log_swallowed(_LOG, u'get_structural_views')
    return sorted(result, key=lambda v: v.Name)


def get_tag_families(doc, bic):
    """Return list of {'name','id','symbol'} for tag families matching bic."""
    _TAG_BIC_MAP = {
        DB.BuiltInCategory.OST_StructuralColumns:    DB.BuiltInCategory.OST_StructuralColumnTags,
        DB.BuiltInCategory.OST_StructuralFraming:    DB.BuiltInCategory.OST_StructuralFramingTags,
        DB.BuiltInCategory.OST_StructuralFoundation: DB.BuiltInCategory.OST_StructuralFoundationTags,
    }
    tag_bic = _TAG_BIC_MAP.get(bic)
    if tag_bic is None:
        return []
    tags = []
    try:
        syms = (DB.FilteredElementCollector(doc)
                  .OfClass(DB.FamilySymbol)
                  .OfCategory(tag_bic)
                  .ToElements())
        for sym in syms:
            try:
                fam_name = sym.Family.Name if (hasattr(sym, 'Family') and sym.Family) else ''
                sym_name = element_name(sym)
                label = '{}: {}'.format(fam_name, sym_name) if fam_name else sym_name
                tags.append({'name': label, 'id': sym.Id, 'symbol': sym})
            except Exception:
                log_swallowed(_LOG, u'get_tag_families')
    except Exception:
        log_swallowed(_LOG, u'get_tag_families')
    return sorted(tags, key=lambda t: t['name'])


def get_spot_elevation_types(doc):
    types = DB.FilteredElementCollector(doc).OfClass(DB.SpotDimensionType).ToElements()
    return [t for t in types if t.StyleType == DB.SpotDimensionStyleType.SpotElevation]


# ─────────────────────────────────────────────────
# Batch annotation actions
# ─────────────────────────────────────────────────

def batch_spot_elevations(doc, views, spot_type_id=None):
    """
    Place spot elevations on the top face of columns and beams in selected views.
    Returns {created, skipped, failed}.
    """
    created = skipped = failed = 0
    ref_opts = DB.Options()
    ref_opts.ComputeReferences = True

    for view in views:
        if view.ViewType not in (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan):
            skipped += 1
            continue
        for bic in (DB.BuiltInCategory.OST_StructuralColumns,
                    DB.BuiltInCategory.OST_StructuralFraming):
            for el in _collect(doc, bic, view):
                try:
                    bbox = el.get_BoundingBox(view)
                    if not bbox: continue
                    # Reference point: mid of element in view
                    mid_x = (bbox.Min.X + bbox.Max.X) / 2.0
                    mid_y = (bbox.Min.Y + bbox.Max.Y) / 2.0
                    z     = bbox.Max.Z
                    origin = DB.XYZ(mid_x, mid_y, z)
                    bend   = DB.XYZ(mid_x + 0.5, mid_y, z)
                    end    = DB.XYZ(mid_x + 1.0, mid_y, z)
                    ref    = DB.Reference(el)
                    sd = DB.Document.Create(doc).NewSpotElevation(
                        view, ref, origin, bend, end, origin, False
                    )
                    if spot_type_id and spot_type_id != DB.ElementId.InvalidElementId:
                        sd.ChangeTypeId(spot_type_id)
                    created += 1
                except Exception:
                    failed += 1
    return {'created': created, 'skipped': skipped, 'failed': failed}


def batch_tag_elements(doc, views, bic, tag_symbol_id, use_leader=False):
    """
    Place tags on elements of bic category in selected views.
    """
    created = skipped = failed = 0
    for view in views:
        existing = set()
        try:
            for t in _collect(doc, DB.BuiltInCategory.OST_Tags, view):
                try:
                    existing.add(get_id_value(t.TaggedElementId))
                except Exception:
                    log_swallowed(_LOG, u'batch_tag_elements')
        except Exception:
            log_swallowed(_LOG, u'batch_tag_elements')
        for el in _collect(doc, bic, view):
            eid = get_id_value(el.Id)
            if eid in existing:
                skipped += 1
                continue
            try:
                loc = el.Location
                if isinstance(loc, DB.LocationPoint):
                    pt = loc.Point
                elif isinstance(loc, DB.LocationCurve):
                    pt = loc.Curve.Evaluate(0.5, True)
                else:
                    skipped += 1; continue
                tag = DB.IndependentTag.Create(
                    doc, view.Id, DB.Reference(el),
                    use_leader, DB.TagMode.TM_ADDBY_CATEGORY,
                    DB.TagOrientation.Horizontal, pt
                )
                if tag_symbol_id and tag_symbol_id != DB.ElementId.InvalidElementId:
                    tag.ChangeTypeId(tag_symbol_id)
                created += 1
            except Exception:
                failed += 1
    return {'created': created, 'skipped': skipped, 'failed': failed}


def batch_grid_bubbles(doc, views, show_bubbles=True):
    """Toggle grid bubble visibility in selected views."""
    updated = failed = 0
    grids = _collect(doc, DB.BuiltInCategory.OST_Grids)
    for view in views:
        for grid in grids:
            try:
                grid.ShowBubbleInView(
                    DB.DatumEnds.End0 if show_bubbles else DB.DatumEnds.End0,
                    view
                )
                updated += 1
            except Exception:
                failed += 1
    return {'updated': updated, 'failed': failed}
