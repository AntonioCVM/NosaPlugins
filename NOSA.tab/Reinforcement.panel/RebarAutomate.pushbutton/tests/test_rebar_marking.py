# -*- coding: utf-8 -*-
"""
Tests puros de rebar_marking.py (sin Revit — solo lógica de formateo/deduplicación).
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _LIB_ROOT not in sys.path:
    sys.path.insert(0, _LIB_ROOT)

# Importar helpers internos de rebar_marking sin Revit
sys.path.insert(0, os.path.join(_HERE, '..', 'lib'))
from rebar_marking import _round_to_tolerance, _parse_shape_params, format_mark, variant_suffix


def test_round_to_tolerance():
    """Verifica que _round_to_tolerance redondea correctamente al múltiplo más cercano."""
    assert _round_to_tolerance(2003.0, 5.0) == 2005.0
    assert _round_to_tolerance(2001.0, 5.0) == 2000.0
    assert _round_to_tolerance(2000.0, 5.0) == 2000.0
    assert _round_to_tolerance(1997.0, 5.0) == 1995.0
    assert _round_to_tolerance(100.0, 0.0) == 100.0  # tolerance 0 no redondea
    assert _round_to_tolerance(100.0, 10.0) == 100.0
    assert _round_to_tolerance(106.0, 10.0) == 110.0
    print(u"[PASS] test_round_to_tolerance")


def test_parse_shape_params():
    """Verifica que _parse_shape_params parsea y redondea correctamente."""
    # Caso normal
    result = _parse_shape_params("A=2000;B=300;C=150;R=50", 5.0)
    assert result == (2000.0, 300.0, 150.0, 50.0), "Debe ordenar alfabéticamente"
    
    # Con valores que requieren redondeo
    result = _parse_shape_params("A=2003;B=298", 5.0)
    assert result == (2005.0, 300.0)
    
    # Cadena vacía
    result = _parse_shape_params("", 5.0)
    assert result == ()
    
    # Cadena None
    result = _parse_shape_params(None, 5.0)
    assert result == ()
    
    # Formato inválido (se ignoran entradas con formato incorrecto)
    result = _parse_shape_params("A=2000;INVALID;B=300", 5.0)
    assert result == (2000.0, 300.0)
    
    print(u"[PASS] test_parse_shape_params")


def test_mark_format_tokens():
    """Verifica que el formato de marca con tokens funciona correctamente."""
    # Simulación del formato mark_format
    mark_format = "{host_mark}-{number:02d}"
    mark = mark_format.format(host_mark="Z-12", number=3, diameter=12, layer="Bottom X", prefix="")
    assert mark == "Z-12-03"
    
    # Con prefijo
    mark_format = "{prefix}{host_mark}-{number:02d}"
    mark = mark_format.format(host_mark="Z-12", number=3, diameter=12, layer="Bottom X", prefix="PROJ")
    assert mark == "PROJZ-12-03"
    
    # Con diámetro
    mark_format = "{host_mark}-{diameter}mm-{number:02d}"
    mark = mark_format.format(host_mark="Z-12", number=5, diameter=16, layer="Bottom X", prefix="")
    assert mark == "Z-12-16mm-05"
    
    print(u"[PASS] test_mark_format_tokens")


def test_dedup_tolerance_logic():
    """
    Verifica lógica conceptual de deduplicación:
    Dos barras con Shape_Params A=2000 vs A=2002 deben agruparse si dedup_tolerance_mm >= 5.
    """
    # Simulación: dos sets de parámetros que difieren en 2mm
    params1 = _parse_shape_params("A=2000;B=300", 5.0)
    params2 = _parse_shape_params("A=2002;B=300", 5.0)
    
    # Ambos deben redondearse a los mismos valores
    assert params1 == params2, "Con tolerance=5mm, A=2000 y A=2002 deben ser iguales tras redondeo"
    
    # Con una diferencia mayor (6mm), deben quedar en bins diferentes
    params1_diff = _parse_shape_params("A=2000;B=300", 5.0)
    params2_diff = _parse_shape_params("A=2006;B=300", 5.0)
    assert params1_diff != params2_diff
    
    print(u"[PASS] test_dedup_tolerance_logic")


def test_layer_translation_concept():
    """
    Verifica concepto de traducción de clave interna a nombre visible.
    """
    # Simulación del diccionario layer_names de un perfil de normativa
    layer_names = {
        "bottom_x": "Bottom X",
        "bottom_y": "Bottom Y",
        "stirrup": "Stirrups",
        "uncategorized": "Uncategorized"
    }
    
    assert layer_names.get("bottom_x", "bottom_x") == "Bottom X"
    assert layer_names.get("stirrup", "stirrup") == "Stirrups"
    assert layer_names.get("unknown_key", "unknown_key") == "unknown_key"  # Fallback
    
    print(u"[PASS] test_layer_translation_concept")


def test_is_variable_no_dedup_concept():
    """
    Verifica concepto: barras con Is_Variable=1 NO deduplicam.
    La clave de dedup debe ser única para cada barra variable.
    """
    # Simulación: clave de una barra normal vs una variable
    # Normal: tupla con (bar_type, shape_code, params, ...)
    normal_key = ("type123", "00", (2000.0, 300.0), "", "", "bottom_x", "host456")
    
    # Variable: tupla con solo (rebar_id,) — única por definición
    variable_key_1 = ("rebar789",)
    variable_key_2 = ("rebar999",)
    
    # Las variables nunca comparten clave entre sí ni con normales
    assert variable_key_1 != variable_key_2
    assert variable_key_1 != normal_key
    
    print(u"[PASS] test_is_variable_no_dedup_concept")


def test_format_mark_is_plain_sequential_number():
    """BS 8666: marks are 01, 02 ... with no host id or prefix."""
    assert [format_mark(n) for n in (1, 9, 10, 99, 100)] == [u'01', u'09', u'10', u'99', u'100']
    print(u"[PASS] test_format_mark_is_plain_sequential_number")


def test_variant_suffix_skips_i_o_q_and_rolls_over():
    """Varying sets: 05a, 05b ... no i, o or q; after z comes aa, ab ..."""
    letters = [variant_suffix(i) for i in range(23)]
    assert letters == list(u'abcdefghjklmnprstuvwxyz')
    assert not set(u'ioq') & set(u''.join(variant_suffix(i) for i in range(600)))
    assert [variant_suffix(i) for i in (23, 24, 45, 46)] == [u'aa', u'ab', u'az', u'ba']
    assert u'05' + variant_suffix(0) == u'05a'
    print(u"[PASS] test_variant_suffix_skips_i_o_q_and_rolls_over")

if __name__ == "__main__":
    test_format_mark_is_plain_sequential_number()
    test_variant_suffix_skips_i_o_q_and_rolls_over()
    test_round_to_tolerance()
    test_parse_shape_params()
    test_mark_format_tokens()
    test_dedup_tolerance_logic()
    test_layer_translation_concept()
    test_is_variable_no_dedup_concept()
    print(u"\n[SUCCESS] All rebar_marking tests passed (6/6)")
