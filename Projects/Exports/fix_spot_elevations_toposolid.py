# -*- coding: utf-8 -*-
"""Script para recrear spot elevations referenciados a la cara superior del toposolido"""
from pyrevit import revit, DB

# Obtener el documento activo
doc = revit.doc
uidoc = revit.uidoc

# ID de la vista activa (WORKING VIEW) - puede cambiar, usar vista activa si está disponible
try:
    active_view = doc.ActiveView
    if active_view:
        view_id = active_view.Id
    else:
        view_id = DB.ElementId(356051)  # Fallback a WORKING VIEW
except:
    view_id = DB.ElementId(356051)  # Fallback a WORKING VIEW

# IDs de los toposolidos
toposolid_ids = [DB.ElementId(652547), DB.ElementId(652559), DB.ElementId(652569)]

# Buscar todos los spot elevations en la vista activa
view = doc.GetElement(view_id)
spot_elevations = []

if view:
    # Obtener todos los elementos de la categoría Spot Elevations en la vista
    collector = DB.FilteredElementCollector(doc, view.Id)
    spot_elevations = collector.OfCategory(DB.BuiltInCategory.OST_SpotElevations).ToElements()

if spot_elevations and len(spot_elevations) > 0:
    print("Se encontraron {} spot elevation(s) en la vista.".format(len(spot_elevations)))
    
    for spot_elevation in spot_elevations:
        # Obtener la posición del spot elevation
        location = spot_elevation.Location
        if isinstance(location, DB.LocationPoint):
            point = location.Point
            
            # Obtener la vista
            view = doc.GetElement(view_id)
            
            if view:
                # Buscar el toposolido más cercano al punto del spot elevation
                closest_toposolid = None
                min_distance = float('inf')
                
                for toposolid_id in toposolid_ids:
                    toposolid = doc.GetElement(toposolid_id)
                    if toposolid:
                        # Obtener la geometría del toposolido
                        geom_options = DB.Options()
                        geom_options.View = view
                        geom_options.ComputeReferences = True
                        
                        try:
                            geometry = toposolid.get_Geometry(geom_options)
                            
                            # Buscar la cara superior más cercana
                            for geom_obj in geometry:
                                if isinstance(geom_obj, DB.Solid):
                                    # Obtener las caras del sólido
                                    for face in geom_obj.Faces:
                                        # Verificar si es una cara superior (normal apuntando hacia arriba)
                                        face_normal = face.ComputeNormal(DB.UV(0.5, 0.5))
                                        if face_normal.Z > 0.5:  # Cara superior
                                            # Obtener un punto en la cara
                                            face_center = face.Evaluate(DB.UV(0.5, 0.5))
                                            
                                            # Calcular distancia
                                            distance = point.DistanceTo(face_center)
                                            if distance < min_distance:
                                                min_distance = distance
                                                closest_toposolid = toposolid
                        except:
                            pass
                
                if closest_toposolid:
                    print("Toposolido más cercano encontrado: {} para spot elevation {}".format(closest_toposolid.Id, spot_elevation.Id))
                    
                    # Verificar y actualizar el parámetro Display Elevations
                    try:
                        param = spot_elevation.LookupParameter("Display Elevations")
                        if param:
                            # 1 = Top Elevation
                            if param.AsInteger() != 1:
                                with revit.Transaction("Update Spot Elevation to Top Elevation"):
                                    param.Set(1)
                                print("  - Parámetro 'Display Elevations' actualizado a 'Top Elevation'")
                            else:
                                print("  - El spot elevation ya está configurado como 'Top Elevation'")
                        else:
                            print("  - No se pudo encontrar el parámetro 'Display Elevations'")
                    except Exception as e:
                        print("  - Error actualizando parámetro: {}".format(str(e)))
                else:
                    print("  - No se encontró un toposolido cercano al spot elevation {}.".format(spot_elevation.Id))
            else:
                print("  - No se encontró la vista para el spot elevation {}.".format(spot_elevation.Id))
        else:
            print("  - El spot elevation {} no tiene una ubicación de punto.".format(spot_elevation.Id))
else:
    print("No se encontraron spot elevations en la vista activa.")

print("\nProceso completado.")
print("\nNota: Si los spot elevations aún no muestran valores positivos,")
print("puede ser necesario recrearlos manualmente en Revit:")
print("1. Selecciona la herramienta Spot Elevation")
print("2. En las opciones, asegúrate de que 'Display Elevations' esté en 'Top Elevation'")
print("3. Selecciona la cara superior del toposolido (la que está por encima de 0)")
print("4. Coloca el spot elevation")

