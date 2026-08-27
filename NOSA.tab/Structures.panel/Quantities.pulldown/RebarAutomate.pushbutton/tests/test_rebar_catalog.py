# -*- coding: utf-8 -*-
"""
Tests puros para nosa_utils.rebar_catalog (F4).
Verifican carga de catálogos JSON y lookup de formas.
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys
import os

# Agregar lib/ al path
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import rebar_catalog


def test_load_en_iso_3766():
    """Verifica que se carga el catálogo EN ISO 3766."""
    catalog = rebar_catalog.load('en_iso_3766')
    assert catalog is not None, "EN ISO 3766 catalog should exist"
    assert 'shapes' in catalog
    assert 'catalog' in catalog
    assert catalog['catalog'] == 'en_iso_3766'
    print('[PASS] EN ISO 3766 catalog loads correctly')


def test_load_bs_8666():
    """Verifica que se carga el catálogo BS 8666:2020."""
    catalog = rebar_catalog.load('bs_8666_2020')
    assert catalog is not None, "BS 8666:2020 catalog should exist"
    assert 'shapes' in catalog
    assert catalog['catalog'] == 'bs_8666_2020'
    print('[PASS] BS 8666:2020 catalog loads correctly')


def test_get_shape_def():
    """Verifica que get_shape_def() retorna definiciones correctas."""
    shape_00 = rebar_catalog.get_shape_def('en_iso_3766', '00')
    assert shape_00 is not None
    assert shape_00['name'] == 'Straight bar'
    assert shape_00['segments'] == 1
    assert shape_00['bends'] == 0
    
    shape_11 = rebar_catalog.get_shape_def('en_iso_3766', '11')
    assert shape_11 is not None
    assert 'L-shape' in shape_11['name']
    assert shape_11['segments'] == 2
    assert shape_11['bends'] == 1
    
    shape_51 = rebar_catalog.get_shape_def('en_iso_3766', '51')
    assert shape_51 is not None
    assert 'U-bar' in shape_51['name']
    assert shape_51['segments'] == 3
    
    print('[PASS] get_shape_def() returns correct definitions')


def test_list_shape_codes():
    """Verifica que list_shape_codes() retorna todos los códigos."""
    codes = rebar_catalog.list_shape_codes('en_iso_3766')
    assert '00' in codes
    assert '11' in codes
    assert '51' in codes
    assert '99' in codes
    print('[PASS] list_shape_codes() returns all expected codes')


def test_is_valid_shape_code():
    """Verifica validación de códigos de forma."""
    assert rebar_catalog.is_valid_shape_code('en_iso_3766', '00') == True
    assert rebar_catalog.is_valid_shape_code('en_iso_3766', '11') == True
    assert rebar_catalog.is_valid_shape_code('en_iso_3766', '99') == True
    assert rebar_catalog.is_valid_shape_code('en_iso_3766', 'XX') == False
    print('[PASS] is_valid_shape_code() validates correctly')


def test_nonexistent_catalog():
    """Verifica que catálogos inexistentes retornan None."""
    catalog = rebar_catalog.load('nonexistent_standard')
    assert catalog is None
    print('[PASS] Nonexistent catalog returns None')


def test_shape_constraints():
    """Verifica que las formas tienen constraints correctos."""
    shape_11 = rebar_catalog.get_shape_def('en_iso_3766', '11')
    assert 'constraints' in shape_11
    assert 'A_min_mm' in shape_11['constraints']
    assert 'B_min_mm' in shape_11['constraints']
    assert 'angle_deg' in shape_11['constraints']
    assert shape_11['constraints']['angle_deg'] == 90
    print('[PASS] Shape constraints are defined correctly')


if __name__ == '__main__':
    test_load_en_iso_3766()
    test_load_bs_8666()
    test_get_shape_def()
    test_list_shape_codes()
    test_is_valid_shape_code()
    test_nonexistent_catalog()
    test_shape_constraints()
    print('\n[SUCCESS] All rebar_catalog tests passed (7/7)')
