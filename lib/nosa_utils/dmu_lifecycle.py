# -*- coding: utf-8 -*-
"""Pile Live Coordinates DMU — reload-safe register / unregister helpers."""

import System
from Autodesk.Revit import DB

_GUID_STR = 'C4F8E23A-7B51-4D0A-9F1C-3E7A8B2D5C06'


def make_updater_id(app):
    return DB.UpdaterId(app.ActiveAddInId, System.Guid(_GUID_STR))


def is_registered(app):
    try:
        return DB.UpdaterRegistry.IsUpdaterRegistered(make_updater_id(app))
    except Exception:
        return False


def unregister(app):
    """Remove the DMU if registered. Safe to call repeatedly."""
    try:
        updater_id = make_updater_id(app)
        if DB.UpdaterRegistry.IsUpdaterRegistered(updater_id):
            DB.UpdaterRegistry.UnregisterUpdater(updater_id)
    except Exception:
        pass
