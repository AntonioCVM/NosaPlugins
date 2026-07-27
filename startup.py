# -*- coding: utf-8 -*-
"""
NOSA Extension startup script.
Runs when pyRevit loads or reloads this extension.
Registers the Pile Live Coordinates Dynamic Model Updater (DMU).
"""
import os
import sys
import imp

_EXT_ROOT = os.path.dirname(__file__)
_EXT_LIB = os.path.join(_EXT_ROOT, 'lib')
_PILE_LIB = os.path.join(
    _EXT_ROOT, 'NOSA.tab', 'Foundations.panel', 'PileMaster.pushbutton', 'lib'
)

for _p in (_EXT_LIB, _PILE_LIB):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_logic_dmu():
    """Fresh load on every startup — avoids stale IronPython types after reload."""
    _name = 'nosa_logic_dmu'
    _path = os.path.join(_PILE_LIB, 'logic_dmu.py')
    if _name in sys.modules:
        try:
            del sys.modules[_name]
        except Exception:
            pass
    return imp.load_source(_name, _path)


def _run():
    from nosa_utils.dmu_lifecycle import unregister as _dmu_unregister

    _app = __revit__.Application  # noqa: F821  (injected by pyRevit)

    # Always tear down any previous registration before creating a new updater.
    _dmu_unregister(_app)

    logic_dmu = _load_logic_dmu()
    _updater, _err = logic_dmu.register(_app)
    if _err:
        try:
            from pyrevit import script
            script.get_logger().warning('NOSA startup: DMU register — %s', _err)
        except Exception:
            pass


try:
    _run()
except Exception as _startup_err:
    try:
        from pyrevit import script
        script.get_logger().error('NOSA startup failed: %s', _startup_err)
    except Exception:
        pass
