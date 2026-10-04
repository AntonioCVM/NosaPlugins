# -*- coding: utf-8 -*-
"""
Project values of the 0900 General notes (T8.13). Each value is a NOSA_GN_* shared parameter of
Project Information (the single source of truth); `apply` writes them into the text notes of the
"0900 General notes" drafting view, keeping the text formatting, and `differences` tells the drawing
check when the sheet no longer matches Project Information.

Slots locate a value inside a note: ('re', pattern with a named group v, occurrence or None = all)
or ('line', pattern identifying the note, line index) for the one-value-per-line table notes.
"""
from __future__ import division
import math
import re

VIEW_NAME = u'0900 General notes'
PARAM_PREFIX = u'NOSA_GN_'
ANCHORAGE_DIAMETERS = (8, 10, 12, 16, 20, 25, 32, 40)

_NUM = r'[\d.]+'

# (key, label, group, default, slots)
FIELDS = [
    (u'Concrete_Grade', u'Concrete grade', u'Concrete', u'C40/50',
     [('re', r'Concrete grade\s+(?P<v>C\d+/\d+)', None)]),
    (u'Cover_Typical', u'Nominal cover — typical', u'Concrete', u'50mm', [('re', r'Typical\t+(?P<v>\d+\s?mm)', None)]),
    (u'Cover_Slabs', u'Nominal cover — slabs', u'Concrete', u'40mm', [('re', r'Slabs\t+(?P<v>\d+\s?mm)', None)]),
    (u'Anchorage_Concrete', u'Anchorage & lap table concrete class', u'Concrete', u'C25/30',
     [('re', r'minimum concrete strength of\s*:\s*(?P<v>C\d+/\d+)', None)]),
    (u'Penetration_Max', u'Penetrations not shown up to', u'Concrete', u'200mm',
     [('re', r'equal to or less than (?P<v>\d+\s?mm) square', None)]),
    (u'Column_Hole_Dia', u'Hole beside a column — diameter', u'Concrete', u'150mm',
     [('re', r'Limited to a single\s+(?P<v>\d+\s?mm) diameter', None)]),
    (u'Column_Hole_Clear', u'Hole beside a column — minimum from column face', u'Concrete', u'275mm',
     [('re', r'Minimum from f/c of hole\s+(?P<v>\d+\s?mm)', None)]),
    (u'Fire_Resistance', u'Fire resistance (REI minutes)', u'Fire & movement', u'60',
     [('re', r'REI\s+(?P<v>\d+) min', None)]),
    (u'Deflection_Total', u'Deflection limit — total load (L/x)', u'Fire & movement', u'250',
     [('re', r'L / (?P<v>\d+)\s+Total load', None)]),
    (u'Deflection_Cantilever', u'Deflection limit — cantilevers (L/x)', u'Fire & movement', u'180',
     [('re', r'L / (?P<v>\d+)\s+Cantilevers', None)]),
    (u'Deflection_Imposed', u'Deflection limit — imposed load (L/x)', u'Fire & movement', u'360',
     [('re', r'L / (?P<v>\d+)\s+Imposed\s+load(?!\s*\()', None)]),
    (u'Deflection_Brittle', u'Deflection limit — imposed, brittle finishes (L/x)', u'Fire & movement', u'500',
     [('re', r'L / (?P<v>\d+)\s+Imposed load \(with brittle', None)]),
    (u'Deflection_Columns', u'Column sway limit (H/x)', u'Fire & movement', u'300',
     [('re', r'H / (?P<v>\d+)\s+Columns', None)]),
    (u'Free_Zone', u'Free zone below suspended structure', u'Fire & movement', u'50mm',
     [('re', r'allow for a (?P<v>\d+\s?mm) free zone', None)]),
    (u'Cladding_Sway', u'Frame movement for cladding — sway', u'Fire & movement', u'1/100',
     [('re', r'Sway\s+(?P<v>1/\d+) of height', None)]),
    (u'Cladding_Vertical', u'Frame movement for cladding — vertical', u'Fire & movement', u'1/250',
     [('re', r'Vertical\s+(?P<v>1/\d+) of length', None)]),
    (u'Glass_Barrier_Deflection', u'Glass balustrade deflection limit', u'Fire & movement', u'10mm',
     [('re', r'glass balustrades should be kept to a maximum of (?P<v>\d+\s?mm)', None)]),
    (u'Wind_Terrain', u'Wind — terrain', u'Wind & thermal', u'Sea',
     [('re', r'Terrain \t+(?P<v>[A-Za-z]+)', None), ('line', r'^\w+\s*\r\d+\s?m/s', 0)]),
    (u'Wind_Speed', u'Wind — basic wind speed', u'Wind & thermal', u'27 m/s',
     [('re', r'Basic wind speed\s+\t(?P<v>\d+\s?m/s)', None), ('line', r'^\w+\s*\r\d+\s?m/s', 1)]),
    (u'Impact_Vertical', u'Vertical impact loading', u'Wind & thermal', u'0.75KN', [('line', r'^\w+\s*\r\d+\s?m/s', 2)]),
    (u'Impact_Horizontal', u'Horizontal impact loading', u'Wind & thermal', u'0.75KN',
     [('line', r'^\w+\s*\r\d+\s?m/s', 3)]),
    (u'Thermal_External', u'Thermal range — external', u'Wind & thermal', u'-05º to +40º',
     [('line', r'^\w+\s*\r\d+\s?m/s', 4)]),
    (u'Thermal_Internal', u'Thermal range — internal', u'Wind & thermal', u' 00º to +30º',
     [('line', r'^\w+\s*\r\d+\s?m/s', 5)]),
    (u'Steel_Grade', u'Structural steel grade', u'Steelwork', u'S275', [('re', r'minimum grade of (?P<v>S\d{3})', None)]),
    (u'Execution_Class', u'Steel execution class', u'Steelwork', u'EXC2', [('re', r'execution class (?P<v>EXC\d)', None)]),
    (u'Corrosion_Interior', u'Corrosivity — interior', u'Steelwork', u'C2',
     [('re', r'Interior\t+\s*(?P<v>C[1-5X])', None)]),
    (u'Corrosion_Exterior', u'Corrosivity — exterior', u'Steelwork', u'C5',
     [('re', r'Exterior\t+\s*(?P<v>C[1-5X])', None)]),
    (u'Tie_Force', u'Minimum accidental tie force', u'Steelwork', u'75KN', [('re', r'shear force or (?P<v>\d+\s?[kK]N)', None)]),
    (u'Bolt_Class', u'Bolt property class', u'Steelwork', u'8.8', [('re', r'property class (?P<v>\d+\.\d+)', 0)]),
    (u'Grout_Strength', u'Grout strength at 28 days', u'Steelwork', u'50N/mm²',
     [('re', r'strength at 28 days of (?P<v>\d+\s?N/mm[²2])', None)]),
    (u'Weld_Min', u'Minimum weld leg length', u'Steelwork', u'6mm', [('re', r'weld leg length be less than (?P<v>\d+\s?mm)', None)]),
    (u'Plate_Min', u'Minimum plate thickness', u'Steelwork', u'8mm', [('re', r'plate thickness be less than (?P<v>\d+\s?mm)', None)]),
    (u'Buried_Steel_Cover', u'Concrete surround to buried steel', u'Steelwork', u'100mm',
     [('re', r'minimum (?P<v>\d+\s?mm) concrete surround', None)]),
    (u'Timber_Solid', u'Solid timber strength class', u'Timber', u'C16', [('re', r'BS EN 338\)\t+(?P<v>C\d+)', None)]),
    (u'Timber_Glulam', u'Glulam strength class', u'Timber', u'GL28h', [('re', r'BS EN 14080\)\t+(?P<v>GL\d+[hc])', None)]),
    (u'Timber_Moisture', u'Timber maximum moisture content', u'Timber', u'12%',
     [('re', r'moisture content of all structural timber to be (?P<v>\d+%)', None)]),
    (u'Brick_Below_Strength', u'Brickwork below DPC — strength', u'Masonry', u'20N/mm²',
     [('re', r'Brickwork below DPC level is to be a minimum compressive strength of (?P<v>' + _NUM + r'\s?N/mm[²2])', None)]),
    (u'Brick_Below_Absorption', u'Brickwork below DPC — water absorption', u'Masonry', u'7%',
     [('re', r'Brickwork below DPC[^\r]*?water absorption of (?P<v>\d+%)', None)]),
    (u'Brick_Above_Strength', u'Brickwork above DPC — strength', u'Masonry', u'20.0N/mm²',
     [('re', r'brickwork above DPC level is to have a minimum compressive strength of\s*(?P<v>' + _NUM + r'\s?N/mm[²2])', None)]),
    (u'Brick_Above_Absorption', u'Brickwork above DPC — absorption', u'Masonry', u'12%',
     [('re', r'brickwork above DPC[^\r]*?absorption rate of (?P<v>\d+%)', None)]),
    (u'Block_Below_Absorption', u'Blockwork below DPC — water absorption', u'Masonry', u'7%',
     [('re', r'water absorption rate of (?P<v>\d+%)', None)]),
    (u'Block_Below_Strength', u'Blockwork below DPC — strength', u'Masonry', u'10.4 N/mm²',
     [('re', r'mean compressive strength\s+(?P<v>' + _NUM + r'\s?N/mm[²2])', 0)]),
    (u'Block_Above_Strength', u'Blockwork above DPC — strength', u'Masonry', u'10.4 N/mm²',
     [('re', r'mean compressive strength\s+(?P<v>' + _NUM + r'\s?N/mm[²2])', 1)]),
    (u'Mortar_Class', u'Mortar class above DPC (BS EN 998-2)', u'Masonry', u'M6',
     [('re', r'Compressive strength class\s+(?P<v>M\d+)', None)]),
    (u'Wall_Tie_Vertical', u'Wall ties — vertical centres', u'Masonry', u'450mm',
     [('re', r'wall ties at (?P<v>\d+\s?mm) vertical', None)]),
    (u'Wall_Tie_Horizontal', u'Wall ties — horizontal centres', u'Masonry', u'900mm',
     [('re', r'vertical and (?P<v>\d+\s?mm) horizontal centres', None)]),
    (u'Movement_Brick', u'Movement joints — brickwork', u'Masonry', u'12m',
     [('re', r'All brickwork leaves[^\r]*?maximum of (?P<v>\d+\s?m) centres', None)]),
    (u'Movement_Block', u'Movement joints — blockwork', u'Masonry', u'6m',
     [('re', r'All blockwork leaves[^\r]*?maximum of (?P<v>\d+\s?m) centres', None)]),
    (u'Movement_Cavity', u'Movement joints — cavity walls', u'Masonry', u'9m',
     [('re', r'Cavity walls to have vertical movement joints at a maximum of (?P<v>\d+\s?m) centres', None)]),
    (u'Excavation_Angle', u'Excavation influence zone angle (degrees)', u'Earthworks', u'30',
     [('re', r'defined by a (?P<v>\d+)-degree angle', None)]),
    (u'Obstruction_Depth', u'Obstructions removed below founding level', u'Earthworks', u'1.0m',
     [('re', r'to a minimum (?P<v>' + _NUM + r'\s?m) below the proposed founding level', None)]),
    (u'Pile_Survey_Time', u'Found piles surveyed within', u'Earthworks', u'48 hours',
     [('re', r'provided to the Engineer within (?P<v>\d+ hours)', None)]),
    (u'Review_Period', u'Contractor design review period', u'Contractor design', u'two weeks',
     [('re', r'turn around period is expected to be (?P<v>\w+ weeks?)', None)]),
    (u'Hard_Copies', u'Hard copies requested', u'Contractor design', u'2',
     [('re', r'contractor is to provide (?P<v>\d+) no\. copies', None)]),
]


