# -*- coding: utf-8 -*-
"""
NOSA File Naming Protocol V2.2 (00000-NOSA-TN-XXX-T-X-0018-I23) as plain rules (T8.12).

The protocol is a guide: a code missing from its tables is accepted with a warning when it keeps
the field's length (user rule 2026-10-04: record new codes in the project BEP). The document-number
series follow the NOSA Revit template, which the user confirmed as the reference.
"""
import re

ERROR = u'error'
WARNING = u'warning'

ORIGINATOR = u'NOSA'

F3_CODES = {
    u'AM': u'Analytical model', u'DT': u'Details', u'EL': u'Elevations', u'GA': u'General arrangement',
    u'GM': u'Geometrical model', u'PV': u'Plan views', u'RC': u'Reinforced concrete', u'SC': u'Sections',
    u'CL': u'Calculations', u'CS': u'Condition survey', u'DS': u'Design certificate',
    u'HS': u'Health and safety', u'IS': u'Issue sheet', u'MS': u'Method statement', u'RA': u'Risk assessment',
    u'RI': u'RFI', u'RO': u'Revision overview', u'RP': u'Reports, registers, schedules', u'RS': u'IRS',
    u'SP': u'Specifications', u'TN': u'Technical notes', u'ZZ': u'Multiple document types',
}
F4_CODES = {
    u'XXX': u'No specific location', u'ZZZ': u'Multiple locations', u'000': u'Ground floor',
    u'BA1': u'Basement -1', u'BA2': u'Basement -2', u'MZ1': u'Mezzanine', u'RF0': u'Roof (general)',
    u'RF1': u'Roof level 01', u'FND': u'Foundation level', u'A01': u'Block A level 01',
    u'AEL': u'Block A elevation', u'ASC': u'Block A section', u'BZZ': u'Block B multiple',
    u'CB2': u'Block C basement 02', u'CZZ': u'Block C multiple', u'ADD': u'Additional structure',
    u'PTL': u'Project title', u'FNP': u'File naming protocols', u'STA': u'NOSA standards',
}
F5_CODES = {u'D': u'Drawing', u'G': u'Graph', u'I': u'Image', u'L': u'List', u'M': u'Model',
            u'T': u'Textual', u'V': u'Video or audio'}
F6_CODES = {u'B': u'Building surveying', u'C': u'Civil', u'D': u'Demolition', u'G': u'Ground engineering',
            u'H': u'Health and safety', u'O': u'Other', u'P': u'Project management', u'S': u'Structural',
            u'X': u'Non-discipline specific', u'Z': u'Multiple disciplines'}

# (first, last, description, expected F3 codes or None, expected F5 codes or None) — NOSA template series
SERIES = [
    (0, 0, u'Issue sheet', (u'IS', u'RP'), (u'L',)),
    (1, 1, u'Project title', None, None),
    (2, 2, u'File naming protocols', None, None),
    (3, 3, u'NOSA standards', None, None),
    (4, 899, u'Text documents', None, None),
    (900, 999, u'Specifications and general notes', None, None),
    (1000, 1499, u'Existing structure', None, (u'D',)),
    (1500, 1799, u'Demolition', None, (u'D',)),
    (1800, 1999, u'Cut and fill', None, (u'D',)),
    (2000, 2099, u'Gridlines with dimensions', (u'GA', u'PV'), (u'D',)),
    (2100, 2199, u'Site plans', (u'GA', u'PV'), (u'D',)),
    (2200, 2499, u'General arrangement plans', (u'GA', u'PV'), (u'D',)),
    (2500, 2999, u'RC reinforcement plans', (u'RC',), (u'D',)),
    (3000, 3499, u'General sections and elevations', (u'SC', u'EL', u'GA'), (u'D',)),
    (3500, 3999, u'RC sections', (u'RC', u'SC'), (u'D',)),
    (4000, 4499, u'Construction details', (u'DT',), (u'D',)),
    (4500, 4999, u'RC details', (u'RC', u'DT'), (u'D',)),
    (5000, 5499, u'Quantity schedules', (u'RP',), (u'L',)),
    (5500, 5999, u'Bar bending schedules', (u'RP', u'RC'), (u'L',)),
    (6000, 6499, u'Structural analysis models', (u'AM',), (u'M',)),
    (6500, 6999, u'Revit BIM models', (u'GM',), (u'M',)),
    (7000, 7499, u'General drawings', None, (u'D',)),
    (7500, 7999, u'Sketches', None, (u'D',)),
    (8000, 8999, u'Health and safety', (u'HS',), None),
    (9999, 9999, u'Superseded', None, None),
]

