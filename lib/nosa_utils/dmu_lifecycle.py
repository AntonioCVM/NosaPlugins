# -*- coding: utf-8 -*-
"""Shared reload-safe register / unregister helpers for NOSA's Dynamic Model
Updaters. Each DMU has its own fixed GUID; pass it explicitly to manage more
than one updater without collisions. The default keeps existing callers
(Pile Live Coordinates) working unchanged."""

import System
from Autodesk.Revit import DB

_GUID_STR = 'C4F8E23A-7B51-4D0A-9F1C-3E7A8B2D5C06'            # Pile Live Coordinates
COMMENTS_GUID_STR = '8A1E4F3B-6C2D-4A9E-B7F1-2D9C5A3E1B8F'     # Element Comments Hub


def make_updater_id(app, guid_str=_GUID_STR):
    return DB.UpdaterId(app.ActiveAddInId, System.Guid(guid_str))


def is_registered(app, guid_str=_GUID_STR):
    try:
        return DB.UpdaterRegistry.IsUpdaterRegistered(make_updater_id(app, guid_str))
    except Exception:
        return False


def unregister(app, guid_str=_GUID_STR):
    """Remove the DMU if registered. Safe to call repeatedly."""
    try:
        updater_id = make_updater_id(app, guid_str)
        if DB.UpdaterRegistry.IsUpdaterRegistered(updater_id):
            DB.UpdaterRegistry.UnregisterUpdater(updater_id)
    except Exception:
        pass


ALL_GUIDS = (_GUID_STR, COMMENTS_GUID_STR)


def unregister_all(app):
    """Remove every NOSA DMU; a Python IUpdater left registered across a pyRevit reload can crash Revit."""
    for guid_str in ALL_GUIDS:
        unregister(app, guid_str)
