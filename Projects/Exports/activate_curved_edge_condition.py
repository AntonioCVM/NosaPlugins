# -*- coding: utf-8 -*-
"""Script para activar Curved Edge Condition en toposólidos
Este script intenta modificar los sketches de los toposólidos para permitir
activar el parámetro Curved Edge Condition, que hace que las líneas de contorno
se vean fluidas en lugar de segmentadas.
"""
from pyrevit import revit, DB

# Obtener el documento activo
doc = revit.doc
uidoc = revit.uidoc

# IDs de los toposólidos que necesitan ser modificados
toposolid_ids = [
    DB.ElementId(652547),
    DB.ElementId(652559)
]

print("=" * 70)
print("ACTIVANDO CURVED EDGE CONDITION EN TOPOSÓLIDOS")
print("=" * 70)

success_count = 0
manual_count = 0

for toposolid_id in toposolid_ids:
    toposolid = doc.GetElement(toposolid_id)
    if not toposolid:
        print("\n✗ Toposólido {} no encontrado.".format(toposolid_id))
        continue
    
    print("\n" + "-" * 70)
    print("Procesando toposólido: {}".format(toposolid_id))
    
    # Obtener el parámetro Curved Edge Condition
    curved_edge_param = toposolid.get_Parameter(DB.BuiltInParameter.CURVED_EDGE_CONDITION)
    if not curved_edge_param:
        print("  ✗ No se pudo encontrar el parámetro Curved Edge Condition")
        continue
    
    current_value = curved_edge_param.AsInteger()
    print("  - Valor actual: {} (0=Segmentado, 1=Suave)".format(current_value))
    
    # Si ya está activado, saltar
    if current_value == 1:
        print("  ✓ Ya está activado (líneas fluidas)")
        success_count += 1
        continue
    
    # Intentar cambiar el parámetro
    try:
        with revit.Transaction("Activate Curved Edge Condition"):
            if curved_edge_param.IsReadOnly:
                print("  ⚠ El parámetro es de solo lectura")
                print("  → Modificando el sketch para permitir activación...")
                
                # Obtener el sketch del toposólido
                sketch_id = toposolid.SketchId
                if sketch_id == DB.ElementId.InvalidElementId:
                    print("  ✗ No se encontró sketch asociado")
                    manual_count += 1
                    continue
                
                sketch = doc.GetElement(sketch_id)
                if not sketch:
                    print("  ✗ No se pudo obtener el sketch")
                    manual_count += 1
                    continue
                
                # Obtener el sketch plane
                sketch_plane = sketch.SketchPlane
                if not sketch_plane:
                    print("  ✗ No se pudo obtener el sketch plane")
                    manual_count += 1
                    continue
                
                # Obtener las curvas del sketch
                sketch_curves = sketch.Profile
                if not sketch_curves or len(sketch_curves) == 0:
                    print("  ✗ No se encontraron curvas en el sketch")
                    manual_count += 1
                    continue
                
                # Intentar modificar el sketch usando SketchEditScope
                try:
                    with DB.SketchEditScope(doc, "Modify Toposolid Sketch") as edit_scope:
                        edit_scope.Start(sketch_id)
                        
                        # Obtener todas las ModelCurves del sketch
                        collector = DB.FilteredElementCollector(doc, sketch_id)
                        model_curves = list(collector.OfClass(DB.ModelCurve).ToElements())
                        
                        lines_found = 0
                        arcs_created = 0
                        lines_to_convert = []
                        
                        # Primero, identificar todas las líneas que necesitan ser convertidas
                        for model_curve in model_curves:
                            geom_curve = model_curve.GeometryCurve
                            
                            if isinstance(geom_curve, DB.Line):
                                lines_found += 1
                                lines_to_convert.append((model_curve, geom_curve))
                        
                        if lines_found > 0:
                            print("  → Se encontraron {} líneas en el sketch".format(lines_found))
                            
                            # Intentar convertir al menos una línea en arco para activar el parámetro
                            # Solo necesitamos convertir una línea para que el parámetro se active
                            if len(lines_to_convert) > 0:
                                model_curve, line = lines_to_convert[0]  # Convertir solo la primera
                                
                                try:
                                    # Convertir línea en arco suave
                                    start = line.GetEndPoint(0)
                                    end = line.GetEndPoint(1)
                                    mid = (start + end) / 2.0
                                    
                                    # Calcular dirección y perpendicular
                                    direction = (end - start).Normalize()
                                    
                                    # Vector perpendicular en el plano del sketch
                                    if abs(direction.Z) < 0.9:
                                        perp = DB.XYZ(-direction.Y, direction.X, 0).Normalize()
                                    else:
                                        perp = DB.XYZ(1, 0, 0)
                                    
                                    # Crear punto medio desplazado (suavidad mínima del 1% de la longitud)
                                    offset_distance = max(line.Length * 0.01, 0.1)  # Mínimo 0.1 pies
                                    arc_mid = mid + perp * offset_distance
                                    
                                    # Crear arco
                                    arc = DB.Arc.Create(start, end, arc_mid)
                                    
                                    # Eliminar la ModelCurve antigua
                                    doc.Delete(model_curve.Id)
                                    
                                    # Crear nueva ModelCurve con el arco
                                    new_model_curve = DB.ModelCurve.Create(doc, arc, sketch_plane)
                                    
                                    if new_model_curve:
                                        arcs_created += 1
                                        print("    ✓ Línea convertida en arco (ID: {})".format(new_model_curve.Id))
                                        
                                        # Intentar activar el parámetro ahora
                                        try:
                                            # Refrescar el parámetro
                                            toposolid = doc.GetElement(toposolid_id)
                                            curved_edge_param = toposolid.get_Parameter(DB.BuiltInParameter.CURVED_EDGE_CONDITION)
                                            if curved_edge_param and not curved_edge_param.IsReadOnly:
                                                curved_edge_param.Set(1)
                                                print("  ✓ Curved Edge Condition activado!")
                                                success_count += 1
                                            else:
                                                print("  → Sketch modificado, pero el parámetro aún es de solo lectura")
                                                print("  → Puede ser necesario regenerar el toposólido")
                                                manual_count += 1
                                        except:
                                            print("  → Sketch modificado, pero no se pudo activar el parámetro automáticamente")
                                            manual_count += 1
                                    else:
                                        print("    ✗ No se pudo crear la nueva ModelCurve con arco")
                                        manual_count += 1
                                        
                                except Exception as arc_e:
                                    print("    ✗ Error convirtiendo línea en arco: {}".format(str(arc_e)))
                                    manual_count += 1
                        else:
                            print("  → No se encontraron líneas para convertir")
                            manual_count += 1
                        
                        edit_scope.Commit()
                        
                except Exception as sketch_e:
                    print("  ✗ Error modificando sketch: {}".format(str(sketch_e)))
                    manual_count += 1
                    
            else:
                # Si no es de solo lectura, cambiar directamente
                curved_edge_param.Set(1)
                print("  ✓ Curved Edge Condition activado exitosamente!")
                success_count += 1
                
    except Exception as e:
        print("  ✗ Error general: {}".format(str(e)))
        manual_count += 1

