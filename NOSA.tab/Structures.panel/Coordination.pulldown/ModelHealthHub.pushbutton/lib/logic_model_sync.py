# -*- coding: utf-8 -*-
"""Model Sync Checker — Logic

Parses a CSV from a structural calculation program (Robot, ETABS, SAP2000, STAAD)
and compares every row against the live Revit model (columns + beams + walls).

Expected CSV columns (flexible mapping):
  ID / Mark / Tag  |  Section / Type  |  Length (m)  |  Level / Floor

Returns a list of result dicts with status:
  OK | MISSING | SECTION | LENGTH | LEVEL | MULTI
"""
import io, csv, math
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
FT2M = 0.3048
LENGTH_TOL_M = 0.10   # ±100 mm tolerance on length comparison

# ── Revit helpers ──────────────────────────────────────────────────────────────



def _level_name(doc, el):
    try:
        for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                    DB.BuiltInParameter.LEVEL_PARAM,
                    DB.BuiltInParameter.WALL_BASE_CONSTRAINT]:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv: return lv.Name
    except Exception: pass
    return ''

def _length_m(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)
        if p and p.HasValue:
            return p.AsDouble() * FT2M
    except Exception: pass
    try:
        lc = el.Location
        if isinstance(lc, DB.LocationCurve):
            return lc.Curve.Length * FT2M
    except Exception: pass
    return None

def _mark(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        if p and p.HasValue and p.AsString():
            return p.AsString().strip()
    except Exception: pass
    return ''

def _type_name(el):
    try:
        return el.Name.strip()
    except Exception: pass
    return ''

def build_revit_index(doc):
    """Build dict: mark → {mark, type, length_m, level, id}"""
    index = {}
    cats = [
        DB.BuiltInCategory.OST_StructuralColumns,
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralFoundation,
        DB.BuiltInCategory.OST_Walls,
    ]
    for cat in cats:
        for el in (DB.FilteredElementCollector(doc)
                     .OfCategory(cat)
                     .WhereElementIsNotElementType()
                     .ToElements()):
            mk = _mark(el)
            if not mk:
                continue
            eid = get_id_value(el.Id)
            entry = {
                'mark':     mk,
                'type':     _type_name(el),
                'length_m': _length_m(el),
                'level':    _level_name(doc, el),
                'id':       eid,
            }
            index.setdefault(mk, []).append(entry)
    return index

# ── CSV parsing ────────────────────────────────────────────────────────────────

_ID_ALIASES      = ('id', 'mark', 'tag', 'element', 'ref')
_SECTION_ALIASES = ('section', 'type', 'profile', 'section type', 'sectiontype')
_LENGTH_ALIASES  = ('length', 'length (m)', 'length(m)', 'len', 'len_m')
_LEVEL_ALIASES   = ('level', 'floor', 'storey', 'story', 'elevation')

def _resolve(header_lower, aliases):
    for a in aliases:
        if a in header_lower:
            return header_lower.index(a)
    return None

def parse_calc_csv(path):
    """Returns list of {mark, section, length_m, level} from CSV."""
    rows = []
    with io.open(path, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        raw_headers = next(reader, [])
        hl = [h.strip().lower() for h in raw_headers]

        ci_id  = _resolve(hl, _ID_ALIASES)
        ci_sec = _resolve(hl, _SECTION_ALIASES)
        ci_len = _resolve(hl, _LENGTH_ALIASES)
        ci_lvl = _resolve(hl, _LEVEL_ALIASES)

        if ci_id is None:
            raise ValueError(
                u'CSV must have an ID/Mark column. Headers found: {}'.format(
                    ', '.join(raw_headers)))

        for line in reader:
            if not line or not any(line):
                continue
            def _cell(i):
                if i is None or i >= len(line): return ''
                return line[i].strip()

            mark = _cell(ci_id)
            if not mark:
                continue
            sec = _cell(ci_sec)
            lv  = _cell(ci_lvl)
            raw_len = _cell(ci_len).replace(',', '.')
            try:
                length_m = float(raw_len) if raw_len else None
            except ValueError:
                length_m = None

            rows.append({'mark': mark, 'section': sec,
                         'length_m': length_m, 'level': lv})
    return rows

# ── Comparison ─────────────────────────────────────────────────────────────────

def _normalise(s):
    return s.strip().lower().replace(' ', '').replace('-', '').replace('_', '')

def compare(calc_rows, revit_index):
    """Return list of result dicts."""
    results = []
    for cr in calc_rows:
        mk = cr['mark']
        matches = revit_index.get(mk, [])

        if not matches:
            results.append({
                'mark':        mk,
                'calc_sec':    cr['section'],
                'calc_len':    _fmt(cr['length_m']),
                'calc_level':  cr['level'],
                'revit_sec':   '—',
                'revit_len':   '—',
                'revit_level': '—',
                'status':      'MISSING',
                'revit_id':    '—',
            })
            continue

        rv = matches[0]
        issues = []
        if cr['section'] and rv['type']:
            if _normalise(cr['section']) != _normalise(rv['type']):
                issues.append('SECTION')
        if cr['length_m'] is not None and rv['length_m'] is not None:
            if abs(cr['length_m'] - rv['length_m']) > LENGTH_TOL_M:
                issues.append('LENGTH')
        if cr['level'] and rv['level']:
            if _normalise(cr['level']) != _normalise(rv['level']):
                issues.append('LEVEL')

        if not issues:
            status = 'OK'
        elif len(issues) == 1:
            status = issues[0]
        else:
            status = 'MULTI'

        results.append({
            'mark':        mk,
            'calc_sec':    cr['section'],
            'calc_len':    _fmt(cr['length_m']),
            'calc_level':  cr['level'],
            'revit_sec':   rv['type'],
            'revit_len':   _fmt(rv['length_m']),
            'revit_level': rv['level'],
            'status':      status,
            'revit_id':    rv['id'],
        })

    # Sort: MISSING first, then MULTI/SECTION/LENGTH/LEVEL, then OK
    _order = {'MISSING': 0, 'MULTI': 1, 'SECTION': 2, 'LENGTH': 3, 'LEVEL': 4, 'OK': 5}
    results.sort(key=lambda r: (_order.get(r['status'], 9), r['mark']))
    return results

def _fmt(v):
    if v is None: return '—'
    return '{:.2f}'.format(v)

def export_csv(results, path):
    headers = ['Mark', 'Status',
               'Calc Section', 'Revit Section',
               'Calc Length (m)', 'Revit Length (m)',
               'Calc Level', 'Revit Level',
               'Revit ID']
    keys = ['mark', 'status',
            'calc_sec', 'revit_sec',
            'calc_len', 'revit_len',
            'calc_level', 'revit_level',
            'revit_id']
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in results:
            w.writerow([r.get(k, '') for k in keys])
