# -*- coding: utf-8 -*-
"""
NOSA Error Registry — Centralised known-error catalogue.

Usage in any plugin:
    from nosa_utils.error_registry import ErrorRegistry
    reg = ErrorRegistry()
    hint = reg.get_hint(exception)       # returns string or None
    reg.log_error(plugin, exception)     # writes to error log + checks registry
"""

import os
import json
import datetime
import traceback
import sys

_REGISTRY_FILE = os.path.join(os.path.dirname(__file__), 'known_errors.json')
_ERROR_LOG_DIR = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'Logs'
)


# ─────────────────────────────────────────────────────────────
# Known error catalogue (also stored / extended in known_errors.json)
# ─────────────────────────────────────────────────────────────

_BUILTIN_KNOWN_ERRORS = [
    {
        "id": "ERR001",
        "plugin": "*",
        "match": "Attempted relative import in non-package",
        "severity": "CRITICAL",
        "cause": "IronPython resolved a lib/ui.py from a different plugin because sys.path was polluted.",
        "fix": "Ensure script.py uses imp.load_source() with a unique module name instead of 'from ui import ...'."
                " Also add a sys.modules['ui'] guard before the import.",
        "docs": "B5.4 — PileMaster fix pattern"
    },
    {
        "id": "ERR002",
        "plugin": "*",
        "match": "has no attribute 'tabs'",
        "severity": "CRITICAL",
        "cause": "ApplyLoadedConfig() was called before self.tabs dict was initialized in __init__.",
        "fix": "Move self.tabs = {...} initialization BEFORE any call to LoadLastConfig / ApplyLoadedConfig.",
        "docs": "ExportSheets fix — initialization order"
    },
    {
        "id": "ERR003",
        "plugin": "ExportSheets",
        "match": "PDF export returned False",
        "severity": "WARNING",
        "cause": "Revit API doc.Export returned False — usually a sheet with no views placed, or a views with temporary hide/isolate active.",
        "fix": "Use the pre-export check (Force Black / pre-export override check in Formats tab) to catch views with temporary state.",
        "docs": "B5.1 — Force Black + pre-export check"
    },
    {
        "id": "ERR004",
        "plugin": "ExportSheets",
        "match": "No se detectó PDF creado",
        "severity": "WARNING",
        "cause": "PDF file was exported but not detected in the folder (race condition or Revit slow I/O).",
        "fix": "Increase the time.sleep() in export_sheet_pdf() or add a retry loop. Also ensure the output folder is accessible.",
        "docs": "exporters.py — _find_newest_pdf"
    },
    {
        "id": "ERR005",
        "plugin": "ClashReport",
        "match": "BooleanOperationsUtils",
        "severity": "WARNING",
        "cause": "Revit Boolean intersection failed for a pair of elements (invalid geometry, linked model, etc.).",
        "fix": "intersect_volume() already catches this and returns 0.0. Safe to ignore — element pair will be skipped.",
        "docs": "StructuralQA logic_clash_report.py — ClashLogic.intersect_volume"
    },
    {
        "id": "ERR006",
        "plugin": "WaffleSlab",
        "match": "Boundary curves do not form a valid planar loop",
        "severity": "ERROR",
        "cause": "The selected boundary curves are not co-planar or do not close properly.",
        "fix": "Ensure all boundary lines are in the same horizontal plane and form a closed loop. Use 'Rectangular area' mode for simpler cases.",
        "docs": "WaffleSlab — crear_forjado_con_rebajes"
    },
    {
        "id": "ERR007",
        "plugin": "TagAll",
        "match": "IndependentTag.Create",
        "severity": "INFO",
        "cause": "Could not create tag for a specific element (no valid reference, element not visible in view, etc.).",
        "fix": "These failures are counted as 'Failed' in the result. Check that the view is at the correct detail level and the element is visible.",
        "docs": "TagAll ui.py — Run_Click"
    },
    {
        "id": "ERR008",
        "plugin": "PileMaster",
        "match": "ValueError: Attempted relative import",
        "severity": "CRITICAL",
        "cause": "Same as ERR001 but specific to PileMaster's logic_*.py relative imports.",
        "fix": "script.py now pre-loads logic modules with imp.load_source. Reload pyRevit after any change to lib/ui.py.",
        "docs": "B5.4 — PileMaster script.py"
    },
    {
        "id": "ERR009",
        "plugin": "HealthScore",
        "match": "GetDependentElements",
        "severity": "WARNING",
        "cause": "GetDependentElements is not available in some Revit API versions or element types.",
        "fix": "RebarCoverage logic.py has a fallback collector. No action needed.",
        "docs": "RebarCoverage logic.py — _has_rebar fallback"
    },
    {
        "id": "ERR010",
        "plugin": "*",
        "match": "DynamicResource BgColor",
        "severity": "WARNING",
        "cause": "WPF DynamicResource not found — window Resources dictionary not set before ApplyTheme call.",
        "fix": "Ensure WPFWindow.__init__ is called BEFORE ApplyTheme. NOSAWindow handles this correctly.",
        "docs": "base_window.py — ApplyTheme"
    },
    {
        "id": "ERR011",
        "plugin": "TemplateGuard",
        "match": "GetCategoryOverrides",
        "severity": "WARNING",
        "cause": "Some categories raise exceptions when querying overrides (e.g. internal categories, categories with no elements).",
        "fix": "Already wrapped in try/except in _has_manual_overrides(). Override count may be slightly underreported.",
        "docs": "TemplateGuard logic.py — _has_manual_overrides"
    },
    {
        "id": "ERR012",
        "plugin": "QuantificationQA",
        "match": "HOST_VOLUME_COMPUTED",
        "severity": "INFO",
        "cause": "HOST_VOLUME_COMPUTED parameter not available for some element types (e.g. structural framing with non-solid geometry).",
        "fix": "Volume will be 0.0 and the element will be flagged in QA Issues as 'Zero volume'. No crash.",
        "docs": "QuantificationQA logic.py — _volume_m3"
    },
    {
        "id": "ERR013",
        "plugin": "SheetExportHub",
        "match": "ExportManager",
        "severity": "ERROR",
        "cause": "ExportManager or SheetExportHub lib modules not importable — path issue or missing lib folder.",
        "fix": "Ensure NOSA.extension/NOSA.tab/Documentation.panel/SheetExportHub.pushbutton/lib exists.",
        "docs": "SheetExportHub ui.py — Export_Click"
    },
    {
        "id": "ERR014",
        "plugin": "*",
        "match": "ShowElements",
        "severity": "WARNING",
        "cause": "uidoc.ShowElements() may fail if the elements are in a different view type than the active one.",
        "fix": "Wrap ShowElements in try/except (already done in most plugins). Selection still applies even if zoom fails.",
        "docs": "All plugins — Select_Click / Select in Model"
    },
    {
        "id": "ERR015",
        "plugin": "LevelNavigator",
        "match": "ActiveView",
        "severity": "ERROR",
        "cause": "Cannot set ActiveView to a 3D or non-plan view, or the view is not open.",
        "fix": "Check that the target view is a FloorPlan and not already closed. LevelNavigator filters to FloorPlan views.",
        "docs": "LevelNavigator script.py"
    },
]


