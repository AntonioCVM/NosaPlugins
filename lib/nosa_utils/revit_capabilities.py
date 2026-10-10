# -*- coding: utf-8 -*-
"""
nosa_utils.revit_capabilities — what each Revit version's API gives the reinforcement tools (T8.55): flags read
from the API by reflection, and the matrix the harness probes record per version (data/revit_capabilities.json:
API present, live probe result, known defects), so the plugin can ask before it relies on a feature.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import io
import json
import os

MATRIX_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'revit_capabilities.json'))

# name: (what it is for, where in the API)
CAPABILITIES = (
    (u'presentation_select', u'typical bar of a set (SMDSC 6.2.2)', u'RebarPresentationMode.Select'),
    (u'multi_rebar_annotation', u'indicator lines (MRA)', u'DB.MultiReferenceAnnotation'),
    (u'varying_length', u'sets following inclined faces', u'DistributionType.VaryingLength'),
    (u'varying_suffix', u'sub-marks of varying sets', u'ReinforcementSettings.RebarVaryingLengthNumberSuffix'),
    (u'free_form', u'bars with several shapes', u'Rebar.CreateFreeForm'),
    (u'couplers', u'mechanical couplers (T8.52)', u'RebarCoupler'),
    (u'fabric', u'welded fabric (T8.51)', u'FabricArea'),
    (u'bending_detail', u'native bending details', u'RebarBendingDetail'),
    (u'hook_orientation', u'hooks up to 2026', u'RebarHookOrientation'),
    (u'terminations', u'bar terminations from 2027', u'BarTerminationsData'),
)


def api_flags(DB, DBS):
    """{capability: bool} read from the loaded Revit API (no model change)."""
    def has(obj, name):
        try:
            return hasattr(obj, name)
        except Exception:
            return False
    settings = getattr(DBS, 'ReinforcementSettings', None)
    return {
        u'presentation_select': has(getattr(DBS, 'RebarPresentationMode', None), 'Select'),
        u'multi_rebar_annotation': has(DB, 'MultiReferenceAnnotation'),
        u'varying_length': has(getattr(DBS, 'DistributionType', None), 'VaryingLength'),
        u'varying_suffix': settings is not None and has(settings, 'RebarVaryingLengthNumberSuffix'),
        u'free_form': has(getattr(DBS, 'Rebar', None), 'CreateFreeForm'),
        u'couplers': has(DBS, 'RebarCoupler'),
        u'fabric': has(DBS, 'FabricArea'),
        u'bending_detail': has(DBS, 'RebarBendingDetail'),
        u'hook_orientation': has(DBS, 'RebarHookOrientation'),
        u'terminations': has(DBS, 'BarTerminationsData'),
    }


def load_matrix(path=MATRIX_PATH):
    if not os.path.isfile(path):
        return {u'versions': {}, u'known_defects': []}
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def supports(version, capability, matrix=None):
    """
    True / False when the matrix knows the version (the live probe if run, else the API flag); None when the
    version was never probed — the caller then falls back to its own try/except.
    """
    data = (matrix or load_matrix()).get(u'versions', {}).get(u'{}'.format(version))
    if not data or capability not in data:
        return None
    entry = data[capability]
    live = entry.get(u'live')
    if live in (u'ok', u'fail'):
        return live == u'ok'
    return bool(entry.get(u'api'))


def merge(matrix, version, flags, live):
    """The matrix with one version's API flags and live results ({capability: ('ok'|'fail', note)})."""
    versions = matrix.setdefault(u'versions', {})
    row = versions.setdefault(u'{}'.format(version), {})
    for name, _what, _where in CAPABILITIES:
        entry = row.setdefault(name, {})
        entry[u'api'] = bool(flags.get(name))
        if name in live:
            entry[u'live'], entry[u'note'] = live[name]
    return matrix
