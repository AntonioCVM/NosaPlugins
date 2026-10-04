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


_COLLECTOR_CLASS = []


def FailureCollector():
    """
    A failures preprocessor that never lets Revit open its failure dialog (T8.1): warnings are
    deleted and kept in `.warnings`; an error rolls the transaction back and is kept in `.errors`.
    The class is built on first use: a Revit interface cannot be subclassed at import time.
    """
    if not _COLLECTOR_CLASS:
        class _FailureCollector(DB.IFailuresPreprocessor):
            def __init__(self):
                self.warnings = []
                self.errors = []

            def PreprocessFailures(self, accessor):
                failed = False
                for message in list(accessor.GetFailureMessages()):
                    text = message.GetDescriptionText()
                    if message.GetSeverity() == DB.FailureSeverity.Warning:
                        self.warnings.append(text)
                        accessor.DeleteWarning(message)
                    else:
                        self.errors.append(text)
                        failed = True
                if failed:
                    return DB.FailureProcessingResult.ProceedWithRollBack
                return DB.FailureProcessingResult.Continue
        _COLLECTOR_CLASS.append(_FailureCollector)
    return _COLLECTOR_CLASS[0]()


def report(name, collector):
    """List the warnings Revit raised; tell the user when Revit undid the change."""
    if collector is None or not (collector.warnings or collector.errors):
        return
    unique = []
    for text in collector.warnings:
        if text not in unique:
            unique.append(text)
    if unique:
        print(u'[NOSA] {}: {} Revit warning(s) cleared — {}'.format(
            name, len(collector.warnings), u' | '.join(unique[:10])))
    if collector.errors:
        message = u'Revit rejected "{}" and the change was undone:\n\n- {}'.format(
            name, u'\n- '.join(collector.errors[:10]))
        try:
            from pyrevit import forms
            forms.alert(message, title=u'NOSA — Revit error')
        except Exception:
            print(u'[NOSA] ' + message)
    collector.warnings, collector.errors = [], []


def _install(transaction, collector):
    options = transaction.GetFailureHandlingOptions()
    options = options.SetFailuresPreprocessor(collector)
    options = options.SetForcedModalHandling(False)
    # without it Revit keeps the failures after the rollback and shows them in its dialog
    options = options.SetClearAfterRollback(True)
    transaction.SetFailureHandlingOptions(options)


class _Guarded(object):
    """A DB.Transaction whose failures go to a FailureCollector, reported on Commit."""

    def __init__(self, transaction):
        self._t = transaction
        self._collector = FailureCollector()
        _install(transaction, self._collector)

    def __getattr__(self, attr):
        return getattr(self._t, attr)

    def Commit(self, *args):
        name = self._t.GetName()
        status = self._t.Commit(*args)
        report(name, self._collector)
        return status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._t.HasStarted() and not self._t.HasEnded():
                self._t.RollBack()
        finally:
            self._t.Dispose()
        return False


def guard(transaction):
    """Wrap a DB.Transaction (before Start) so Revit failures never open a dialog."""
    return _Guarded(transaction)


_REVIT_TRANSACTION = []


def revit_transaction(name=None, doc=None, **kwargs):
    """pyrevit.revit.Transaction with the same protection — drop-in for `revit.Transaction(...)`."""
    if not _REVIT_TRANSACTION:
        from pyrevit import revit

        class NosaRevitTransaction(revit.Transaction):
            def __init__(self, *args, **kw):
                revit.Transaction.__init__(self, *args, **kw)
                self._nosa = FailureCollector()
                if isinstance(self._rvtxn, DB.Transaction):
                    _install(self._rvtxn, self._nosa)

            def __exit__(self, exception, exception_value, traceback):
                name = self.name
                result = revit.Transaction.__exit__(self, exception, exception_value, traceback)
                report(name, self._nosa)
                return result
        _REVIT_TRANSACTION.append(NosaRevitTransaction)
    return _REVIT_TRANSACTION[0](name, doc, **kwargs)


class _NosaTransaction(object):

    def __init__(self, doc, name):
        self._t    = guard(DB.Transaction(doc, name))
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
