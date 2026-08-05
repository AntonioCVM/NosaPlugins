# -*- coding: utf-8 -*-
"""
NOSA Element Comments — Dynamic Model Updater (DMU).

Registered application-wide by startup.py when pyRevit loads.
On new-element creation, for the configured structural categories:
  - if another element of the EXACT same (Category, Family, Type) already
    carries a non-empty Comments value, that value is copied to the new
    element;
  - otherwise the Type is genuinely new, so the next free number under
    that Type's default prefix is assigned.
Grouping is always keyed on the exact Family+Type — never on Category or
Family alone — so differently sized elements can never end up sharing a
Comments code, even automatically.

Configuration is read from NOSA_Configs/element_comments_dmu.json on every
Execute() call so UI toggles take effect immediately, matching the Pile
Live Coordinates DMU pattern (logic_dmu.py under PileMaster).
"""
import os
import io
import json
import sys

from Autodesk.Revit import DB
from nosa_utils.dmu_lifecycle import (
    make_updater_id as _base_make_id,
    unregister as _lifecycle_unregister,
    COMMENTS_GUID_STR,
)

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
    'StructuralFraming':    DB.BuiltInCategory.OST_StructuralFraming,
    'StructuralColumns':    DB.BuiltInCategory.OST_StructuralColumns,
    'StructuralFoundation': DB.BuiltInCategory.OST_StructuralFoundation,
    'Floors':                DB.BuiltInCategory.OST_Floors,
    'Walls':                 DB.BuiltInCategory.OST_Walls,
}

_registered_updater = None
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
        pass
    return dict(_DEFAULTS)


def write_config(cfg):
    try:
        d = os.path.dirname(_CFG_PATH)
        if not os.path.exists(d):
            os.makedirs(d)
        with io.open(_CFG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


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
        if not added_ids:
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
                    pass
            return

        wanted = set(cfg.get('categories') or [])
        tlogic = _elc_logic.TypeCommentsLogic(doc)

        for eid in added_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    continue
                cat_key, fam_name, type_name = tlogic.element_type_info(el)
                if cat_key is None or cat_key not in wanted:
                    continue

                p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if p is None or p.IsReadOnly:
                    continue
                if (p.AsString() or u'').strip():
                    continue  # already has a Comments value — never overwrite

                existing = _elc_logic.existing_comment_for_type(
                    doc, cat_key, fam_name, type_name, exclude_id=el.Id)
                if existing:
                    p.Set(existing)
                    continue

                prefix = _elc_logic.default_prefix_for(cat_key, fam_name, type_name)
                num_part = _elc_logic.next_code_for_new_type(doc, prefix)
                p.Set(u'{}{}'.format(prefix, num_part))
            except Exception:
                pass

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
            filt = DB.ElementCategoryFilter(bic)
            DB.UpdaterRegistry.AddTrigger(
                updater_id, filt, DB.Element.GetChangeTypeElementAddition())
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
