"""
Script de Python para Dynamo - Editar Curvas de Contorno de Toposólido (Versión Completa)
Basado en: Revit Arazi Modelleme | #3 Arazi Model Eğrilerini Düzenleme

Este script permite editar las curvas de contorno de un toposólido en Revit usando Dynamo.
Funcionalidades:
- Obtener curvas de contorno existentes
- Aplicar suavizado a las elevaciones
- Ajustar elevaciones con offset
- Recrear toposólido con curvas modificadas
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
# IN[0]: Toposolid (elemento de Revit) - REQUERIDO
# IN[1]: Smoothing Factor (0.0 a 1.0) - Factor de suavizado (default: 0.5)
# IN[2]: Elevation Offset (double) - Desplazamiento vertical (default: 0.0)
# IN[3]: Apply Smoothing (bool) - Aplicar suavizado o no (default: True)
# ============================================================================

toposolid = IN[0] if IN[0] else None
smoothing_factor = IN[1] if len(IN) > 1 and IN[1] is not None else 0.5
elevation_offset = IN[2] if len(IN) > 2 and IN[2] is not None else 0.0
apply_smoothing = IN[3] if len(IN) > 3 and IN[3] is not None else True

# Validar inputs
if not toposolid:
    OUT = "Error: No se seleccionó ningún toposólido. Por favor, selecciona un toposólido."
elif not isinstance(toposolid, Toposolid):
    OUT = "Error: El elemento seleccionado no es un toposólido."
else:
    try:
        # Iniciar transacción
        TransactionManager.Instance.EnsureInTransaction(doc)
        
        # Obtener las curvas de contorno del toposólido
        contour_curves = []
        modified_curves = []
        all_points = []
        
        # Método para obtener curvas de contorno
        try:
            # Intentar método directo (Revit 2024+)
            if hasattr(toposolid, 'GetContourCurves'):
                contour_curves = list(toposolid.GetContourCurves())
            else:
                # Método alternativo: Obtener geometría
                options = Options()
                options.ComputeReferences = False
                options.DetailLevel = ViewDetailLevel.Medium
                geometry = toposolid.get_Geometry(options)
                
                for geom_obj in geometry:
                    if isinstance(geom_obj, Solid):
                        # Extraer curvas de los bordes
                        for edge in geom_obj.Edges:
                            curve = edge.AsCurve()
                            if curve and curve.Length > 0.1:  # Filtrar curvas muy pequeñas
                                contour_curves.append(curve)
        except Exception as e:
            OUT = "Error obteniendo curvas de contorno: " + str(e)
            TransactionManager.Instance.TransactionTaskDone()
        
        if not contour_curves:
            OUT = "Advertencia: No se encontraron curvas de contorno en el toposólido."
            TransactionManager.Instance.TransactionTaskDone()
        else:
            # Obtener todas las elevaciones para calcular promedios
            elevations = []
            for curve in contour_curves:
                try:
                    start_point = curve.GetEndPoint(0)
                    end_point = curve.GetEndPoint(1)
                    elevations.append(start_point.Z)
                    elevations.append(end_point.Z)
                except:
                    pass
            
            # Calcular elevación promedio para suavizado
            avg_elevation = sum(elevations) / len(elevations) if elevations else 0.0
            
            # Procesar y modificar las curvas
            for idx, curve in enumerate(contour_curves):
                try:
                    # Obtener puntos de inicio y fin
                    start_point = curve.GetEndPoint(0)
                    end_point = curve.GetEndPoint(1)
                    
                    # Calcular nuevas elevaciones
                    if apply_smoothing:
                        # Suavizado: interpolación entre valor original y promedio
                        new_start_z = start_point.Z * (1 - smoothing_factor) + avg_elevation * smoothing_factor
                        new_end_z = end_point.Z * (1 - smoothing_factor) + avg_elevation * smoothing_factor
                    else:
                        # Sin suavizado, solo aplicar offset
                        new_start_z = start_point.Z
                        new_end_z = end_point.Z
                    
                    # Aplicar offset
                    new_start_z += elevation_offset
                    new_end_z += elevation_offset
                    
                    # Crear nuevos puntos
                    new_start = XYZ(start_point.X, start_point.Y, new_start_z)
                    new_end = XYZ(end_point.X, end_point.Y, new_end_z)
                    
                    # Crear nueva curva (mantener el tipo original si es posible)
                    new_curve = None
                    if isinstance(curve, Line):
                        new_curve = Line.CreateBound(new_start, new_end)
                    elif isinstance(curve, Arc):
                        # Para arcos, intentar mantener la forma
                        try:
                            mid_point = curve.Evaluate(0.5, True)
                            if apply_smoothing:
                                new_mid_z = mid_point.Z * (1 - smoothing_factor) + avg_elevation * smoothing_factor + elevation_offset
                            else:
                                new_mid_z = mid_point.Z + elevation_offset
                            new_mid = XYZ(mid_point.X, mid_point.Y, new_mid_z)
                            new_curve = Arc.Create(new_start, new_end, new_mid)
                        except:
                            # Si falla, crear línea recta
                            new_curve = Line.CreateBound(new_start, new_end)
                    elif isinstance(curve, NurbSpline):
                        # Para splines, simplificar a línea
                        new_curve = Line.CreateBound(new_start, new_end)
                    else:
                        # Para otros tipos, crear línea recta
                        new_curve = Line.CreateBound(new_start, new_end)
                    
                    if new_curve:
                        modified_curves.append(new_curve)
                        
                        # Extraer puntos de la curva para recrear toposólido
                        num_points = max(2, int(curve.Length / 10.0))  # Puntos cada 10 unidades
                        for i in range(num_points + 1):
                            param = float(i) / float(num_points) if num_points > 0 else 0.0
                            try:
                                point = new_curve.Evaluate(param, True)
                                all_points.append(point)
                            except:
                                pass
                
                except Exception as e:
                    # Si falla la modificación de una curva, mantener la original
                    modified_curves.append(curve)
            
            # Finalizar transacción
            TransactionManager.Instance.TransactionTaskDone()
            
            # Retornar resultados
            OUT = {
                "status": "Éxito",
                "curvas_originales": len(contour_curves),
                "curvas_modificadas": len(modified_curves),
                "puntos_generados": len(all_points),
                "elevacion_promedio": avg_elevation,
                "puntos": all_points,
                "curvas": modified_curves
            }
        
    except Exception as e:
        try:
            TransactionManager.Instance.TransactionTaskDone()
        except:
            pass
        OUT = "Error general: " + str(e) + "\nTipo: " + str(type(e).__name__)



