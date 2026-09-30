# tests_support

Helpers for testing plugin logic with a plain `python` interpreter, without Revit.
`revit_stubs` registers fake `Autodesk.Revit.DB` / `System` modules in `sys.modules`,
so modules that do `from Autodesk.Revit import DB` at import time can be loaded.

Tests are plain scripts (`python tests/test_x.py`); pytest is optional.

## Using it from a plugin

Put the extension `lib/` folder on `sys.path`. Count the `..` from the `tests/` folder
up to `NOSA.extension`:

| Test location | `..` count |
|---|---|
| `Panel.panel/Plugin.pushbutton/tests/` | 4 |
| `Panel.panel/Pulldown.pulldown/Plugin.pushbutton/tests/` | 5 |

```python
import os, sys

_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                        '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs

DB, DBS = revit_stubs.install_revit_stubs(
    structure_attrs=revit_stubs.rebar_structure_attrs())
DB.XYZ = MyFakeXYZ                      # add only what your code touches
DB.FilteredElementCollector = revit_stubs.collector_factory()
revit_stubs.install_system_stubs()      # System.Collections.Generic.List

_LIB = os.path.join(os.path.dirname(__file__), '..', 'lib')
logic = revit_stubs.load_module('myplugin_logic', os.path.join(_LIB, 'logic.py'))
```

Install the stubs **before** importing the module under test.

## API

| Name | Purpose |
|---|---|
| `install_revit_stubs(db_attrs=None, structure_attrs=None, only_if_missing=False)` | Registers `Autodesk`, `Autodesk.Revit`, `Autodesk.Revit.DB` (+ `DB.Structure` when `structure_attrs` is a dict, even `{}`). Returns `(DB, DBS)`. |
| `install_system_stubs(full_tree=False, only_if_missing=False)` | Registers `System.Collections.Generic` with `List`. `full_tree=True` also registers `System` and `System.Collections`. Leave it `False` if the code has a guarded `import System`. |
| `rebar_structure_attrs(**extra)` | Default `DB.Structure` members (`RebarHostData`, `RebarBarType`, `RebarShape`, `RebarStyle`, `RebarHookOrientation`, `RebarHookType`) plus any extras. |
| `collector_factory(elements=None)` | Value for `DB.FilteredElementCollector`. `elements` is a list (read at call time, so tests can mutate it in place) or a callable `f(category) -> list`. |
| `FakeElementId`, `element_id_namespace()` | Hashable id with value equality; `DB.ElementId` stand-in exposing `InvalidElementId`. |
| `NoRebarHostData` | `RebarHostData` whose `GetRebarHostData` raises. |
| `namespace(**attrs)` | Attribute bag for enums (`types.SimpleNamespace` works on CPython 3 only). |
| `stub_module(name, attrs)` | Bare `ModuleType` with attributes set. |
| `load_module(name, path)` | Imports a file under an explicit name and registers it in `sys.modules`. |

Geometry fakes (`XYZ`, `Line`, `Solid`, ...) are deliberately **not** shared: each test
suite models only the behaviour it checks. Keep them in the test file.

Reference usage: `NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton/tests/`.
