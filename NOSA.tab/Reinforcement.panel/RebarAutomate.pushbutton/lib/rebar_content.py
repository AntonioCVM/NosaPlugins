# -*- coding: utf-8 -*-
"""NOSA content families: packaged versions (data/content_manifest.json) against those loaded (T4.3)."""
from __future__ import absolute_import, print_function, unicode_literals

import io
import json
import os

EXT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
MANIFEST_PATH = os.path.join(EXT_ROOT, 'data', 'content_manifest.json')
VERSION_PARAM = u'NOSA_Content_Version'

OK, OUTDATED, UNVERSIONED, MISSING = u'ok', u'outdated', u'unversioned', u'missing'


def load_manifest(path=MANIFEST_PATH):
    with io.open(path, encoding='utf-8') as f:
        return json.load(f).get('families', [])


def parse_version(text):
    """'1.2.0' -> (1, 2, 0); None for anything else."""
    try:
        return tuple(int(part) for part in text.strip().split(u'.'))
    except (AttributeError, ValueError):
        return None


def family_status(packaged_version, loaded):
    """
    loaded: None if the family is not in the project, else its NOSA_Content_Version
    ('' when the family carries none). Returns ok / outdated / unversioned / missing.
    """
    if loaded is None:
        return MISSING
    have, want = parse_version(loaded), parse_version(packaged_version)
    if have is None:
        return UNVERSIONED
    return OUTDATED if want is not None and have < want else OK


def status_lines(report):
    """User-facing summary lines (British English) for the families that need attention."""
    texts = {
        MISSING: u'{name} is not loaded — use Load NOSA Families.',
        OUTDATED: u'{name} {loaded} is older than the packaged {version} — use Load NOSA Families.',
        UNVERSIONED: u'{name} has no {param}: it may be an old copy — reload it with Load NOSA Families.',
    }
    return [texts[r['status']].format(param=VERSION_PARAM, **r) for r in report if r['status'] in texts]


def _loaded_versions(doc):
    """{family name: NOSA_Content_Version ('' if absent)} for the families in the project."""
    from Autodesk.Revit import DB  # Lazy import
    versions = {}
    for family in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        try:
            name = DB.Element.Name.GetValue(family)
        except Exception:
            continue
        version = u''
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            param = symbol.LookupParameter(VERSION_PARAM) if symbol is not None else None
            if param is not None and param.AsString():
                version = param.AsString()
                break
        versions[name] = version
    return versions


def check(doc, families=None):
    """One dict per manifest family: name, version, loaded, file, file_exists, status."""
    families = load_manifest() if families is None else families
    loaded = _loaded_versions(doc)
    report = []
    for fam in families:
        path = os.path.join(EXT_ROOT, fam.get('file', u''))
        have = loaded.get(fam['name'])
        report.append({'name': fam['name'], 'version': fam.get('version', u''), 'loaded': have,
                       'file': path, 'file_exists': os.path.isfile(path),
                       'status': family_status(fam.get('version', u''), have)})
    return report


def load_packaged(doc, report):
    """Load (overwriting) every packaged family that is missing or out of date; caller owns the Transaction."""
    from Autodesk.Revit import DB  # Lazy import

    class _Overwrite(DB.IFamilyLoadOptions):
        def OnFamilyFound(self, family_in_use, overwrite_parameter_values):
            overwrite_parameter_values.Value = True
            return True

        def OnSharedFamilyFound(self, shared_family, family_in_use, source, overwrite_parameter_values):
            overwrite_parameter_values.Value = True
            return True

    loaded, skipped = [], []
    for row in report:
        if row['status'] == OK:
            continue
        if not row['file_exists']:
            skipped.append(row['name'])
            continue
        if doc.LoadFamily(row['file'], _Overwrite()):
            loaded.append(row['name'])
        else:
            skipped.append(row['name'])
    return loaded, skipped
