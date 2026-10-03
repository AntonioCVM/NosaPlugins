# -*- coding: utf-8 -*-
"""
NOSA Pile Live Coordinates — Dynamic Model Updater (DMU).

Registered application-wide by startup.py when pyRevit loads.
When active, writes X/Y/Rotation parameters to any OST_StructuralFoundation
element that is moved or created, inside the same Revit transaction that
caused the change — no extra undo step, no delay.

Configuration is read from NOSA_Configs/live_coords.json on every Execute()
so that param names / coord mode changes take effect immediately.
"""
import os
import io
import json
import sys

from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.dmu_lifecycle import make_updater_id, unregister as _lifecycle_unregister
from nosa_utils.telemetry import log_swallowed
_LOG = u'pilemaster'
# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CFG_PATH = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs', 'live_coords.json'
)

_DEFAULTS = {
    'active':          False,
    'param_x':         'X coordinate',
    'param_y':         'Y coordinate',
    'param_rot':       'Rotation angle',
    'coord_mode':      'coordination',
    'update_rotation': True,
}

# Absolute path to PileMaster lib — needed to import logic_coords from Execute()
_LIB_DIR = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension',
    'NOSA.tab', 'Foundations.panel', 'PileTools.pulldown', 'PileMaster.pushbutton', 'lib'
)

# Stable GUID — canonical copy lives in nosa_utils.dmu_lifecycle

# Module-level reference — prevents the updater instance from being GC'd
_registered_updater = None
# Guards against spamming the error log on every pile move when import fails
_IMPORT_WARNED = False


def read_config():
    try:
        if os.path.exists(_CFG_PATH):
            with io.open(_CFG_PATH, encoding='utf-8') as f:
                data = json.load(f)
            cfg = dict(_DEFAULTS)
            cfg.update(data)
            return cfg
    except Exception:
        log_swallowed(_LOG, u'read_config')
    return dict(_DEFAULTS)


def write_config(cfg):
    try:
        d = os.path.dirname(_CFG_PATH)
        if not os.path.exists(d):
            os.makedirs(d)
        with io.open(_CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        log_swallowed(_LOG, u'write_config')


# ---------------------------------------------------------------------------
# IUpdater implementation
# ---------------------------------------------------------------------------

_FOUND_CAT_INT = None


def _found_cat_int():
    global _FOUND_CAT_INT
    if _FOUND_CAT_INT is None:
        _FOUND_CAT_INT = int(DB.BuiltInCategory.OST_StructuralFoundation)
    return _FOUND_CAT_INT


class PileLiveCoordUpdater(DB.IUpdater):
    """
    Fires whenever an OST_StructuralFoundation element is moved or added.
    Reads config each call so changes in PileMaster take effect immediately.
    Must NOT create a Transaction — already inside Revit's own transaction.
    """

    def __init__(self, updater_id):
        self._id = updater_id

    def Execute(self, data):
        cfg = read_config()
        if not cfg.get('active'):
            return

        doc = data.GetDocument()
        el_ids = (list(data.GetModifiedElementIds()) +
                  list(data.GetAddedElementIds()))
        if not el_ids:
            return

        # Lazy-import logic_coords to avoid circular imports at module load time
        global _IMPORT_WARNED
        if _LIB_DIR not in sys.path:
            sys.path.insert(0, _LIB_DIR)
        try:
            from logic_coords import CoordinateLogic
        except Exception as _e:
            if not _IMPORT_WARNED:
                _IMPORT_WARNED = True
                try:
                    from nosa_utils.telemetry import log_error
                    log_error('DMU/logic_coords', str(_e))
                except Exception:
                    log_swallowed(_LOG, u'PileLiveCoordUpdater.Execute')
            return

        logic = CoordinateLogic(doc)
        inv   = logic._get_inverse_total_transform()

        for eid in el_ids:
            try:
                el = doc.GetElement(eid)
                if el is None or el.Category is None:
                    continue
                cat_int = get_id_value(el.Category.Id)

                if cat_int != _found_cat_int():
                    continue

                logic._write_coords_to_element(
                    el,
                    cfg['param_x'],
                    cfg['param_y'],
                    cfg['param_rot'],
                    cfg['coord_mode'],
                    cfg.get('update_rotation', True),
                    inv,
                )
            except Exception:
                log_swallowed(_LOG, u'PileLiveCoordUpdater.Execute')

    def GetUpdaterId(self):
        return self._id

    def GetUpdaterName(self):
        return 'NOSA Pile Live Coordinates'

    def GetAdditionalInformation(self):
        return ('Writes X/Y/Rotation shared parameters to pile foundations '
                'whenever they are moved or created.')

    def GetChangePriority(self):
        return DB.ChangePriority.Annotations


# ---------------------------------------------------------------------------
# Registration helpers (called from startup.py)
# ---------------------------------------------------------------------------

def register(app):
    """
    Register the updater application-wide. Safe to call multiple times
    (unregisters any previous instance first).

    Returns (updater_instance, error_string_or_None).
    """
    global _registered_updater

    updater_id = make_updater_id(app)

    _lifecycle_unregister(app)

    updater = PileLiveCoordUpdater(updater_id)
    try:
        DB.UpdaterRegistry.RegisterUpdater(updater, False)
    except Exception as e:
        return None, u'RegisterUpdater failed: {}'.format(e)

    filt = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_StructuralFoundation)
    try:
        DB.UpdaterRegistry.AddTrigger(
            updater_id, filt, DB.Element.GetChangeTypeGeometry()
        )
        DB.UpdaterRegistry.AddTrigger(
            updater_id, filt, DB.Element.GetChangeTypeElementAddition()
        )
    except Exception as e:
        return updater, u'AddTrigger failed: {}'.format(e)

    # Keep reference alive so Python GC doesn't collect the updater object
    _registered_updater = updater
    return updater, None


def unregister(app):
    """Unregister the updater (called when live mode is fully disabled)."""
    global _registered_updater
    _lifecycle_unregister(app)
    _registered_updater = None


def is_registered(app):
    try:
        from nosa_utils.dmu_lifecycle import is_registered as _lifecycle_is_registered
        return _lifecycle_is_registered(app)
    except Exception:
        return False
