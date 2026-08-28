# -*- coding: utf-8 -*-
"""
nosa_utils.standards
=====================
Loader and calculation helpers for NOSA's rebar-standard profiles. See
docs/REBARAUTOMATE_BLUEPRINT.md Part 06 for the full profile schema
and the worked EHE-08 example this module's calculations are derived
from.

F2 rule (c) — same as nosa_utils.revit_compat / shared_params: this
module has NO Revit API dependency at all — pure JSON + dict math. It
is the single lowest-risk module in this whole plugin to import from
anywhere, including a plain pytest run outside pyRevit entirely.

Public API
----------
load(code) -> dict
    Resolved profile: data/rebar_standards/<code>.json (factory
    defaults) deep-merged with NOSA_Configs/rebar_standards/<code>.json
    (optional user override) if present.

list_available() -> [str, ...]
    Every profile code found under data/rebar_standards/ (sorted),
    read from each file's own "code" field — for the UI's dropdown.

deep_merge(base, user) -> dict
    Recursive dict merge — `user` wins key-by-key, nested dicts merge
    recursively rather than being replaced wholesale.

cover_for(std, element_kind, exposure=None) -> float or None
lap_length_mm(std, bar_diameter_mm, in_compression=False, pct_lapped=25.0) -> float
anchorage_length_mm(std, bar_diameter_mm, good_bond=True, in_compression=False) -> float
mandrel_diameter_mm(std, bar_diameter_mm, is_stirrup) -> float
hook_extension_mm(std, bar_diameter_mm, angle_deg) -> float
    All five: `std` is a resolved profile dict from load(). Every
    result is a fresh calculation from `std`'s own tables — nothing is
    cached, so a live standard swap in the UI is picked up immediately
    on the next call.

validate_profile(profile, schema=None) -> (bool, [str errors])
    Best-effort schema check — uses the real `jsonschema` package if
    it happens to be importable (a plain CPython dev/CI environment
    might have it), otherwise falls back to a hand-rolled checker that
    only verifies "required" keys are present at each declared nesting
    level (NOT a full JSON-Schema implementation — see its own
    docstring). No external dependency is required either way, keeping
    this module usable under IronPython 2.7.
"""
import copy
import json
import os

from nosa_utils.compat import text_type

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXTENSION_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
_STANDARDS_DIR = os.path.join(_EXTENSION_ROOT, 'data', 'rebar_standards')
_SCHEMA_PATH = os.path.join(_STANDARDS_DIR, '_schema.json')
_USER_OVERRIDE_DIR = os.path.join(_EXTENSION_ROOT, 'NOSA_Configs', 'rebar_standards')


# ══════════════════════════════════════════════════════════════════════════
# Loading
# ══════════════════════════════════════════════════════════════════════════

def _profile_path(code):
    return os.path.join(_STANDARDS_DIR, u'{}.json'.format(code))


def _user_override_path(code):
    return os.path.join(_USER_OVERRIDE_DIR, u'{}.json'.format(code))


def deep_merge(base, user):
    """
    Recursive dict merge: every key in `user` overrides the same key
    in `base`; if BOTH sides have a dict at that key, merge those
    recursively instead of replacing the whole sub-dict wholesale (so
    a user override touching only e.g. cover_mm.by_element.column
    doesn't silently drop every other cover_mm.by_element entry from
    the factory profile). Neither argument is mutated — returns a new
    dict.
    """
    result = copy.deepcopy(base)
    for key, user_value in user.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(user_value, dict):
            result[key] = deep_merge(base_value, user_value)
        else:
            result[key] = copy.deepcopy(user_value)
    return result


def load(code):
    """
    Resolved profile for `code` — factory JSON deep-merged with the
    user's own override file, if one exists.

    Raises:
        IOError: the factory file for `code` doesn't exist at all —
            this is NOT swallowed, since a caller asking for a profile
            that isn't shipped is a real configuration error, not a
            "fall back to defaults" situation.
        ValueError: the factory (or override) file isn't valid JSON.
    """
    import io
    factory_path = _profile_path(code)
    with io.open(factory_path, 'r', encoding='utf-8') as f:
        base = json.load(f)

    override_path = _user_override_path(code)
    if os.path.isfile(override_path):
        with io.open(override_path, 'r', encoding='utf-8') as f:
            user_override = json.load(f)
        return deep_merge(base, user_override)
    return base


