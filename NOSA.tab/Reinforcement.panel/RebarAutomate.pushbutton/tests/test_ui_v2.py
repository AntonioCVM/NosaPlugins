# -*- coding: utf-8 -*-
"""Phase 10: the v2 window - shell logic and the XAML contract with the code (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import io
import os
import re
import sys
import xml.dom.minidom

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import tab_shell as sh  # noqa: E402

XAML = io.open(os.path.join(_lib, 'ui.xaml'), encoding='utf-8').read()


def _code():
    out = u''
    for name in os.listdir(_lib):
        if name == 'ui.py' or (name.startswith('tab_') and name.endswith('.py')):
            out += io.open(os.path.join(_lib, name), encoding='utf-8').read()
    return out


def test_selection_text_and_tab():
    assert sh.selection_text({}).startswith(u'Nothing selected')
    t = sh.selection_text({'beam': 2, 'slab': 1}, [u'B10', u'B11', u''])
    assert t == u'Selected: 1 slab · 2 beams (B10, B11)'
    assert sh.tab_for({'beam': 2, 'slab': 1}) == 'TabBeams'
    assert sh.tab_for({'base': 1}) == 'TabSlabs'
    assert sh.tab_for({}) is None


def test_element_ids_in_a_log_line():
    assert sh.element_ids(u'Beam 1499707: lap moved; see 1521813') == [1499707, 1521813]
    assert sh.element_ids(u'stock length 12000 mm, 150 mm pitch') == []


def test_status_number_and_visibility():
    assert sh.first_line(u'\n  10 bars created\nmore') == u'10 bars created'
    assert sh.looks_failed(u'No floors or foundations selected.')
    assert not sh.looks_failed(u'Created 10 bars in 2 beams; no clashes')
    assert sh.number_ok(u'150') and not sh.number_ok(u'15o')
    assert sh.number_ok(u'Auto', allow_auto=True) and not sh.number_ok(u'Auto')
    assert sh.visible_for(u'floors', {}) and sh.visible_for(u'footings', {'beam': 1})
    assert not sh.visible_for(u'floors', {'base': 2}) and sh.visible_for(u'footings', {'base': 2})


def test_xaml_is_well_formed_and_keeps_every_control_the_code_uses():
    xml.dom.minidom.parseString(XAML.encode('utf-8'))
    names = set(re.findall(r'\sName="(\w+)"', XAML))
    code = _code()
    used = set(re.findall(r'self\.((?:Txt|Chk|Cmb|Cbo|Btn|Panel|Lst|Tab|Badge|Dot)[A-Za-z0-9]+)(?![A-Za-z0-9_])', code))
    missing = sorted(n for n in used if n not in names)
    assert not missing, missing
    for tab, handler, log in sh.ELEMENT_TABS:
        assert tab in names and log in names and u'def {}('.format(handler) in code


def test_xaml_rules():
    # NOSA rule (Phase 3.6): no SelectedIndex / SelectionChanged on a selector in XAML
    assert u'SelectedIndex' not in XAML and u'SelectionChanged=' not in XAML
    # British English only, SMDSC 4th ed. references only
    for word in (u'Floors only', u'Footings only', u'MC6', u'MCB1', u'MST1', u'MW3', u'SMDSC 5.1.9', u'ch. 9'):
        assert word not in XAML, word
    visible = re.sub(u'<!--.*?-->', u'', XAML, flags=re.S)        # comments are not UI
    assert not re.search(u'[áéíóúñ¿¡]', visible)
    for tab, _h, _l in sh.ELEMENT_TABS:
        assert u'<TabItem Name="{}"'.format(tab) in XAML
    assert XAML.count(u'Name="BtnGenerate"') == 1


if __name__ == '__main__':
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_'):
            _fn()
    print('test_ui_v2: OK')
