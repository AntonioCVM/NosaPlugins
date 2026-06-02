"""
Script para convertir Generic Models de tipo Shaft a Shaft Openings
Mantiene las mismas posiciones y dimensiones

INSTRUCCIONES DE USO:
1. Abre tu modelo de Revit con los elementos Shaft
2. Ejecuta este script desde pyRevit
3. El script identificará los 7 elementos Shaft y mostrará sus propiedades
4. Confirma la conversión cuando se te solicite
5. El script creará los Shaft Openings y eliminará los Shaft originales

NOTA: Este script requiere que los elementos Shaft tengan los parámetros:
- Base Level
- Top Level  
- Base Offset
- Top Offset
- Shaft Dimension A
- Shaft Dimension B
"""

from pyrevit import revit, DB
from pyrevit import forms
from pyrevit import script

# Obtener el documento activo
doc = revit.doc
uidoc = revit.uidoc

def get_id_value(element_id):
    """Get integer value from ElementId - compatible with Revit 2024+."""
    if hasattr(element_id, "Value"):
        return element_id.Value
    elif hasattr(element_id, "IntegerValue"):
        return element_id.IntegerValue
    else:
        return int(str(element_id))

# IDs de los elementos Shaft a convertir
SHAFT_IDS = [3114514, 3114541, 3118018, 3119021, 3119022, 3119837, 3119951]

def get_shaft_data(shaft_element):
    """Obtiene todos los datos necesarios de un elemento Shaft"""
    # Obtener parámetros
    base_level_param = shaft_element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM)
    top_level_param = shaft_element.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
    base_offset_param = shaft_element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET)
    top_offset_param = shaft_element.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET)
    
    # Obtener dimensiones (parámetros específicos de la familia)
    dim_a_param = None
    dim_b_param = None
    
    for param in shaft_element.Parameters:
        if param.Definition.Name == "Shaft Dimension A":
            dim_a_param = param
        elif param.Definition.Name == "Shaft Dimension B":
            dim_b_param = param
    
    # Obtener ubicación
    location = shaft_element.Location
    location_point = None
    if isinstance(location, DB.LocationPoint):
        location_point = location.Point
    
    # Convertir unidades
    def mm_to_feet(mm_value):
        return mm_value / 304.8
    
    return {
        'element': shaft_element,
        'base_level_id': base_level_param.AsElementId(),
        'top_level_id': top_level_param.AsElementId(),
        'base_offset': mm_to_feet(base_offset_param.AsDouble()),
        'top_offset': mm_to_feet(top_offset_param.AsDouble()),
        'dimension_a': mm_to_feet(dim_a_param.AsDouble()) if dim_a_param else 0,
        'dimension_b': mm_to_feet(dim_b_param.AsDouble()) if dim_b_param else 0,
        'location_point': location_point
    }

