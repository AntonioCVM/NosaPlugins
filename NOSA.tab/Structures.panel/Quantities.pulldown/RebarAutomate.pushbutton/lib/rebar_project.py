# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Project-level settings (Phase F1)
============================================================================

`rebar_project.json` — ONE file per Revit document (keyed by a short
hash of Document.PathName, since a document doesn't carry a stable
ElementId-like identity of its own before it has a path), living in
NOSA_Configs/rebar_project/ alongside every other plugin's own
per-user runtime state (_rebar_automate.json etc.) — NOT versioned in
git, same convention as the rest of this extension.

Schema (blueprint Part 12):
    {
      "standard_code": "EHE-08",
      "project_number": "",
      "sheet_series": "",
      "revision": "",
      "issue_status": "",
      "mark_prefix_scheme": "",
      "insert_shared_params_into_user_file": false
    }

F1 rule (c) — this module has NO Revit API dependency at all beyond
reading `doc.PathName`/`doc.Title` (both plain attribute reads, safe
on a fake/mock doc in a pure test) — no `import Autodesk.Revit` here.
"""
import hashlib
import json
import os

_DEFAULT_SCHEMA = {
    'standard_code': u'EHE-08',
    'project_number': u'',
    'sheet_series': u'',
    'revision': u'',
    'issue_status': u'',
    'mark_prefix_scheme': u'',
    'insert_shared_params_into_user_file': False,
}

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXTENSION_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', '..'))
_CONFIG_DIR = os.path.join(_EXTENSION_ROOT, 'NOSA_Configs', 'rebar_project')


def doc_key(doc):
    """
    Short, stable identifier for `doc`, used as the config filename.
    Prefers Document.PathName (the saved file path — stable across
    sessions); falls back to Document.Title (works for an unsaved new
    document, though that key won't survive a later save-as).
    """
    path = u''
    try:
        path = doc.PathName or u''
    except Exception:
        pass
    if not path:
        try:
            path = doc.Title or u'untitled'
        except Exception:
            path = u'untitled'
    return hashlib.md5(path.encode('utf-8')).hexdigest()[:16]


def config_path(doc):
    return os.path.join(_CONFIG_DIR, doc_key(doc) + u'.json')


def exists(doc):
    """True if this document already has a saved rebar_project.json —
    used by ui.py to decide whether this is the FIRST launch on this
    document (and therefore whether to show the one-time
    insert-into-office-file dialog)."""
    return os.path.isfile(config_path(doc))


def load(doc):
    """
    Returns the full schema (defaults merged with whatever is saved),
    never raises — a missing or corrupt file just yields the defaults.
    """
    data = dict(_DEFAULT_SCHEMA)
    path = config_path(doc)
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass
    return data


def save(doc, data):
    """
    Merges `data` onto the current saved state (or the defaults, if
    none saved yet) and writes it back. Returns the merged dict that
    was actually written.
    """
    if not os.path.isdir(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR)
    merged = load(doc)
    merged.update(data)
    with open(config_path(doc), 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, sort_keys=True)
    return merged
