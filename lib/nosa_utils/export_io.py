# -*- coding: utf-8 -*-
"""
nosa_utils.export_io
====================
Shared CSV and Excel export helpers for NOSA plugins.

Usage:
    from nosa_utils.export_io import write_csv, write_csv_dicts

    write_csv(path, ['Col A', 'Col B'], [[val1, val2], ...])
    write_csv_dicts(path, ['Col A', 'Col B'], [{'Col A': v1, 'Col B': v2}, ...])

Dialog-based flow (remembers the last output folder across all plugins):

    from nosa_utils.export_io import save_csv
    path = save_csv(['Col A', 'Col B'], rows, default_name=u'clash_report')
    if path: ...  # None = user cancelled
"""
import io
import csv
import json
import os
import datetime

_CFG = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs', '_export_io.json')


def _load_last_folder():
    try:
        with open(_CFG, 'r') as f:
            folder = json.load(f).get('last_folder', u'')
        if folder and os.path.isdir(folder):
            return folder
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def _save_last_folder(folder):
    try:
        d = os.path.dirname(_CFG)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(_CFG, 'w') as f:
            json.dump({'last_folder': folder}, f)
    except Exception:
        pass


def ask_save_path(default_name, extension='csv'):
    """Show a save dialog with the shared remembered folder. Path or None."""
    from Microsoft.Win32 import SaveFileDialog
    dlg = SaveFileDialog()
    dlg.Title            = u'NOSA — Export'
    dlg.Filter           = u'{0} files (*.{1})|*.{1}|All files (*.*)|*.*'.format(
        extension.upper(), extension)
    dlg.DefaultExt       = extension
    dlg.InitialDirectory = _load_last_folder()
    dlg.FileName         = u'{}_{}'.format(
        default_name, datetime.datetime.now().strftime('%Y%m%d_%H%M'))
    if not dlg.ShowDialog():
        return None
    path = dlg.FileName
    _save_last_folder(os.path.dirname(path))
    return path


def save_csv(headers, rows, default_name=u'nosa_export'):
    """Save dialog + write_csv. Returns saved path, or None if cancelled."""
    path = ask_save_path(default_name, 'csv')
    if not path:
        return None
    write_csv(path, headers, rows)
    return path


def save_text(text, default_name=u'nosa_note', extension='txt'):
    """Save dialog + plain-text write. Returns saved path, or None if cancelled."""
    path = ask_save_path(default_name, extension)
    if not path:
        return None
    with io.open(path, 'w', encoding='utf-8-sig') as f:
        f.write(text)
    return path


def _cell(v):
    if v is None:
        return u''
    try:
        return str(v)
    except Exception:
        return u''


def write_csv(path, headers, rows):
    """
    Write a list of lists to a UTF-8-sig CSV file.

    Parameters
    ----------
    path    : str         — output file path
    headers : list[str]   — column names (first row)
    rows    : list[list]  — data rows; each inner list maps to a header column
    """
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow([_cell(v) for v in row])


def write_csv_dicts(path, headers, rows):
    """
    Write a list of dicts to a UTF-8-sig CSV file.

    Parameters
    ----------
    path    : str         — output file path
    headers : list[str]   — ordered column names
    rows    : list[dict]  — each dict maps header names to values
    """
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        w.writeheader()
        for row in rows:
            w.writerow({h: _cell(row.get(h)) for h in headers})
