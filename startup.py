# -*- coding: utf-8 -*-
"""
NOSA Extension startup script.
Runs when pyRevit loads or reloads this extension.
Registers the Pile Live Coordinates and Element Comments Dynamic Model
Updaters (DMUs) — independent GUIDs, each guarded so a failure in one
never blocks the other.
"""
import os
import sys
import imp

_EXT_ROOT = os.path.dirname(__file__)
_EXT_LIB = os.path.join(_EXT_ROOT, 'lib')
_PILE_LIB = os.path.join(
    _EXT_ROOT, 'NOSA.tab', 'Foundations.panel', 'PileMaster.pushbutton', 'lib'
)
_ELC_LIB = os.path.join(
    _EXT_ROOT, 'NOSA.tab', 'Structures.panel', 'ElementCommentsHub.pushbutton', 'lib'
)

for _p in (_EXT_LIB, _PILE_LIB, _ELC_LIB):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_fresh(module_name, path):
    """Fresh load on every startup — avoids stale IronPython types after reload."""
    if module_name in sys.modules:
        try:
            del sys.modules[module_name]
        except Exception:
            pass
    return imp.load_source(module_name, path)


def _register(module_name, path, app, dmu_unregister, label):
    try:
        logic_dmu = _load_fresh(module_name, path)
        dmu_unregister(app)
        _updater, _err = logic_dmu.register(app)
        if _err:
            try:
                from pyrevit import script
                script.get_logger().warning('NOSA startup: %s register — %s', label, _err)
            except Exception:
                pass
    except Exception as _e:
        try:
            from pyrevit import script
            script.get_logger().warning('NOSA startup: %s failed — %s', label, _e)
        except Exception:
            pass


def _run():
    from nosa_utils.dmu_lifecycle import unregister as _pile_unregister

    _app = __revit__.Application  # noqa: F821  (injected by pyRevit)

    # Pile Live Coordinates
    _register('nosa_logic_dmu', os.path.join(_PILE_LIB, 'logic_dmu.py'),
              _app, _pile_unregister, 'Pile Live Coordinates DMU')

    # Element Comments Hub
    _elc_dmu_path = os.path.join(_ELC_LIB, 'logic_dmu.py')
    if os.path.isfile(_elc_dmu_path):
        def _elc_unregister(app):
            from nosa_utils.dmu_lifecycle import unregister as _u, COMMENTS_GUID_STR
            _u(app, COMMENTS_GUID_STR)
        _register('nosa_logic_dmu_element_comments', _elc_dmu_path,
                  _app, _elc_unregister, 'Element Comments DMU')


try:
    _run()
except Exception as _startup_err:
    try:
        from pyrevit import script
        script.get_logger().error('NOSA startup failed: %s', _startup_err)
    except Exception:
        pass
