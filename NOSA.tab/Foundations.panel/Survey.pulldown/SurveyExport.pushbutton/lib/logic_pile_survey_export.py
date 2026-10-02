# -*- coding: utf-8 -*-
"""
Pile Survey Export v1.0 — Logic

Detects pile elements and computes their survey attributes:
  - Head coordinates (X, Y, Z) in project units (mm)
  - Toe coordinates
  - Length, diameter, inclination, azimuth
"""
import math, io, csv
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils import unit_conversion as _uc10
from nosa_utils.telemetry import log_swallowed
_LOG = u'surveyexport'
FT2MM = _uc10.FT_TO_MM
FT_M  = _uc10.FT_TO_M

_PILE_KEYWORDS = ['pile', 'pilote', 'pila', 'micropilote', 'micropile']

def _pile_bics():
    return [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
    ]




def _ps(el, bip, default=u''):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsString() or default
    except Exception:
        log_swallowed(_LOG, u'_ps')
    return default


def _pd(el, bip, default=0.0):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsDouble()
    except Exception:
        log_swallowed(_LOG, u'_pd')
    return default


def _is_pile(el, doc):
    """Return True if element is a pile (by keyword, NOSA param, or category heuristic)."""
    # 1. NOSA_IsPile shared parameter
    try:
        p = el.LookupParameter('NOSA_IsPile')
        if p and p.AsInteger() == 1:
            return True
    except Exception:
        log_swallowed(_LOG, u'_is_pile')
    # 2. Family name contains pile keyword
    try:
        name = ''
        if isinstance(el, DB.FamilyInstance):
            name = el.Symbol.FamilyName or ''
        else:
            name = el.Name or ''
        name_lo = name.lower()
        if any(kw in name_lo for kw in _PILE_KEYWORDS):
            return True
    except Exception:
        log_swallowed(_LOG, u'_is_pile')
    # 3. Type name contains pile keyword
    try:
        t = doc.GetElement(el.GetTypeId())
        if t:
            tname = element_name(t).lower()
            if any(kw in tname for kw in _PILE_KEYWORDS):
                return True
    except Exception:
        log_swallowed(_LOG, u'_is_pile')
    return False


def _pile_geometry(el):
    """
    Return (head_pt, toe_pt, length_mm, diam_mm, inclination_deg, azimuth_deg).
    head = top/start; toe = bottom/end.
    """
    try:
        loc = el.Location
        if isinstance(loc, DB.LocationCurve):
            p0 = loc.Curve.GetEndPoint(0)
            p1 = loc.Curve.GetEndPoint(1)
            # Head = higher Z (ground level), Toe = lower Z
            if p0.Z >= p1.Z:
                head, toe = p0, p1
            else:
                head, toe = p1, p0

            dx = toe.X - head.X
            dy = toe.Y - head.Y
            dz = toe.Z - head.Z
            horiz = math.sqrt(dx*dx + dy*dy)
            length_ft = math.sqrt(dx*dx + dy*dy + dz*dz)
            length_mm = length_ft * FT2MM

            inclination_deg = math.degrees(math.atan2(-dz, horiz)) if horiz or dz else 90.0
            azimuth_deg     = math.degrees(math.atan2(dx, dy)) % 360 if horiz > 1e-9 else 0.0

            return head, toe, round(length_mm, 0), None, round(inclination_deg, 2), round(azimuth_deg, 2)

        if isinstance(loc, DB.LocationPoint):
            pt = loc.Point
            # For point-based piles, derive length from bounding box
            length_mm = 0.0
            try:
                bb = el.get_BoundingBox(None)
                if bb:
                    length_mm = abs(bb.Max.Z - bb.Min.Z) * FT2MM
            except Exception:
                log_swallowed(_LOG, u'_pile_geometry')
            return pt, None, round(length_mm, 0), None, 90.0, 0.0
    except Exception:
        log_swallowed(_LOG, u'_pile_geometry')
    return None, None, 0.0, None, 0.0, 0.0


def _diameter_mm(el, doc):
    """Try to extract pile diameter from type parameters."""
    for bip in [DB.BuiltInParameter.STRUCTURAL_SECTION_COMMON_DIAMETER,
                DB.BuiltInParameter.GENERIC_WIDTH,
                DB.BuiltInParameter.GENERIC_DEPTH]:
        try:
            t = doc.GetElement(el.GetTypeId())
            if t:
                v = _pd(t, bip)
                if v > 0:
                    return round(v * FT2MM, 0)
        except Exception:
            log_swallowed(_LOG, u'_diameter_mm')
    # Try instance parameter
    try:
        p = el.LookupParameter('Diameter') or el.LookupParameter('Diámetro')
        if p and p.HasValue:
            return round(p.AsDouble() * FT2MM, 0)
    except Exception:
        log_swallowed(_LOG, u'_diameter_mm')
    return None


def _level_name(el, doc):
    for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.LEVEL_PARAM]:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv:
                    return lv.Name or u''
        except Exception:
            log_swallowed(_LOG, u'_level_name')
    return u''


def _family_type_names(el, doc):
    try:
        t = doc.GetElement(el.GetTypeId())
        if isinstance(el, DB.FamilyInstance):
            return el.Symbol.FamilyName or u'', element_name(t)
        return u'', element_name(t)
    except Exception:
        return u'', u''


# ── COLLECTION ────────────────────────────────────────────────────────────────

