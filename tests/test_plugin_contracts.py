# -*- coding: utf-8 -*-
"""Window/XAML/script contracts of every active plugin, checked statically (no Revit, no WPF).

A broken contract here is a window that crashes or a button that does nothing when clicked:
- every XAML is well-formed;
- every XAML event handler (Click="X", SelectionChanged="X", ...) exists as a method;
- every control the code reads as self.<Control> exists in one of the plugin's XAML files;
- script.py puts the extension's lib/ folder on sys.path (correct '..' depth).
"""
import ast
import io
import os
import re
import unittest
import xml.etree.ElementTree as ET

_EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_TAB = os.path.join(_EXT, 'NOSA.tab')
_BASE_WINDOW = os.path.join(_EXT, 'lib', 'nosa_utils', 'base_window.py')

EVENTS = {
    'Click', 'Checked', 'Unchecked', 'SelectionChanged', 'TextChanged', 'MouseDoubleClick',
    'MouseLeftButtonDown', 'MouseLeftButtonUp', 'MouseRightButtonUp', 'MouseEnter', 'MouseLeave',
    'PreviewMouseLeftButtonDown', 'PreviewMouseDoubleClick', 'KeyDown', 'KeyUp', 'PreviewKeyDown',
    'PreviewTextInput', 'Loaded', 'Unloaded', 'Closing', 'Closed', 'ValueChanged', 'LostFocus',
    'GotFocus', 'SizeChanged', 'DropDownClosed', 'DropDownOpened', 'CellEditEnding',
    'BeginningEdit', 'Sorting', 'Expanded', 'Collapsed', 'Drop', 'DragEnter', 'DragOver',
    'SelectedItemChanged', 'ContextMenuOpening', 'PasswordChanged', 'ScrollChanged',
    'CurrentCellChanged', 'LoadingRow', 'PreviewMouseWheel', 'MouseMove', 'Activated',
}
# Members of System.Windows.Window / pyRevit WPFWindow that code reads as self.<Name>.
WINDOW_MEMBERS = {
    'Title', 'Width', 'Height', 'MinWidth', 'MinHeight', 'MaxWidth', 'MaxHeight', 'Left', 'Top',
    'Resources', 'Close', 'Owner', 'DataContext', 'ShowDialog', 'Show', 'Hide', 'Dispatcher',
    'IsLoaded', 'Content', 'ActualWidth', 'ActualHeight', 'Cursor', 'WindowState', 'Topmost',
    'Activate', 'Closing', 'Closed', 'Loaded', 'ContentRendered', 'DialogResult', 'Visibility',
    'IsVisible', 'Background', 'Foreground', 'FontFamily', 'FontSize', 'SizeToContent',
    'WindowStartupLocation', 'ResizeMode', 'Icon', 'Tag', 'Focus', 'KeyDown', 'PreviewKeyDown',
    'InputBindings', 'CommandBindings', 'UpdateLayout', 'FindName', 'FindResource',
    'TryFindResource', 'IsActive', 'ShowInTaskbar', 'Effect', 'Opacity', 'RenderSize',
    'LayoutUpdated', 'SizeChanged', 'StateChanged', 'Deactivated', 'Activated', 'Name',
    'Style', 'Template', 'BorderBrush', 'Margin', 'IsEnabled', 'Language', 'Owner', 'Parent',
    'OwnedWindows', 'Measure', 'Arrange', 'DesiredSize', 'ApplyTemplate', 'BeginInit', 'EndInit',
    'MouseLeftButtonDown', 'DragMove', 'WindowStyle', 'AllowsTransparency', 'Uid',
    'PreviewMouseDown', 'MouseDown', 'Drop', 'AllowDrop', 'ToolTip', 'ContextMenu',
    'SetResourceReference', 'SetValue', 'GetValue', 'ClearValue', 'RegisterName',
}
CONTROL = re.compile(r'^(Txt|Btn|Cbo|Cmb|Combo|Chk|Lst|List|Grid|Dg|Rb|Lbl|Panel|Tab|Canvas|Tb|Pb|Prog|'
                     r'Sld|Img|Border|Stack|Exp|Tree|Popup|Rect|Run|Pnl)[A-Z_]')


def plugins():
    out = []
    for dirpath, dirnames, _files in os.walk(_TAB):
        dirnames[:] = [d for d in dirnames if not d.endswith(('.nobutton', '.DISABLED')) and d != '__pycache__']
        for d in list(dirnames):
            if d.endswith('.pushbutton'):
                out.append(os.path.join(dirpath, d))
                dirnames.remove(d)
    return sorted(out)


def _files(folder, ext):
    for dirpath, dirnames, files in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', 'tests')]
        for f in files:
            if f.endswith(ext):
                yield os.path.join(dirpath, f)


def _read(path):
    with io.open(path, encoding='utf-8-sig') as f:
        return f.read()


