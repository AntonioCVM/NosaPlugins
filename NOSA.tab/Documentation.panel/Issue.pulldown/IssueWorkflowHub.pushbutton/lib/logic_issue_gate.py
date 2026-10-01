# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.telemetry import log_swallowed
_LOG = u'IssueWorkflowHub'

_dpc_logic = None


def _load_dpc_logic():
    global _dpc_logic
    if _dpc_logic is None:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        for suffix in ('pushbutton', 'nobutton'):
            path = os.path.join(base, 'DrawingProtocolChecker.{}'.format(suffix), 'lib', 'logic.py')
            if os.path.exists(path):
                from nosa_utils.bootstrap import load_module
                _dpc_logic = load_module('dpc_logic_gate', path)
                break
    return _dpc_logic


def check_protocol(doc):
    """Run NOSA sheet protocol validation via DrawingProtocolChecker logic."""
    try:
        logic = _load_dpc_logic()
        if logic is None:
            return {'status': 'error', 'count': 0, 'items': [],
                    'error': u'DrawingProtocolChecker logic not found'}
        results = logic.run_protocol_checks(doc)
        items = []
        fail_count = 0
        warn_count = 0
        for r in results:
            if r.status == 'green' or not r.issues:
                continue
            if r.status == 'red':
                sev = u'FAIL'
                fail_count += 1
            else:
                sev = u'WARN'
                warn_count += 1
            items.append({
                'number':   r.sheet_number,
                'name':     r.sheet_name,
                'issue':    u'; '.join(r.issues),
                'severity': sev,
            })
        status = 'fail' if fail_count > 0 else ('warn' if warn_count > 0 else 'pass')
        return {'status': status, 'count': len(items), 'items': items}
    except Exception as e:
        return {'status': 'error', 'count': 0, 'items': [], 'error': str(e)}


def check_revisions(doc):
    """Sheets with no current revision set."""
    items = []
    try:
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
            try:
                p = sheet.LookupParameter(u'Current Revision')
                val = (p.AsString() or u'').strip() if (p and p.HasValue) else u''
                if not val or val in (u'-', u'—', u'--'):
                    items.append({
                        'number':   sheet.SheetNumber,
                        'name':     sheet.Name,
                        'issue':    u'Current Revision is empty',
                        'severity': u'FAIL',
                    })
            except Exception:
                log_swallowed(_LOG, u'check_revisions')
    except Exception:
        log_swallowed(_LOG, u'check_revisions')
    return {'status': ('fail' if items else 'pass'), 'count': len(items), 'items': items}


def check_titleblock(doc):
    """Sheets missing Drawn By or Checked By parameters."""
    params_to_check = [
        (u'Drawn by',   u'WARN'),
        (u'Checked by', u'WARN'),
    ]
    items = []
    try:
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
            for param_name, severity in params_to_check:
                try:
                    p = sheet.LookupParameter(param_name)
                    val = (p.AsString() or u'').strip() if (p and p.HasValue) else u''
                    if not val:
                        items.append({
                            'number':   sheet.SheetNumber,
                            'name':     sheet.Name,
                            'issue':    u'"{}" is empty'.format(param_name),
                            'severity': severity,
                        })
                except Exception:
                    log_swallowed(_LOG, u'check_titleblock')
    except Exception:
        log_swallowed(_LOG, u'check_titleblock')
    affected = len(set(i['number'] for i in items))
    return {'status': ('warn' if items else 'pass'), 'count': affected, 'items': items}


def check_duplicates(doc):
    """Sheets with duplicate sheet numbers."""
    counts = {}
    names = {}
    try:
        for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
            n = (sheet.SheetNumber or u'').strip()
            if not n:
                continue
            counts[n] = counts.get(n, 0) + 1
            names.setdefault(n, []).append(sheet.Name or u'')
    except Exception:
        log_swallowed(_LOG, u'check_duplicates')
    items = []
    for n, cnt in counts.items():
        if cnt > 1:
            for nm in names[n]:
                items.append({
                    'number':   n,
                    'name':     nm,
                    'issue':    u'Sheet number appears {} times'.format(cnt),
                    'severity': u'FAIL',
                })
    dup_count = len([n for n, c in counts.items() if c > 1])
    return {'status': ('fail' if items else 'pass'), 'count': dup_count, 'items': items}


def run_all(doc):
    return {
        'protocol':   check_protocol(doc),
        'revisions':  check_revisions(doc),
        'titleblock': check_titleblock(doc),
        'duplicates': check_duplicates(doc),
    }
