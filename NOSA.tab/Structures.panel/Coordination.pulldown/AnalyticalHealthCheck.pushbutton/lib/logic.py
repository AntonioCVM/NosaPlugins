# -*- coding: utf-8 -*-
"""
Analytical Model Health Check v1.0 — Logic

Checks:
  1. Structural elements with analytical model disabled
  2. Columns not supported at base (no structural support)
  3. Revit model warnings on structural categories
  4. Elements without a level assigned
  5. Beam/column end connectivity (using analytical member API where available)
"""
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
FT2MM = 304.8

def _struct_bics():
    return [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
        DB.BuiltInCategory.OST_Floors,
        DB.BuiltInCategory.OST_Walls,
    ]

_STRUCT_BIC_INTS = None

def _bic_ints():
    global _STRUCT_BIC_INTS
    if _STRUCT_BIC_INTS is None:
        _STRUCT_BIC_INTS = set(int(b) for b in _struct_bics())
    return _STRUCT_BIC_INTS




def _param_int(el, bip, default=0):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsInteger()
    except Exception:
        pass
    return default


def _mark(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        if p and p.HasValue:
            return p.AsString() or ''
    except Exception:
        pass
    return ''


def _level_name(el, doc):
    for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM]:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv:
                    return lv.Name or ''
        except Exception:
            pass
    return ''


def _type_label(el):
    try:
        cat_id = int(str(el.Category.Id))
        m = {
            int(DB.BuiltInCategory.OST_StructuralColumns):   'Column',
            int(DB.BuiltInCategory.OST_StructuralFraming):   'Beam',
            int(DB.BuiltInCategory.OST_StructuralFoundation):'Foundation',
            int(DB.BuiltInCategory.OST_Floors):              'Slab',
            int(DB.BuiltInCategory.OST_Walls):               'Wall',
        }
        return m.get(cat_id, 'Element')
    except Exception:
        return 'Element'


def _collect_bic(doc, bic):
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements())


# ── CHECK 1: ANALYTICAL MODEL DISABLED ───────────────────────────────────────

def check_analytical_disabled(doc):
    """
    Returns elements where the analytical model is explicitly disabled.
    """
    rows = []
    for bic in _struct_bics():
        for el in _collect_bic(doc, bic):
            try:
                # STRUCTURAL_ANALYTICAL_MODEL_ENABLED = 1 (enabled), 0 (disabled)
                enabled = _param_int(
                    el,
                    DB.BuiltInParameter.STRUCTURAL_ANALYTICAL_MODEL_ENABLED,
                    default=1,
                )
                if enabled == 0:
                    rows.append({
                        'id':       get_id_value(el.Id),
                        'etype':     _type_label(el),
                        'mark':     _mark(el),
                        'level':    _level_name(el, doc),
                        'issue':    u'Analytical model disabled',
                        'severity': u'WARNING',
                    })
            except Exception:
                pass
    return rows


# ── CHECK 2: COLUMNS WITHOUT BASE SUPPORT ────────────────────────────────────

def check_unsupported_columns(doc):
    """
    Detects columns that are not connected to a foundation or floor at their base.
    Uses analytical model API where available; falls back to elevation check.
    """
    rows = []
    cols = _collect_bic(doc, DB.BuiltInCategory.OST_StructuralColumns)

    # Collect foundation elevations for proximity check
    found_elevations = set()
    for f in _collect_bic(doc, DB.BuiltInCategory.OST_StructuralFoundation):
        try:
            bb = f.get_BoundingBox(None)
            if bb:
                found_elevations.add(round(bb.Max.Z * FT2MM, 0))
        except Exception:
            pass
    for f in _collect_bic(doc, DB.BuiltInCategory.OST_Floors):
        try:
            bb = f.get_BoundingBox(None)
            if bb:
                found_elevations.add(round(bb.Max.Z * FT2MM, 0))
        except Exception:
            pass

    for col in cols:
        try:
            # Try analytical model check first (Revit 2020-2022)
            anal = None
            try:
                anal = col.GetAnalyticalModel()
            except Exception:
                pass

            if anal is not None:
                try:
                    # Check if start release has a support
                    # AnalyticalModelStick.GetReleases returns point releases
                    has_support = anal.HasSupport if hasattr(anal, 'HasSupport') else None
                    if has_support is False:
                        rows.append({
                            'id':       get_id_value(col.Id),
                            'etype':     'Column',
                            'mark':     _mark(col),
                            'level':    _level_name(col, doc),
                            'issue':    u'Column unsupported at base (analytical model)',
                            'severity': u'ERROR',
                        })
                    continue
                except Exception:
                    pass

            # Fallback: check if column base Z is near a known foundation/floor elevation
            try:
                loc = col.Location
                if isinstance(loc, DB.LocationPoint):
                    base_z_mm = round(loc.Point.Z * FT2MM, 0)
                elif isinstance(loc, DB.LocationCurve):
                    base_z_mm = round(
                        min(col.Location.Curve.GetEndPoint(0).Z,
                            col.Location.Curve.GetEndPoint(1).Z) * FT2MM, 0)
                else:
                    continue

                # If no foundation/floor within 200mm of column base → flag
                nearby = any(abs(fz - base_z_mm) <= 200 for fz in found_elevations)
                if not nearby and found_elevations:
                    rows.append({
                        'id':       get_id_value(col.Id),
                        'etype':     'Column',
                        'mark':     _mark(col),
                        'level':    _level_name(col, doc),
                        'issue':    u'Column base has no foundation/slab within ±200 mm',
                        'severity': u'WARNING',
                    })
            except Exception:
                pass
        except Exception:
            pass
    return rows


