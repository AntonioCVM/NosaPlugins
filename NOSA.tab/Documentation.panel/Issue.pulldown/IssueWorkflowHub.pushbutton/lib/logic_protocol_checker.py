# -*- coding: utf-8 -*-
import os
import sys
import imp

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import sheet_protocol as _sp

_sn = None
_VALID_F6 = None


def _sheet_namer():
    global _sn, _VALID_F6
    if _sn is None:
        own_dl = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        panel  = os.path.dirname(own_dl)
        # SheetNamer lives in Sheets.pulldown since v5.7; check both locations
        for base in (os.path.join(panel, 'Sheets.pulldown'), own_dl):
            for suffix in ('nobutton', 'pushbutton'):
                path = os.path.join(base, 'SheetNamer.{}'.format(suffix), 'lib', 'logic.py')
                if os.path.isfile(path):
                    _sn = imp.load_source('sheet_namer_logic', path)
                    break
            if _sn is not None:
                break
        if _sn is None:
            raise IOError(u'Sheet Namer logic not found (Sheets or Issue pulldown).')
        _VALID_F6 = {code for code, _ in _sn.F6_CODES}
    return _sn


class SheetCheckResult(object):
    def __init__(self, sheet_number, sheet_name, status, issues):
        self.sheet_number = sheet_number
        self.sheet_name = sheet_name
        self.status = status
        self.issues = issues


def _read_fields(doc, sheet):
    sn = _sheet_namer()
    fields = sn.read_fields_from_sheet(doc, sheet.Id)
    if fields:
        return fields
    parsed = sn.parse_nosa_number(sheet.SheetNumber or u'')
    return parsed or {}


def _validate_sheet(doc, sheet, number_counts):
    number = (sheet.SheetNumber or u'').strip()
    name = sheet.Name or u''
    issues = []

    if not number:
        return SheetCheckResult(number, name, 'red', [u'Sheet has no number.'])

    sn = _sheet_namer()
    legacy_parsed = sn.parse_nosa_number(number)
    if legacy_parsed:
        issues.append(
            u'Sheet number still holds the legacy full NOSA string — should be F7 only.')

    fields = _read_fields(doc, sheet)
    if legacy_parsed:
        for k, v in legacy_parsed.items():
            fields.setdefault(k, v)

    f1 = fields.get('f1', _sp.read_project_number(doc, sheet))
    f3 = fields.get('f3', _sp.param_str(sheet, 'Functional Breakdown'))
    f4 = fields.get('f4', _sp.param_str(sheet, 'Spatial Breakdown'))
    f5 = fields.get('f5', _sp.read_form_value(doc, sheet))
    f6 = fields.get('f6', _sp.param_str(sheet, 'Discipline'))
    f7 = fields.get('f7', _sp.read_document_number(doc, sheet))
    f8 = fields.get('f8', _sp.param_str(sheet, 'Current Revision'))

    for err in sn.validate_fields(f1, f3, f4, f5, f6, f7, f8):
        issues.append(err)

    if f6 and f6.upper() not in _VALID_F6:
        issues.append(u'F6 discipline "{}" is not a recognised NOSA code.'.format(f6))

    if number in number_counts and number_counts[number] > 1:
        issues.append(u'Duplicate sheet number ({} copies).'.format(number_counts[number]))

    if f7 and number and not legacy_parsed and f7 != number:
        issues.append(
            u'Sheet number "{}" does not match document number (F7) "{}".'.format(number, f7))

    if not issues:
        return SheetCheckResult(number, name, 'green', [])
    status = 'red' if any('Duplicate' in i or 'legacy' in i for i in issues) else 'amber'
    return SheetCheckResult(number, name, status, issues)


def run_protocol_checks(doc):
    sheets = list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements())
    number_counts = {}
    for sheet in sheets:
        num = (sheet.SheetNumber or u'').strip()
        if num:
            number_counts[num] = number_counts.get(num, 0) + 1

    results = []
    for sheet in sorted(sheets, key=lambda s: s.SheetNumber or u''):
        results.append(_validate_sheet(doc, sheet, number_counts))
    return results


def summarise(results):
    green = sum(1 for r in results if r.status == 'green')
    amber = sum(1 for r in results if r.status == 'amber')
    red = sum(1 for r in results if r.status == 'red')
    return {'total': len(results), 'green': green, 'amber': amber, 'red': red}