def list_available():
    """
    Every profile code shipped under data/rebar_standards/ — for the
    UI's normativa dropdown. Reads each file's own "code" field rather
    than assuming the filename matches it exactly.
    """
    codes = []
    if not os.path.isdir(_STANDARDS_DIR):
        return codes
    for fname in sorted(os.listdir(_STANDARDS_DIR)):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        path = os.path.join(_STANDARDS_DIR, fname)
        try:
            import io
            with io.open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            code = data.get('code')
            if code:
                codes.append(code)
        except Exception:
            continue
    return sorted(codes)


# ══════════════════════════════════════════════════════════════════════════
# Calculations — every one a pure function of `std` (a resolved profile)
# ══════════════════════════════════════════════════════════════════════════

def cover_for(std, element_kind, exposure=None):
    """
    Nominal cover, mm, for `element_kind` (one of the by_element keys
    in the profile — "foundation", "column", "beam", "slab", "wall",
    "pile_cap") and, if given, `exposure` (one of the by_exposure
    keys). Exposure-based cover takes priority when both are available
    (exposure class governs durability requirements more precisely
    than a per-element-type typical value) — falls back to
    by_element[element_kind] if exposure isn't given or isn't a
    recognised class for this profile.

    Returns:
        float (mm), or None if neither table has an entry for the
        given inputs — the CALLER is responsible for the final
        code-level fallback (this module never invents a cover value
        for an unknown element/exposure combination). See
        rebar_engine.DEFAULT_COVER_MM / ui.py's own
        get_native_cover_mm(..., default_mm=...) call sites for where
        that final fallback lives.
    """
    cover_block = std.get('cover_mm', {})
    if exposure is not None:
        by_exposure = cover_block.get('by_exposure', {})
        if exposure in by_exposure:
            return float(by_exposure[exposure])
    by_element = cover_block.get('by_element', {})
    if element_kind in by_element:
        return float(by_element[element_kind])
    return None


def mandrel_diameter_mm(std, bar_diameter_mm, is_stirrup):
    """
    Bend mandrel diameter, mm, for a bar of `bar_diameter_mm` — the
    first bracket in std.bend.mandrel_factor (sorted ascending by
    bar_max_mm, as authored) whose bar_max_mm is >= bar_diameter_mm;
    the LAST bracket is used as a disclosed fallback if
    bar_diameter_mm exceeds every bracket's own bar_max_mm (rather
    than raising — a larger-than-catalogued bar still needs SOME
    mandrel figure to keep the caller's own pipeline running; using
    the largest bracket's factor is the safer, more conservative
    choice for a bar this module has no dedicated bracket for).
    """
    brackets = std['bend']['mandrel_factor']
    factor_key = 'stirrup_factor' if is_stirrup else 'bar_factor'
    for bracket in brackets:
        if bar_diameter_mm <= bracket['bar_max_mm']:
            return bar_diameter_mm * bracket[factor_key]
    return bar_diameter_mm * brackets[-1][factor_key]


def _interpolated_tension_factor(std, pct_lapped):
    """
    std.lap.tension_factor only names two points
    (pct_lapped_le_25/pct_lapped_gt_50) — this project's own disclosed
    approximation for the band between them (25% < pct_lapped <= 50%,
    where the blueprint's own example doesn't name a factor) is a
    straight linear interpolation between the two known points, rather
    than guessing a third breakpoint the profile never declared.
    """
    tension_factor = std['lap']['tension_factor']
    low = tension_factor['pct_lapped_le_25']
    high = tension_factor['pct_lapped_gt_50']
    if pct_lapped <= 25.0:
        return low
    if pct_lapped > 50.0:
        return high
    # Linear interpolation across the undeclared 25-50% band.
    span = (pct_lapped - 25.0) / (50.0 - 25.0)
    return low + span * (high - low)


