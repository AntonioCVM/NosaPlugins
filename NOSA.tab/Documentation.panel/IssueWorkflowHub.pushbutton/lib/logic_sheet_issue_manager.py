# -*- coding: utf-8 -*-
import os, sys, json, datetime

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
_LOG = u'IssueWorkflowHub'

_LOG_KEY = u'sheet_issues'
_CONFIGS = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs')


def _log_path():
    return os.path.join(_CONFIGS, '_sheet_issues_log.json')


def load_log():
    path = _log_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            log_swallowed(_LOG, u'load_log')
    return []


def save_log(records):
    try:
        if not os.path.isdir(_CONFIGS):
            os.makedirs(_CONFIGS)
        with open(_log_path(), 'w') as f:
            json.dump(records, f, indent=2)
    except Exception:
        log_swallowed(_LOG, u'save_log')


def collect_sheets(doc):
    sheets = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .ToElements()
    )
    return sorted(sheets, key=lambda s: s.SheetNumber or u'')


def sheet_revision(sheet):
    try:
        rev_ids = list(sheet.GetAllRevisionIds())
        if rev_ids:
            rev = sheet.Document.GetElement(rev_ids[-1])
            if rev is not None:
                seq = rev.get_Parameter(DB.BuiltInParameter.PROJECT_REVISION_SEQUENCE_NUM)
                return seq.AsString() if seq else str(get_id_value(rev_ids[-1]))
    except Exception:
        log_swallowed(_LOG, u'sheet_revision')
    return u''


def add_issue(records, sheet_numbers, revision, recipient, package, notes, issued_by):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    for sn in sheet_numbers:
        records.append({
            'date':       now,
            'sheet':      sn,
            'revision':   revision,
            'recipient':  recipient,
            'package':    package,
            'notes':      notes,
            'issued_by':  issued_by,
        })
    return records


def delete_records(records, indices):
    indices_set = set(indices)
    return [r for i, r in enumerate(records) if i not in indices_set]


def export_csv(records, path):
    from nosa_utils.export_io import write_csv
    keys = ('date', 'sheet', 'revision', 'recipient', 'package', 'notes', 'issued_by')
    write_csv(path, ['Date', 'Sheet', 'Revision', 'Recipient', 'Package', 'Notes', 'Issued By'],
              [[r.get(k, '') for k in keys] for r in records])