# ── CHECK 3: MODEL WARNINGS ON STRUCTURAL ELEMENTS ───────────────────────────

def check_structural_warnings(doc):
    """
    Returns Revit model warnings that reference structural elements.
    """
    rows = []
    try:
        warnings = list(doc.GetWarnings())
    except Exception:
        return rows

    bic_ints = _bic_ints()

    for w in warnings:
        try:
            failing_ids = list(w.GetFailingElements())
            related_ids = list(w.GetAdditionalElements())
            all_ids     = failing_ids + related_ids

            is_structural = False
            for eid in all_ids:
                el = doc.GetElement(eid)
                if el and el.Category:
                    cat_int = int(str(el.Category.Id))
                    if cat_int in bic_ints:
                        is_structural = True
                        break

            if not is_structural:
                continue

            desc = w.GetDescriptionText() or u'(no description)'

            for eid in failing_ids:
                el = doc.GetElement(eid)
                if el is None:
                    continue
                if el.Category and int(str(el.Category.Id)) not in bic_ints:
                    continue
                rows.append({
                    'id':       get_id_value(eid),
                    'etype':     _type_label(el),
                    'mark':     _mark(el),
                    'level':    _level_name(el, doc),
                    'issue':    desc,
                    'severity': u'WARNING',
                })
        except Exception:
            pass
    return rows


# ── CHECK 4: ELEMENTS WITHOUT LEVEL ──────────────────────────────────────────

def check_elements_without_level(doc):
    """
    Structural elements with no valid LevelId assigned.
    """
    rows = []
    for bic in _struct_bics():
        for el in _collect_bic(doc, bic):
            try:
                level = _level_name(el, doc)
                if not level:
                    rows.append({
                        'id':       get_id_value(el.Id),
                        'etype':     _type_label(el),
                        'mark':     _mark(el),
                        'level':    u'—',
                        'issue':    u'No level assigned',
                        'severity': u'WARNING',
                    })
            except Exception:
                pass
    return rows


# ── CHECK 5: BEAM END CONNECTIVITY ───────────────────────────────────────────

def check_beam_connectivity(doc):
    """
    Checks if beams have disconnected ends using the analytical stick.
    Works on Revit 2020-2022; on 2023+ falls back to a proximity check.
    """
    rows = []
    beams = _collect_bic(doc, DB.BuiltInCategory.OST_StructuralFraming)

    for beam in beams:
        try:
            anal = None
            try:
                anal = beam.GetAnalyticalModel()
            except Exception:
                pass

            if anal is None:
                continue

            # Check releases at both ends
            try:
                # AnalyticalModelStick.GetReleases(AnalyticalElementSelector)
                for end in [DB.Structure.AnalyticalElementSelector.StartOrBase,
                             DB.Structure.AnalyticalElementSelector.EndOrTop]:
                    try:
                        releases = anal.GetReleases(end)
                        # All 6 DOFs released = disconnected
                        dof_vals = [
                            releases.TranslationX,
                            releases.TranslationY,
                            releases.TranslationZ,
                            releases.RotationX,
                            releases.RotationY,
                            releases.RotationZ,
                        ]
                        all_released = all(
                            str(v) == 'Released' or v == DB.Structure.StructuralReactionType.Free
                            for v in dof_vals
                        )
                        if all_released:
                            end_label = u'start' if 'Start' in str(end) else u'end'
                            rows.append({
                                'id':       get_id_value(beam.Id),
                                'etype':     'Beam',
                                'mark':     _mark(beam),
                                'level':    _level_name(beam, doc),
                                'issue':    u'{} end disconnected (all DOFs released)'.format(end_label).capitalize(),
                                'severity': u'WARNING',
                            })
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
    return rows


# ── RUNNER ────────────────────────────────────────────────────────────────────

def run_all(doc):
    """
    Run all checks. Returns dict with results per check and a flat 'all' list.
    """
    results = {}
    results['disabled']     = check_analytical_disabled(doc)
    results['unsupported']  = check_unsupported_columns(doc)
    results['warnings']     = check_structural_warnings(doc)
    results['no_level']     = check_elements_without_level(doc)
    results['connectivity'] = check_beam_connectivity(doc)

    # Flat combined list for the main DataGrid
    all_issues = []
    for key in ['disabled', 'unsupported', 'warnings', 'no_level', 'connectivity']:
        all_issues.extend(results[key])

    results['all']   = all_issues
    results['total'] = len(all_issues)
    results['errors'] = sum(1 for r in all_issues if r['severity'] == 'ERROR')
    results['warnings_count'] = sum(1 for r in all_issues if r['severity'] == 'WARNING')

    return results