def collect_piles(doc, options):
    """
    options = {
        'filter_level_id': int|None,
        'sort_by':         'mark'|'x'|'y',
        'coord_decimals':  int,
        'only_flagged':    bool,  # only NOSA_IsPile=1 elements
    }
    Returns list of pile dicts.
    """
    filter_lv   = options.get('filter_level_id', None)
    sort_by     = options.get('sort_by', 'mark')
    decimals    = options.get('coord_decimals', 1)
    only_flagged = options.get('only_flagged', False)

    rows = []
    seen = set()

    for bic in _pile_bics():
        for el in (DB.FilteredElementCollector(doc)
                   .OfCategory(bic)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            eid = get_id_value(el.Id)
            if eid in seen:
                continue

            if only_flagged:
                try:
                    p = el.LookupParameter('NOSA_IsPile')
                    if not p or p.AsInteger() != 1:
                        continue
                except Exception:
                    continue
            elif not _is_pile(el, doc):
                continue

            seen.add(eid)

            # Level filter
            if filter_lv is not None:
                lv_match = False
                for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                            DB.BuiltInParameter.LEVEL_PARAM]:
                    try:
                        p = el.get_Parameter(bip)
                        if p and p.HasValue and get_id_value(p.AsElementId()) == filter_lv:
                            lv_match = True
                            break
                    except Exception:
                        log_swallowed(_LOG, u'collect_piles')
                if not lv_match:
                    continue

            head, toe, length_mm, _, incl, azim = _pile_geometry(el)
            if head is None:
                continue

            diam = _diameter_mm(el, doc)
            mark = _ps(el, DB.BuiltInParameter.ALL_MODEL_MARK)
            fam, tname = _family_type_names(el, doc)
            level = _level_name(el, doc)
            comments = _ps(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)

            row = {
                'id':        eid,
                'mark':      mark,
                'family':    fam,
                'etype':      tname,
                'level':     level,
                'x_head':    round(head.X * FT2MM, decimals),
                'y_head':    round(head.Y * FT2MM, decimals),
                'z_head':    round(head.Z * FT2MM, decimals),
                'x_toe':     round(toe.X * FT2MM, decimals) if toe else u'',
                'y_toe':     round(toe.Y * FT2MM, decimals) if toe else u'',
                'z_toe':     round(toe.Z * FT2MM, decimals) if toe else u'',
                'length_mm': length_mm,
                'diam_mm':   diam or u'',
                'incl_deg':  incl,
                'azim_deg':  azim,
                'comments':  comments,
            }
            rows.append(row)

    sort_map = {
        'mark': lambda r: (r['mark'] or ''),
        'x':    lambda r: (r['x_head'] or 0,),
        'y':    lambda r: (r['y_head'] or 0,),
    }
    rows.sort(key=sort_map.get(sort_by, sort_map['mark']))
    return rows


def get_levels(doc):
    levels = sorted(
        DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
        key=lambda lv: lv.Elevation)
    return [(lv.Name, get_id_value(lv.Id)) for lv in levels]


# ── EXPORT ────────────────────────────────────────────────────────────────────

_HEADERS = [
    'ID', 'Mark', 'Family', 'Type', 'Level',
    'X Head', 'Y Head', 'Z Head',
    'X Toe',  'Y Toe',  'Z Toe',
    'Length (mm)', 'Diam. (mm)', 'Incl. (°)', 'Azimuth (°)', 'Comments',
]
_KEYS = [
    'id', 'mark', 'family', 'etype', 'level',
    'x_head', 'y_head', 'z_head',
    'x_toe',  'y_toe',  'z_toe',
    'length_mm', 'diam_mm', 'incl_deg', 'azim_deg', 'comments',
]


def export_csv(rows, path):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(_HEADERS)
        for r in rows:
            w.writerow([r.get(k, '') for k in _KEYS])


def export_xlsx(rows, path, project_name=''):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils  import get_column_letter

    wb  = openpyxl.Workbook()
    ws  = wb.active
    ws.title = u'Pile Survey'
    accent  = 'FFFF5F00'
    thin    = Side(border_style='thin', color='FFE0E0E0')
    bdr     = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fnt = Font(bold=True, color='FFFFFFFF', name='Century Gothic', size=10)
    reg_fnt = Font(name='Century Gothic', size=9)
    ctr     = Alignment(horizontal='center', vertical='center')

    ws.merge_cells('A1:P1')
    ws['A1'] = u'PILE SURVEY EXPORT — {}'.format(project_name or 'PROYECTO')
    ws['A1'].font      = Font(bold=True, size=14, name='Century Gothic', color=accent[2:])
    ws['A1'].alignment = ctr

    for col, h in enumerate(_HEADERS, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font      = hdr_fnt
        cell.fill      = PatternFill('solid', fgColor=accent[2:])
        cell.alignment = ctr
        cell.border    = bdr

    for i, r in enumerate(rows, 4):
        for col, k in enumerate(_KEYS, 1):
            cell = ws.cell(row=i, column=col, value=r.get(k, ''))
            cell.font   = reg_fnt
            cell.border = bdr
            if col >= 6:
                cell.alignment = ctr
            if i % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='FFFFF0E8')

    widths = [70, 80, 140, 140, 90, 90, 90, 90, 90, 90, 90, 90, 80, 70, 70, 120]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w / 7.5

    ws.freeze_panes = 'A4'
    wb.save(path)





