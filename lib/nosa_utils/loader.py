# -*- coding: utf-8 -*-
import sys


def load_local_module(name, path):
    """Load a Python file as a module — compatible with CPython 3.x and IronPython 2.7."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    except (ImportError, AttributeError):
        from nosa_utils.bootstrap import load_module
        mod = load_module(name, path)
        sys.modules[name] = mod
        return mod