print("\n" + "=" * 70)
print("RESUMEN")
print("=" * 70)
print("✓ Activados automáticamente: {}".format(success_count))
print("⚠ Requieren edición manual: {}".format(manual_count))

if manual_count > 0:
    print("\n" + "=" * 70)
    print("INSTRUCCIONES PARA ACTIVACIÓN MANUAL")
    print("=" * 70)
    print("Para activar 'Curved Edge Condition' en los toposólidos restantes:")
    print()
    print("1. Selecciona el toposólido en Revit")
    print("2. En la cinta de opciones, haz clic en 'Edit Sketch' (Modificar Sketch)")
    print("3. Selecciona las líneas del perímetro que quieres hacer fluidas")
    print("4. En la cinta de opciones, busca la opción 'Convert Line to Arc'")
    print("   O crea arcos manualmente usando la herramienta 'Arc'")
    print("5. Una vez que tengas al menos un arco en el sketch:")
    print("   - Haz clic en 'Finish Sketch' (Finalizar Sketch)")
    print("   - El parámetro 'Curved Edge Condition' se activará automáticamente")
    print("   - Las líneas de contorno se verán fluidas")
    print()
    print("NOTA: No es necesario convertir todas las líneas en arcos.")
    print("      Con tener al menos una curva en el sketch, el parámetro se activará.")

print("\n" + "=" * 70)
