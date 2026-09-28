# -*- coding: utf-8 -*-
"""
DIAGNÓSTICO - Verificar estado de shared parameters NOSA
Ejecutar desde pyRevit Script Editor
"""
from pyrevit import revit, forms
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector
import sys
import os

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import shared_params

doc = revit.doc

# 1. Verificar si ensure_bound se ejecutó
print("=" * 80)
print("DIAGNÓSTICO SHARED PARAMETERS NOSA")
print("=" * 80)

# 2. Intentar ejecutar ensure_bound de nuevo
print("\n1. Ejecutando ensure_bound()...")
try:
    report = shared_params.ensure_bound(doc)
    print("   ÉXITO - ensure_bound() completó")
    print("   Bound: {}".format(len(report.get('bound', []))))
    print("   Already: {}".format(len(report.get('already', []))))
    print("   Skipped: {}".format(len(report.get('skipped', []))))
    print("   Errors: {}".format(len(report.get('errors', []))))
    
    if report.get('errors'):
        print("\n   ERRORES:")
        for err in report['errors']:
            print("   - {}".format(err))
except Exception as e:
    print("   ERROR: {}".format(e))

# 3. Buscar una barra y verificar si tiene parámetros
print("\n2. Buscando barras en el documento...")
rebars = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()
print("   Encontradas: {} barras".format(len(list(rebars))))

if rebars:
    rebar = list(rebars)[0]
    print("\n3. Verificando parámetros en barra ID {}:".format(rebar.Id))
    
    # Intentar leer algunos parámetros clave
    test_params = [
        ("NOSA_Rebar_Batch_Id", "7c1f3e8a-d5c4-4b1a-9f2e-8a6b5c4d3e2f"),
        ("NOSA_Rebar_Mark", "a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
        ("NOSA_Rebar_Number", "e8f9a0b1-c2d3-4e5f-6789-0abcdef12345"),
    ]
    
    for name, guid in test_params:
        # Buscar por GUID
        try:
            import System
            guid_obj = System.Guid(guid)
            param = rebar.get_Parameter(guid_obj)
            if param:
                print("   ✓ {} (por GUID): EXISTE".format(name))
            else:
                print("   ✗ {} (por GUID): NO ENCONTRADO".format(name))
        except Exception as e:
            print("   ✗ {} (por GUID): ERROR - {}".format(name, e))
        
        # Buscar por nombre
        try:
            param = rebar.LookupParameter(name)
            if param:
                print("   ✓ {} (por nombre): EXISTE".format(name))
            else:
                print("   ✗ {} (por nombre): NO ENCONTRADO".format(name))
        except Exception as e:
            print("   ✗ {} (por nombre): ERROR - {}".format(name, e))

print("\n" + "=" * 80)
print("FIN DIAGNÓSTICO")
print("=" * 80)
