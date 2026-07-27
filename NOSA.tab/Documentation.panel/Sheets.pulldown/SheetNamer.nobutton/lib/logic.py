# -*- coding: utf-8 -*-
import re
import sys
import os

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import sheet_protocol as _sp
from nosa_utils.revit_helpers import coerce_element_id, get_id_value

# NOSA File Naming Protocol v2.2 — field definitions

F3_CODES = [
    ('AM', u'Analytical model'),
    ('CL', u'Calculations'),
    ('CS', u'Condition survey'),
    ('DT', u'Details'),
    ('DS', u'Design certificate'),
    ('EL', u'Elevation'),
    ('GA', u'General arrangement'),
    ('GM', u'Geometrical model'),
    ('HS', u'Health and safety'),
    ('IS', u'Issue sheet'),
    ('MS', u'Method statement'),
    ('PV', u'Plan view'),
    ('RA', u'Risk assessment'),
    ('RC', u'Reinforced concrete details'),
    ('RI', u'RFI'),
    ('RO', u'Revision overview'),
    ('RP', u'Reports'),
    ('RS', u'IRS'),
    ('SC', u'Section'),
    ('SP', u'Specifications'),
    ('TN', u'Technical notes'),
    ('ZZ', u'Multiple things'),
]

F4_PRESETS = [
    ('000', u'Ground floor'),
    ('001', u'Level 01'),
    ('002', u'Level 02'),
    ('003', u'Level 03'),
    ('004', u'Level 04'),
    ('BA1', u'Basement level -1'),
    ('BA2', u'Basement level -2'),
    ('BZZ', u'Block B multiple'),
    ('FND', u'Foundation'),
    ('FRO', u'Front building'),
    ('MZ1', u'Mezzanine'),
    ('REA', u'Rear building'),
    ('RF1', u'Roof level 01'),
    ('XXX', u'No location'),
    ('ZZZ', u'Multiple locations'),
]

REAR_KEYWORDS = (u'rear building', u'building rear', u'rear')
FRONT_KEYWORDS = (u'front building', u'building front', u'front')
BUILDING_F4_CODES = {u'rear': u'REA', u'front': u'FRO'}
VALID_F4_CODES = set(c for c, _ in F4_PRESETS) | set(BUILDING_F4_CODES.values())


def _is_valid_f4_code(code):
    if not code or len(code) != 3:
        return False
    if code in VALID_F4_CODES:
        return True
    return code.isdigit()

LEVEL_KEYWORDS = (
    (u'ground floor', u'000'),
    (u'ground level', u'000'),
    (u'ground', u'000'),
    (u'gf ', u'000'),
    (u'first floor', u'001'),
    (u'first', u'001'),
    (u'level 1', u'001'),
    (u'level 01', u'001'),
    (u'l01', u'001'),
    (u'l1 ', u'001'),
    (u'second floor', u'002'),
    (u'second', u'002'),
    (u'level 2', u'002'),
    (u'level 02', u'002'),
    (u'l02', u'002'),
    (u'l2 ', u'002'),
    (u'third floor', u'003'),
    (u'third', u'003'),
    (u'level 3', u'003'),
    (u'level 03', u'003'),
    (u'l03', u'003'),
    (u'l3 ', u'003'),
    (u'fourth floor', u'004'),
    (u'fourth', u'004'),
    (u'level 4', u'004'),
    (u'level 04', u'004'),
    (u'l04', u'004'),
    (u'l4 ', u'004'),
    (u'roof level', u'RF1'),
    (u'roof', u'RF1'),
    (u'basement 2', u'BA2'),
    (u'basement 1', u'BA1'),
    (u'basement', u'BA1'),
    (u'foundation', u'FND'),
    (u'mezzanine', u'MZ1'),
)

F5_CODES = [
    ('D', u'Drawing'),
    ('G', u'Graph'),
    ('I', u'Image'),
    ('L', u'List'),
    ('M', u'Model'),
    ('T', u'Textual'),
    ('V', u'Video'),
]

