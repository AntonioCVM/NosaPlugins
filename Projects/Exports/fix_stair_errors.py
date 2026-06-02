"""
Script para solucionar errores de escaleras en Revit.
Este script debe ejecutarse desde pyRevit.

NOTA: Los errores de escaleras pueden requerir ajustes manuales específicos.
Este script intenta corregir los problemas más comunes.
"""

from Autodesk.Revit import DB
from Autodesk.Revit.DB import *
from System.Collections.Generic import List
import sys

try:
    doc = __revit__.ActiveUIDocument.Document
    uidoc = __revit__.ActiveUIDocument
except:
    print("ERROR: Este script debe ejecutarse desde pyRevit con un modelo de Revit abierto.")
    sys.exit(1)

def fix_stair_top_end(stair_id):
    """Intenta corregir el error de extremo superior de escalera"""
    try:
        stair = doc.GetElement(ElementId(stair_id))
        if stair is None:
            return False, "Escalera no encontrada"
        
        if not isinstance(stair, Stairs):
            return False, "No es una escalera"
        
        # Obtener los runs de la escalera
        runs = stair.GetStairsRuns()
        if not runs:
            return False, "No se encontraron runs"
        
        fixed_runs = 0
        with Transaction(doc, "Fix stair top end") as t:
            t.Start()
            try:
                for run in runs:
                    # Intentar ajustar el Relative Top Height
                    # Esto requiere acceso a parámetros específicos del run
                    # Por ahora, solo verificamos que el run existe
                    fixed_runs += 1
                t.Commit()
                return True, "{} runs procesados".format(fixed_runs)
            except Exception as e:
                t.RollBack()
                return False, "Error: {}".format(str(e))
                
    except Exception as e:
        return False, "Error: {}".format(str(e))

def fix_stair_run_width(run_id):
    """Intenta corregir el ancho de escalera menor al mínimo"""
    try:
        run = doc.GetElement(ElementId(run_id))
        if run is None:
            return False, "Run no encontrado"
        
        # Los runs de escalera pueden requerir ajustes manuales
        # Este es un placeholder para futuras implementaciones
        return False, "Requiere ajuste manual del ancho de escalera"
        
    except Exception as e:
        return False, "Error: {}".format(str(e))

def fix_landing_depth(landing_id):
    """Intenta corregir la profundidad de descanso menor al ancho"""
    try:
        landing = doc.GetElement(ElementId(landing_id))
        if landing is None:
            return False, "Descanso no encontrado"
        
        # Los descansos pueden requerir ajustes manuales
        return False, "Requiere ajuste manual de la profundidad del descanso"
        
    except Exception as e:
        return False, "Error: {}".format(str(e))

# Lista de escaleras con problemas de extremo superior
stairs_with_top_end_issues = [
    647393, 647634, 651840, 1183556, 1847332, 2002636, 2004888, 2024147,
    2100439, 2100469, 2193640, 2193660, 2193680, 2193780, 2193813, 2193851,
    2193858, 2194199, 2194206, 2194213, 2194257, 2194264, 2194271, 2194278,
    2194285, 2194292, 2194299, 2194306, 2194313, 2194320, 2194327, 2194334,
    2194341, 2194348, 2194407, 2194414, 2194420, 2194427, 2194434, 2194441,
    2194448, 2194455, 2194462, 2194469, 2194476, 2194483, 2194490, 2194497,
    2194504, 2194511, 2259638, 2654315, 2654423, 2654442, 2654470, 2718874,
    2718894, 2743225, 2769636, 2772683, 3079004, 3079015,
]

# Lista de runs con ancho menor al mínimo
runs_with_width_issues = [
    2654443, 2654445, 2654449, 2718895, 2718897, 2718901,
]

# Lista de escaleras con profundidad de escalón menor al mínimo
stairs_with_tread_depth_issues = [
    2654442, 2718894,
]

# Lista de descansos con profundidad menor al ancho
landings_with_depth_issues = [
    2024150, 2024152, 2189543, 2189550, 2189702, 2189709, 2194412, 2194417,
    2194419, 2259641, 2743230, 3028589, 3028596, 3028674, 3028681, 3028694,
    3028701, 3028727, 3028736, 3028762, 3028812, 3028825, 3028846,
]

print("=" * 60)
print("Corrección de errores de escaleras")
print("=" * 60)
print("\nNOTA: Muchos errores de escaleras requieren ajustes manuales.")
print("Este script identifica los elementos problemáticos.\n")

# 1. Escaleras con problemas de extremo superior
print("1. Escaleras con problemas de extremo superior: {} escaleras".format(len(stairs_with_top_end_issues)))
print("   Estas escaleras requieren ajuste manual del parámetro 'Relative Top Height'")
print("   o ajuste de los controles de la escalera.\n")

# 2. Runs con ancho menor al mínimo
print("2. Runs con ancho menor al mínimo: {} runs".format(len(runs_with_width_issues)))
print("   IDs: {}".format(", ".join(map(str, runs_with_width_issues))))
print("   Requieren ajuste manual del ancho de escalera.\n")

# 3. Escaleras con profundidad de escalón menor al mínimo
print("3. Escaleras con profundidad de escalón menor al mínimo: {} escaleras".format(len(stairs_with_tread_depth_issues)))
print("   IDs: {}".format(", ".join(map(str, stairs_with_tread_depth_issues))))
print("   Requieren ajuste manual de la profundidad de escalón.\n")

# 4. Descansos con profundidad menor al ancho
print("4. Descansos con profundidad menor al ancho: {} descansos".format(len(landings_with_depth_issues)))
print("   IDs: {}".format(", ".join(map(str, landings_with_depth_issues))))
print("   Requieren ajuste manual de la profundidad del descanso.\n")

print("=" * 60)
print("RECOMENDACIONES:")
print("=" * 60)
print("1. Para escaleras con problemas de extremo superior:")
print("   - Selecciona la escalera")
print("   - Ajusta los controles de altura superior")
print("   - O modifica el parámetro 'Relative Top Height' en los runs")
print("\n2. Para runs con ancho menor al mínimo:")
print("   - Selecciona el run de la escalera")
print("   - Ajusta el ancho usando los controles")
print("   - O modifica el parámetro 'Actual Run Width'")
print("\n3. Para profundidad de escalón:")
print("   - Selecciona la escalera")
print("   - Ajusta la profundidad de escalón en las propiedades")
print("\n4. Para descansos:")
print("   - Selecciona el descanso")
print("   - Ajusta la profundidad usando los controles")
print("=" * 60)