def param_name(key):
    return PARAM_PREFIX + key


def defaults():
    return dict((f[0], f[3]) for f in FIELDS)


def find(text, slot):
    """[(start, end)] of the value spans of one slot in a note's plain text."""
    kind, pattern, which = slot
    if kind == 're':
        spans = [m.span('v') for m in re.finditer(pattern, text)]
        if which is not None:
            spans = spans[which:which + 1]
        return spans
    if not re.search(pattern, text):
        return []
    pos = 0
    for i, line in enumerate(text.split(u'\r')):
        if i == which:
            return [(pos, pos + len(line))]
        pos += len(line) + 1
    return []


def edits(text, values):
    """[(start, end, new value, key)] for one note, non-overlapping, sorted from the end."""
    out = []
    for key, _label, _group, _default, slots in FIELDS:
        if key not in values or values[key] is None:
            continue
        for slot in slots:
            for start, end in find(text, slot):
                if text[start:end] != values[key]:
                    out.append((start, end, values[key], key))
    out.sort(key=lambda e: -e[0])
    return out


def read_text_values(texts):
    """{key: value as written on the sheet} — first slot match across the notes."""
    found = {}
    for key, _label, _group, _default, slots in FIELDS:
        for text in texts:
            for slot in slots:
                spans = find(text, slot)
                if spans and key not in found:
                    start, end = spans[0]
                    found[key] = text[start:end]
    return found