def create_shaft_opening(shaft_data):
    """Crea un Shaft Opening basado en los datos del Shaft"""
    try:
        # Obtener niveles
        base_level = doc.GetElement(shaft_data['base_level_id'])
        top_level = doc.GetElement(shaft_data['top_level_id'])
        
        if not base_level or not top_level:
            print("Error: No se pudieron obtener los niveles")
            return None
        
        # Obtener la vista de planta del nivel base para el sketch plane
        view_plan = None
        collector = DB.FilteredElementCollector(doc)
        views = collector.OfClass(DB.ViewPlan).ToElements()
        
        for view in views:
            if view.GenLevel and view.GenLevel.Id == base_level.Id:
                view_plan = view
                break
        
        if not view_plan:
            print("Error: No se encontró una vista de planta para el nivel base")
            return None
        
        # Calcular las coordenadas del rectángulo
        location = shaft_data['location_point']
        dim_a = shaft_data['dimension_a']
        dim_b = shaft_data['dimension_b']
        
        # Obtener la elevación del nivel base con el offset
        base_elevation = base_level.Elevation + shaft_data['base_offset']
        
        # Crear el rectángulo centrado en el punto de ubicación
        half_a = dim_a / 2.0
        half_b = dim_b / 2.0
        
        # Crear los puntos del rectángulo en la elevación del nivel base
        p1 = DB.XYZ(location.X - half_a, location.Y - half_b, base_elevation)
        p2 = DB.XYZ(location.X + half_a, location.Y - half_b, base_elevation)
        p3 = DB.XYZ(location.X + half_a, location.Y + half_b, base_elevation)
        p4 = DB.XYZ(location.X - half_a, location.Y + half_b, base_elevation)
        
        # Crear las curvas del rectángulo
        line1 = DB.Line.CreateBound(p1, p2)
        line2 = DB.Line.CreateBound(p2, p3)
        line3 = DB.Line.CreateBound(p3, p4)
        line4 = DB.Line.CreateBound(p4, p1)
        
        # Crear el Shaft Opening usando Transaction
        with revit.Transaction("Create Shaft Opening"):
            # Crear el SketchPlane en el nivel base
            # El SketchPlane se crea usando el plano del nivel
            normal = DB.XYZ.BasisZ
            origin = DB.XYZ(location.X, location.Y, base_elevation)
            plane = DB.Plane.CreateByNormalAndOrigin(normal, origin)
            sketch_plane = DB.SketchPlane.Create(doc, plane)
            
            # Crear el CurveArray con las curvas del boundary
            curve_array = DB.CurveArray()
            curve_array.Append(line1)
            curve_array.Append(line2)
            curve_array.Append(line3)
            curve_array.Append(line4)
            
            # Crear el Opening usando el método correcto de la API
            # Opening.Create requiere: document, levelId (base), levelId (top), curveArray
            opening = None
            try:
                opening = DB.Opening.Create(doc, base_level.Id, top_level.Id, curve_array)
            except Exception as create_error:
                print("  Error al crear Opening: {}".format(str(create_error)))
                # El método Opening.Create puede variar según la versión de Revit
                # Si falla, puede ser necesario usar un enfoque diferente
                raise
            
            if opening:
                # Establecer offsets usando los parámetros correctos de Opening
                # Los parámetros de Opening son diferentes a los de FamilyInstance
                # Base Offset (BuiltInParameter -1001108)
                base_offset_param = opening.get_Parameter(DB.BuiltInParameter.LEVEL_OFFSET)
                if not base_offset_param:
                    # Intentar con el ID directo si el BuiltInParameter no funciona
                    for param in opening.Parameters:
                        if get_id_value(param.Id) == -1001108 or param.Definition.Name == "Base Offset":
                            base_offset_param = param
                            break
                
                if base_offset_param and not base_offset_param.IsReadOnly:
                    base_offset_param.Set(shaft_data['base_offset'])
                
                # Top Offset (BuiltInParameter -1001109)
                top_offset_param = None
                for param in opening.Parameters:
                    if get_id_value(param.Id) == -1001109 or param.Definition.Name == "Top Offset":
                        top_offset_param = param
                        break
                
                if top_offset_param and not top_offset_param.IsReadOnly:
                    top_offset_param.Set(shaft_data['top_offset'])
                
                print("  ✓ Shaft Opening creado con ID: {}".format(opening.Id))
                return opening
            else:
                print("  ✗ No se pudo crear el Opening")
                return None
        
    except Exception as e:
        print("Error al crear Shaft Opening: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        return None

def main():
    """Función principal"""
    # Obtener los elementos Shaft
    shaft_elements = []
    for shaft_id in SHAFT_IDS:
        element = doc.GetElement(DB.ElementId(shaft_id))
        if element:
            shaft_elements.append(element)
        else:
            print("Advertencia: No se encontró el elemento con ID {}".format(shaft_id))
    
    if not shaft_elements:
        forms.alert("No se encontraron elementos Shaft para convertir", title="Error")
        return
    
    print("Encontrados {} elementos Shaft".format(len(shaft_elements)))
    
    # Recopilar datos de todos los Shaft
    shaft_data_list = []
    for shaft in shaft_elements:
        data = get_shaft_data(shaft)
        shaft_data_list.append(data)
        print("\nShaft ID: {}".format(shaft.Id))
        print("  Dimension A: {:.2f} ft".format(data['dimension_a']))
        print("  Dimension B: {:.2f} ft".format(data['dimension_b']))
        print("  Base Level: {}".format(doc.GetElement(data['base_level_id']).Name))
        print("  Top Level: {}".format(doc.GetElement(data['top_level_id']).Name))
        print("  Base Offset: {:.2f} ft".format(data['base_offset']))
        print("  Top Offset: {:.2f} ft".format(data['top_offset']))
        print("  Location: ({:.2f}, {:.2f}, {:.2f})".format(
            data['location_point'].X, 
            data['location_point'].Y, 
            data['location_point'].Z))
    
    # Confirmar con el usuario
    if not forms.alert("¿Desea convertir estos {} elementos Shaft a Shaft Openings?\n\n"
                      "Los elementos Shaft originales serán eliminados después de crear los Shaft Openings.".format(
                      len(shaft_data_list)), 
                      title="Confirmar conversión", 
                      ok=False, 
                      yes=True, 
                      no=True):
        return
    
    # Crear los Shaft Openings
    created_openings = []
    failed_elements = []
    
    with revit.TransactionGroup("Convert Shaft to Shaft Opening"):
        for i, shaft_data in enumerate(shaft_data_list):
            print("\nProcesando Shaft {} de {}...".format(i+1, len(shaft_data_list)))
            
            # Crear el Shaft Opening
            opening = create_shaft_opening(shaft_data)
            
            if opening:
                created_openings.append(opening)
                # Eliminar el Shaft original
                try:
                    doc.Delete(shaft_data['element'].Id)
                    print("  ✓ Shaft Opening creado y Shaft eliminado")
                except Exception as e:
                    print("  ✗ Error al eliminar Shaft: {}".format(str(e)))
                    failed_elements.append(shaft_data['element'].Id)
            else:
                print("  ✗ No se pudo crear el Shaft Opening")
                failed_elements.append(shaft_data['element'].Id)
    
    # Mostrar resumen
    print("\n" + "="*50)
    print("RESUMEN")
    print("="*50)
    print("Shaft Openings creados: {}".format(len(created_openings)))
    print("Elementos fallidos: {}".format(len(failed_elements)))
    
    if failed_elements:
        print("\nIDs de elementos que fallaron:")
        for elem_id in failed_elements:
            print("  - {}".format(elem_id))

if __name__ == "__main__":
    main()

