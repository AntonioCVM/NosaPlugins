# -*- coding: utf-8 -*-
"""
Survey Layout Table v1.0 — Logic

Collects structural point elements (columns, piles, pile caps, isolated foundations)
and returns their survey coordinates (X, Y, Z) with descriptive attributes.
"""
import math, io, csv
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils import unit_conversion as _uc10
FT2MM = _uc10.FT_TO_MM

_PILE_KEYWORDS = [
    'pile', 'pilote', 'pila', 'pilón', 'pilon',
    'micropile', 'micropilote', 'micropilon', 'micro pile', 'micro-pile',
    'pin pile', 'driven pile', 'bored pile', 'cast-in-situ pile',
    'cfa', 'continuous flight auger',
    'spun pile', 'precast pile', 'phc pile',
    'h-pile', 'sheet pile', 'tubular pile',
]
_PILECAP_KEYWORDS = [
    'encepado', 'pile cap', 'pilecap', 'pile-cap',
    'cap beam', 'pilecap footing', 'group cap',
    'ceppo', 'groupe de pieux',
]

def _survey_bics():
    return [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]

# ── helpers ───────────────────────────────────────────────────────────────────



def _ps(el, bip, default=u''):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsString() or default
    except Exception:
        pass
    return default


def _family_name(el):
    try:
        if isinstance(el, DB.FamilyInstance):
            return el.Symbol.FamilyName or u''
    except Exception:
        pass
    return u''


def _type_name(el, doc):
    try:
        t = doc.GetElement(el.GetTypeId())
        return element_name(t)
    except Exception:
        return u''


def _name_contains(el, doc, keywords):
    fam = _family_name(el).lower()
    typ = _type_name(el, doc).lower()
    return any(k in fam or k in typ for k in keywords)


def _bb_dims(el):
    """Return (x_range_mm, y_range_mm, z_range_mm) from bounding box, or None."""
    try:
        bb = el.get_BoundingBox(None)
        if bb:
            return (abs(bb.Max.X - bb.Min.X) * FT2MM,
                    abs(bb.Max.Y - bb.Min.Y) * FT2MM,
                    abs(bb.Max.Z - bb.Min.Z) * FT2MM)
    except Exception:
        pass
    return None


def _looks_like_pile_by_geometry(el):
    """
    Piles are tall and narrow: depth (Z) >> max(X, Y).
    Heuristic: Z > 3 × max(X_plan, Y_plan).
    Also requires minimum depth of 500 mm to exclude short stubs.
    """
    dims = _bb_dims(el)
    if dims is None:
        return False
    x, y, z = dims
    plan = max(x, y)
    if plan < 1.0:  # degenerate element
        return False
    return z > 500 and z > 3.0 * plan


def _looks_like_pilecap_by_geometry(el):
    """
    Pile caps are wide and relatively shallow: max(X,Y) >> Z.
    Heuristic: max(X,Y) > 1.5 × Z AND Z < 2500 mm (not a wall).
    """
    dims = _bb_dims(el)
    if dims is None:
        return False
    x, y, z = dims
    plan = max(x, y)
    if z < 1.0:
        return False
    return plan > 1.5 * z and z < 2500


def _has_curve_location(el):
    """Return True if element has a LocationCurve (like a pile modelled as framing/column)."""
    try:
        return isinstance(el.Location, DB.LocationCurve)
    except Exception:
        return False


def _is_pile(el, doc):
    # 1. Explicit NOSA shared parameter
    try:
        p = el.LookupParameter('NOSA_IsPile')
        if p and p.AsInteger() == 1:
            return True
    except Exception:
        pass
    # 2. Family / type name keyword match
    if _name_contains(el, doc, _PILE_KEYWORDS):
        return True
    # 3. Geometry heuristic: deep & narrow
    if _looks_like_pile_by_geometry(el):
        return True
    # 4. LocationCurve on a structural column → typically a slanted/raking pile
    if _has_curve_location(el):
        return True
    return False


def _is_pilecap(el, doc):
    # 1. Explicit NOSA shared parameter
    try:
        p = el.LookupParameter('NOSA_IsPileCap')
        if p and p.AsInteger() == 1:
            return True
    except Exception:
        pass
    # 2. Family / type name keyword match
    if _name_contains(el, doc, _PILECAP_KEYWORDS):
        return True
    # 3. Geometry heuristic: wide & shallow (typical pilecap shape)
    if _looks_like_pilecap_by_geometry(el):
        return True
    return False


def _level_name(el, doc):
    for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM]:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv:
                    return lv.Name or u''
        except Exception:
            pass
    return u''


def _material_name(el, doc):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if p and p.HasValue:
            mat = doc.GetElement(p.AsElementId())
            if mat:
                return mat.Name or u'—'
    except Exception:
        pass
    return u'—'


