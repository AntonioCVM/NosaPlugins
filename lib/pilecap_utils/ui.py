# -*- coding: utf-8 -*-
"""
User Interface utilities for pilecap creation.
"""
from pyrevit import revit, forms
from Autodesk.Revit import DB
try:
    from nosa_utils.unit_conversion import feet_to_mm
    from . import data_retrieval
except ImportError:  # nosa-lint: disable=NOSA006 - optional at import time
    pass

def _doc():
    return revit.doc


def _uidoc():
    return revit.uidoc

def get_user_input(config_manager_instance=None):
    """
    Obtiene la configuracion del usuario.
    
    Args:
        config_manager_instance: Instancia opcional de ConfigManager para guardar/cargar defaults
        
    Returns:
        dict: Diccionario con la configuracion o None
    """
    try:
        # Seleccionar tipo de pilote
        pile_options, pile_dict = data_retrieval.get_pile_types()
        if not pile_options:
            forms.alert("No se encontraron tipos de pilotes en el modelo.", title="Error")
            return None
        
        # TODO: Implement last used selection if config_manager provided
        default_pile = pile_options[0] if pile_options else None
        
        pile_type_name = forms.ask_for_one_item(
            items=pile_options,
            default=default_pile,
            prompt="Selecciona el tipo de pilote:\n\nEl espaciado recomendado se calculara automaticamente.",
            title="Tipo de Pilote"
        )
        if not pile_type_name: return None
        
        pile_type_id = pile_dict.get(pile_type_name)
        if not pile_type_id: return None
        
        pile_family_symbol = _doc().GetElement(DB.ElementId(pile_type_id))
        if not pile_family_symbol: return None
        
        print("Obteniendo tamano del pilote...")
        pile_size_mm = data_retrieval.get_pile_size_from_symbol(pile_family_symbol)
        if pile_size_mm:
            print("Tamano del pilote obtenido: {:.0f}mm".format(pile_size_mm))
        else:
            print("ADVERTENCIA: No se pudo obtener el tamano. Espaciado no calculado.")
        
        # Grid input
        num_horizontal_str = forms.ask_for_one_item(
            items=[str(i) for i in range(1, 9)], default="2",
            prompt="Numero de pilotes en horizontal (X):", title="Configuracion de Pilotes"
        )
        if not num_horizontal_str: return None
        num_horizontal = int(num_horizontal_str)
        
        num_vertical_str = forms.ask_for_one_item(
            items=[str(i) for i in range(1, 9)], default="2",
            prompt="Numero de pilotes en vertical (Y):", title="Configuracion de Pilotes"
        )
        if not num_vertical_str: return None
        num_vertical = int(num_vertical_str)
        
        # Spacing logic
        spacing_options = []
        default_spacing = "2000"
        prompt_spacing = "Distancia entre pilotes (mm):"
        
        if pile_size_mm:
            min_spacing = int(pile_size_mm * 2.0)
            rec_spacing = int(pile_size_mm * 3.0)
            
            rec_spacing_str = str(rec_spacing)
            min_spacing_str = str(min_spacing)
            
            spacing_options = [rec_spacing_str, min_spacing_str]
            spacing_options.extend([str(int(pile_size_mm * x)) for x in [2.5, 3.5, 4.0]])
            spacing_options.extend(["1500", "2000", "2500", "3000", "3500", "4000", "4500", "5000"])
            
            # Unique ordered list with Reccomended first
            seen = set()
            final_options = []
            if rec_spacing_str not in seen:
                final_options.append(rec_spacing_str); seen.add(rec_spacing_str)
            for opt in spacing_options:
                if opt not in seen:
                    final_options.append(opt); seen.add(opt)
            spacing_options = final_options
            
            default_spacing = rec_spacing_str
            prompt_spacing = "Distancia entre pilotes (mm):\n\nRECOMENDADO (3D): {}mm\nMinimo (2D): {}mm".format(rec_spacing, min_spacing)
        else:
            spacing_options = ["2000", "1500", "2500", "3000", "3500", "4000"]
            
        pile_spacing_str = forms.ask_for_one_item(
            items=spacing_options, default=default_spacing,
            prompt=prompt_spacing, title="Espaciado"
        )
        if not pile_spacing_str: return None
        pile_spacing = float(pile_spacing_str)
        
        # Warning checks
        if pile_size_mm and pile_spacing < pile_size_mm * 1.5:
             if not forms.alert(
                "ADVERTENCIA: Espaciado ({:.0f}mm) menor a 2D ({:.0f}mm).\nContinuar?".format(pile_spacing, pile_size_mm*2),
                yes=True, no=True
            ): return None
            
        # Clearance
        clearance_options = []
        default_clearance = "500"
        
        if pile_size_mm:
            rec_clearance = max(250, int(pile_size_mm / 2.0))
            pile_radius = int(pile_size_mm / 2.0)
            start_clearance = max(pile_radius, 200)
            
            clearance_vals = sorted(list(set(
                [rec_clearance] + list(range(start_clearance, 751, 50))
            )))
            clearance_options = [str(c) for c in clearance_vals]
            
            # Ensure rec first
            if str(rec_clearance) in clearance_options:
                clearance_options.remove(str(rec_clearance))
            clearance_options.insert(0, str(rec_clearance))
            default_clearance = str(rec_clearance)
        else:
            clearance_options = [str(c) for c in range(200, 751, 50)]
            
        clearance_str = forms.ask_for_one_item(
            items=clearance_options, default=default_clearance,
            prompt="Clearance (mm):", title="Clearance"
        )
        if not clearance_str: return None
        clearance = float(clearance_str)
        
        # Cut-off
        cut_off_str = forms.ask_for_one_item(
            items=["50", "75", "100", "125", "150", "200", "250", "300"],
            default="75",
            prompt="Cut-off (Embebido en mm):", title="Cut-off"
        )
        if not cut_off_str: return None
        cut_off = float(cut_off_str)
        
        return {
            'num_horizontal': num_horizontal,
            'num_vertical': num_vertical,
            'pile_spacing': pile_spacing,
            'clearance': clearance,
            'cut_off': cut_off,
            'pile_type_name': pile_type_name,
            'pile_type_id': pile_type_id
        }
        
    except Exception as e:
        print("Error UI: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        return None

def get_level_for_placement():
    """Selecciona nivel."""
    try:
        levels = DB.FilteredElementCollector(_doc()).OfClass(DB.Level).ToElements()
        if not levels: return None
        
        levels_list = sorted(list(levels), key=lambda l: l.Elevation)
        level_options = []
        level_dict = {}
        
        for level in levels_list:
            display = "{} ({:.0f} mm)".format(level.Name, feet_to_mm(level.Elevation))
            level_options.append(display)
            level_dict[display] = level
            
        sel = forms.ask_for_one_item(
            items=level_options, default=level_options[0],
            prompt="Selecciona nivel:", title="Seleccion de Nivel"
        )
        return level_dict.get(sel)
    except Exception:
        return None

def get_user_location():
    """Selecciona punto."""
    try:
        return _uidoc().Selection.PickPoint("Selecciona el punto central del pilecap:")
    except Exception:
        return None

def show_preview(config):
    """Muestra preview."""
    try:
        msg = """
===========================================================
           PREVISUALIZACION DEL PILECAP
===========================================================

CONFIGURACION DE PILOTES:
   - Horizontal (X): {} pilotes
   - Vertical (Y): {} pilotes
   - Total: {} pilotes

DIMENSIONES:
   - Distancia entre pilotes: {:.0f} mm
   - Clearance: {:.0f} mm
   - Dimensiones losa: {:.0f} x {:.0f} mm
   - Espesor losa: {:.0f} mm

EMBEBIDO:
   - Cut-off: {:.0f} mm

TIPO DE PILOTE:
   - {}

===========================================================
""".format(
            config['num_horizontal'], config['num_vertical'],
            config['num_horizontal'] * config['num_vertical'],
            config['pile_spacing'], config['clearance'],
            config['width'], config['length'],
            config['thickness'], config['cut_off'],
            config.get('pile_type_name', 'N/A')
        )
        return forms.alert(msg, title="Previsualizacion", yes=True, no=True)
    except Exception:
        return forms.alert("Continuar?", title="Confirmar", yes=True, no=True)

def show_rotation_instructions():
    """Instrucciones rotacion."""
    msg = """
INSTRUCCIONES PARA ROTAR:

1. Selecciona TODOS los elementos (losa + pilotes)
2. Usa 'Rotate' (R)
3. Selecciona centro
4. Rota

Nota: Elementos independientes permiten rotacion libre.
Si necesitas agrupar despues, crea el grupo manualmente.
"""
    forms.alert(msg, title="Tip de Rotacion", ok=True)
