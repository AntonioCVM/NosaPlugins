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
    except Exception:
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
                except Exception:
                    pass
        try:
            if os.path.isfile('{}.{}'.format(_LOG_FILE, 1)):
                os.remove('{}.{}'.format(_LOG_FILE, 1))
            os.rename(_LOG_FILE, '{}.{}'.format(_LOG_FILE, 1))
        except Exception:
            pass
    except Exception:
        pass


def _revit_version():
    try:
        from pyrevit import HOST_APP
        return str(HOST_APP.version)
    except Exception:
        pass
    try:
        import Autodesk.Revit.UI as _UI
        app = _UI.UIApplication
        return str(app.Application.VersionNumber)
    except Exception:
        return u'unknown'


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
        u'  ERROR: {}'.format(exception_msg),
    ]
    if stack_trace and stack_trace.strip():
        for ln in stack_trace.strip().splitlines():
            lines.append(u'  | {}'.format(ln))
    lines.append(u'')

    entry = u'\n'.join(lines) + u'\n'

    try:
        with open(_LOG_FILE, 'a') as f:
            f.write(entry)
    except Exception:
        pass


def log_info(script_name, message):
    """Write an INFO entry (non-error events, plugin launches, etc.)."""
    _ensure_log_dir()
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    entry = u'[{}] INFO script={} user={} — {}\n'.format(ts, script_name, _USER, message)
    try:
        with open(_LOG_FILE, 'a') as f:
            f.write(entry)
    except Exception:
        pass


def get_log_path():
    """Return the absolute path to the current log file."""
    return _LOG_FILE