def _element_location(el):
    """Return (x_mm, y_mm, z_mm, rotation_deg)."""
    try:
        loc = el.Location
        if isinstance(loc, DB.LocationPoint):
            pt = loc.Point
            return (round(pt.X * FT2MM, 1),
                    round(pt.Y * FT2MM, 1),
                    round(pt.Z * FT2MM, 1),
                    round(math.degrees(loc.Rotation), 2))
        if isinstance(loc, DB.LocationCurve):
            p0 = loc.Curve.GetEndPoint(0)
            p1 = loc.Curve.GetEndPoint(1)
            base = p0 if p0.Z <= p1.Z else p1
            top  = p1 if p0.Z <= p1.Z else p0
            dx = top.X - base.X
            dy = top.Y - base.Y
            rot = math.degrees(math.atan2(dy, dx)) if (dx or dy) else 0.0
            return (round(base.X * FT2MM, 1),
                    round(base.Y * FT2MM, 1),
                    round(base.Z * FT2MM, 1),
                    round(rot, 2))
    except Exception:
        pass
    try:
        bb = el.get_BoundingBox(None)
        if bb:
            cx = (bb.Min.X + bb.Max.X) / 2 * FT2MM
            cy = (bb.Min.Y + bb.Max.Y) / 2 * FT2MM
            cz = bb.Min.Z * FT2MM
            return (round(cx, 1), round(cy, 1), round(cz, 1), 0.0)
    except Exception:
        pass
    return (None, None, None, 0.0)


# ── category classification ───────────────────────────────────────────────────

CAT_ALL        = None
CAT_COLUMN     = u'Column'
CAT_PILE       = u'Pile'
CAT_PILECAP    = u'Pile Cap'
CAT_FOUNDATION = u'Foundation'

FILTER_OPTIONS = [CAT_COLUMN, CAT_PILE, CAT_PILECAP, CAT_FOUNDATION]


def _classify(el, doc, bic):
    """
    Classification priority:
    - Structural Columns: pile (tall/narrow or explicit) → else column
    - Structural Foundations:
        * explicit NOSA param wins
        * keyword match on pile name → pile (some firms model piles as foundations)
        * keyword match on pilecap name → pile cap
        * geometry: tall/narrow → pile; wide/flat → pile cap
        * default → isolated foundation
    """
    if bic == DB.BuiltInCategory.OST_StructuralColumns:
        # For columns: piles are tall/narrow or have pile keyword
        # Normal columns tend to be short relative to their plan size
        if _is_pile(el, doc):
            return CAT_PILE
        return CAT_COLUMN

    # --- OST_StructuralFoundation ---
    # Explicit params take priority
    try:
        p = el.LookupParameter('NOSA_IsPile')
        if p and p.AsInteger() == 1:
            return CAT_PILE
    except Exception:
        pass
    try:
        p = el.LookupParameter('NOSA_IsPileCap')
        if p and p.AsInteger() == 1:
            return CAT_PILECAP
    except Exception:
        pass

    # Keyword match — check pilecap FIRST (more specific)
    if _name_contains(el, doc, _PILECAP_KEYWORDS):
        return CAT_PILECAP
    if _name_contains(el, doc, _PILE_KEYWORDS):
        return CAT_PILE

    # Geometry heuristics
    dims = _bb_dims(el)
    if dims is not None:
        x, y, z = dims
        plan = max(x, y)
        if plan > 1.0 and z > 500 and z > 3.0 * plan:
            return CAT_PILE        # tall & narrow → pile
        if plan > 1.0 and plan > 1.5 * z and z < 2500:
            return CAT_PILECAP     # wide & shallow → pile cap
    elif _has_curve_location(el):
        return CAT_PILE            # curve location in foundation → likely inclined pile

    return CAT_FOUNDATION


# ── survey collection ─────────────────────────────────────────────────────────

