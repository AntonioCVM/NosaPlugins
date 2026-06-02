"""
Script para solucionar errores restantes de Revit (vigas fuera de eje y líneas de propiedad).
Este script debe ejecutarse desde pyRevit.
"""

from Autodesk.Revit import DB
from Autodesk.Revit.DB import *
from System.Collections.Generic import List
import sys
import math

try:
    doc = __revit__.ActiveUIDocument.Document
    uidoc = __revit__.ActiveUIDocument
except:
    print("ERROR: Este script debe ejecutarse desde pyRevit con un modelo de Revit abierto.")
    sys.exit(1)

def fix_off_axis_beam(beam_id):
    """Intenta corregir una viga ligeramente fuera de eje"""
    try:
        beam = doc.GetElement(ElementId(beam_id))
        if beam is None:
            return False, "Viga no encontrada"
        
        if not isinstance(beam, FamilyInstance):
            return False, "No es una viga"
        
        # Obtener la ubicación de la viga
        location = beam.Location
        if location is None:
            return False, "No se puede obtener la ubicación"
        
        if isinstance(location, LocationCurve):
            curve = location.Curve
            if curve is None:
                return False, "No se puede obtener la curva"
            
            # Verificar si la curva está alineada con los ejes principales
            start_point = curve.GetEndPoint(0)
            end_point = curve.GetEndPoint(1)
            
            # Calcular el vector de dirección
            direction = end_point - start_point
            direction_normalized = direction.Normalize()
            
            # Verificar alineación con ejes principales (X, Y, Z)
            # Si está muy cerca de un eje principal, ajustar
            tolerance = 0.001  # Tolerancia en pies
            
            # Verificar alineación con eje X
            if abs(abs(direction_normalized.X) - 1.0) < tolerance:
                # Está alineado con X, verificar si necesita ajuste
                return True, "Viga alineada con eje X (puede requerir ajuste manual)"
            
            # Verificar alineación con eje Y
            if abs(abs(direction_normalized.Y) - 1.0) < tolerance:
                return True, "Viga alineada con eje Y (puede requerir ajuste manual)"
            
            # Verificar alineación con eje Z
            if abs(abs(direction_normalized.Z) - 1.0) < tolerance:
                return True, "Viga alineada con eje Z (puede requerir ajuste manual)"
            
            return False, "Viga no alineada con ejes principales (requiere ajuste manual)"
        else:
            return False, "La viga no tiene una ubicación de curva"
            
    except Exception as e:
        return False, "Error: {}".format(str(e))

def fix_off_axis_line(line_id):
    """Intenta corregir una línea ligeramente fuera de eje"""
    try:
        line = doc.GetElement(ElementId(line_id))
        if line is None:
            return False, "Línea no encontrada"
        
        # Las líneas de modelo pueden requerir ajustes manuales
        return False, "Requiere ajuste manual de la línea"
        
    except Exception as e:
        return False, "Error: {}".format(str(e))

def fix_property_line(property_line_id):
    """Intenta corregir una línea de propiedad que no forma un bucle cerrado"""
    try:
        property_line = doc.GetElement(ElementId(property_line_id))
        if property_line is None:
            return False, "Línea de propiedad no encontrada"
        
        # Las líneas de propiedad que no forman un bucle cerrado
        # requieren ajuste manual de los puntos
        return False, "Requiere ajuste manual para cerrar el bucle"
        
    except Exception as e:
        return False, "Error: {}".format(str(e))

# Lista de vigas fuera de eje
beams_off_axis = [
    2062408, 2082357, 2568082, 2849321, 2854413, 2945461,
]

# Lista de líneas fuera de eje
lines_off_axis = [
    3049453, 3049456,
]

# Línea de propiedad sin bucle cerrado
property_line_not_closed = [
    3083071,
]

print("=" * 60)
print("Corrección de errores restantes")
print("=" * 60)

# 1. Vigas fuera de eje
print("\n1. Vigas ligeramente fuera de eje: {} vigas".format(len(beams_off_axis)))
checked_count = 0
for beam_id in beams_off_axis:
    success, message = fix_off_axis_beam(beam_id)
    if success:
        checked_count += 1
        print("  ✓ Viga {}: {}".format(beam_id, message))
    else:
        print("  ✗ Viga {}: {}".format(beam_id, message))
print("  Total verificadas: {}/{}".format(checked_count, len(beams_off_axis)))

# 2. Líneas fuera de eje
print("\n2. Líneas ligeramente fuera de eje: {} líneas".format(len(lines_off_axis)))
for line_id in lines_off_axis:
    success, message = fix_off_axis_line(line_id)
    print("  ✗ Línea {}: {}".format(line_id, message))

# 3. Línea de propiedad sin bucle cerrado
print("\n3. Línea de propiedad sin bucle cerrado: {} línea".format(len(property_line_not_closed)))
for prop_line_id in property_line_not_closed:
    success, message = fix_property_line(prop_line_id)
    print("  ✗ Línea de propiedad {}: {}".format(prop_line_id, message))

print("\n" + "=" * 60)
print("RECOMENDACIONES:")
print("=" * 60)
print("1. Para vigas fuera de eje:")
print("   - Selecciona la viga")
print("   - Ajusta los puntos de inicio y fin para alinearlos con los ejes principales")
print("   - Usa Snap para asegurar alineación perfecta")
print("\n2. Para líneas fuera de eje:")
print("   - Selecciona la línea")
print("   - Ajusta los puntos para alinearlos con los ejes principales")
print("\n3. Para líneas de propiedad sin bucle cerrado:")
print("   - Selecciona la línea de propiedad")
print("   - Verifica que todos los segmentos formen un bucle cerrado")
print("   - Ajusta los puntos para cerrar el bucle")
print("=" * 60)