def xaml_info(path):
    """(names, [(event, handler)]) of one XAML file."""
    root = ET.fromstring(_read(path).encode('utf-8'))
    names, events = set(), []
    for el in root.iter():
        for key, value in el.attrib.items():
            local = key.split('}')[-1]
            if local == 'Name':
                names.add(value)
            elif local in EVENTS and re.match(r'^[A-Za-z_]\w*$', value):
                events.append((local, value))
    return names, events


def python_info(folder):
    """(defined function/method names, attributes assigned on self, self.X reads per file)."""
    defined, assigned, reads = set(), set(), {}
    for path in list(_files(folder, '.py')) + [_BASE_WINDOW]:
        tree = ast.parse(_read(path))
        file_reads = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == 'self':
                if isinstance(node.ctx, ast.Store):
                    assigned.add(node.attr)
                else:
                    file_reads.add(node.attr)
            elif isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'setattr' \
                    and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                assigned.add(node.args[1].value)
        if path != _BASE_WINDOW:
            reads[path] = file_reads
    return defined, assigned, reads


def _joined_path(script, call):
    while isinstance(call, ast.Call) and getattr(call.func, 'attr', None) in ('abspath', 'normpath'):
        call = call.args[0]
    if not (isinstance(call, ast.Call) and getattr(call.func, 'attr', None) == 'join'):
        return None
    parts = [os.path.dirname(script)]
    for arg in call.args[1:]:
        if not isinstance(arg, ast.Constant):
            return None
        parts.append(arg.value)
    return os.path.normcase(os.path.normpath(os.path.join(*parts)))


def script_lib_problem(script, lib):
    """None if script.py inserts the extension lib/ into sys.path before importing nosa_utils."""
    tree = ast.parse(_read(script))
    paths, inserted_at, first_import = {}, None, None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            path = _joined_path(script, node.value)
            for target in node.targets:
                if isinstance(target, ast.Name) and path:
                    paths[target.id] = path
        elif isinstance(node, ast.ImportFrom) and (node.module or '').startswith('nosa_utils') \
                and node.col_offset == 0:
            first_import = node.lineno if first_import is None else min(first_import, node.lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'insert' \
                and len(node.args) == 2 and isinstance(node.args[1], ast.Name) \
                and paths.get(node.args[1].id) == lib:
            inserted_at = node.lineno if inserted_at is None else min(inserted_at, node.lineno)
    if first_import is None:
        return None
    if inserted_at is None:
        return u'extension lib/ never inserted into sys.path ({})'.format(sorted(paths.values()))
    if inserted_at > first_import:
        return u'nosa_utils imported (line {}) before lib/ is on sys.path (line {})'.format(
            first_import, inserted_at)
    return None


class PluginContractTests(unittest.TestCase):

    def test_plugins_are_found(self):
        self.assertGreaterEqual(len(plugins()), 30)

    def test_xaml_is_well_formed_and_handlers_exist(self):
        problems = []
        for folder in plugins():
            defined, _assigned, _reads = python_info(folder)
            for xaml in _files(folder, '.xaml'):
                try:
                    _names, events = xaml_info(xaml)
                except ET.ParseError as e:
                    problems.append(u'{}: XAML parse error {}'.format(os.path.relpath(xaml, _TAB), e))
                    continue
                for event, handler in events:
                    if handler not in defined:
                        problems.append(u'{}: {}="{}" has no method'.format(
                            os.path.relpath(xaml, _TAB), event, handler))
        self.assertEqual(problems, [], u'\n'.join(problems))

    def test_controls_read_by_code_exist_in_xaml(self):
        problems = []
        for folder in plugins():
            names = set()
            for xaml in _files(folder, '.xaml'):
                names |= xaml_info(xaml)[0]
            if not names:
                continue
            defined, assigned, reads = python_info(folder)
            for path, attrs in sorted(reads.items()):
                for attr in sorted(attrs):
                    if CONTROL.match(attr) and attr not in names and attr not in assigned \
                            and attr not in defined and attr not in WINDOW_MEMBERS:
                        problems.append(u'{}: self.{} is not in any XAML of the plugin'.format(
                            os.path.relpath(path, _TAB), attr))
        self.assertEqual(problems, [], u'\n'.join(problems))

    def test_script_puts_extension_lib_on_sys_path(self):
        problems = []
        lib = os.path.normcase(os.path.join(_EXT, 'lib'))
        for folder in plugins():
            script = os.path.join(folder, 'script.py')
            if not os.path.isfile(script):
                problems.append(u'{}: no script.py'.format(os.path.relpath(folder, _TAB)))
                continue
            problem = script_lib_problem(script, lib)
            if problem:
                problems.append(u'{}: {}'.format(os.path.relpath(script, _TAB), problem))
        self.assertEqual(problems, [], u'\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
