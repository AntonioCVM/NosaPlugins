# -*- coding: utf-8 -*-
"""
nosa_utils.revit_compat
========================
Single facade for the Revit API members that differ (or may differ)
between Revit 2024 and 2027. See docs/REBARAUTOMATE_BLUEPRINT.md
Part 04 for the full rationale and the delta table this module
implements.

F0 design rules (confirmed 2026-08-27, RebarAutomate blueprint
Part 17 + F0 approval adjustments a-c):

  (a) NO create_rebar_from_curves here. rebar_engine.RebarWrapper is
      already the creation-abstraction layer for this extension
      (proven in fire since Phase 4/5) and is instantiated per-doc
      (RebarWrapper(doc)) — it does not fit as a method on this
      module's singleton-style facade. This facade covers only the
      REAL per-version deltas RebarWrapper's own internals (and other
      callers) need: ElementId, BuiltInParameter aliasing,
      RebarBarType diameter, tag creation, centerline curves,
      category-id resolution, and the mm<->ft conversion edge.

  (b) bip(name) starts with an EMPTY alias table. No BuiltInParameter
      rename for Rebar has been CONFIRMED between 2024 and 2025+ as of
      this writing — do not guess ahead of evidence. The table is
      populated only once the Part 15 smoke matrix catches a real
      rename on a specific Revit year; see _BIP_ALIASES below.

  (c) This module MUST import cleanly with no live Revit session
      present (pytest, CI, any pure test). Autodesk.Revit / pyrevit
      are imported lazily, inside the functions/methods that actually
      need them — never at module scope. revit_year() and the derived
      YEAR / IS_2025_PLUS module globals never raise outside Revit;
      they degrade to None / False.

Usage
-----
    from nosa_utils import revit_compat
    c = revit_compat.api()                 # auto-detects the live Revit year
    c = revit_compat.api(year=2025)        # explicit year, e.g. in a test
    dia_mm = c.from_internal(c.bar_diameter(bar_type))
"""

_MM_PER_FT = 304.8


# PHASE F0 — get_id_value/element_id_from_int are DUPLICATED here
# rather than imported from nosa_utils.revit_helpers, because
# revit_helpers.py itself does `from Autodesk.Revit.DB import (...)`
# at MODULE SCOPE — importing it (even just for these two functions)
# would make THIS module fail to import outside a live Revit session
# too, exactly the F0 rule (c) this module exists to satisfy. Logic is
# identical to revit_helpers.py's own copy (same 2024->2025 ElementId
# cut: .Value on 2025+, .IntegerValue on 2024). Flagged as a follow-up:
# revit_helpers.py could make its own top-level Revit import lazy to
# fix this at the source, but that file is shared across every NOSA
# plugin — out of scope for RebarAutomate's own F0 branch.

def get_id_value(element_id):
    """Return the integer value of an ElementId (2024-2027 safe)."""
    if element_id is None:
        return 0
    try:
        if hasattr(element_id, 'Value'):
            return int(element_id.Value)
    except Exception:
        pass
    try:
        if hasattr(element_id, 'IntegerValue'):
            return int(element_id.IntegerValue)
    except Exception:
        pass
    return int(str(element_id))


def element_id_from_int(val):
    """Construct an ElementId from an int -- uses Int64 on Revit 2024+."""
    from Autodesk.Revit.DB import ElementId
    try:
        from System import Int64
        return ElementId(Int64(int(val)))
    except Exception:
        return ElementId(int(val))  # nosa-lint: disable=NOSA010 (pre-2024 fallback)


def revit_year(app=None):
    """
    Revit application year (2024..2027) as an int, or None if it
    cannot be determined — no live Revit session (pure test/CI
    context), or an unrecognised `app` shape. Never raises.

    Args:
        app: a UIApplication / Application-like object exposing
             `.VersionNumber` (directly, or via `.Application`), or
             None to auto-detect via pyrevit.HOST_APP.
    """
    if app is None:
        try:
            from pyrevit import HOST_APP
            app = HOST_APP.app
        except Exception:
            return None
    try:
        version = getattr(app, 'VersionNumber', None)
        if version is None:
            version = getattr(app, 'Application', None)
            version = getattr(version, 'VersionNumber', None)
        if version is None:
            return None
        return int(version)
    except Exception:
        return None


try:
    YEAR = revit_year()
except Exception:
    YEAR = None

IS_2025_PLUS = bool(YEAR is not None and YEAR >= 2025)


