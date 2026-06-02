# -*- coding: utf-8 -*-
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow


def _lm(unique, path):
    try:
        import importlib.util as iu
        spec = iu.spec_from_file_location(unique, path)
        m = iu.module_from_spec(spec)
        sys.modules[unique] = m
        spec.loader.exec_module(m)
        return m
    except (ImportError, AttributeError):
        import imp
        m = imp.load_source(unique, path)
        sys.modules[unique] = m
        return m


class DiRootsHubWindow(NOSAWindow):

    def __init__(self, doc, uidoc=None):
        xaml_path = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml_path, 'diroots_hub')
        self._doc = doc
        self._uidoc = uidoc
        self.BtnInstances.Content = u'Bulk parameter editor\n(instances)'
        self.BtnTypes.Content = u'structural type manager\n(ElementTypes)'
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get(u'dark_mode', self.dark_mode)

    def _open_child(self, win):
        """Hide hub, show child window, then close hub when child closes."""
        self.Hide()
        try:
            win.show()
        finally:
            self.Close()

    def Instances_Click(self, sender, args):
        try:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            bulk_ui = os.path.join(base, u'BulkParameterEditor.pushbutton', u'lib', u'ui.py')
            ui_mod = _lm(u'diroots_hub_bulk_proxy', bulk_ui)
            win = ui_mod.BulkParameterEditorWindow(self._doc, self._uidoc)
            self._open_child(win)
        except Exception as e:
            try:
                from pyrevit import forms as _f
                _f.alert(u'Could not open Bulk Parameter Editor:\n{}'.format(e))
            except Exception:
                pass

    def Types_Click(self, sender, args):
        try:
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
            struct_ui = os.path.join(
                root, u'Structures.panel', u'Elements.pulldown',
                u'StructuralTypeManager.pushbutton', u'lib', u'ui.py')
            ui_mod = _lm(u'diroots_hub_struct_proxy', struct_ui)
            win = ui_mod.StructuralTypeManagerWindow(self._doc, self._uidoc)
            self._open_child(win)
        except Exception as e:
            try:
                from pyrevit import forms as _f
                _f.alert(u'Could not open Structural Type Manager:\n{}'.format(e))
            except Exception:
                pass
