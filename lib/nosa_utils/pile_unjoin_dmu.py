# -*- coding: utf-8 -*-
"""Dynamic Model Updater: keeps pile caps unjoined from their nested piles so PILE_Embedment stays visible."""
from Autodesk.Revit import DB
from nosa_utils.dmu_lifecycle import (
    make_updater_id as _make_id,
    unregister as _unregister,
    PILE_UNJOIN_GUID_STR,
)
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.pile_unjoin_dmu'


def _is_foundation(el):
    cat = el.Category
    return cat is not None and cat.Id.IntegerValue == int(DB.BuiltInCategory.OST_StructuralFoundation)


def unjoin_pairs(doc, caps):
    """Unjoin every joined cap/nested-foundation pair; returns the number unjoined."""
    done = 0
    for cap in caps:
        try:
            sub_ids = list(cap.GetSubComponentIds())
        except Exception:
            continue
        for sid in sub_ids:
            try:
                sub = doc.GetElement(sid)
                if sub is None or not _is_foundation(sub):
                    continue
                if DB.JoinGeometryUtils.AreElementsJoined(doc, cap, sub):
                    DB.JoinGeometryUtils.UnjoinGeometry(doc, cap, sub)
                    done += 1
            except Exception:
                log_swallowed(_LOG, u'unjoin_pairs')
    return done


class PileUnjoinUpdater(DB.IUpdater):
    def __init__(self, updater_id):
        self._id = updater_id

    def Execute(self, data):
        try:
            doc = data.GetDocument()
            ids = list(data.GetAddedElementIds()) + list(data.GetModifiedElementIds())
            caps = []
            for eid in ids:
                el = doc.GetElement(eid)
                if isinstance(el, DB.FamilyInstance) and _is_foundation(el):
                    caps.append(el)
            if caps:
                unjoin_pairs(doc, caps)
        except Exception:
            log_swallowed(_LOG, u'PileUnjoinUpdater.Execute')

    def GetUpdaterId(self):
        return self._id

    def GetUpdaterName(self):
        return 'NOSA Pile Unjoin'

    def GetAdditionalInformation(self):
        return ('Unjoins pile caps from their nested piles so the embedded '
                'part of the pile (PILE_Embedment) is not cut by the cap.')

    def GetChangePriority(self):
        return DB.ChangePriority.FloorsRoofsStructuralWalls


def register(app):
    """Register the updater application-wide; returns (updater, error_or_None)."""
    updater_id = _make_id(app, PILE_UNJOIN_GUID_STR)
    _unregister(app, PILE_UNJOIN_GUID_STR)
    updater = PileUnjoinUpdater(updater_id)
    try:
        DB.UpdaterRegistry.RegisterUpdater(updater, False)
    except Exception as e:
        return None, u'RegisterUpdater failed: {}'.format(e)
    try:
        filt = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_StructuralFoundation)
        DB.UpdaterRegistry.AddTrigger(updater_id, filt, DB.Element.GetChangeTypeElementAddition())
        DB.UpdaterRegistry.AddTrigger(updater_id, filt, DB.Element.GetChangeTypeGeometry())
    except Exception as e:
        return updater, u'AddTrigger failed: {}'.format(e)
    return updater, None
