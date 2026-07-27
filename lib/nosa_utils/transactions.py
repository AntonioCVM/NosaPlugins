# -*- coding: utf-8 -*-
"""
nosa_utils.transactions
=======================
Context manager for Revit transactions with automatic rollback on error.

Usage:
    from nosa_utils.transactions import nosa_transaction

    with nosa_transaction(doc, u'NOSA — Do something') as t:
        # model changes here
        element.Name = u'New name'
    # commits on success, rolls back on any exception

For operations with a known cancel path:
    with nosa_transaction(doc, u'NOSA — Bulk edit') as t:
        for item in items:
            if cancelled:
                t.cancel()   # explicit rollback + exit
                break
            ...
"""
from Autodesk.Revit import DB


class _NosaTransaction(object):

    def __init__(self, doc, name):
        self._t    = DB.Transaction(doc, name)
        self._done = False

    def __enter__(self):
        self._t.Start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._done:
            return False
        if exc_type is None:
            self._t.Commit()
        else:
            if self._t.HasStarted():
                self._t.RollBack()
        return False

    def cancel(self):
        """Explicit rollback — use when a user cancels mid-operation."""
        if self._t.HasStarted():
            self._t.RollBack()
        self._done = True
        raise _CancelledError()

    def commit_early(self):
        """Commit before the with-block exits (advanced use only)."""
        self._t.Commit()
        self._done = True


class _CancelledError(Exception):
    """Raised by _NosaTransaction.cancel() to exit the with-block cleanly."""
    pass


def nosa_transaction(doc, name):
    """Return a context-managed Revit transaction named 'NOSA — ...'."""
    if not name.startswith(u'NOSA'):
        name = u'NOSA — {}'.format(name)
    return _NosaTransaction(doc, name)


def transaction(name):
    """
    Decorator for NOSAWindow methods that write to the Revit model.

    Usage:
        @transaction(u'Rename Elements')
        def Apply_Click(self, sender, args):
            for el in self._selection:
                el.Name = u'New name'

    The decorated method must be on an object with a `doc` attribute.
    The transaction name is auto-prefixed with 'NOSA — ' if absent.
    """
    def decorator(func):
        def wrapper(self_or_doc, *args, **kwargs):
            doc = getattr(self_or_doc, 'doc', self_or_doc)
            with nosa_transaction(doc, name):
                return func(self_or_doc, *args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


def run_in_transaction(doc, name, func, *args, **kwargs):
    """
    Run func(*args, **kwargs) inside a transaction.

    Returns (success, result_or_error_str).
    """
    try:
        with nosa_transaction(doc, name):
            result = func(*args, **kwargs)
        return True, result
    except _CancelledError:
        return False, u'Cancelled'
    except Exception as ex:
        return False, str(ex)
