"""
Script para solucionar errores de Revit detectados en el informe de errores.
Este script debe ejecutarse desde pyRevit.

INSTRUCCIONES:
1. Abre Revit con el modelo cargado
2. Abre pyRevit
3. Ejecuta este script desde pyRevit

O ejecuta el script maestro: EJECUTAR_TODOS_LOS_SCRIPTS.py
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

def unjoin_elements(element1_id, element2_id):
    """Desune dos elementos que están unidos pero no se intersectan"""
    try:
        element1 = doc.GetElement(ElementId(element1_id))
        element2 = doc.GetElement(ElementId(element2_id))
        
        if element1 is None or element2 is None:
            return False
            
        # Intentar desunir usando JoinGeometryUtils
        if JoinGeometryUtils.AreElementsJoined(doc, element1, element2):
            with Transaction(doc, "Unjoin elements") as t:
                t.Start()
                try:
                    JoinGeometryUtils.UnjoinGeometry(doc, element1, element2)
                    t.Commit()
                    return True
                except:
                    t.RollBack()
                    return False
    except Exception as e:
        print("Error unjoining elements {} and {}: {}".format(element1_id, element2_id, str(e)))
        return False
    return False

def detach_wall_from_target(wall_id, target_id):
    """Desadjunta un muro de su objetivo"""
    try:
        wall = doc.GetElement(ElementId(wall_id))
        target = doc.GetElement(ElementId(target_id))
        
        if wall is None or target is None:
            return False
            
        if isinstance(wall, Wall):
            with Transaction(doc, "Detach wall") as t:
                t.Start()
                try:
                    wall.DetachFromHost()
                    t.Commit()
                    return True
                except:
                    t.RollBack()
                    return False
    except Exception as e:
        print("Error detaching wall {} from target {}: {}".format(wall_id, target_id, str(e)))
        return False
    return False

def fix_overlapping_floors(floor1_id, floor2_id):
    """Intenta resolver pisos superpuestos eliminando el más pequeño o ajustando geometría"""
    try:
        floor1 = doc.GetElement(ElementId(floor1_id))
        floor2 = doc.GetElement(ElementId(floor2_id))
        
        if floor1 is None or floor2 is None:
            return False, "Elemento no encontrado"
            
        # Desunir primero si están unidos
        if JoinGeometryUtils.AreElementsJoined(doc, floor1, floor2):
            with Transaction(doc, "Unjoin overlapping floors") as t:
                t.Start()
                try:
                    JoinGeometryUtils.UnjoinGeometry(doc, floor1, floor2)
                    t.Commit()
                except Exception as e:
                    t.RollBack()
                    return False, "Error al desunir: {}".format(str(e))
        
        # Obtener áreas de los pisos
        area1_param = floor1.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        area2_param = floor2.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)
        
        area1 = area1_param.AsDouble() if area1_param and area1_param.HasValue else 0
        area2 = area2_param.AsDouble() if area2_param and area2_param.HasValue else 0
        
        # Si las áreas son muy similares (duplicado), eliminar el más pequeño
        # Solo eliminar si la diferencia es menor al 1% y ambas áreas son significativas
        if area1 > 0 and area2 > 0:
            area_diff = abs(area1 - area2) / max(area1, area2)
            if area_diff < 0.01:  # Menos del 1% de diferencia
                floor_to_delete = floor2 if area2 <= area1 else floor1
                with Transaction(doc, "Delete duplicate floor") as t:
                    t.Start()
                    try:
                        doc.Delete(floor_to_delete.Id)
                        t.Commit()
                        return True, "Piso duplicado eliminado"
                    except Exception as e:
                        t.RollBack()
                        return False, "Error al eliminar: {}".format(str(e))
            else:
                return True, "Pisos desunidos (áreas diferentes)"
        else:
            return True, "Pisos desunidos"
                    
    except Exception as e:
        return False, "Error: {}".format(str(e))

# Lista de elementos unidos que no se intersectan
elements_to_unjoin = [
    (635470, 1033704),  # Column - Floor
    (635494, 1033704),  # Column - Floor
    (635505, 1033704),  # Column - Floor
    (640772, 1841319),  # Wall - Beam
    (659343, 1033704),  # Column - Floor
    (659356, 1033704),  # Column - Floor
    (659369, 1033704),  # Column - Floor
    (659876, 1033704),  # Column - Floor
    (659995, 1033704),  # Column - Floor
    (894364, 1033704),  # Column - Floor
    (1014154, 2738026), # Floor - Column
    (1014154, 2738036), # Floor - Column
    (1014467, 2738066), # Floor - Column
    (1018487, 1185212), # Floor - Floor
    (1033704, 1808807), # Floor - Wall
    (1033704, 1808809), # Floor - Wall
    (1033704, 1808879), # Floor - Wall
    (1033704, 1832279), # Floor - Wall
    (1033704, 1833382), # Floor - Wall
    (1033704, 3030364), # Floor - Floor
    (1050809, 2632939), # Column - Foundation
    (1067310, 2594968), # Floor - Wall
    (1454462, 2977749), # Floor - Floor
    (2079661, 2079682), # Beam - Beam
]

# Lista de muros adjuntos que no alcanzan objetivos
walls_to_detach = [
    (1808809, 1033704),  # Wall - Floor
    (1833382, 1033704),  # Wall - Floor
    (2189467, 1033704),  # Wall - Floor
]

# Lista de pisos superpuestos (todos los del informe)
overlapping_floors = [
    (1014154, 2035110),
    (1018487, 1038660),
    (2632169, 3030163),
    (2632414, 3030163),
    (2634019, 2977749),
    (2880524, 2922735),
    (2977749, 3030111),
    # Pisos de 235mm superpuestos (muchos casos)
    (2571591, 3130090),
    (2571591, 3130318),
    (2727557, 3129210),
    (2727557, 3129466),
    (3130202, 3130506),
    (3130247, 3130506),
    (3130259, 3130506),
    (3130506, 3130532),
    (3138439, 3138566),
    (3138439, 3138629),
    (3138462, 3138495),
    (3138462, 3138518),
    (3138591, 3138655),
    (3138609, 3138655),
    (3138617, 3138655),
    (3138655, 3138681),
    (3138710, 3138837),
    (3138710, 3138900),
    (3138733, 3138766),
    (3138733, 3138789),
    (3138862, 3138926),
    (3138880, 3138926),
    (3138888, 3138926),
    (3138926, 3138952),
    (3138977, 3139104),
    (3138977, 3139167),
    (3139000, 3139033),
    (3139000, 3139056),
    (3139129, 3139193),
    (3139147, 3139193),
    (3139155, 3139193),
    (3139193, 3139219),
    (3139244, 3139371),
    (3139244, 3139434),
    (3139267, 3139300),
    (3139267, 3139323),
    (3139396, 3139460),
    (3139414, 3139460),
    (3139422, 3139460),
    (3139460, 3139486),
    (3139512, 3139639),
    (3139512, 3139702),
    (3139535, 3139568),
    (3139535, 3139591),
    (3139664, 3139728),
    (3139682, 3139728),
    (3139690, 3139728),
    (3139728, 3139754),
    (3139779, 3139906),
    (3139779, 3139969),
    (3139802, 3139835),
    (3139802, 3139858),
    (3139931, 3139995),
    (3139949, 3139995),
    (3139957, 3139995),
    (3139995, 3140021),
    (3140046, 3140173),
    (3140046, 3140236),
    (3140069, 3140102),
    (3140069, 3140125),
    (3140198, 3140262),
    (3140216, 3140262),
    (3140224, 3140262),
    (3140262, 3140288),
    (3140313, 3140440),
    (3140313, 3140503),
    (3140336, 3140369),
    (3140336, 3140392),
    (3140465, 3140529),
    (3140483, 3140529),
    (3140491, 3140529),
    (3140529, 3140555),
    (3140580, 3140707),
    (3140580, 3140770),
    (3140603, 3140636),
    (3140603, 3140659),
    (3140732, 3140796),
    (3140750, 3140796),
    (3140758, 3140796),
    (3140796, 3140822),
    (3140847, 3140974),
    (3140847, 3141037),
    (3140870, 3140903),
    (3140870, 3140926),
    (3140999, 3141063),
    (3141017, 3141063),
    (3141025, 3141063),
    (3141063, 3141089),
    (3141114, 3141241),
    (3141114, 3141304),
    (3141137, 3141170),
    (3141137, 3141193),
    (3141266, 3141330),
    (3141284, 3141330),
    (3141292, 3141330),
    (3141330, 3141356),
]

print("=" * 60)
print("Iniciando corrección de errores de Revit")
print("=" * 60)

# 1. Desunir elementos que no se intersectan
print("\n1. Desuniendo elementos que no se intersectan...")
unjoined_count = 0
for elem1_id, elem2_id in elements_to_unjoin:
    if unjoin_elements(elem1_id, elem2_id):
        unjoined_count += 1
        print("  ✓ Desunidos: {} y {}".format(elem1_id, elem2_id))
print("  Total desunidos: {}/{}".format(unjoined_count, len(elements_to_unjoin)))

# 2. Desadjuntar muros
print("\n2. Desadjuntando muros...")
detached_count = 0
for wall_id, target_id in walls_to_detach:
    if detach_wall_from_target(wall_id, target_id):
        detached_count += 1
        print("  ✓ Desadjuntado muro {} del objetivo {}".format(wall_id, target_id))
print("  Total desadjuntados: {}/{}".format(detached_count, len(walls_to_detach)))

# 3. Resolver pisos superpuestos
print("\n3. Resolviendo pisos superpuestos...")
fixed_floors_count = 0
for floor1_id, floor2_id in overlapping_floors:
    success, message = fix_overlapping_floors(floor1_id, floor2_id)
    if success:
        fixed_floors_count += 1
        print("  ✓ Pisos {} y {}: {}".format(floor1_id, floor2_id, message))
    else:
        print("  ✗ Pisos {} y {}: {}".format(floor1_id, floor2_id, message))
print("  Total resueltos: {}/{}".format(fixed_floors_count, len(overlapping_floors)))

print("\n" + "=" * 60)
print("Corrección completada")
print("=" * 60)

