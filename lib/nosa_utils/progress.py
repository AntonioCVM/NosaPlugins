# -*- coding: utf-8 -*-
"""
nosa_utils.progress
===================
Progress bar helper with throttling, cancellation, and transaction rollback.

Usage — script with a pyRevit output/ProgressBar:

    from nosa_utils.progress import nosa_progress

    items = collect_piles(doc)
    with nosa_progress(len(items), u'Processing piles', step=10) as pb:
        for i, item in enumerate(items):
            pb.update(i)           # throttled: only repaints every `step` items
            if pb.cancelled:
                break
            # ... model changes ...

Usage — inside a NOSAWindow (SetLoading pattern):

    with nosa_progress(len(items), u'Calculating', window=self) as pb:
        for i, item in enumerate(items):
            pb.update(i)
            if pb.cancelled:
                break

Usage — with automatic transaction rollback on cancel:

    from nosa_utils.transactions import nosa_transaction
    with nosa_transaction(doc, u'NOSA — Bulk edit') as t:
        with nosa_progress(len(items), u'Bulk editing', step=25) as pb:
            for i, item in enumerate(items):
                pb.update(i)
                if pb.cancelled:
                    t.cancel()   # rolls back + exits both with-blocks
                # ... model changes ...
"""
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.progress'


class _NosaProgress(object):

    def __init__(self, total, title, step=None, window=None, cancellable=True):
        self._total       = max(1, total)
        self._title       = title
        self._step        = step or max(1, self._total // 100) or 1
        self._window      = window
        self._cancellable = cancellable
        self._pb          = None
        self.cancelled    = False
        self._last_update = -1

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop()
        return False

    def _start(self):
        if self._window is not None:
            try:
                self._window.SetLoading(True, self._title)
            except Exception:
                log_swallowed(_LOG, u'_start')
        else:
            try:
                from pyrevit import forms as _forms
                self._pb = _forms.ProgressBar(
                    title=self._title,
                    indeterminate=False,
                    cancellable=self._cancellable,
                )
                self._pb.__enter__()
            except Exception:
                self._pb = None

    def _stop(self):
        if self._window is not None:
            try:
                self._window.SetLoading(False)
            except Exception:
                log_swallowed(_LOG, u'_stop')
        if self._pb is not None:
            try:
                self._pb.__exit__(None, None, None)
            except Exception:
                log_swallowed(_LOG, u'_stop')
            self._pb = None

    def update(self, current, message=None):
        """
        Report progress. Only repaints the UI every `step` calls.

        current : 0-based index of the current item.
        """
        # Throttle: only update every `step` items or on last item
        if (current - self._last_update) < self._step and current < self._total - 1:
            return
        self._last_update = current

        pct = int(current * 100.0 / self._total)

        if self._pb is not None:
            try:
                msg = message or u'{} / {}'.format(current + 1, self._total)
                self._pb.update_progress(current + 1, self._total)
                if hasattr(self._pb, 'update_title'):
                    self._pb.update_title(u'{} — {}'.format(self._title, msg))
                if self._cancellable and self._pb.cancelled:
                    self.cancelled = True
            except Exception:
                log_swallowed(_LOG, u'update')
        elif self._window is not None:
            try:
                msg = message or u'{} of {} ({} %)'.format(
                    current + 1, self._total, pct)
                self._window.SetLoading(True, u'{} — {}'.format(self._title, msg))
            except Exception:
                log_swallowed(_LOG, u'update')

    def set_total(self, new_total):
        """Update total if the count wasn't known at construction time."""
        self._total = max(1, new_total)
        self._step  = max(1, self._total // 100) or 1


def nosa_progress(total, title, step=None, window=None, cancellable=True):
    """
    Return a context-managed progress helper.

    Parameters
    ----------
    total       : int   — total item count
    title       : str   — display title (prefix for all messages)
    step        : int   — repaint every N items (default: max(1, total//100))
    window      : NOSAWindow instance — if provided, uses SetLoading instead of ProgressBar
    cancellable : bool  — whether to show a Cancel button (ProgressBar mode only)
    """
    return _NosaProgress(total, title, step=step, window=window, cancellable=cancellable)