F6_CODES = [
    ('S', u'Structural engineering'),
    ('C', u'Civil engineer'),
    ('G', u'Ground engineering'),
    ('B', u'Building surveying'),
    ('H', u'Health and safety'),
    ('D', u'Demolition'),
    ('O', u'Other'),
    ('P', u'Project management'),
    ('X', u'Non-discipline'),
    ('Z', u'Multiple disciplines'),
]

F7_HINTS = {
    'GA': '2200', 'EL': '3000', 'SC': '3000', 'DT': '4000',
    'RC': '4500', 'RP': '5000', 'AM': '6000', 'GM': '6500',
    'PV': '2200', 'CL': '0001', 'SP': '0900', 'HS': '8001',
    'IS': '0000', 'TN': '0001', 'CS': '1000',
}

F8_STAGES = [
    u'P01', u'P02', u'P03', u'P04', u'P05',
    u'C01', u'C02', u'C03', u'C04', u'C05',
    u'I01', u'I02', u'I03',
    u'PC01', u'PC02', u'PC03',
]

NOSA_NUMBER_RE = re.compile(
    r'^(\d{5})\s+NOSA\s+(\w{2})\s+(\w{3})\s+(\w)\s+(\w)\s+(\d{4})\s+(\S+)$'
)

_PARAM_FIELD_MAP = {
    'f1': 'Project Number',
    'f3': 'Functional Breakdown',
    'f4': 'Spatial Breakdown',
    'f5': 'Form',
    'f6': 'Discipline',
    'f7': 'Document Number',
    'f8': 'Current Revision',
}


def build_sheet_number(f1, f3, f4, f5, f6, f7, f8):
    """Full NOSA display string for UI preview — not written to ViewSheet.SheetNumber."""
    return _sp.build_nosa_number(f1, f3, f4, f5, f6, f7, f8)


def validate_fields(f1, f3, f4, f5, f6, f7, f8):
    errors = []
    if not f1 or len(f1) != 5 or not f1.isdigit():
        errors.append(u'F1 (Project No.) must be exactly 5 digits.')
    if not f3 or len(f3) != 2:
        errors.append(u'F3 (Function) must be 2 characters.')
    if not f4 or len(f4) != 3:
        errors.append(u'F4 (Spatial) must be exactly 3 characters.')
    if not f5 or len(f5) != 1:
        errors.append(u'F5 (Form) must be 1 character.')
    if not f6 or len(f6) != 1:
        errors.append(u'F6 (Discipline) must be 1 character.')
    if not f7 or len(f7) != 4 or not f7.isdigit():
        errors.append(u'F7 (Doc No.) must be exactly 4 digits.')
    return errors


def get_all_sheets(doc):
    sheets = DB.FilteredElementCollector(doc) \
                .OfClass(DB.ViewSheet) \
                .ToElements()
    result = []
    for s in sheets:
        result.append({
            'id':     get_id_value(s.Id),
            'number': s.SheetNumber or u'',
            'name':   s.Name or u'',
        })
    return sorted(result, key=lambda x: x['number'])


def get_existing_numbers(doc):
    return set(s['number'] for s in get_all_sheets(doc))


def _f4_from_level_name(level_name):
    """Map a Revit level name to an F4 spatial code."""
    name = (level_name or u'').upper()
    if 'B2' in name or 'BASEMENT 2' in name or 'BASE -2' in name:
        return 'BA2'
    if 'B1' in name or 'BASEMENT' in name or 'BASE -1' in name:
        return 'BA1'
    if 'FND' in name or 'FOUNDATION' in name:
        return 'FND'
    if 'GF' in name or 'GROUND' in name or name in ('L00', 'LEVEL 0', 'LEVEL 00'):
        return '000'
    if 'ROOF' in name or name.startswith('RF'):
        return 'RF1'
    if 'MEZ' in name or 'MEZZANINE' in name:
        return 'MZ1'
    m = re.search(r'(?:L(?:EVEL)?\s*)?(\d+)', name)
    if m:
        return '{:03d}'.format(int(m.group(1)))
    return None


def _normalise_f1(val):
    """Extract a 5-digit project number from text (pads or truncates)."""
    digits = re.sub(r'\D', u'', val or u'')
    if not digits:
        return u''
    if len(digits) >= 5:
        return digits[:5]
    return digits.zfill(5)


