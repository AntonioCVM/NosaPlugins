# -*- coding: utf-8 -*-
"""
NOSA Element Comments — Dynamic Model Updater (DMU).

Registered application-wide by startup.py when pyRevit loads.
For the configured structural categories, whenever an element is added
OR an existing element's Type changes (e.g. via the Type Selector):
  - if another element of the EXACT same (Category, Family, Type) already
    carries a non-empty Comments value, that value is copied;
  - otherwise the Type is genuinely new (to this element, or to the
    model), so the next free number under that Type's default prefix is
    assigned.
Grouping is always keyed on the exact Family+Type — never on Category or
Family alone — so differently sized elements can never end up sharing a
Comments code, even automatically.

Detecting "the Type actually changed" (as opposed to the element merely
being moved, which also fires a geometry-change trigger) requires
remembering what Type an element had last time its Comments value was
verified — a lone element of its Type has no sibling to compare against,
so peer data alone can't tell a retype from a move. That state is kept
in a small Extensible Storage schema on each managed element.

Configuration is read from NOSA_Configs/element_comments_dmu.json on every
Execute() call so UI toggles take effect immediately, matching the Pile
Live Coordinates DMU pattern (logic_dmu.py under PileMaster).
"""
import os
import io
import json
import sys

import System
from Autodesk.Revit import DB
from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, Entity, AccessLevel
from nosa_utils.dmu_lifecycle import (
    make_updater_id as _base_make_id,
    unregister as _lifecycle_unregister,
    COMMENTS_GUID_STR,
)
from nosa_utils.telemetry import log_swallowed
_LOG = u'elementcommentshub'

_CFG_PATH = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs',
    'element_comments_dmu.json'
)

_DEFAULTS = {
    'active':     False,
    'categories': ['StructuralFraming', 'StructuralColumns',
                   'StructuralFoundation', 'Floors', 'Walls'],
}

# This plugin's own lib dir — needed to import logic.py (TypeCommentsLogic)
# from Execute() without relying on the caller's sys.path state.
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))

# Category keys this updater can trigger on, mapped to BuiltInCategory —
# duplicated (not imported) from logic.py on purpose, so register()/
# unregister() never depend on a lazy cross-module import succeeding.
_TARGET_BICS = {
    'StructuralFraming':    'OST_StructuralFraming',
    'StructuralColumns':    'OST_StructuralColumns',
    'StructuralFoundation': 'OST_StructuralFoundation',
    'Floors':                'OST_Floors',
    'Walls':                 'OST_Walls',
}

_registered_updater = None
_IMPORT_WARNED = False

# ---------------------------------------------------------------------------
# Per-element "last known Type" tracking (Extensible Storage)
# ---------------------------------------------------------------------------

_TRACK_SCHEMA_GUID = System.Guid('4C8E7A2D-1F9B-4E3A-9C6D-2B7E5A1F8D3C')
_TRACK_FIELD = 'LastTypeId'
_track_schema = None


def _get_track_schema():
    global _track_schema
    if _track_schema is not None:
        return _track_schema
    schema = Schema.Lookup(_TRACK_SCHEMA_GUID)
    if schema is None:
        builder = SchemaBuilder(_TRACK_SCHEMA_GUID)
        builder.SetSchemaName('NosaElementCommentsTypeTrack')
        builder.SetVendorId('NOSA')
        builder.SetReadAccessLevel(AccessLevel.Public)
        builder.SetWriteAccessLevel(AccessLevel.Public)
        builder.AddSimpleField(_TRACK_FIELD, System.Int64)
        schema = builder.Finish()
    _track_schema = schema
    return schema


def _read_last_type_id(el):
    """Stored TypeId (int) from the last time this element's Comments
    value was verified, or None if never tracked."""
    schema = Schema.Lookup(_TRACK_SCHEMA_GUID)
    if schema is None:
        return None
    try:
        entity = el.GetEntity(schema)
        if not entity.IsValid():
            return None
        return int(entity.Get[System.Int64](_TRACK_FIELD))
    except Exception:
        return None


def _write_last_type_id(el, type_id_int):
    try:
        schema = _get_track_schema()
        entity = Entity(schema)
        entity.Set[System.Int64](_TRACK_FIELD, System.Int64(type_id_int))
        el.SetEntity(entity)
    except Exception:
        log_swallowed(_LOG, u'_write_last_type_id')


