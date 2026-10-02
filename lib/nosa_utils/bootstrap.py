# -*- coding: utf-8 -*-
"""
nosa_utils.bootstrap
====================
Unified module loader for the NOSA extension.

Replaces all four script.py / ui.py header variants and every
`imp.load_source(...)` call across ~130 files.

Works in:
  - IronPython 2.7  (pyRevit 4.x/5.x/6.x)
  - CPython 3.x     (pyRevit 6 + future pyRevit 7)

Public API
----------
load_module(name, path)
    Load a .py file as a module by its absolute path.
    Returns the module object (same contract as imp.load_source).

nosa_lib_path(depth)
    Return the absolute path to NOSA.extension/lib for a given
    script.py/ui.py at `depth` levels below the extension root.
    depth=3 → direct pushbutton script.py
    depth=4 → pulldown pushbutton script.py  (or direct lib/*.py)
    depth=5 → pulldown pushbutton lib/*.py

ensure_lib(caller_file, extra_depth=0)
    Derive the lib path from __file__ automatically, add it to sys.path,
    and return it. `extra_depth` is 1 when called from lib/*.py instead
    of script.py (because lib/ adds one level).

Example usage in script.py (replacing the 4-line header + imp.load_source)
---------------------------------------------------------------------------
    # Direct pushbutton script.py
    import os, sys
    _b = os.path.join(os.path.dirname(__file__), '..','..','..', 'lib','nosa_utils','bootstrap.py')
    import importlib.util as _iu; _spec=_iu.spec_from_file_location('bootstrap',_b); _boot=_iu.module_from_spec(_spec); _spec.loader.exec_module(_boot)  # noqa
    _boot.ensure_lib(__file__)   # adds lib/ to sys.path
    from nosa_utils.base_window import launch_nosa_window
    from pyrevit import revit
    _ui = _boot.load_module('myplugin_ui', os.path.join(os.path.dirname(__file__),'lib','ui.py'))
    launch_nosa_window(_ui.MyWindow, revit.doc)

Note: in practice, once bootstrap.py is on sys.path you can import it normally.
The one-liner above is only needed the very first time before lib/ is on sys.path.
"""
import os
import sys


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

def load_module(name, path):
    """
    Load the .py file at `path` as a module named `name`.

    Tries importlib (CPython 3) first, then imp (IronPython 2).
    """
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        raise ImportError(u'NOSA bootstrap: file not found — {}'.format(path))

    # CPython 3 / IronPython with importlib; errors raised by the module itself propagate
    try:
        import importlib.util as _iu
        _iu.spec_from_file_location
    except (ImportError, AttributeError):
        _iu = None
    if _iu is not None:
        spec   = _iu.spec_from_file_location(name, path)
        module = _iu.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as ex:
            sys.modules.pop(name, None)
            raise ImportError(
                u'NOSA bootstrap: cannot load {} from {}: {!r}'.format(name, path, ex))
        return module

    # IronPython 2 fallback
    try:
        import imp
        module = imp.load_source(name, path)
        return module
    except Exception as ex:
        raise ImportError(
            u'NOSA bootstrap: cannot load {} from {}: {}'.format(name, path, ex))


# ---------------------------------------------------------------------------
# sys.path management
# ---------------------------------------------------------------------------

def nosa_lib_path(caller_file, depth):
    """
    Return absolute path to NOSA.extension/lib.

    depth  caller location
    -----  --------------------------------------------------------
    3      NOSA.tab/Panel.panel/Plugin.pushbutton/script.py
    4      NOSA.tab/Panel.panel/Pulldown.pulldown/Plugin.pushbutton/script.py
           OR  NOSA.tab/Panel.panel/Plugin.pushbutton/lib/ui.py
    5      NOSA.tab/Panel.panel/Pulldown.pulldown/Plugin.pushbutton/lib/ui.py
    """
    parts = [os.path.dirname(caller_file)] + ['..'] * depth + ['lib']
    return os.path.abspath(os.path.join(*parts))


def ensure_lib(caller_file, extra_depth=0):
    """
    Auto-detect lib/ path from __file__ and add it to sys.path if absent.

    extra_depth=0  for script.py in a direct pushbutton
    extra_depth=1  for lib/ui.py or lib/logic.py in a direct pushbutton
    extra_depth=1  for script.py in a pulldown pushbutton
    extra_depth=2  for lib/ui.py or lib/logic.py in a pulldown pushbutton

    Returns the lib path.
    """
    base_depth = 3 + extra_depth
    lib = nosa_lib_path(caller_file, base_depth)

    # If that doesn't resolve to an existing dir, try depths 3-5
    if not os.path.isdir(lib):
        for d in (3, 4, 5):
            candidate = nosa_lib_path(caller_file, d)
            if os.path.isdir(candidate):
                lib = candidate
                break

    if lib not in sys.path:
        sys.path.insert(0, lib)
    return lib


# ---------------------------------------------------------------------------
# Convenience: load a plugin's local ui/logic module by convention
# ---------------------------------------------------------------------------

def load_local(caller_file, module_name, filename):
    """
    Load a file from the same directory as caller_file.

    Example:
        _ui = load_local(__file__, 'myplugin_ui', 'ui.py')
    """
    path = os.path.join(os.path.dirname(caller_file), filename)
    return load_module(module_name, path)
