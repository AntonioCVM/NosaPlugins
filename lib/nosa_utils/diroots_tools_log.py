# -*- coding: utf-8 -*-
"""Minimal file logging for DiRoots-style NOSA tools (no telemetry / no PII policy)."""

import os
import time
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.diroots_tools_log'


def _safe_makedirs(root):
    if not root:
        return
    try:
        if not os.path.exists(root):
            os.makedirs(root)
    except (OSError, IOError):
        log_swallowed(_LOG, u'_safe_makedirs')


def log_dir():
    return os.path.join(
        os.getenv('APPDATA', ''),
        u'pyRevit', u'Extensions', u'NOSA.extension', u'NOSA_Logs')


def log_event(tool_key, event_key, detail_message):
    """
    Append one UTF-8 line: ISO time | tool_key | event_key | message
    Safe to call on any failure path.
    """
    root = log_dir()
    _safe_makedirs(root)
    path = os.path.join(root, u'diroots_apply.log')
    try:
        ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        line = u'{} | {} | {} | {}\n'.format(ts, tool_key, event_key, detail_message or u'')
        with open(path, 'a') as f:
            f.write(line.encode('utf-8'))
    except Exception:
        log_swallowed(_LOG, u'log_event')