class _ApiBase(object):
    """
    Revit 2024 behaviour — the baseline every later-year override
    diffs against. Methods expose DOMAIN semantics (bar_diameter,
    create_tag), never a 1:1 wrapper of one specific API member — see
    the module docstring's rule (a) and the blueprint Part 04's own
    "métodos con semántica de dominio" principle: a Revit 2027 rename
    is absorbed here without touching any caller.
    """

    # PHASE F0 item (b) — deliberately empty. Populate ONLY once the
    # Part 15 smoke matrix confirms a real BuiltInParameter rename for
    # a specific year, e.g. {'REBAR_SOME_NAME': 'REBAR_RENAMED_2025'}.
    _BIP_ALIASES = {}

    def bip(self, name):
        """BuiltInParameter by name, resolved through this year's
        alias table (empty until a real rename is confirmed)."""
        from Autodesk.Revit.DB import BuiltInParameter
        real_name = self._BIP_ALIASES.get(name, name)
        return getattr(BuiltInParameter, real_name)

    def category_id(self, built_in_category):
        from Autodesk.Revit.DB import ElementId
        return ElementId(built_in_category)

    def bar_diameter(self, bar_type):
        """
        RebarBarType diameter, in Revit's own internal feet (caller
        converts via from_internal). Tries, in order:
        BarModelDiameter (current) -> BarNominalDiameter -> the
        long-obsolete BarDiameter.
        """
        for attr_name in ('BarModelDiameter', 'BarNominalDiameter', 'BarDiameter'):
            try:
                return getattr(bar_type, attr_name)
            except Exception:
                continue
        raise AttributeError(
            u'RebarBarType exposes none of BarModelDiameter / '
            u'BarNominalDiameter / BarDiameter on this Revit version.')

    def to_internal(self, value_mm):
        """
        mm -> Revit's internal feet. PHASE F0 / Decision 6.B: a fixed
        304.8 factor (1 ft = 304.8 mm exactly, by definition) — already
        proven throughout rebar_engine/column_rebar/footing_rebar.
        UnitUtils/UnitTypeId is reserved for the UI edge (displaying
        or parsing a value in the PROJECT's own display units), never
        for this internal conversion.
        """
        return value_mm / _MM_PER_FT

    def from_internal(self, value_ft):
        """Revit's internal feet -> mm. See to_internal."""
        return value_ft * _MM_PER_FT

    def create_tag(self, doc, view, reference, add_leader, tag_mode, tag_orientation, point):
        """IndependentTag.Create using the 2022+ overload — stable
        across 2024-2027 per the blueprint's own Part 04 audit."""
        from Autodesk.Revit.DB import IndependentTag
        return IndependentTag.Create(
            doc, view.Id, reference, add_leader, tag_mode, tag_orientation, point)

    def centerline_curves(self, rebar, adjust=True, suppress_hooks=False,
                           suppress_bend_radius=False, multiplanar_option=None,
                           bar_index=0):
        """
        Rebar.GetCenterlineCurves, defaulting multiplanar_option to
        IncludeOnlyPlanarCurves when the caller doesn't need to
        override it.

        FORWARD NOTE (flagged at F0, not acted on): this default is
        correct for every straight/planar bar shape this extension
        currently generates. F4's rebar_shape_classifier will need to
        pass multiplanar_option explicitly for genuinely 3D shapes
        (helical column ties/spirals, shape code 77 per Part 07/11) —
        IncludeOnlyPlanarCurves would silently drop the helix's own
        out-of-plane geometry for those. See blueprint Part 07.
        """
        from Autodesk.Revit.DB.Structure import MultiplanarOption
        mp_option = (multiplanar_option if multiplanar_option is not None
                     else MultiplanarOption.IncludeOnlyPlanarCurves)
        return rebar.GetCenterlineCurves(
            adjust, suppress_hooks, suppress_bend_radius, mp_option, bar_index)


class _Api2025Plus(_ApiBase):
    """
    Revit 2025+ overrides. Nothing beyond ElementId (already handled
    centrally by revit_helpers.get_id_value/element_id_from_int, used
    unconditionally by every year) is CONFIRMED different as of this
    writing. Kept as an explicit subclass — not merged into
    _ApiBase — so a future confirmed delta has an obvious home instead
    of growing an `if IS_2025_PLUS:` branch inside a shared method.
    """
    pass


def api(year=None):
    """
    Return the API facade for `year` — an explicit int (2024..2027,
    for tests or a known context), or None to auto-detect from the
    live Revit session via revit_year(). Falls back to the 2024
    baseline facade if the year can't be determined at all (pure
    test/CI context with no year given) — the 2024 behaviour is a
    safe default since every later-year facade is additive.
    """
    resolved_year = year if year is not None else YEAR
    if resolved_year is not None and resolved_year >= 2025:
        return _Api2025Plus()
    return _ApiBase()