def collect_survey(doc, options):
    """
    options = {
        'filter_category': str|None   — one of CAT_* constants or None (all)
        'filter_level_id': int|None
        'sort_by':         'mark'|'level'|'x'|'y'
        'coord_decimals':  int
    }
    Returns list of row dicts.
    """
    filter_cat = options.get('filter_category', None)
    filter_lv  = options.get('filter_level_id', None)
    sort_by    = options.get('sort_by', 'mark')
    decimals   = options.get('coord_decimals', 1)

    rows = []

    for bic in _survey_bics():
        for el in (DB.FilteredElementCollector(doc)
                   .OfCategory(bic)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            try:
                cat_label = _classify(el, doc, bic)

                if filter_cat and cat_label != filter_cat:
                    continue

                if filter_lv is not None:
                    lv_match = False
                    for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                                DB.BuiltInParameter.LEVEL_PARAM]:
                        try:
                            p = el.get_Parameter(bip)
                            if p and p.HasValue:
                                if get_id_value(p.AsElementId()) == filter_lv:
                                    lv_match = True
                                    break
                        except Exception:
                            pass
                    if not lv_match:
                        continue

                x, y, z, rot = _element_location(el)
                if x is None:
                    continue

                rows.append({
                    'id':       get_id_value(el.Id),
                    'category': cat_label,
                    'mark':     _ps(el, DB.BuiltInParameter.ALL_MODEL_MARK),
                    'level':    _level_name(el, doc),
                    'family':   _family_name(el),
                    'etype':     _type_name(el, doc),
                    'material': _material_name(el, doc),
                    'x_mm':     round(x, decimals),
                    'y_mm':     round(y, decimals),
                    'z_mm':     round(z, decimals),
                    'rot_deg':  round(rot, 2),
                    'comments': _ps(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS),
                })
            except Exception:
                pass

    sort_map = {
        'mark':  lambda r: (r['mark'] or ''),
        'level': lambda r: (r['level'] or '', r['mark'] or ''),
        'x':     lambda r: (r['x_mm'] or 0,),
        'y':     lambda r: (r['y_mm'] or 0,),
    }
    rows.sort(key=sort_map.get(sort_by, sort_map['mark']))
    return rows


# ── levels ────────────────────────────────────────────────────────────────────

def get_levels(doc):
    levels = sorted(
        DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
        key=lambda lv: lv.Elevation)
    return [(lv.Name, get_id_value(lv.Id)) for lv in levels]


# ── export ────────────────────────────────────────────────────────────────────

_CSV_HEADERS = ['ID', 'Category', 'Mark', 'Level', 'Family', 'Type', 'Material',
                'X (mm)', 'Y (mm)', 'Z (mm)', 'Rot. (°)', 'Comments']
_CSV_KEYS    = ['id', 'category', 'mark', 'level', 'family', 'etype', 'material',
                'x_mm', 'y_mm', 'z_mm', 'rot_deg', 'comments']


def load_survey_csv(path):
    """
    Load a survey CSV file.
    Expected columns (case-insensitive): Mark, X, Y, Z  (or Easting/Northing/Elevation).
    Returns list of dicts with keys: mark, sx, sy, sz.
    """
    import io as _io, csv as _csv
    col_aliases = {
        'mark':     ['mark', 'id', 'ref', 'element', 'name', 'label'],
        'x':        ['x', 'easting', 'este', 'e'],
        'y':        ['y', 'northing', 'norte', 'n'],
        'z':        ['z', 'elevation', 'cota', 'height', 'rl', 'level'],
    }
    with _io.open(path, 'r', encoding='utf-8-sig') as f:
        reader = _csv.DictReader(f)
        raw_headers = [h.strip().lower() for h in (reader.fieldnames or [])]

        def _find_col(key):
            for alias in col_aliases[key]:
                if alias in raw_headers:
                    return reader.fieldnames[[h.strip().lower()
                                             for h in reader.fieldnames].index(alias)]
            return None

        col_mark = _find_col('mark')
        col_x    = _find_col('x')
        col_y    = _find_col('y')
        col_z    = _find_col('z')

        if not (col_x and col_y):
            raise ValueError(
                u'Could not find X/Y columns. Expected headers like: Mark, X, Y, Z')

        points = []
        for row in reader:
            try:
                mark = str(row.get(col_mark, '') or '').strip() if col_mark else ''
                sx   = float(row[col_x])   * 1000.0  # convert m → mm
                sy   = float(row[col_y])   * 1000.0
                sz   = float(row[col_z])   * 1000.0 if col_z and row.get(col_z) else None
                points.append({'mark': mark, 'sx': sx, 'sy': sy, 'sz': sz})
            except (ValueError, KeyError):
                continue
    return points