# (first, last, package) — the sheet packages of the NOSA template (Package parameter)
PACKAGES = [
    (0, 999, u"0000's - Documentation"),
    (1000, 1999, u"1000's - Existing and demolition drawings"),
    (2000, 2999, u"2000's - Plan views"),
    (3000, 3999, u"3000's - Sections and elevations"),
    (4000, 4499, u"4000's - Details"),
    (4500, 4999, u"4500's - RC details"),
    (5000, 5499, u"5000's - Schedules"),
    (5500, 5999, u"5500's - RC schedules"),
    (6000, 6999, u"6000's - Structural analysis models"),
    (7000, 7999, u"7000's - General drawings"),
    (8000, 8999, u"8000's - Health and safety"),
    (9999, 9999, u'SS - Superseded'),
]

_REVISION = re.compile(r'^(P|I|C|PC)(\d{2})(\.\d{2})?$')


def package(f7):
    """The template package name of a 4-digit document number, or None."""
    try:
        n = int(f7)
    except (TypeError, ValueError):
        return None
    for first, last, name in PACKAGES:
        if first <= n <= last:
            return name
    return None


def series(f7):
    """The template series row of a 4-digit document number, or None."""
    try:
        n = int(f7)
    except (TypeError, ValueError):
        return None
    for row in SERIES:
        if row[0] <= n <= row[1]:
            return row
    return None


def check_fields(fields):
    """[(severity, field, message)] for one document's fields f1..f8 (str or empty)."""
    out = []
    f = dict((k, (fields.get(k) or u'').strip()) for k in (u'f1', u'f2', u'f3', u'f4', u'f5', u'f6', u'f7', u'f8'))
    f[u'f2'] = f[u'f2'] or ORIGINATOR

    def need(key, ok, message):
        if not ok:
            out.append((ERROR, key, message))
            return False
        return True

    need(u'f1', re.match(r'^\d{5}$', f[u'f1']), u'F1 project number must be 5 digits (00000 for company-wide).')
    need(u'f2', f[u'f2'] == ORIGINATOR, u'F2 originator must be NOSA.')
    for key, length, table, label, pattern in (
            (u'f3', 2, F3_CODES, u'F3 functional breakdown', r'^[A-Z]{2}$'),
            (u'f4', 3, F4_CODES, u'F4 spatial breakdown', r'^[A-Z0-9]{3}$'),
            (u'f5', 1, F5_CODES, u'F5 form', r'^[A-Z]$'),
            (u'f6', 1, F6_CODES, u'F6 discipline', r'^[A-Z]$')):
        value = f[key]
        if need(key, re.match(pattern, value), u'{} must be {} capital character(s) (now "{}").'.format(
                label, length, value)):
            known = value in table or (key == u'f4' and value.isdigit())
            if not known:
                out.append((WARNING, key, u'{} "{}" is not in the protocol tables — fine if it is recorded in the '
                                          u'project BEP.'.format(label, value)))
    if need(u'f7', re.match(r'^\d{4}$', f[u'f7']), u'F7 document number must be 4 digits.'):
        row = series(f[u'f7'])
        if row is None:
            out.append((WARNING, u'f7', u'F7 {} is outside the NOSA template series.'.format(f[u'f7'])))
        else:
            _first, _last, label, f3s, f5s = row
            if f3s and f[u'f3'] and f[u'f3'] not in f3s:
                out.append((WARNING, u'f3', u'{} series ({}xx) usually uses F3 {}, not {}.'.format(
                    label, f[u'f7'][:2], u'/'.join(f3s), f[u'f3'])))
            if f5s and f[u'f5'] and f[u'f5'] not in f5s:
                out.append((WARNING, u'f5', u'{} series ({}xx) is form {}, not {}.'.format(
                    label, f[u'f7'][:2], u'/'.join(f5s), f[u'f5'])))
    m = _REVISION.match(f[u'f8'])
    if need(u'f8', m, u'F8 revision must be P01, I01, C01 or PC01 style (now "{}").'.format(f[u'f8'])) and m.group(3):
        out.append((WARNING, u'f8', u'F8 {} is a draft: remove the {} suffix before a formal issue.'.format(
            f[u'f8'], m.group(3))))
    return out


def file_name(fields, description=u'', issue_date=None):
    """XXXXX-NOSA-F3-F4-F5-F6-F7-F8[ description]; issue sheets get ' Issue Sheet (yymmdd)'."""
    parts = [fields.get(k) or u'' for k in (u'f1', u'f2', u'f3', u'f4', u'f5', u'f6', u'f7', u'f8')]
    parts[1] = parts[1] or ORIGINATOR
    name = u'-'.join(parts)
    if issue_date is not None:
        return u'{} Issue Sheet ({})'.format(name, issue_date.strftime('%y%m%d'))
    return u'{} {}'.format(name, description).strip() if description else name
