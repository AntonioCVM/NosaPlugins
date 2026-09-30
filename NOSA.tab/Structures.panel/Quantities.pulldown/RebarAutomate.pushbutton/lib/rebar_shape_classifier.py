# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Shape classifier.
Blueprint Parte 7 (F4).

Analiza curvas de rebar y asigna código de forma + parámetros (Shape_Code, Shape_Params).
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import rebar_catalog
from nosa_utils.compat import text_type
import math

_FT_TO_MM = 304.8
_MM_TO_FT = 1.0 / 304.8


def _analyze_curves(curves):
    """
    Analiza lista de curvas (Revit Curve objects) y retorna dict con:
    - segments: número de segmentos lineales
    - bends: número de bends detectados
    - total_length_mm: longitud total en mm
    - angles: lista de ángulos entre segmentos consecutivos (grados)
    - segment_lengths_mm: lista de longitudes de cada segmento (mm)
    """
    if not curves:
        return {
            'segments': 0,
            'bends': 0,
            'total_length_mm': 0.0,
            'angles': [],
            'segment_lengths_mm': []
        }

    # Lazy import
    from Autodesk.Revit.DB import Line

    segments = []
    total_length = 0.0

    for curve in curves:
        if isinstance(curve, Line):
            length_ft = curve.Length
            total_length += length_ft
            segments.append({
                'length_mm': length_ft * _FT_TO_MM,
                'direction': curve.Direction.Normalize()
            })

    # Detectar ángulos entre segmentos consecutivos
    angles = []
    for i in range(len(segments) - 1):
        dir1 = segments[i]['direction']
        dir2 = segments[i + 1]['direction']
        
        # Calcular ángulo entre direcciones
        dot = dir1.DotProduct(dir2)
        # Clamp para evitar errores de precisión
        dot = max(-1.0, min(1.0, dot))
        angle_rad = math.acos(dot)
        angle_deg = math.degrees(angle_rad)
        
        # Si el ángulo es significativo (> 5°), es un bend
        if angle_deg > 5.0:
            angles.append(angle_deg)

    return {
        'segments': len(segments),
        'bends': len(angles),
        'total_length_mm': total_length * _FT_TO_MM,
        'angles': angles,
        'segment_lengths_mm': [s['length_mm'] for s in segments],
        'directions': [s['direction'] for s in segments]
    }


def _classify_shape_code(analysis):
    """
    Clasifica el código de forma basándose en el análisis de curvas.
    Retorna código de forma como string (ej: '00', '11', '21', '51', '99').
    Códigos BS 8666:2020 / ISO 3766: 21 = U, 51 = cerco cerrado (decisión del usuario 2026-09-30).
    """
    segments = analysis['segments']
    bends = analysis['bends']
    angles = analysis['angles']

    # Forma 00: barra recta (1 segmento, sin bends)
    if segments == 1 and bends == 0:
        return '00'

    # Forma 11: L-shape (2 segmentos, 1 bend ~90°)
    if segments == 2 and bends == 1:
        if len(angles) == 1 and 85.0 <= angles[0] <= 95.0:
            return '11'

    # Forma 21: U-bar (3 segmentos, 2 bends ~90°)
    if segments == 3 and bends == 2:
        if len(angles) == 2:
            angle1, angle2 = angles
            if (85.0 <= angle1 <= 95.0) and (85.0 <= angle2 <= 95.0):
                return '21'

    # Forma 51: cerco cerrado — 4+ tramos con lados opuestos antiparalelos
    directions = analysis.get('directions', [])
    if segments >= 4 and len(directions) >= 4:
        if directions[0].DotProduct(directions[2]) < -0.99 and                 directions[1].DotProduct(directions[3]) < -0.99:
            return '51'

    # Por defecto: forma personalizada
    return '99'


def _compute_shape_params(shape_code, analysis, bending=None):
    """
    Calcula parámetros de forma (A, B, C, R...) basándose en el código de forma y análisis.
    Retorna string en formato "A=2000;B=300;C=150;R=50" (valores en mm, redondeados).
    With `bending` (rebar_bending.bending_legs) the legs are BS 8666 outer
    dimensions and R the real bend radius (T4.1), not centreline tangents / 50.
    """
    lengths = analysis['segment_lengths_mm']
    radius = 50
    if bending:
        lengths = [l for l, _a in bending['legs']]
        if bending.get('mandrel_mm'):
            radius = int(round(bending['mandrel_mm'] / 2.0))

    if shape_code == '00':
        # Barra recta: solo A (longitud total)
        A = round(analysis['total_length_mm'], 1)
        return u'A={}'.format(int(A))

    elif shape_code == '11':
        # L-shape: A (primer segmento), B (segundo segmento), R (radio estimado)
        if len(lengths) >= 2:
            A = round(lengths[0], 1)
            B = round(lengths[1], 1)
            R = radius
            return u'A={};B={};R={}'.format(int(A), int(B), int(R))

    elif shape_code == '51':
        # Cerco cerrado: A y B (dos lados consecutivos), R (radio)
        if len(lengths) >= 2:
            return u'A={};B={};R={}'.format(int(round(lengths[0], 1)), int(round(lengths[1], 1)), radius)

    elif shape_code == '21':
        # U-bar: A (primer segmento), B (segmento central), C (tercer segmento), R (radio)
        if len(lengths) >= 3:
            A = round(lengths[0], 1)
            B = round(lengths[1], 1)
            C = round(lengths[2], 1)
            R = radius
            return u'A={};B={};C={};R={}'.format(int(A), int(B), int(C), int(R))

    # Forma 99 o desconocida: solo longitud total
    total = round(analysis['total_length_mm'], 1)
    return u'A={}'.format(int(total))