def _normalize_sheet_name(name):
    """Lowercase sheet title with common typo fixes for keyword matching."""
    low = (name or u'').lower()
    low = low.replace(u'genral', u'general')
    return low


def suggest_f4_from_sheet_name(sheet_name):
    """Infer F4 spatial (level) code from sheet title — priority over stale params."""
    return suggest_f4_level_from_name(sheet_name)


def suggest_f4_building_from_name(sheet_name):
    """Infer building-specific F4 code from sheet title keywords."""
    low = (sheet_name or u'').lower()
    for kw in REAR_KEYWORDS:
        if kw in low:
            return BUILDING_F4_CODES[u'rear']
    for kw in FRONT_KEYWORDS:
        if kw in low:
            return BUILDING_F4_CODES[u'front']
    return None


def building_key_from_name(sheet_name):
    """Short building label for F7 grouping (rear / front / empty)."""
    low = (sheet_name or u'').lower()
    if any(kw in low for kw in REAR_KEYWORDS):
        return u'rear'
    if any(kw in low for kw in FRONT_KEYWORDS):
        return u'front'
    return u''


def suggest_f4_level_from_name(sheet_name):
    """Infer level-based F4 from sheet title keywords."""
    norm = _normalize_sheet_name(sheet_name)
    low = u' {} '.format(norm)
    for phrase, code in LEVEL_KEYWORDS:
        if u' {} '.format(phrase) in low and _is_valid_f4_code(code):
            return code
    for pat in (r'LEVEL\s*(\d+)', r'L(?:EVEL)?\s*(\d+)', r'LVL\s*(\d+)', r'\bL(\d{1,2})\b'):
        m = re.search(pat, (sheet_name or u'').upper())
        if m:
            code = u'{:03d}'.format(int(m.group(1)))
            if _is_valid_f4_code(code):
                return code
    code = _f4_from_level_name(sheet_name)
    if code and _is_valid_f4_code(code):
        return code
    return None


def suggest_f4_from_name(sheet_name):
    """Infer F4 spatial code from sheet title — level preferred, then building."""
    level = suggest_f4_level_from_name(sheet_name)
    if level:
        return level
    building = suggest_f4_building_from_name(sheet_name)
    if building:
        return building
    return None


def suggest_f7_from_legacy(number, name, f3):
    """Infer F7 from legacy sheet number prefix or functional hint."""
    for src in (number, name):
        m = re.match(r'^(\d{4})\b', (src or u'').strip())
        if m:
            return m.group(1)
    return F7_HINTS.get(f3, u'2200')


def suggest_f3_strong_from_name(sheet_name):
    """High-confidence F3 from cover/issue/title keywords in sheet name."""
    name = _normalize_sheet_name(sheet_name).upper()
    if any(k in name for k in (
            u'ISSUE SHEET', u'DOCUMENT ISSUE', u'DRAWING INDEX', u'DRAWING LIST',
            u'TRANSMITTAL', u'REGISTER OF DRAWINGS')):
        return u'IS'
    if any(k in name for k in (
            u'TITLE SHEET', u'PROJECT TITLE', u'COVER SHEET', u'COVER PAGE',
            u'FRONT COVER', u'PROJECT COVER')):
        return u'GA'
    if any(k in name for k in (
            u'GENERAL ARRANGEMENT', u'GENERAL ARR', u'G.A.', u' G.A ', u' GA ',
            u' GA-', u'-GA ', u' GA.', u' GA')):
        return u'GA'
    if any(k in name for k in (u'REVISION OVERVIEW', u'REVISION SCHEDULE', u'REV OVERVIEW')):
        return u'RO'
    if u'sITE PLAN' in name:
        return u'SP'
    return None


