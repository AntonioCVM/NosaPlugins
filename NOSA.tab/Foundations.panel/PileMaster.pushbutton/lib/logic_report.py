# -*- coding: utf-8 -*-
"""
PileMaster — Report Logic

Collects all pile elements, extracts coordinates, geometry, and analytical
load status, and provides Excel/CSV export.
"""
import math, io, csv
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils import unit_conversion as _uc10
FT2MM  = _uc10.FT_TO_MM
FT2M   = _uc10.FT_TO_M

_PILE_KEYWORDS = [
    'pile', 'pilote', 'pila', 'pilon',
    'micropile', 'micropilote', 'micro pile', 'micro-pile',
    'pin pile', 'driven pile', 'bored pile', 'cfa',
    'spun pile', 'precast pile', 'phc pile',
    'h-pile', 'tubular pile',
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


def _is_pile_by_name(el, doc):
    fam = _family_name(el).lower()
    typ = _type_name(el, doc).lower()
    return any(k in fam or k in typ for k in _PILE_KEYWORDS)


def _is_pile_by_param(el):
    try:
        p = el.LookupParameter('NOSA_IsPile')
        if p and p.AsInteger() == 1:
            return True
    except Exception:
        pass
    return False


def _pile_endpoints(el):
    """
    Return (head_xyz, toe_xyz) where head = top (higher Z), toe = bottom.
    Falls back to bounding-box min/max Z centred in XY if no location curve.
    """
    try:
        loc = el.Location
        if isinstance(loc, DB.LocationCurve):
            p0 = loc.Curve.GetEndPoint(0)
            p1 = loc.Curve.GetEndPoint(1)
            if p0.Z >= p1.Z:
                return p0, p1
            return p1, p0
    except Exception:
        pass
    # Fallback: bounding box
    try:
        bb = el.get_BoundingBox(None)
        if bb:
            cx = (bb.Min.X + bb.Max.X) / 2.0
            cy = (bb.Min.Y + bb.Max.Y) / 2.0
            head = DB.XYZ(cx, cy, bb.Max.Z)
            toe  = DB.XYZ(cx, cy, bb.Min.Z)
            return head, toe
    except Exception:
        pass
    return None, None


def _load_status(el, doc):
    """
    Return load status string: 'Loaded', 'Unloaded', or 'Unknown'.
    Checks analytical model for support conditions.
    """
    try:
        am = el.GetAnalyticalModel()
        if am is None:
            return u'No analytical model'
        # Check if there are any analytical node supports
        for node in am.GetAnalyticalModelNodes():
            try:
                supp = am.GetRestraintCondition(node)
                if supp is not None:
                    return u'Loaded'
            except Exception:
                pass
        return u'Unloaded'
    except Exception:
        pass
    return u'Unknown'


def _diameter_mm(el, doc):
    """Try to read a diameter or width parameter from the pile type."""
    try:
        t = doc.GetElement(el.GetTypeId())
        if t:
            for bip in [DB.BuiltInParameter.GENERIC_WIDTH,
                        DB.BuiltInParameter.FAMILY_WIDTH_PARAM,
                        DB.BuiltInParameter.STRUCTURAL_FOUNDATION_WIDTH]:
                p = t.get_Parameter(bip)
                if p and p.HasValue:
                    v = p.AsDouble()
                    if v > 0:
                        return round(v * FT2MM, 0)
            # Search by name
            for p in t.Parameters:
                n = p.Definition.Name.lower()
                if ('diam' in n or 'width' in n or 'size' in n) and p.HasValue:
                    if p.StorageType == DB.StorageType.Double:
                        v = p.AsDouble()
                        if v > 0:
                            return round(v * FT2MM, 0)
    except Exception:
        pass
    return None


# ── collection ────────────────────────────────────────────────────────────────

class PileReportRow(object):
    __slots__ = ['el_id', 'mark', 'family', 'type_name', 'level',
                 'x_mm', 'y_mm', 'z_head_mm', 'z_toe_mm',
                 'length_mm', 'diam_mm', 'inclination_deg',
                 'load_status', 'comments']

    def __init__(self, **kw):
        for s in self.__slots__:
            setattr(self, s, kw.get(s, None))

    # WPF-bindable properties (plain attribute access)
    @property
    def mark_str(self):      return self.mark      or u'—'
    @property
    def family_str(self):    return self.family    or u'—'
    @property
    def type_str(self):      return self.type_name or u'—'
    @property
    def level_str(self):     return self.level     or u'—'
    @property
    def x_str(self):
        return u'{:.1f}'.format(self.x_mm) if self.x_mm is not None else u'—'
    @property
    def y_str(self):
        return u'{:.1f}'.format(self.y_mm) if self.y_mm is not None else u'—'
    @property
    def z_head_str(self):
        return u'{:.1f}'.format(self.z_head_mm) if self.z_head_mm is not None else u'—'
    @property
    def z_toe_str(self):
        return u'{:.1f}'.format(self.z_toe_mm)  if self.z_toe_mm  is not None else u'—'
    @property
    def length_str(self):
        return u'{:.0f}'.format(self.length_mm) if self.length_mm is not None else u'—'
    @property
    def diam_str(self):
        return u'{:.0f}'.format(self.diam_mm)   if self.diam_mm   is not None else u'—'
    @property
    def incl_str(self):
        return u'{:.1f}°'.format(self.inclination_deg) if self.inclination_deg is not None else u'0.0°'
    @property
    def load_str(self):      return self.load_status or u'—'
    @property
    def comments_str(self):  return self.comments  or u''


def collect_report(doc, options):
    """
    options = {
        'filter_level_id': int|None,
        'sort_by':         'mark'|'level'|'x'|'y',
        'coord_system':    'shared'|'project'|'survey',
    }
    Returns list of PileReportRow.
    """
    filter_lv  = options.get('filter_level_id', None)
    sort_by    = options.get('sort_by', 'mark')

    bics = [DB.BuiltInCategory.OST_StructuralColumns,
            DB.BuiltInCategory.OST_StructuralFoundation,
            DB.BuiltInCategory.OST_StructuralFraming]

    rows = []

    for bic in bics:
        for el in (DB.FilteredElementCollector(doc)
                   .OfCategory(bic)
                   .WhereElementIsNotElementType()
                   .ToElements()):
            try:
                if not (_is_pile_by_param(el) or _is_pile_by_name(el, doc)):
                    continue

                # Level filter
                if filter_lv is not None:
                    match = False
                    for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                                DB.BuiltInParameter.LEVEL_PARAM]:
                        try:
                            p = el.get_Parameter(bip)
                            if p and p.HasValue and get_id_value(p.AsElementId()) == filter_lv:
                                match = True
                                break
                        except Exception:
                            pass
                    if not match:
                        continue

                head, toe = _pile_endpoints(el)
                if head is None:
                    continue

                x_mm     = round(head.X * FT2MM, 1)
                y_mm     = round(head.Y * FT2MM, 1)
                z_h_mm   = round(head.Z * FT2MM, 1)
                z_t_mm   = round(toe.Z  * FT2MM, 1) if toe else None

                length_mm = None
                if toe is not None:
                    dx = (head.X - toe.X) * FT2MM
                    dy = (head.Y - toe.Y) * FT2MM
                    dz = (head.Z - toe.Z) * FT2MM
                    length_mm = round(math.sqrt(dx*dx + dy*dy + dz*dz), 0)

                incl_deg = 0.0
                if toe is not None and length_mm and length_mm > 0:
                    horiz = math.sqrt(((head.X-toe.X)*FT2MM)**2 + ((head.Y-toe.Y)*FT2MM)**2)
                    vert  = abs((head.Z - toe.Z) * FT2MM)
                    incl_deg = round(math.degrees(math.atan2(horiz, vert)), 1) if vert > 0 else 0.0

                rows.append(PileReportRow(
                    el_id          = get_id_value(el.Id),
                    mark           = _ps(el, DB.BuiltInParameter.ALL_MODEL_MARK),
                    family         = _family_name(el),
                    type_name      = _type_name(el, doc),
                    level          = _level_name(el, doc),
                    x_mm           = x_mm,
                    y_mm           = y_mm,
                    z_head_mm      = z_h_mm,
                    z_toe_mm       = z_t_mm,
                    length_mm      = length_mm,
                    diam_mm        = _diameter_mm(el, doc),
                    inclination_deg= incl_deg,
                    load_status    = _load_status(el, doc),
                    comments       = _ps(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS),
                ))
            except Exception:
                pass

    sort_key = {
        'mark':  lambda r: (r.mark or ''),
        'level': lambda r: (r.level or '', r.mark or ''),
        'x':     lambda r: (r.x_mm or 0,),
        'y':     lambda r: (r.y_mm or 0,),
    }
    rows.sort(key=sort_key.get(sort_by, sort_key['mark']))
    return rows


