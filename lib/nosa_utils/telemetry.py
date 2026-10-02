# -*- coding: utf-8 -*-
"""
nosa_utils.telemetry
====================
Centralised error logging for NOSA extension.

Usage:
    from nosa_utils.telemetry import log_error

    try:
        risky_operation()
    except Exception as ex:
        import traceback
        log_error('MyPlugin', str(ex), traceback.format_exc())
        from pyrevit import forms
        forms.alert(u'Operation failed. See NOSA error log for details.')

Log file: %APPDATA%/pyRevit/Extensions/NOSA.extension/NOSA_Configs/logs/nosa_errors.log
Rotation: 5 MB max per file, keeps last 3 files.
"""
import io
import os
import sys
import datetime
import traceback as _tb

try:
    import getpass as _getpass
    _USER = _getpass.getuser()
except Exception:
    _USER = u'unknown'

_APPDATA   = os.getenv('APPDATA', '')
_LOG_DIR   = os.path.join(_APPDATA, 'pyRevit', 'Extensions',
                          'NOSA.extension', 'NOSA_Configs', 'logs')
_LOG_FILE  = os.path.join(_LOG_DIR, 'nosa_errors.log')
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
_BACKUPS   = 3


def _ensure_log_dir():
    try:
        if not os.path.isdir(_LOG_DIR):
            os.makedirs(_LOG_DIR)
    except Exception:  # nosa-lint: disable=NOSA006 - logging helpers must never raise
        pass


def _rotate():
    """Simple size-based rotation: rename .log → .log.1 → .log.2 → .log.3."""
    try:
        if not os.path.isfile(_LOG_FILE):
            return
        if os.path.getsize(_LOG_FILE) < _MAX_BYTES:
            return
        for i in range(_BACKUPS - 1, 0, -1):
            src = '{}.{}'.format(_LOG_FILE, i)
            dst = '{}.{}'.format(_LOG_FILE, i + 1)
            if os.path.isfile(src):
                try:
                    if os.path.isfile(dst):
                        os.remove(dst)
                    os.rename(src, dst)
                except Exception:  # nosa-lint: disable=NOSA006 - logging helpers must never raise
                    pass
        try:
            if os.path.isfile('{}.{}'.format(_LOG_FILE, 1)):
                os.remove('{}.{}'.format(_LOG_FILE, 1))
            os.rename(_LOG_FILE, '{}.{}'.format(_LOG_FILE, 1))
        except Exception:  # nosa-lint: disable=NOSA006 - logging helpers must never raise
            pass
    except Exception:  # nosa-lint: disable=NOSA006 - logging helpers must never raise
        pass


def _revit_version():
    # __revit__ (the UIApplication pyRevit injects), never `from pyrevit import HOST_APP`:
    # that import reads pyRevit_config.ini and fails while another Revit holds the lock.
    try:
        try:
            import __builtin__ as _builtins
        except ImportError:
            import builtins as _builtins
        return str(getattr(_builtins, '__revit__').Application.VersionNumber)
    except Exception:
        return u'unknown'


def _text(value):
    try:
        if isinstance(value, type(u'')):
            return value
        if isinstance(value, bytes):
            return value.decode('utf-8', 'replace')
        return u'{}'.format(value)
    except Exception:
        return u'<unprintable>'


def _append(entry):
    # UTF-8 explicitly: open(.., 'a') used the ANSI code page and dropped non-ASCII messages
    try:
        with io.open(_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(entry)
    except Exception:  # nosa-lint: disable=NOSA006 - the logger cannot log its own failure
        pass


def log_error(script_name, exception_msg, stack_trace=u'', revit_version=None):
    """
    Write one error entry to the NOSA log.

    Parameters
    ----------
    script_name : str
        Plugin or script name (e.g. 'ViewOrganiser', 'lib/logic.py').
    exception_msg : str
        str(exception).
    stack_trace : str
        traceback.format_exc() output.
    revit_version : str, optional
        Revit version string (auto-detected if None).
    """
    _ensure_log_dir()
    _rotate()

    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    rv = revit_version or _revit_version()

    lines = [
        u'[{}] script={} revit={} user={}'.format(ts, script_name, rv, _USER),
        u'  ERROR: {}'.format(_text(exception_msg)),
    ]
    stack_trace = _text(stack_trace) if stack_trace else u''
    if stack_trace.strip():
        for ln in stack_trace.strip().splitlines():
            lines.append(u'  | {}'.format(ln))
    lines.append(u'')

    _append(u'\n'.join(lines) + u'\n')


_SWALLOWED_SEEN = set()


def log_swallowed(script_name, where=u''):
    """Log the exception being handled once per (script, where) per session; never raises."""
    try:
        key = (script_name, where)
        if key in _SWALLOWED_SEEN:
            return
        _SWALLOWED_SEEN.add(key)
        exc = sys.exc_info()[1]
        try:
            msg = u'swallowed in {}: {}: {}'.format(where, type(exc).__name__, exc)
        except Exception:
            msg = u'swallowed in {}: {}'.format(where, type(exc).__name__)
        log_error(script_name, msg, _tb.format_exc())
    except Exception:  # nosa-lint: disable=NOSA006 — logging must never break the caller
        pass


def log_info(script_name, message):
    """Write an INFO entry (non-error events, plugin launches, etc.)."""
    _ensure_log_dir()
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    _append(u'[{}] INFO script={} user={} — {}\n'.format(ts, script_name, _USER, _text(message)))


def get_log_path():
    """Return the absolute path to the current log file."""
    return _LOG_FILE