def suggest_f4_from_level(doc, sheet):
    """Infer F4 from levels of views placed on the sheet."""
    codes = []
    try:
        for vid in sheet.GetAllViewports():
            vp = doc.GetElement(coerce_element_id(vid))
            if vp is None:
                continue
            view = doc.GetElement(coerce_element_id(vp.ViewId))
            if view is None:
                continue
            level = None
            try:
                if hasattr(view, 'GenLevel') and view.GenLevel:
                    level = view.GenLevel
            except Exception:
                pass
            if level is None:
                try:
                    lid = view.LevelId
                    if lid and lid != DB.ElementId.InvalidElementId:
                        level = doc.GetElement(coerce_element_id(lid))
                except Exception:
                    pass
            if level:
                code = _f4_from_level_name(level.Name)
                if code:
                    codes.append(code)
            vname = view.Name or u''
            if vname:
                uname = vname.upper()
                if u'FND' in uname or u'FOUNDATION' in uname:
                    codes.append(u'FND')
                elif u'ROOF' in uname:
                    codes.append(u'RF1')
                else:
                    vcode = suggest_f4_from_name(vname)
                    if vcode:
                        codes.append(vcode)
    except Exception:
        pass
    if not codes:
        return None
    unique = list(dict.fromkeys(codes))
    if len(unique) == 1:
        return unique[0]
    return u'ZZZ'


def _f3_from_view_type(view):
    """Infer F3 from Revit view type."""
    try:
        vt = view.ViewType
        if vt == DB.ViewType.Section:
            return 'SC'
        if vt == DB.ViewType.Elevation:
            return 'EL'
        if vt in (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan):
            return 'PV'
        if vt == DB.ViewType.Detail:
            return 'DT'
        if vt == DB.ViewType.ThreeD:
            return 'GM'
        if vt == DB.ViewType.DrawingSheet:
            return None
        if vt == DB.ViewType.Schedule:
            return 'RP'
    except Exception:
        pass
    return None


def suggest_f3_from_views(doc, sheet):
    """Infer F3 from view types and names placed on the sheet."""
    codes = []
    plan_count = 0
    try:
        for vid in sheet.GetAllViewports():
            vp = doc.GetElement(coerce_element_id(vid))
            if vp is None:
                continue
            view = doc.GetElement(coerce_element_id(vp.ViewId))
            if view is None:
                continue
            code = _f3_from_view_type(view)
            if not code:
                vname = view.Name or u''
                if vname:
                    code = suggest_f3_from_name(vname)
            if code:
                codes.append(code)
                if code == u'PV':
                    plan_count += 1
    except Exception:
        pass
    if not codes:
        return None
    if plan_count == len(codes) and plan_count > 0:
        return u'PV'
    for c in codes:
        if c not in (u'GA', u'PV'):
            return c
    return codes[0]


def suggest_f3_from_name(sheet_name):
    """Infer F3 code from sheet name keywords."""
    strong = suggest_f3_strong_from_name(sheet_name)
    if strong:
        return strong
    low = _normalize_sheet_name(sheet_name)
    if u'site plan' in low:
        return u'SP'
    if u'plan view' in low or u'plan views' in low:
        if any(kw in low for kw in (u'building', u'front', u'rear', u'general')):
            return u'GA'
    name = low.upper()
    if any(k in name for k in (u'SECTION', u'SECT')):
        return u'SC'
    if any(k in name for k in (u'ELEVATION', u'ELEV')):
        return u'EL'
    if any(k in name for k in (u'DETAIL',)):
        return u'DT'
    if any(k in name for k in (u'RC ', u'REINFORC', u'REBAR')):
        return u'RC'
    if any(k in name for k in (u'PLAN', u'FLOOR')):
        return u'PV'
    if any(k in name for k in (u'FOUNDATION', u'FND', u'PILE')):
        return u'GA'
    if any(k in name for k in (u'SCHEDULE', u'LIST', u'TABLE')):
        return u'RP'
    if any(k in name for k in (u'CALC', u'ANALYSIS')):
        return u'CL'
    if any(k in name for k in (u'LAYOUT',)):
        return u'GA'
    return u'GA'


def parse_nosa_number(number):
    """Parse a NOSA-format sheet number into field dict, or None."""
    m = NOSA_NUMBER_RE.match((number or u'').strip())
    if not m:
        return None
    return {
        'f1': m.group(1), 'f3': m.group(2), 'f4': m.group(3),
        'f5': m.group(4), 'f6': m.group(5), 'f7': m.group(6), 'f8': m.group(7),
    }


