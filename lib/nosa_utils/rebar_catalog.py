# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Shape catalog loader.
Blueprint Parte 7 (F4).

Carga catálogos de formas normativas desde data/shape_catalogs/<standard_code>/catalog.json.
"""
from __future__ import absolute_import, print_function, unicode_literals
import os
import json
from .compat import text_type

_CATALOGS = {}


def load(standard_code):
    """
    Carga el catálogo de formas para 'standard_code' (ej: 'en_iso_3766').
    Retorna dict {catalog, display_name, shapes: {...}} o None si no existe.
    Cacheado internamente.
    """
    if not standard_code or not isinstance(standard_code, text_type):
        return None

    # Normalizar: minúsculas, - → _
    normalized_code = standard_code.lower().replace('-', '_')

    if normalized_code in _CATALOGS:
        return _CATALOGS[normalized_code]

    # Intentar cargar desde data/shape_catalogs/<code>/catalog.json
    # Path relativo desde este fichero: ../../data/shape_catalogs/<code>/catalog.json
    this_dir = os.path.dirname(__file__)
    catalog_path = os.path.abspath(
        os.path.join(this_dir, '..', '..', 'data', 'shape_catalogs', normalized_code, 'catalog.json')
    )

    if not os.path.exists(catalog_path):
        _CATALOGS[normalized_code] = None
        return None

    try:
        with open(catalog_path, 'r') as f:
            catalog = json.load(f)
        _CATALOGS[normalized_code] = catalog
        return catalog
    except (IOError, ValueError) as e:
        print(u'[rebar_catalog] Error loading {}: {}'.format(catalog_path, e))
        _CATALOGS[normalized_code] = None
        return None


def get_shape_def(standard_code, shape_code):
    """
    Retorna la definición de una forma (dict con name, segments, bends, params, constraints)
    o None si no existe.
    """
    catalog = load(standard_code)
    if not catalog or 'shapes' not in catalog:
        return None

    shapes = catalog.get('shapes', {})
    return shapes.get(shape_code)


def list_shape_codes(standard_code):
    """
    Retorna lista de shape codes disponibles en el catálogo (ej: ['00', '11', '51', '99']).
    """
    catalog = load(standard_code)
    if not catalog or 'shapes' not in catalog:
        return []

    return list(catalog['shapes'].keys())


def is_valid_shape_code(standard_code, shape_code):
    """
    Verifica si 'shape_code' existe en el catálogo de 'standard_code'.
    """
    return get_shape_def(standard_code, shape_code) is not None