def compare_survey(model_rows, survey_points, tolerance_mm=10.0):
    """
    Match survey points to model elements by Mark and compute coordinate deltas.

    model_rows:    list of row dicts from collect_elements() — must have 'mark','x_mm','y_mm','z_mm'
    survey_points: list of dicts from load_survey_csv() — 'mark','sx','sy','sz'
    tolerance_mm:  flag differences exceeding this value

    Returns list of comparison dicts:
      mark, model_x, model_y, model_z, survey_x, survey_y, survey_z,
      dx, dy, dz, d_horiz, d_total, status
    """
    survey_idx = {}
    for pt in survey_points:
        mk = pt['mark'].lower().strip()
        if mk:
            survey_idx[mk] = pt

    results = []
    for r in model_rows:
        mk_raw = str(r.get('mark', '') or '').strip()
        mk     = mk_raw.lower()
        mx     = r.get('x_mm')
        my     = r.get('y_mm')
        mz     = r.get('z_mm')

        if mk not in survey_idx:
            results.append({
                'mark': mk_raw, 'status': u'No survey point',
                'model_x': mx, 'model_y': my, 'model_z': mz,
                'survey_x': None, 'survey_y': None, 'survey_z': None,
                'dx': None, 'dy': None, 'dz': None,
                'd_horiz': None, 'd_total': None,
            })
            continue

        sp = survey_idx[mk]
        dx = round(mx - sp['sx'], 1) if mx is not None else None
        dy = round(my - sp['sy'], 1) if my is not None else None
        dz = round(mz - sp['sz'], 1) if (mz is not None and sp['sz'] is not None) else None

        d_horiz = round(math.sqrt((dx or 0)**2 + (dy or 0)**2), 1) if dx is not None and dy is not None else None
        d_total = round(math.sqrt((dx or 0)**2 + (dy or 0)**2 + (dz or 0)**2), 1) \
                  if d_horiz is not None and dz is not None else d_horiz

        if d_total is not None and d_total > tolerance_mm:
            status = u'OUT OF TOLERANCE ({:.0f}mm)'.format(d_total)
        elif d_total is not None:
            status = u'OK ({:.0f}mm)'.format(d_total)
        else:
            status = u'Matched'

        results.append({
            'mark': mk_raw, 'status': status,
            'model_x': mx,     'model_y': my,     'model_z': mz,
            'survey_x': sp['sx'], 'survey_y': sp['sy'], 'survey_z': sp['sz'],
            'dx': dx, 'dy': dy, 'dz': dz,
            'd_horiz': d_horiz, 'd_total': d_total,
        })

    # Also report survey points with no model match
    model_marks = {str(r.get('mark', '') or '').lower() for r in model_rows}
    for pt in survey_points:
        if pt['mark'].lower() not in model_marks:
            results.append({
                'mark': pt['mark'], 'status': u'No model element',
                'model_x': None, 'model_y': None, 'model_z': None,
                'survey_x': pt['sx'], 'survey_y': pt['sy'], 'survey_z': pt['sz'],
                'dx': None, 'dy': None, 'dz': None,
                'd_horiz': None, 'd_total': None,
            })

    return results


_COMPARE_HEADERS = [u'Mark', u'Status',
                    u'Model X (mm)', u'Model Y (mm)', u'Model Z (mm)',
                    u'Survey X (mm)', u'Survey Y (mm)', u'Survey Z (mm)',
                    u'ΔX (mm)', u'ΔY (mm)', u'ΔZ (mm)',
                    u'ΔHoriz (mm)', u'ΔTotal (mm)']
_COMPARE_KEYS = ['mark', 'status',
                 'model_x', 'model_y', 'model_z',
                 'survey_x', 'survey_y', 'survey_z',
                 'dx', 'dy', 'dz', 'd_horiz', 'd_total']


def export_compare_csv(results, path):
    """Export survey comparison results to CSV."""
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(_COMPARE_HEADERS)
        for r in results:
            w.writerow([r.get(k, '') for k in _COMPARE_KEYS])


def export_csv(rows, path):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(_CSV_HEADERS)
        for r in rows:
            w.writerow([r.get(k, '') for k in _CSV_KEYS])


def export_xlsx(rows, path, project_name=''):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils  import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = u'Survey Layout'

    accent  = 'FF5F00'
    thin    = Side(border_style='thin', color='FFE0E0E0')
    bdr     = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fnt = Font(bold=True, color='FFFFFFFF', name='Century Gothic', size=10)
    reg_fnt = Font(name='Century Gothic', size=9)
    center  = Alignment(horizontal='center', vertical='center')

    ws.merge_cells('A1:L1')
    ws['A1'] = u'SURVEY LAYOUT TABLE — {}'.format(project_name or 'PROJECT')
    ws['A1'].font      = Font(bold=True, size=14, name='Century Gothic', color=accent)
    ws['A1'].alignment = center

    for col, h in enumerate(_CSV_HEADERS, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font      = hdr_fnt
        cell.fill      = PatternFill('solid', fgColor=accent)
        cell.alignment = center
        cell.border    = bdr

    for i, r in enumerate(rows, 4):
        for col, k in enumerate(_CSV_KEYS, 1):
            cell = ws.cell(row=i, column=col, value=r.get(k, ''))
            cell.font   = reg_fnt
            cell.border = bdr
            if col >= 8:
                cell.alignment = center
            if i % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='FFF0E8')

    widths = [80, 100, 80, 100, 160, 160, 120, 90, 90, 90, 70, 150]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w / 7.5

    ws.freeze_panes = 'A4'
    wb.save(path)