def read_fields_from_sheet(doc, sheet_or_id):
    """Read NOSA fields from sheet parameters and title blocks."""
    if sheet_or_id is None:
        return {}
    if hasattr(sheet_or_id, 'SheetNumber'):
        sheet = sheet_or_id
    else:
        sheet = doc.GetElement(coerce_element_id(sheet_or_id))
    if sheet is None:
        return {}
    return _sp.read_nosa_fields_from_sheet(doc, sheet)


def _pick_with_source(candidates):
    """Return (value, source_label) from ordered (label, value) pairs."""
    for label, val in candidates:
        if val:
            return val, label
    return u'', u''


def _current_field_values(parsed, params, row_params, config):
    """Existing values on the sheet (before suggestion)."""
    return {
        u'f1': _first_nonempty(
            (parsed or {}).get(u'f1'), params.get(u'f1'),
            row_params.get(u'Project Number'), config.get(u'f1', u'')),
        u'f3': _first_nonempty(
            (parsed or {}).get(u'f3'), params.get(u'f3'),
            row_params.get(u'Functional Breakdown')),
        u'f4': _first_nonempty(
            (parsed or {}).get(u'f4'), params.get(u'f4'),
            row_params.get(u'Spatial Breakdown')),
        u'f5': _first_nonempty(
            (parsed or {}).get(u'f5'), params.get(u'f5'), row_params.get(u'Form')),
        u'f6': _first_nonempty(
            (parsed or {}).get(u'f6'), params.get(u'f6'), row_params.get(u'Discipline')),
        u'f7': _first_nonempty(
            (parsed or {}).get(u'f7'), params.get(u'f7'), row_params.get(u'Document Number')),
        u'f8': _first_nonempty(
            (parsed or {}).get(u'f8'), params.get(u'f8'), row_params.get(u'Current Revision')),
        u'f9': u'',
    }


def write_nosa_fields(doc, sheet, f1, f3, f4, f5, f6, f7, f8, debug=False):
    """Write each NOSA protocol parameter individually (sheet + title blocks)."""
    return _sp.write_nosa_protocol_fields(
        doc, sheet, f1, f3, f4, f5, f6, f7, f8, debug=debug)


def apply_nosa_to_sheet(doc, sheet, f1, f3, f4, f5, f6, f7, f8,
                        new_number=None, new_name=None, debug=False):
    """Write NOSA fields individually; ViewSheet.SheetNumber = F7 only."""
    if sheet is None:
        return False, {}, []
    try:
        results = write_nosa_fields(doc, sheet, f1, f3, f4, f5, f6, f7, f8, debug=debug)
        if new_name is not None:
            sheet.Name = new_name
        critical = (u'f3', u'f4', u'f5', u'f6', u'f7')
        wrote_any = any(results.get(k, {}).get(u'ok') for k in critical)
        field_vals = {
            u'f1': f1, u'f2': _sp.NOSA_ORIGINATOR, u'f3': f3, u'f4': f4,
            u'f5': f5, u'f6': f6, u'f7': f7, u'f8': f8,
        }
        warnings = []
        for fkey, res in results.items():
            if res.get(u'skipped'):
                continue
            if res.get(u'ok'):
                continue
            val = (field_vals.get(fkey) or u'').strip()
            if not val:
                continue
            if fkey == u'f2' and val.upper() == _sp.NOSA_ORIGINATOR:
                continue
            warnings.append(fkey)
        return wrote_any, results, warnings
    except Exception:
        return False, {}, []


def _first_nonempty(*values):
    for v in values:
        if v:
            return v
    return u''


def _read_package(sheet_dict, sheet):
    pkg = (sheet_dict.get('package') or sheet_dict.get('Package') or u'').strip()
    if pkg:
        return pkg
    if sheet is None:
        return u''
    try:
        p = sheet.LookupParameter('Package')
        if p:
            return (p.AsString() or p.AsValueString() or u'').strip()
    except Exception:
        pass
    return u''


def _f7_group_key(package, f4, building_key):
    return (
        (package or u'').strip().upper(),
        (f4 or u'').strip().upper(),
        (building_key or u'').strip().lower(),
    )


def _parse_f7_int(f7):
    try:
        return int(f7)
    except Exception:
        return None


