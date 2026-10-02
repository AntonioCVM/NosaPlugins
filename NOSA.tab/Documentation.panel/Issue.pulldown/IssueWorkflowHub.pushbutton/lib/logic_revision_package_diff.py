# -*- coding: utf-8 -*-
import json
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.telemetry import log_swallowed
_LOG = u'IssueWorkflowHub'


def snapshot_revisions(doc):
    """
    Return {sheet_number: {'name': ..., 'current_rev': ..., 'rev_date': ..., 'rev_desc': ...}}
    """
    result = {}
    try:
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
            try:
                num  = (sheet.SheetNumber or u'').strip()
                name = (sheet.Name or u'').strip()
                if not num:
                    continue

                def _pstr(pname):
                    try:
                        p = sheet.LookupParameter(pname)
                        return (p.AsString() or u'').strip() if (p and p.HasValue) else u''
                    except Exception:
                        return u''

                result[num] = {
                    'name':     name,
                    'rev':      _pstr(u'Current Revision'),
                    'rev_date': _pstr(u'Current Revision Date'),
                    'rev_desc': _pstr(u'Current Revision Description'),
                }
            except Exception:
                log_swallowed(_LOG, u'snapshot_revisions')
    except Exception:
        log_swallowed(_LOG, u'snapshot_revisions')
    return result


def diff_snapshots(baseline, current):
    """
    Return list of change records.
    change_type: 'New Sheet' | 'Revised' | 'Removed' | 'Unchanged'
    """
    all_nums = sorted(set(list(baseline.keys()) + list(current.keys())))
    diffs = []
    for num in all_nums:
        b = baseline.get(num)
        c = current.get(num)
        if b is None:
            diffs.append({
                'number':   num,
                'name':     c.get('name', u''),
                'change':   u'New Sheet',
                'old_rev':  u'—',
                'new_rev':  c.get('rev', u''),
                'new_date': c.get('rev_date', u''),
                'new_desc': c.get('rev_desc', u''),
            })
        elif c is None:
            diffs.append({
                'number':   num,
                'name':     b.get('name', u''),
                'change':   u'Removed',
                'old_rev':  b.get('rev', u''),
                'new_rev':  u'—',
                'new_date': u'',
                'new_desc': u'',
            })
        elif b.get('rev') != c.get('rev'):
            diffs.append({
                'number':   num,
                'name':     c.get('name', u''),
                'change':   u'Revised',
                'old_rev':  b.get('rev', u''),
                'new_rev':  c.get('rev', u''),
                'new_date': c.get('rev_date', u''),
                'new_desc': c.get('rev_desc', u''),
            })
        else:
            diffs.append({
                'number':   num,
                'name':     c.get('name', u''),
                'change':   u'Unchanged',
                'old_rev':  b.get('rev', u''),
                'new_rev':  c.get('rev', u''),
                'new_date': u'',
                'new_desc': u'',
            })
    return diffs


def export_transmittal_csv(diffs, path):
    """Export only changed/new sheets to a CSV transmittal list."""
    rows = [r for r in diffs if r['change'] != u'Unchanged']
    from nosa_utils.export_io import write_csv
    write_csv(path, ['Sheet No', 'Sheet Name', 'Change', 'Previous Rev', 'New Rev', 'Date', 'Description'],
              [[r['number'], r['name'], r['change'], r['old_rev'], r['new_rev'], r['new_date'], r['new_desc']]
               for r in rows])
