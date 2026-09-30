# -*- coding: utf-8 -*-
"""Fake Autodesk.Revit.DB / System modules so plugin code imports outside Revit."""
import os
import sys
import types


class Namespace(object):
    """Attribute bag (types.SimpleNamespace is CPython 3 only)."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)

    def __repr__(self):
        return 'Namespace(%s)' % ', '.join(
            '%s=%r' % kv for kv in sorted(self.__dict__.items()))


def namespace(**attrs):
    return Namespace(**attrs)


def generic_list(item_type):
    """Stand-in for System.Collections.Generic.List[T]: List[T](items) -> list."""
    return lambda items: list(items)


class FakeElementId(object):
    def __init__(self, value):
        self._value = value

    def __eq__(self, other):
        return isinstance(other, FakeElementId) and other._value == self._value

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._value)


def element_id_namespace():
    """DB.ElementId replacement exposing only InvalidElementId."""
    return Namespace(InvalidElementId=FakeElementId(-1))


class NoRebarHostData(object):
    @staticmethod
    def GetRebarHostData(host):
        raise RuntimeError('not mocked')


class FakeCollector(object):
    """FilteredElementCollector stand-in.

    WhereElementIsNotElementType() returns a copy of `elements`, read at call
    time so tests can mutate the list in place (`lst[:] = [...]`). `elements`
    may also be a callable taking the category passed to OfCategory().
    """

    def __init__(self, elements=None):
        self._elements = elements if elements is not None else []
        self._cat = None

    def OfClass(self, cls):
        return self

    def OfCategory(self, cat):
        self._cat = cat
        return self

    def WhereElementIsNotElementType(self):
        if callable(self._elements):
            return list(self._elements(self._cat))
        return list(self._elements)

    def ToElements(self):
        return []


def collector_factory(elements=None):
    """Value for DB.FilteredElementCollector: a fresh FakeCollector per call."""
    return lambda doc: FakeCollector(elements)


def rebar_structure_attrs(**extra):
    """The Autodesk.Revit.DB.Structure members rebar code touches at import/build time."""
    attrs = dict(
        RebarHostData=NoRebarHostData,
        RebarBarType=object,
        RebarShape=object,
        RebarStyle=Namespace(Standard=1, StirrupTie=2),
        RebarHookOrientation=Namespace(Left=1, Right=2),
        RebarHookType=object,
    )
    attrs.update(extra)
    return attrs


def stub_module(name, attrs=None):
    mod = types.ModuleType(name)
    for key, value in (attrs or {}).items():
        setattr(mod, key, value)
    return mod


def install_revit_stubs(db_attrs=None, structure_attrs=None, only_if_missing=False):
    """Register fake Autodesk, Autodesk.Revit, Autodesk.Revit.DB in sys.modules.

    `structure_attrs=None` leaves Autodesk.Revit.DB.Structure uninstalled; pass
    a dict (possibly empty) to install it. Returns (DB, DBS) — DBS is None when
    not installed. With only_if_missing=True an existing 'Autodesk' entry wins
    and the already-registered modules are returned.
    """
    if only_if_missing and 'Autodesk' in sys.modules:
        return (sys.modules.get('Autodesk.Revit.DB'),
                sys.modules.get('Autodesk.Revit.DB.Structure'))

    db = stub_module('Autodesk.Revit.DB', db_attrs)
    dbs = None
    if structure_attrs is not None:
        dbs = stub_module('Autodesk.Revit.DB.Structure', structure_attrs)
        db.Structure = dbs

    autodesk = types.ModuleType('Autodesk')
    revit_mod = types.ModuleType('Autodesk.Revit')
    autodesk.Revit = revit_mod
    revit_mod.DB = db
    sys.modules['Autodesk'] = autodesk
    sys.modules['Autodesk.Revit'] = revit_mod
    sys.modules['Autodesk.Revit.DB'] = db
    if dbs is not None:
        sys.modules['Autodesk.Revit.DB.Structure'] = dbs
    return db, dbs


def install_system_stubs(full_tree=False, only_if_missing=False):
    """Register a fake System.Collections.Generic exposing List.

    By default only the leaf module is registered, so guarded `import System`
    in plugin code still fails as it would outside .NET. full_tree=True also
    registers System and System.Collections.
    """
    if only_if_missing and 'System' in sys.modules:
        return sys.modules.get('System.Collections.Generic')
    generic = stub_module('System.Collections.Generic', {'List': generic_list})
    if full_tree:
        sys.modules['System'] = types.ModuleType('System')
        sys.modules['System.Collections'] = types.ModuleType('System.Collections')
    sys.modules['System.Collections.Generic'] = generic
    return generic


def load_module(name, path):
    """Import a file under an explicit module name and register it in sys.modules."""
    try:
        import importlib.util
    except ImportError:
        import imp
        return imp.load_source(name, path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def extension_lib_dir():
    """Absolute path of NOSA.extension/lib (the directory containing tests_support)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