def _collect_existing_f7_by_group(doc):
    """Max F7 per package + F4 + building keyword from all sheets in the model."""
    groups = {}
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        pkg = u''
        try:
            p = s.LookupParameter('Package')
            if p:
                pkg = (p.AsString() or p.AsValueString() or u'').strip()
        except Exception:
            pass
        fields = _sp.read_nosa_fields_from_sheet(doc, s)
        f4 = fields.get(u'f4', u'')
        f7 = fields.get(u'f7', u'') or (s.SheetNumber or u'').strip()
        if f7 and not f7.isdigit() and len(f7) <= 4:
            parsed = parse_nosa_number(s.SheetNumber or u'')
            if parsed:
                f7 = parsed.get(u'f7', f7)
        bld = building_key_from_name(s.Name or u'')
        key = _f7_group_key(pkg, f4, bld)
        n = _parse_f7_int(f7)
        if n is not None:
            groups[key] = max(groups.get(key, 0), n)
    return groups


def assign_f7_sequences(doc, suggestions, config):
    """
    Assign incremental F7 document numbers within each package + spatial + building group.
    Mutates suggestion dicts in place.
    """
    if not suggestions:
        return
    existing = _collect_existing_f7_by_group(doc)
    batches = {}
    for sug in suggestions:
        pkg = sug.get(u'package', u'')
        f4 = sug.get(u'f4', u'')
        bld = sug.get(u'_building_key', u'')
        key = _f7_group_key(pkg, f4, bld)
        batches.setdefault(key, []).append(sug)
    for key, items in batches.items():
        items.sort(key=lambda s: (
            (s.get(u'f9') or s.get(u'name') or u'').lower(),
            (s.get(u'current_fields') or {}).get(u'f7', u'')))
        if len(items) <= 1:
            continue
        f3 = items[0].get(u'f3', u'GA')
        base = _parse_f7_int(F7_HINTS.get(f3, u'2200')) or 2200
        next_num = max(existing.get(key, base - 1), base - 1)
        for sug in items:
            next_num += 1
            new_f7 = u'{:04d}'.format(next_num)
            sug[u'f7'] = new_f7
            if sug.get(u'suggested_fields'):
                sug[u'suggested_fields'][u'f7'] = new_f7
            sug.setdefault(u'sources', {})[u'f7'] = u'Package/building sequence'


def _sheet_row_params(sheet_dict):
    row_params = {}
    for key in (u'Project Number', u'Functional Breakdown', u'Spatial Breakdown',
                u'Form', u'Discipline', u'Document Number', u'Current Revision'):
        val = sheet_dict.get(key, u'')
        if val:
            row_params[key] = val
    return row_params


def _resolve_sheet(doc, sheet_dict):
    sid = sheet_dict.get('id')
    sheet = sheet_dict.get('element')
    if sheet is None and sid is not None:
        sheet = doc.GetElement(coerce_element_id(sid))
    if sid is None and sheet is not None:
        sid = get_id_value(sheet.Id)
    current = sheet_dict.get('number') or (sheet.SheetNumber if sheet else u'') or u''
    name = sheet_dict.get('name') or (sheet.Name if sheet else u'') or u''
    return sheet, sid, current, name


def _build_display_number(fields):
    """Full NOSA display string from field dict (preview only)."""
    try:
        return _sp.build_nosa_number(
            fields.get(u'f1', u''), fields.get(u'f3', u''), fields.get(u'f4', u''),
            fields.get(u'f5', u''), fields.get(u'f6', u''), fields.get(u'f7', u''),
            fields.get(u'f8', u''))
    except Exception:
        return u''