def lap_length_mm(std, bar_diameter_mm, in_compression=False, pct_lapped=25.0):
    """
    Lap ("empalme") length, mm, for a bar of `bar_diameter_mm`.
    Compression laps use std.lap.compression_factor directly; tension
    laps use the tension_factor table (interpolated between its two
    named points for the band it doesn't name explicitly — see
    _interpolated_tension_factor). Clamped to std.lap.min_mm.
    """
    lap_block = std['lap']
    factor = (lap_block['compression_factor'] if in_compression
              else _interpolated_tension_factor(std, pct_lapped))
    return max(bar_diameter_mm * factor, lap_block['min_mm'])


def anchorage_length_mm(std, bar_diameter_mm, good_bond=True, in_compression=False):
    """
    Anchorage length, mm, for a bar of `bar_diameter_mm`. Uses
    std.anchorage.basic_length_factor['good_bond' or 'poor_bond'],
    scaled by compression_factor if in_compression, clamped to both
    min_mm and min_factor * bar_diameter_mm (whichever is larger).
    """
    anchorage_block = std['anchorage']
    factor_key = 'good_bond' if good_bond else 'poor_bond'
    factor = anchorage_block['basic_length_factor'][factor_key]
    if in_compression:
        factor *= anchorage_block.get('compression_factor', 1.0)
    length_mm = bar_diameter_mm * factor
    min_mm = anchorage_block.get('min_mm', 0.0)
    min_factor_mm = bar_diameter_mm * anchorage_block.get('min_factor', 0.0)
    return max(length_mm, min_mm, min_factor_mm)


def hook_extension_mm(std, bar_diameter_mm, angle_deg):
    """
    Straight hook extension length, mm, for a bar of
    `bar_diameter_mm` bent through `angle_deg` (90/135/180 — the keys
    std.hook.hook_extension_factor declares, as strings, matching the
    JSON's own key type). Clamped to std.hook.min_hook_extension_mm.
    Raises KeyError if `angle_deg` isn't one of the angles this
    profile's own hook_extension_factor table declares — a caller
    asking for an undeclared angle is a real configuration error, not
    something to silently guess at.
    """
    hook_block = std['hook']
    angle_key = str(int(angle_deg))
    factor = hook_block['hook_extension_factor'][angle_key]
    return max(bar_diameter_mm * factor, hook_block.get('min_hook_extension_mm', 0.0))


# ══════════════════════════════════════════════════════════════════════════
# Schema validation
# ══════════════════════════════════════════════════════════════════════════

def _load_schema():
    import io
    with io.open(_SCHEMA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def _minimal_required_keys_check(profile, schema, path=u''):
    """
    NOT a JSON-Schema implementation — checks only that every key
    named in each level's own "required" list is present, recursing
    into "properties" sub-schemas that are themselves type "object".
    Sufficient for this project's own schema shape (Part 06) without
    an external dependency; does NOT check "type", "enum", or array
    item schemas — a real jsonschema validator (used automatically
    when importable — see validate_profile) catches more.
    """
    errors = []
    if schema.get('type') == 'object':
        for required_key in schema.get('required', []):
            if required_key not in profile:
                errors.append(u'{}: missing required key "{}"'.format(
                    path or u'<root>', required_key))
        properties = schema.get('properties', {})
        for key, sub_schema in properties.items():
            if sub_schema.get('type') == 'object' and key in profile and isinstance(profile[key], dict):
                errors.extend(_minimal_required_keys_check(
                    profile[key], sub_schema, path=u'{}.{}'.format(path, key) if path else key))
    return errors


def validate_profile(profile, schema=None):
    """
    Best-effort schema check for a resolved (or raw factory) profile
    dict. Uses the real `jsonschema` package if it happens to be
    importable; otherwise falls back to _minimal_required_keys_check
    (required-keys-present only, recursively — see its own docstring
    for exactly what it does NOT check). No external dependency is
    required either way.

    Args:
        profile (dict): the profile to validate.
        schema  (dict or None): defaults to _schema.json's own content.

    Returns:
        (is_valid: bool, errors: list[unicode])
    """
    schema = schema if schema is not None else _load_schema()
    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        errors = [text_type(e.message) for e in validator.iter_errors(profile)]
        return (not errors, errors)
    except ImportError:
        errors = _minimal_required_keys_check(profile, schema)
        return (not errors, errors)