def _sync_element_comment(doc, elc_logic, el, cat_key, fam_name, type_name):
    """
    Keep one element's Comments value in sync with its current Type.
    No-ops cheaply (one Extensible Storage read, no model scan) unless
    the element's Type actually differs from what was last recorded for
    it — covering both a brand-new element (nothing recorded yet) and an
    existing element that was retyped, without ever reacting to a plain
    move/rotate that leaves the Type unchanged.
    """
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is None or p.IsReadOnly:
        return
    type_id_int = int(el.GetTypeId().Value if hasattr(el.GetTypeId(), 'Value')
                       else el.GetTypeId().IntegerValue)
    stored = _read_last_type_id(el)
    if stored == type_id_int:
        return

    cur_comment = (p.AsString() or u'').strip()
    existing = elc_logic.existing_comment_for_type(
        doc, cat_key, fam_name, type_name, exclude_id=el.Id)

    if stored is None and cur_comment and (not existing or existing == cur_comment):
        # First time we've tracked this element (e.g. it was set up via
        # the manual grid) and its current value already looks right for
        # its current Type — trust it, just start tracking from here.
        pass
    elif existing:
        p.Set(existing)
    else:
        prefix = elc_logic.default_prefix_for(cat_key, fam_name, type_name)
        num_part = elc_logic.next_code_for_new_type(doc, prefix)
        p.Set(u'{}{}'.format(prefix, num_part))

    _write_last_type_id(el, type_id_int)


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


class ElementCommentUpdater(DB.IUpdater):
    """
    Fires whenever an element of a configured structural category is added.
    Must NOT create a Transaction — already inside Revit's own transaction.
    """

    def __init__(self, updater_id):
        self._id = updater_id

    def Execute(self, data):
        cfg = read_config()
        if not cfg.get('active'):
            return

        doc = data.GetDocument()
        added_ids = list(data.GetAddedElementIds())
        modified_ids = list(data.GetModifiedElementIds())
        element_ids = added_ids + modified_ids
        if not element_ids:
            return

        # Lazy-import to avoid stale IronPython/CPython types after reload
        # (same pattern as PileMaster's logic_dmu.py).
        global _IMPORT_WARNED
        if _LIB_DIR not in sys.path:
            sys.path.insert(0, _LIB_DIR)
        try:
            import logic as _elc_logic
        except Exception as e:
            if not _IMPORT_WARNED:
                _IMPORT_WARNED = True
                try:
                    from nosa_utils.telemetry import log_error
                    log_error('DMU/ElementComments logic import', str(e))
                except Exception:
                    log_swallowed(_LOG, u'ElementCommentUpdater.Execute')
            return

        wanted = set(cfg.get('categories') or [])
        tlogic = _elc_logic.TypeCommentsLogic(doc)

        for eid in element_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    continue
                cat_key, fam_name, type_name = tlogic.element_type_info(el)
                if cat_key is None or cat_key not in wanted:
                    continue
                _sync_element_comment(doc, _elc_logic, el, cat_key, fam_name, type_name)
            except Exception:
                log_swallowed(_LOG, u'ElementCommentUpdater.Execute')

    def GetUpdaterId(self):
        return self._id

    def GetUpdaterName(self):
        return 'NOSA Element Comments'

    def GetAdditionalInformation(self):
        return ('Assigns a shared Comments code per exact Family+Type to new '
                'structural elements (beams, columns, foundations, floors, walls); '
                'copies the code from an existing element of the same Type, or '
                'creates the next free number when the Type is new.')

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

    updater_id = _base_make_id(app, COMMENTS_GUID_STR)
    _lifecycle_unregister(app, COMMENTS_GUID_STR)

    updater = ElementCommentUpdater(updater_id)
    try:
        DB.UpdaterRegistry.RegisterUpdater(updater, False)
    except Exception as e:
        return None, u'RegisterUpdater failed: {}'.format(e)

    # One trigger per category (PileMaster's proven pattern) rather than a
    # single ElementMulticategoryFilter — avoids relying on a List[BuiltInCategory]
    # marshalling path that isn't exercised elsewhere in this codebase.
    errors = []
    for cat_key, bic in _TARGET_BICS.items():
        try:
            filt = DB.ElementCategoryFilter(getattr(DB.BuiltInCategory, bic))
            DB.UpdaterRegistry.AddTrigger(
                updater_id, filt, DB.Element.GetChangeTypeElementAddition())
            DB.UpdaterRegistry.AddTrigger(
                updater_id, filt, DB.Element.GetChangeTypeGeometry())
        except Exception as e:
            errors.append(u'{}: {}'.format(cat_key, e))

    _registered_updater = updater
    return updater, (u'; '.join(errors) if errors else None)


def unregister(app):
    """Unregister the updater (called when live mode is fully disabled)."""
    global _registered_updater
    _lifecycle_unregister(app, COMMENTS_GUID_STR)
    _registered_updater = None


def is_registered(app):
    try:
        from nosa_utils.dmu_lifecycle import is_registered as _lifecycle_is_registered
        return _lifecycle_is_registered(app, COMMENTS_GUID_STR)
    except Exception:
        return False