def read_current_for_sheet(doc, sheet_dict, config):
    """Read current NOSA field values from Revit (no protocol suggestions)."""
    sheet, _, current, name = _resolve_sheet(doc, sheet_dict)
    parsed = parse_nosa_number(current)
    params = _sp.read_nosa_fields_from_sheet(doc, sheet) if sheet else {}
    row_params = _sheet_row_params(sheet_dict)
    current_fields = _current_field_values(parsed, params, row_params, config)
    current_fields[u'f2'] = _sp.NOSA_ORIGINATOR
    current_fields[u'f9'] = name
    current_display = _build_display_number(current_fields)
    if not current_display and sheet:
        current_display = _sp.build_nosa_display_from_sheet(doc, sheet)
    return {
        u'f1': current_fields[u'f1'],
        u'f2': _sp.NOSA_ORIGINATOR,
        u'f3': current_fields[u'f3'],
        u'f4': current_fields[u'f4'],
        u'f5': current_fields[u'f5'],
        u'f6': current_fields[u'f6'],
        u'f7': current_fields[u'f7'],
        u'f8': current_fields[u'f8'],
        u'f9': name,
        u'current_fields': current_fields,
        u'current_display': current_display,
        u'status': u'loaded',
        u'status_label': u'Loaded',
        u'message': u'Current values from Revit.',
    }