# ── anchorage & lap table (EC2 8.4 / 8.7 with the UK NA, as the template's table) ──────────────

def _fck(concrete_class):
    m = re.match(r'C(\d+)/\d+', (concrete_class or u'').strip())
    return float(m.group(1)) if m else 25.0


def _ceil(value, step=10.0):
    return int(math.ceil(value / step - 1e-9) * step)


def anchorage_table(concrete_class, fyk=500.0, gamma_s=1.15, gamma_c=1.5, cd=25.0):
    """
    {dia: {'straight': (good, poor), 'other': (good, poor), 'lap50': (good, poor), 'lap100': (good, poor)}}
    in mm. fbd = 2.25·η1·η2·fctd (UK NA αct = 1),
    straight bars with α2 = 1 − 0.15(cd − φ)/φ in [0.7, 1] for cd = 25 mm, laps α6 = 1.4 / 1.5,
    poor bond η1 = 0.7, η2 = (132 − φ)/100 above 32 mm; rounded up to 10 mm.
    """
    fck = _fck(concrete_class)
    fctk = 0.7 * 0.30 * fck ** (2.0 / 3.0) if fck <= 50 else 0.7 * 2.12 * math.log(1 + (fck + 8) / 10.0)
    fctd = fctk / gamma_c
    fyd = fyk / gamma_s
    table = {}
    for dia in ANCHORAGE_DIAMETERS:
        eta2 = 1.0 if dia <= 32 else (132.0 - dia) / 100.0
        rows = {}
        for bond, eta1 in (('good', 1.0), ('poor', 0.7)):
            lb_rqd = dia / 4.0 * fyd / (2.25 * eta1 * eta2 * fctd)
            alpha2 = min(1.0, max(0.7, 1.0 - 0.15 * (cd - dia) / dia))
            straight = alpha2 * lb_rqd
            rows.setdefault('straight', []).append(_ceil(straight))
            rows.setdefault('other', []).append(_ceil(lb_rqd))
            rows.setdefault('lap50', []).append(_ceil(1.4 * straight))
            rows.setdefault('lap100', []).append(_ceil(1.5 * straight))
        table[dia] = dict((k, tuple(v)) for k, v in rows.items())
    return table


