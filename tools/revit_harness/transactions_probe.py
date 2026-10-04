# -*- coding: utf-8 -*-
"""
T8.1: a warning and an error posted inside nosa_tx.guard / nosa_tx.revit_transaction must never
open a Revit dialog: the warning is listed, the error rolls back and is reported. Everything is
rolled back. Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT.
"""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

from io import StringIO
_console = StringIO()
_old = sys.stdout
sys.stdout = _console
_log = []


def _definitions():
    """(warning id, error id) from the built-in failures."""
    from Autodesk.Revit.ApplicationServices import Application
    registry = Application.GetFailureDefinitionRegistry()
    warn = err = None
    for group in ('OverlapFailures', 'GeneralFailures', 'JoinElementsFailures', 'InaccurateFailures'):
        holder = getattr(DB.BuiltInFailures, group, None)
        if holder is None:
            continue
        for name in dir(holder):
            try:
                fid = getattr(holder, name)
            except Exception:  # nosa-lint: disable=NOSA006 - not a failure id
                continue
            if not isinstance(fid, DB.FailureDefinitionId):
                continue
            definition = registry.FindFailureDefinition(fid)
            if definition is None:
                continue
            severity = definition.GetSeverity()
            if severity == DB.FailureSeverity.Warning and warn is None:
                warn = (group + '.' + name, fid)
            if severity == DB.FailureSeverity.Error and err is None and definition.HasResolutions() is False:
                err = (group + '.' + name, fid)
    return warn, err


group = None
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils import transactions as nosa_tx
    from pyrevit import forms
    alerts = []
    forms.alert = lambda msg, *a, **k: alerts.append(msg) or True
    warn, err = _definitions()
    _log.append(u'warning def {} | error def {}'.format(warn and warn[0], err and err[0]))
    group = DB.TransactionGroup(doc, u'NOSA test - transactions')
    group.Start()
    level = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))[0]
    for label, make in ((u'guard', lambda n: nosa_tx.guard(DB.Transaction(doc, n))),
                        (u'revit_transaction', None)):
        for kind, fid in ((u'warning', warn[1]), (u'error', err[1])):
            name = u'NOSA test - {} {}'.format(label, kind)
            before = len(alerts)
            if make is not None:
                t = make(name)
                t.Start()
                DB.Level.Create(doc, 123.0 / 304.8)
                doc.PostFailure(DB.FailureMessage(fid))
                status = t.Commit()
            else:
                with nosa_tx.revit_transaction(name, doc):
                    DB.Level.Create(doc, 123.0 / 304.8)
                    doc.PostFailure(DB.FailureMessage(fid))
                status = u'(context closed)'
            _log.append(u'{} {}: status {} | alerts +{}'.format(label, kind, status, len(alerts) - before))
    group.RollBack()
    group = None
    _log.append(u'rolled back')
except Exception:
    _log.append(u'EXCEPTION:\n' + traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
        _log.append(u'rolled back (after error)')
    sys.stdout = _old

RESULT = u'\n'.join(_log) + u'\n--- console ---\n' + _console.getvalue()[-2000:]