def suggest_bulk_for_sheet(doc, sheet_dict, config, existing_numbers=None):
    """
    Suggest NOSA v2.2 fields for a sheet.
    Returns dict with f1-f9, sources, current_fields, new_number, status, status_label, message.
    """
    sheet, _, current, name = _resolve_sheet(doc, sheet_dict)
    parsed = parse_nosa_number(current)
    params = _sp.read_nosa_fields_from_sheet(doc, sheet) if sheet else {}
    row_params = _sheet_row_params(sheet_dict)
    package = _read_package(sheet_dict, sheet)
    building_key = building_key_from_name(name)

    current_fields = _current_field_values(parsed, params, row_params, config)
    current_fields[u'f9'] = name
    sources = {}

    raw_f1 = _first_nonempty(
        (parsed or {}).get(u'f1'),
        params.get(u'f1'),
        row_params.get(u'Project Number'),
        _sp.read_project_number(doc, sheet) if sheet else u'',
        config.get(u'f1', u''))
    f1, sources[u'f1'] = _pick_with_source([
        (u'Existing NOSA number', _normalise_f1((parsed or {}).get(u'f1', u''))),
        (u'Sheet / title block parameter', _normalise_f1(params.get(u'f1', u''))),
        (u'Drawing index data', _normalise_f1(row_params.get(u'Project Number', u''))),
        (u'Project information', _normalise_f1(
            _sp.read_project_number(doc, sheet) if sheet else u'')),
        (u'Config default', _normalise_f1(config.get(u'f1', u''))),
    ])

    f3, sources[u'f3'] = _pick_with_source([
        (u'Sheet name keyword', suggest_f3_strong_from_name(name)),
        (u'Sheet name keyword', suggest_f3_from_name(name)),
        (u'Existing NOSA number', (parsed or {}).get(u'f3')),
        (u'Sheet / title block parameter', params.get(u'f3')),
        (u'Drawing index data', row_params.get(u'Functional Breakdown')),
    ])
    if not f3 and sheet:
        f3 = suggest_f3_from_views(doc, sheet)
        if f3:
            sources[u'f3'] = u'Views on sheet'
    if not f3:
        f3 = config.get(u'f3', u'GA')
        sources[u'f3'] = u'Config default'

    f4 = suggest_f4_from_sheet_name(name)
    if f4:
        sources[u'f4'] = u'Sheet name (level)'
    else:
        f4, sources[u'f4'] = _pick_with_source([
            (u'Existing NOSA number', (parsed or {}).get(u'f4')),
            (u'Sheet / title block parameter', params.get(u'f4')),
            (u'Drawing index data', row_params.get(u'Spatial Breakdown')),
        ])
        if not f4 and sheet:
            f4 = suggest_f4_from_level(doc, sheet)
            if f4:
                sources[u'f4'] = u'View levels on sheet'
        if not f4:
            f4 = config.get(u'f4', u'XXX')
            sources[u'f4'] = u'Config default'

    f5, sources[u'f5'] = _pick_with_source([
        (u'Existing NOSA number', (parsed or {}).get(u'f5')),
        (u'Sheet / title block parameter', params.get(u'f5')),
        (u'Drawing index data', row_params.get(u'Form')),
        (u'Config default', config.get(u'f5', u'D')),
    ])

    f6, sources[u'f6'] = _pick_with_source([
        (u'Existing NOSA number', (parsed or {}).get(u'f6')),
        (u'Sheet / title block parameter', params.get(u'f6')),
        (u'Drawing index data', row_params.get(u'Discipline')),
        (u'Config default', config.get(u'f6', u'S')),
    ])

    f7, sources[u'f7'] = _pick_with_source([
        (u'Existing NOSA number', (parsed or {}).get(u'f7')),
        (u'Sheet / title block parameter', params.get(u'f7')),
        (u'Drawing index data', row_params.get(u'Document Number')),
        (u'Legacy sheet number', suggest_f7_from_legacy(current, name, f3)),
    ])
    if not f7:
        f7 = F7_HINTS.get(f3, u'2200')
        sources[u'f7'] = u'Functional breakdown hint'

    f8, sources[u'f8'] = _pick_with_source([
        (u'Existing NOSA number', (parsed or {}).get(u'f8')),
        (u'Sheet / title block parameter', params.get(u'f8')),
        (u'Drawing index data', row_params.get(u'Current Revision')),
    ])
    if not f8:
        sources[u'f8'] = u'(empty — set when issuing)'

    f2 = _sp.NOSA_ORIGINATOR
    sources[u'f2'] = u'NOSA protocol (fixed)'
    f9 = name
    sources[u'f9'] = u'Current sheet title'

    errors = validate_fields(f1, f3, f4, f5, f6, f7, f8)
    try:
        new_number = _sp.build_nosa_number(f1, f3, f4, f5, f6, f7, f8)
    except Exception:
        new_number = u''

    current_display = _build_display_number(current_fields)
    if not current_display and sheet:
        current_display = _sp.build_nosa_display_from_sheet(doc, sheet)
    current_f7 = current_fields.get(u'f7') or (parsed or {}).get(u'f7') or current

    status = u'ok'
    status_label = u'OK'
    message = u'Compliant with NOSA v2.2.'

    if errors:
        status = u'error'
        status_label = u'Error'
        message = u'; '.join(errors)
    elif new_number and new_number != current_display:
        status = u'change'
        status_label = u'Suggested change'
        message = u'Proposed number differs from current.'
    elif not current_display and not parsed:
        status = u'change'
        status_label = u'Suggested change'
        message = u'Current number is not NOSA format — fields suggested from sheet data.'

    if existing_numbers and f7 and f7 in existing_numbers and f7 != current_f7:
        status = u'error'
        status_label = u'Error'
        message = u'Duplicate: another sheet already uses this document number.'

    suggested_fields = {
        u'f1': f1, u'f2': f2, u'f3': f3, u'f4': f4, u'f5': f5,
        u'f6': f6, u'f7': f7, u'f8': f8, u'f9': f9,
    }
    return {
        u'f1': f1, u'f2': f2, u'f3': f3, u'f4': f4, u'f5': f5,
        u'f6': f6, u'f7': f7, u'f8': f8, u'f9': f9,
        u'package': package,
        u'name': name,
        u'_building_key': building_key,
        u'current_fields': current_fields,
        u'suggested_fields': suggested_fields,
        u'sources': sources,
        u'new_number': new_number,
        u'status': status,
        u'status_label': status_label,
        u'message': message,
    }


def apply_sheet_number(doc, sheet_id, new_number, new_name=None,
                       f1=None, f3=None, f4=None, f5=None, f6=None, f7=None, f8=None):
    sheet = doc.GetElement(coerce_element_id(sheet_id))
    if sheet is None:
        return False
    try:
        parsed = parse_nosa_number(new_number) if new_number else None
        if parsed:
            ok, _, _ = apply_nosa_to_sheet(
                doc, sheet,
                parsed[u'f1'], parsed[u'f3'], parsed[u'f4'], parsed[u'f5'],
                parsed[u'f6'], parsed[u'f7'], parsed[u'f8'],
                new_name=new_name)
            return ok
        if all(v is not None for v in (f1, f3, f4, f5, f6, f7)):
            ok, _, _ = apply_nosa_to_sheet(
                doc, sheet, f1, f3, f4, f5, f6, f7, f8 or u'',
                new_name=new_name)
            return ok
        if new_number:
            sheet.SheetNumber = new_number
        if new_name is not None:
            sheet.Name = new_name
        return True
    except Exception:
        return False