def get_levels(doc):
    levels = sorted(
        DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
        key=lambda lv: lv.Elevation)
    return [(getattr(lv, 'Name', None) or str(lv.Id), get_id_value(lv.Id)) for lv in levels]


# ── export ────────────────────────────────────────────────────────────────────

_HEADERS = ['No.', 'Mark', 'Family', 'Type', 'Level',
            'X (mm)', 'Y (mm)', 'Z Head (mm)', 'Z Toe (mm)',
            'Length (mm)', 'Ø (mm)', 'Incl. (°)', 'Load Status', 'Comments']


def export_xlsx(rows, path, project_name=''):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils  import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = u'Pile Report'

    accent  = 'FF5F00'
    thin    = Side(border_style='thin', color='FFE0E0E0')
    bdr     = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fnt = Font(bold=True, color='FFFFFFFF', name='Century Gothic', size=10)
    reg_fnt = Font(name='Century Gothic', size=9)
    center  = Alignment(horizontal='center', vertical='center')

    ws.merge_cells('A1:N1')
    ws['A1'] = u'PILE REPORT — {}'.format(project_name or 'PROJECT')
    ws['A1'].font      = Font(bold=True, size=14, name='Century Gothic', color=accent)
    ws['A1'].alignment = center

    for col, h in enumerate(_HEADERS, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font      = hdr_fnt
        cell.fill      = PatternFill('solid', fgColor=accent)
        cell.alignment = center
        cell.border    = bdr

    for i, r in enumerate(rows, 1):
        vals = [i, r.mark_str, r.family_str, r.type_str, r.level_str,
                r.x_mm, r.y_mm, r.z_head_mm, r.z_toe_mm,
                r.length_mm, r.diam_mm, r.inclination_deg,
                r.load_str, r.comments_str]
        fill = PatternFill('solid', fgColor='FFF0E8') if i % 2 == 0 else None
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=i+3, column=col, value=v)
            cell.font   = reg_fnt
            cell.border = bdr
            if fill:
                cell.fill = fill
            if col >= 6:
                cell.alignment = center

    widths = [5, 10, 20, 22, 14, 12, 12, 14, 14, 13, 8, 9, 14, 22]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.freeze_panes = 'A4'
    wb.save(path)


def export_csv(rows, path):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(_HEADERS)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r.mark_str, r.family_str, r.type_str, r.level_str,
                        r.x_mm, r.y_mm, r.z_head_mm, r.z_toe_mm,
                        r.length_mm, r.diam_mm, r.inclination_deg,
                        r.load_str, r.comments_str])
