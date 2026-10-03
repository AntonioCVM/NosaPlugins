# -*- coding: utf-8 -*-
"""
Column presets for Sheet Export Hub's sheet/view DataGrid.

Two built-in presets — "NOSA Protocols" for sheets (sourced from
nosa_utils.sheet_protocol so it stays in sync with Drawing Index) and
"View Info" for views, which don't carry sheet or project-level fields at
all — plus any number of user-saved custom presets, each just a named,
ordered list of parameter names to show as columns. "Save as new preset..."
with a subset of parameters is how a user builds a smaller/custom column
set without touching a built-in one.
"""
import os
import json
import datetime

from config import Config
from nosa_utils import sheet_protocol as _sp
from nosa_utils.telemetry import log_swallowed
from nosa_utils.logging import Logger
_LOG = u'SheetExportHub/column_presets'

logger = Logger()

BUILTIN_PRESETS = {
    "NOSA Protocols": list(_sp.NOSA_PARAM_ORDER),
    # View parameters ViewCollector.get_view_parameters() always sets,
    # regardless of what raw parameters the view actually carries. Sheet
    # Number / Project Number / Originator etc. don't apply to views.
    "View Info": ['View Number', 'View Name', 'View Type', 'Discipline', 'Level'],
}

# Sensible defaults, one per mode — baked into the built-in dict above.
DEFAULT_PRESET_NAME = "NOSA Protocols"
DEFAULT_VIEW_PRESET_NAME = "View Info"


class ColumnPresetManager(object):
    """Static-style manager, mirrors NamingProfileManager's shape."""

    @staticmethod
    def is_builtin(name):
        return name in BUILTIN_PRESETS

    @staticmethod
    def get_all_preset_names():
        """Built-in presets first (in declaration order), then custom presets A-Z."""
        custom = []
        try:
            if os.path.exists(Config.COLUMN_PRESETS_DIR):
                for filename in os.listdir(Config.COLUMN_PRESETS_DIR):
                    if filename.endswith('.json'):
                        custom.append(filename.replace('.json', ''))
        except Exception:
            log_swallowed(_LOG, u'get_all_preset_names')
        return list(BUILTIN_PRESETS.keys()) + sorted(custom)

    @staticmethod
    def load_preset(name):
        """Return the ordered list of column/parameter names for a preset,
        or None if it doesn't exist."""
        if name in BUILTIN_PRESETS:
            return list(BUILTIN_PRESETS[name])
        try:
            filepath = os.path.join(Config.COLUMN_PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    return list(data.get('columns', []))
        except Exception as e:
            logger.error("Error loading column preset '{}'".format(name), e)
        return None

    @staticmethod
    def save_preset(name, columns):
        """Save/overwrite a custom preset. Refuses to shadow a built-in name."""
        if not name or name in BUILTIN_PRESETS:
            return False
        try:
            filepath = os.path.join(Config.COLUMN_PRESETS_DIR, "{}.json".format(name))
            data = {
                'name': name,
                'columns': list(columns),
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error("Error saving column preset '{}'".format(name), e)
            return False

    @staticmethod
    def delete_preset(name):
        """Delete a custom preset. Built-in presets cannot be deleted."""
        if name in BUILTIN_PRESETS:
            return False
        try:
            filepath = os.path.join(Config.COLUMN_PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception as e:
            logger.error("Error deleting column preset '{}'".format(name), e)
        return False

    @staticmethod
    def get_available_columns(sheet_items, project_params=None):
        """
        Union of every parameter name a user could plausibly add as a column:
        the NOSA Protocols set, Project Information params, and whatever real
        parameters are found on the first sheet/view actually loaded — same
        scan pattern Export Sheets Pro already uses for its naming param list.
        """
        names = set(_sp.NOSA_PARAM_ORDER)
        if project_params:
            for k in project_params.keys():
                names.add(k)
        if sheet_items:
            first = sheet_items[0]
            element = getattr(first, 'Element', None) or getattr(first, '_element', None)
            if element is not None:
                try:
                    for p in element.Parameters:
                        if p.Definition:
                            names.add(p.Definition.Name)
                except Exception:
                    log_swallowed(_LOG, u'get_available_columns')
        return sorted(names)