class ErrorRegistry:
    """
    Central registry for known NOSA plugin errors.
    Provides hint lookup and structured error logging.
    """

    def __init__(self):
        self._catalogue = list(_BUILTIN_KNOWN_ERRORS)
        self._load_custom()
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        if not os.path.exists(_ERROR_LOG_DIR):
            try:
                os.makedirs(_ERROR_LOG_DIR)
            except (OSError, IOError):
                pass

    def _load_custom(self):
        """Load extra entries from known_errors.json if present."""
        try:
            if os.path.exists(_REGISTRY_FILE):
                with open(_REGISTRY_FILE, 'r') as f:
                    extra = json.load(f)
                    if isinstance(extra, list):
                        self._catalogue.extend(extra)
        except Exception:
            pass

    # ──────────────────────────────────────────────
    # Lookup
    # ──────────────────────────────────────────────

    def get_hint(self, exception, plugin='*'):
        """
        Given a caught exception, return a hint string from the catalogue.
        Returns None if no match found.
        """
        msg = str(exception)
        tb  = traceback.format_exc() or ''
        combined = msg + '\n' + tb
        for entry in self._catalogue:
            kw = entry.get('match', '')
            if not kw:
                continue
            if kw.lower() in combined.lower():
                ep = entry.get('plugin', '*')
                if ep == '*' or ep.lower() in plugin.lower():
                    return "[{id}] {cause}\nFix: {fix}".format(**entry)
        return None

    def find_by_id(self, error_id):
        for e in self._catalogue:
            if e.get('id') == error_id:
                return e
        return None

    def find_by_plugin(self, plugin):
        return [e for e in self._catalogue
                if e.get('plugin', '*') in ('*', plugin)]

    # ──────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────

    def log_error(self, plugin, exception, context=''):
        """
        Write a structured error entry to the NOSA error log.
        Returns the hint string if a known error was matched.
        """
        hint = self.get_hint(exception, plugin)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_path  = os.path.join(
            _ERROR_LOG_DIR,
            'nosa_errors_{}.log'.format(
                datetime.datetime.now().strftime('%Y%m%d')
            )
        )
        entry = {
            'ts':      timestamp,
            'plugin':  plugin,
            'error':   str(exception),
            'context': context,
            'hint_id': None,
            'tb':      traceback.format_exc() or '',
        }
        if hint:
            for e in self._catalogue:
                if (e.get('match', '').lower() in str(exception).lower()):
                    entry['hint_id'] = e.get('id')
                    break

        line = "[{ts}] [{plugin}] {error}".format(**entry)
        if entry['hint_id']:
            line += "  → see {hint_id}".format(**entry)
        if context:
            line += "  (context: {context})".format(**entry)
        line += '\n'
        if entry['tb'] and entry['tb'].strip() != 'NoneType: None':
            line += entry['tb'] + '\n'

        try:
            with open(log_path, 'a') as f:
                f.write(line)
        except (OSError, IOError):
            sys.stderr.write("ErrorRegistry: could not write log: {}\n".format(log_path))

        return hint

    # ──────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────

    def get_catalogue_summary(self):
        """Return list of (id, plugin, severity, match) tuples for display."""
        return [(e['id'], e.get('plugin','*'), e.get('severity','?'), e.get('match',''))
                for e in self._catalogue]
