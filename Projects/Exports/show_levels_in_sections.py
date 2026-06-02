# -*- coding: utf-8 -*-
"""Script para hacer visible la categoría de niveles en todas las secciones B-1 a B-37"""
from pyrevit import revit, DB

# Obtener el documento activo
doc = revit.doc

# ID de la categoría de niveles
levels_category_id = DB.ElementId(DB.BuiltInCategory.OST_Levels)

# IDs de las secciones B-1 a B-37
section_ids = [
    676451,  # Section B-1
    773078,  # Section B-2
    773088,  # Section B-3
    773097,  # Section B-4
    773106,  # Section B-5
    773115,  # Section B-6
    773124,  # Section B-7
    773133,  # Section B-8
    773142,  # Section B-9
    773151,  # Section B-10
    773160,  # Section B-11
    773169,  # Section B-12
    773178,  # Section B-13
    773187,  # Section B-14
    773196,  # Section B-15
    773205,  # Section B-16
    773214,  # Section B-17
    773223,  # Section B-18
    773232,  # Section B-19
    773241,  # Section B-20
    773250,  # Section B-21
    773258,  # Section B-22
    773267,  # Section B-23
    773276,  # Section B-24
    773285,  # Section B-25
    773294,  # Section B-26
    773303,  # Section B-27
    773312,  # Section B-28
    773321,  # Section B-29
    773330,  # Section B-30
    773339,  # Section B-31
    773348,  # Section B-32
    773357,  # Section B-33
    773366,  # Section B-34
    773375,  # Section B-35
    773384,  # Section B-36
    773394,  # Section B-37
]

# Iniciar transacción
with revit.Transaction("Show Levels in Sections"):
    processed = 0
    errors = 0
    
    for section_id in section_ids:
        try:
            # Obtener la vista
            view = doc.GetElement(DB.ElementId(section_id))
            
            if view and isinstance(view, DB.ViewSection):
                # Hacer visible la categoría de niveles
                view.SetCategoryHidden(levels_category_id, False)
                processed += 1
                print("Niveles habilitados en: {}".format(view.Name))
            else:
                print("Advertencia: No se encontró la vista con ID: {} o no es una ViewSection".format(section_id))
                errors += 1
        except Exception as e:
            print("Error procesando sección {}: {}".format(section_id, str(e)))
            errors += 1

print("\nProceso completado. Procesadas: {}, Errores: {}".format(processed, errors))