def _fbd_ratio(concrete_class, fyk=500.0, gamma_s=1.15, gamma_c=1.5):
    """lb,rqd / φ in good bond (η2 = 1)."""
    fck = _fck(concrete_class)
    fctk = 0.7 * 0.30 * fck ** (2.0 / 3.0) if fck <= 50 else 0.7 * 2.12 * math.log(1 + (fck + 8) / 10.0)
    return (fyk / gamma_s) / (4.0 * 2.25 * fctk / gamma_c)


def compression_multiples(concrete_class):
    """The 'reinforcement in compression' column, in the template's note order and rounding."""
    base = _fbd_ratio(concrete_class)

    def half_up(v):
        return int(math.floor(v + 0.5))

    def up(v):
        return int(math.ceil(v - 1e-9))
    return [half_up(base), half_up(base / 0.7), half_up(base), half_up(base / 0.7),
            up(1.4 * base), up(1.4 * base / 0.7), up(1.5 * base), up(1.5 * base / 0.7)]


def anchorage_column(table, dia):
    """The 8 values of one diameter column, in the template's note order."""
    row = table[dia]
    return [row[k][i] for k in ('straight', 'other', 'lap50', 'lap100') for i in (0, 1)]


def table_note_edits(text, concrete_class):
    """
    [(start, end, value)] to refresh one anchorage-table note: a diameter column (first line the
    diameter, then 8 values) or the compression column (8 values ending in Ø). Empty if neither.
    """
    lines = text.split(u'\r')
    positions, pos = [], 0
    for line in lines:
        positions.append((pos, pos + len(line), line.strip()))
        pos += len(line) + 1
    filled = [p for p in positions if p[2]]
    if len(filled) == 9 and filled[0][2].isdigit() and int(filled[0][2]) in ANCHORAGE_DIAMETERS             and all(p[2].isdigit() for p in filled[1:]):
        values = [str(v) for v in anchorage_column(anchorage_table(concrete_class), int(filled[0][2]))]
        cells = filled[1:]
    elif len(filled) == 8 and all(p[2].endswith(u'Ø') and p[2][:-1].isdigit() for p in filled):
        values = [u'{}Ø'.format(v) for v in compression_multiples(concrete_class)]
        cells = filled
    else:
        return []
    out = []
    for (start, end, current), value in zip(cells, values):
        if current != value:
            lead = len(text[start:end]) - len(text[start:end].lstrip())
            out.append((start + lead, start + lead + len(current), value))
    return sorted(out, key=lambda e: -e[0])
