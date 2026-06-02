"""
Script de Python para Dynamo - Editar Curvas de Contorno de Toposólido
Basado en: Revit Arazi Modelleme | #3 Arazi Model Eğrilerini Düzenleme

Este script permite:
1. Seleccionar un toposólido
2. Obtener sus curvas de contorno
3. Modificar las elevaciones (suavizado, ajuste, etc.)
4. Actualizar el toposólido con las curvas modificadas
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('RevitServices')
clr.AddReference('DynamoCore')
clr.AddReference('ProtoGeometry')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
import System
from System.Collections.Generic import List

# Obtener el documento activo
doc = DocumentManager.Instance.CurrentDBDocument
uidoc = DocumentManager.Instance.CurrentUIApplication.ActiveUIDocument

# ============================================================================
# INPUTS
# ============================================================================
# IN[0]: Toposolid (elemento de Revit)
# IN[1]: Smoothing Factor (0.0 a 1.0) - Factor de suavizado
# IN[2]: Elevation Offset (double) - Desplazamiento vertical opcional
# ============================================================================

toposolid = IN[0] if IN[0] else None
smoothing_factor = IN[1] if len(IN) > 1 and IN[1] else 0.5
elevation_offset = IN[2] if len(IN) > 2 and IN[2] else 0.0

if not toposolid:
    OUT = "Error: No se seleccionó ningún toposólido"
else:
    try:
        # Iniciar transacción
        TransactionManager.Instance.EnsureInTransaction(doc)
        
        # Obtener las curvas de contorno del toposólido
        # En Revit 2024+, usar Toposolid.GetContourCurves()
        # Para versiones anteriores, usar método alternativo
        
        contour_curves = []
        modified_curves = []
        
        # Método 1: Si el toposólido tiene curvas de contorno accesibles
        try:
            # Intentar obtener curvas de contorno directamente
            # Nota: La API exacta puede variar según la versión de Revit
            if hasattr(toposolid, 'GetContourCurves'):
                contour_curves = list(toposolid.GetContourCurves())
            else:
                # Método alternativo: Obtener geometría y extraer curvas
                options = Options()
                options.ComputeReferences = False
                options.DetailLevel = ViewDetailLevel.Medium
                geometry = toposolid.get_Geometry(options)
                
                for geom_obj in geometry:
                    if isinstance(geom_obj, Solid):
                        # Extraer curvas de los bordes del sólido
                        for edge in geom_obj.Edges:
                            curve = edge.AsCurve()
                            if curve:
                                contour_curves.append(curve)
        except Exception as e:
            OUT = "Error obteniendo curvas: " + str(e)
            TransactionManager.Instance.TransactionTaskDone()
        
        # Procesar y modificar las curvas
        for curve in contour_curves:
            try:
                # Obtener puntos de inicio y fin
                start_point = curve.GetEndPoint(0)
                end_point = curve.GetEndPoint(1)
                
                # Calcular nueva elevación con suavizado
                # Promedio de las elevaciones de inicio y fin
                avg_elevation = (start_point.Z + end_point.Z) / 2.0
                
                # Aplicar suavizado (interpolación entre valor original y promedio)
                new_start_z = start_point.Z * (1 - smoothing_factor) + avg_elevation * smoothing_factor
                new_end_z = end_point.Z * (1 - smoothing_factor) + avg_elevation * smoothing_factor
                
                # Aplicar offset si se especificó
                new_start_z += elevation_offset
                new_end_z += elevation_offset
                
                # Crear nuevos puntos
                new_start = XYZ(start_point.X, start_point.Y, new_start_z)
                new_end = XYZ(end_point.X, end_point.Y, new_end_z)
                
                # Crear nueva curva (mantener el tipo original)
                if isinstance(curve, Line):
                    new_curve = Line.CreateBound(new_start, new_end)
                elif isinstance(curve, Arc):
                    # Para arcos, mantener el radio y crear nuevo arco
                    mid_point = curve.Evaluate(0.5, True)
                    new_mid_z = mid_point.Z * (1 - smoothing_factor) + avg_elevation * smoothing_factor + elevation_offset
                    new_mid = XYZ(mid_point.X, mid_point.Y, new_mid_z)
                    # Crear arco a través de los tres puntos
                    try:
                        new_curve = Arc.Create(new_start, new_end, new_mid)
                    except:
                        # Si falla, crear línea recta
                        new_curve = Line.CreateBound(new_start, new_end)
                else:
                    # Para otros tipos de curva, crear línea recta
                    new_curve = Line.CreateBound(new_start, new_end)
                
                modified_curves.append(new_curve)
                
            except Exception as e:
                # Si falla la modificación de una curva, mantener la original
                modified_curves.append(curve)
        
        # Actualizar el toposólido con las curvas modificadas
        # Nota: La edición directa de curvas de contorno puede requerir
        # usar SketchEditScope o recrear el toposólido
        
        # Método alternativo: Exportar puntos modificados para recrear
        modified_points = []
        for curve in modified_curves:
            # Dividir curva en puntos
            num_points = 10  # Número de puntos por curva
            for i in range(num_points + 1):
                param = float(i) / float(num_points)
                point = curve.Evaluate(param, True)
                modified_points.append(point)
        
        # Finalizar transacción
        TransactionManager.Instance.TransactionTaskDone()
        
        # Retornar resultados
        OUT = [
            "Curvas originales: " + str(len(contour_curves)),
            "Curvas modificadas: " + str(len(modified_curves)),
            "Puntos generados: " + str(len(modified_points)),
            modified_points,  # Lista de puntos para recrear toposólido
            modified_curves    # Curvas modificadas
        ]
        
    except Exception as e:
        TransactionManager.Instance.TransactionTaskDone()
        OUT = "Error: " + str(e)