def _bending(doc, rebar, curves):
    """Outer legs and mandrel of this bar (rebar_bending), or None."""
    try:
        import rebar_bending
        bar_dia_mm = doc.GetElement(rebar.GetTypeId()).BarModelDiameter * _FT_TO_MM
        return rebar_bending.bending_from_curves(curves, bar_dia_mm)
    except Exception:
        return None


_COMPUTED_CODES = ('00', '11', '21', '51', '99')


def _revit_shape_params(doc, rebar):
    """A=..;B=.. read from the bar's own Revit shape family (e.g. 26, 75), in mm."""
    try:
        shape = doc.GetElement(rebar.GetShapeId())
        pairs = []
        for param_id in shape.GetRebarShapeDefinition().GetParameters():
            name = doc.GetElement(param_id).Name
            if len(name) > 2 or not name[:1].isalpha():
                continue
            param = rebar.LookupParameter(name)
            if param is not None and param.HasValue:
                pairs.append((name, int(round(param.AsDouble() * _FT_TO_MM))))
        pairs = [(n, v) for n, v in sorted(pairs) if v != 0 or n in ('A', 'B', 'C')]
        return u';'.join(u'{}={}'.format(n, v) for n, v in pairs)
    except Exception:
        return None


def classify_and_stamp(doc, rebar_id, standard_code):
    """
    Clasifica la forma de una barra (ElementId) y sella NOSA_Rebar_Shape_Code + Shape_Params.
    
    Parámetros:
    - doc: Revit Document
    - rebar_id: ElementId de la barra
    - standard_code: código de normativa (ej: 'en_iso_3766') para validar contra catálogo
    
    Retorna tuple (shape_code, shape_params_str) o (None, None) si falla.
    """
    # BUG FIX (2026-09-01) — Rebar lives in Autodesk.Revit.DB.Structure,
    # NOT Autodesk.Revit.DB. Reported live as "Shape classification
    # failed: Cannot import name Rebar" on EVERY batch run, silently
    # skipping F4 shape classification entirely.
    from Autodesk.Revit.DB.Structure import Rebar  # Lazy import
    from nosa_utils import shared_params

    rebar = doc.GetElement(rebar_id)
    if not rebar or not isinstance(rebar, Rebar):
        return (None, None)

    try:
        # Obtener curvas centerline de la barra (bar 0, esqueleto)
        curves = list(rebar.GetCenterlineCurves(False, False, False, 0, 0))
        
        if not curves:
            return (None, None)

        # Analizar curvas
        analysis = _analyze_curves(curves)
        
        # Clasificar forma — a Revit shape that is itself a catalogue code
        # (e.g. the lapped circle 75) wins over the curve analysis.
        shape_code = None
        try:
            revit_shape = doc.GetElement(rebar.GetShapeId())
            from Autodesk.Revit.DB import Element  # Lazy import; .Name fails on RebarShape in IronPython
            name = Element.Name.GetValue(revit_shape) if revit_shape is not None else None
            if name and name not in ('00', '99') and standard_code and \
                    rebar_catalog.is_valid_shape_code(standard_code, name):
                shape_code = name
        except Exception:
            shape_code = None
        if shape_code is None:
            shape_code = _classify_shape_code(analysis)
        
        # Validar contra catálogo (si existe)
        if standard_code and not rebar_catalog.is_valid_shape_code(standard_code, shape_code):
            # Si el código no existe en el catálogo, caer a '99'
            shape_code = '99'

        # Calcular parámetros
        shape_params = _compute_shape_params(shape_code, analysis, _bending(doc, rebar, curves))
        if shape_code not in _COMPUTED_CODES:
            family_params = _revit_shape_params(doc, rebar)
            if family_params:
                shape_params = family_params

        # Sellar parámetros compartidos
        # BUG FIX (2026-09-02) — same signature mismatch as
        # rebar_marking.py: shared_params.write(elem, name, value) takes
        # an ELEMENT first, not (doc, id) — this called it as (doc,
        # rebar_id, name, value), 4 args against a 3-arg signature,
        # raising on every single bar ("write() takes exactly 3
        # arguments (4 given)"), reported live for beams/walls/floors —
        # F4 classified 0 bars in every run despite `rebar` already
        # being the resolved element right here.
        shared_params.write(rebar, "NOSA_Rebar_Shape_Code", shape_code)
        shared_params.write(rebar, "NOSA_Rebar_Shape_Params", shape_params)

        return (shape_code, shape_params)

    except Exception as e:
        print(u'[rebar_shape_classifier] Error classifying rebar {}: {}'.format(rebar_id, e))
        return (None, None)


def batch_classify(doc, rebar_ids, standard_code):
    """
    Clasifica un lote de barras (lista de ElementIds) y sella sus formas.
    Retorna dict summary {classified: int, failed: int, shapes: {code: count}}.
    """
    summary = {
        'classified': 0,
        'failed': 0,
        'shapes': {}
    }

    for rid in rebar_ids:
        shape_code, _ = classify_and_stamp(doc, rid, standard_code)
        if shape_code:
            summary['classified'] += 1
            summary['shapes'][shape_code] = summary['shapes'].get(shape_code, 0) + 1
        else:
            summary['failed'] += 1

    return summary
