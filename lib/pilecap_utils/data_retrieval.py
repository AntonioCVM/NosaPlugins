# -*- coding: utf-8 -*-
"""
Data retrieval utilities for pilecap creation in Revit.
"""
from pyrevit import revit
from Autodesk.Revit import DB
import sys
from nosa_utils.telemetry import log_swallowed
_LOG = u'pilecap_utils.data_retrieval'

# Constants
OST_STRUCTURAL_FOUNDATION = -2001300

# Helper to import from parent lib if needed (assuming nosa_utils is in path)
# NOSA utils are expected to be in sys.path
try:
    from nosa_utils.revit_helpers import get_id_value, element_name
    from nosa_utils.unit_conversion import feet_to_mm
except ImportError:
    def element_name(element):
        return getattr(element, 'Name', None) or u''

    def feet_to_mm(val):
        return val * 304.8

    def get_id_value(element_id):
        if hasattr(element_id, 'Value'):
            return element_id.Value
        return int(str(element_id))


def get_element_id_int(element_id):
    return get_id_value(element_id)

def _doc():
    return revit.doc

def get_slab_thickness(slab_type):
    """
    Obtiene el espesor de un tipo de Foundation Slab en milimetros.
    
    Args:
        slab_type: El tipo de Foundation Slab (FloorType)
        
    Returns:
        float: Espesor en milimetros, o None si no se puede obtener
    """
    try:
        # Metodo 1: Buscar Foundation Thickness (BuiltInParameter)
        try:
            thickness_param = slab_type.get_Parameter(DB.BuiltInParameter.FOUNDATION_THICKNESS)
            if thickness_param and thickness_param.HasValue:
                return feet_to_mm(thickness_param.AsDouble())
        except Exception:
            log_swallowed(_LOG, u'get_slab_thickness')
        
        # Metodo 2: Buscar por nombre o ID
        for param in slab_type.Parameters:
            try:
                param_name = param.Definition.Name
                param_id = get_id_value(param.Id)
                if (param_name == "Foundation Thickness" or param_id == -1001557):
                    if param.HasValue:
                        return feet_to_mm(param.AsDouble())
            except Exception:
                continue
        
        # Metodo 3: Default Thickness como fallback
        try:
            default_thickness_param = slab_type.get_Parameter(DB.BuiltInParameter.DEFAULT_THICKNESS)
            if default_thickness_param and default_thickness_param.HasValue:
                return feet_to_mm(default_thickness_param.AsDouble())
        except Exception:
            log_swallowed(_LOG, u'get_slab_thickness')
            
    except Exception as e:
        print("Advertencia: No se pudo obtener el espesor del tipo de losa: {}".format(str(e)))
    
    return None

def get_foundation_slab_types():
    """
    Obtiene todos los tipos de Foundation Slab disponibles en el modelo.
    Busca de multiples formas para asegurar que encuentra los tipos.
    
    Returns:
        tuple: (lista_de_opciones, diccionario_nombre_tipo)
    """
    slab_types = []
    slab_dict = {}
    
    try:
        # Metodo 1: Buscar FloorType con categoria OST_StructuralFoundation
        collector = DB.FilteredElementCollector(_doc()).OfClass(DB.FloorType)
        
        for floor_type in collector:
            try:
                if floor_type.Category:
                    category_id = get_id_value(floor_type.Category.Id)
                    if category_id == OST_STRUCTURAL_FOUNDATION:
                        # Obtener nombre del tipo usando parametro BuiltInParameter
                        type_name = 'Unknown'
                        try:
                            type_name_param = floor_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
                            if type_name_param and type_name_param.HasValue:
                                type_name = type_name_param.AsString()
                            else:
                                type_name = element_name(floor_type) or type_name
                        except Exception:
                            log_swallowed(_LOG, u'get_foundation_slab_types')
                        
                        family_name = 'Unknown'
                        try:
                            if floor_type.Family:
                                family_name = floor_type.Family.Name
                        except Exception:
                            log_swallowed(_LOG, u'get_foundation_slab_types')
                        
                        # Excluir "Pile Cap" y buscar solo Foundation Slabs
                        if "pile cap" not in type_name.lower() and "pile cap" not in family_name.lower():
                            if type_name and type_name != 'Unknown':
                                display_name = type_name
                            elif family_name and family_name != 'Unknown':
                                display_name = family_name
                            else:
                                continue
                            
                            if display_name not in slab_dict:
                                slab_types.append(display_name)
                                slab_dict[display_name] = floor_type
            except Exception as e:
                continue
        
        # Metodo 2: Buscar todos los FloorType y filtrar por nombre si no se encontro nada
        if not slab_types:
            collector_all = DB.FilteredElementCollector(_doc()).OfClass(DB.FloorType)
            for floor_type in collector_all:
                try:
                    type_name = 'Unknown'
                    try:
                        type_name_param = floor_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
                        if type_name_param and type_name_param.HasValue:
                            type_name = type_name_param.AsString()
                        else:
                            type_name = element_name(floor_type) or type_name
                    except Exception:
                        log_swallowed(_LOG, u'get_foundation_slab_types')
                    
                    family_name = 'Unknown'
                    try:
                        if floor_type.Family:
                            family_name = floor_type.Family.Name
                    except Exception:
                        log_swallowed(_LOG, u'get_foundation_slab_types')
                    
                    type_name_lower = type_name.lower()
                    family_name_lower = family_name.lower()
                    
                    keywords = ['slab', 'losa', 'foundation', 'cimentacion', 'zapata']
                    has_keyword = any(kw in type_name_lower or kw in family_name_lower for kw in keywords)
                    has_mm_dimension = 'mm' in type_name_lower and any(c.isdigit() for c in type_name)
                    
                    if (has_keyword or has_mm_dimension) and 'pile cap' not in type_name_lower:
                        display_name = type_name if type_name != 'Unknown' else family_name
                        if display_name == 'Unknown':
                            continue
                        
                        if display_name not in slab_dict:
                            slab_types.append(display_name)
                            slab_dict[display_name] = floor_type
                except Exception:
                    continue
        
        # Ordenar
        def sort_key(name):
            try:
                import re
                numbers = re.findall(r'\d+', name)
                return int(numbers[0]) if numbers else 0
            except Exception:
                return 0
        
        slab_types.sort(key=sort_key)
        
    except Exception as e:
        print("Error al obtener tipos de Foundation Slab: {}".format(str(e)))
        import traceback
        traceback.print_exc()
    
    return slab_types, slab_dict

def get_pile_types():
    """
    Obtiene todos los TIPOS (FamilySymbol) de pilotes disponibles.
    
    Returns:
        tuple: (lista_de_opciones, diccionario_nombre_id)
    """
    pile_options = []
    pile_dict = {}
    
    try:
        collector = DB.FilteredElementCollector(_doc()).OfClass(DB.FamilySymbol)
        
        for symbol in collector:
            try:
                if not symbol.Family or not symbol.Family.FamilyCategory:
                    continue
                
                category_id = get_id_value(symbol.Family.FamilyCategory.Id)
                if category_id == OST_STRUCTURAL_FOUNDATION:
                    family_name = getattr(symbol.Family, 'Name', 'Unknown')
                    
                    symbol_name = 'Unknown'
                    try:
                        type_name_param = symbol.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
                        if type_name_param and type_name_param.HasValue:
                            symbol_name = type_name_param.AsString()
                        else:
                            symbol_name_param = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                            if symbol_name_param and symbol_name_param.HasValue:
                                symbol_name = symbol_name_param.AsString()
                            else:
                                symbol_name = element_name(symbol) or symbol_name
                    except Exception:
                        log_swallowed(_LOG, u'get_pile_types')
                    
                    if 'pile cap' in family_name.lower() or 'pile cap' in symbol_name.lower():
                        continue
                    
                    if symbol_name == 'Unknown' or family_name == 'Unknown':
                        continue
                    
                    display_name = "{} - {}".format(family_name, symbol_name)
                    
                    try:
                        if not symbol.IsActive:
                            symbol.Activate()
                    except Exception:
                        log_swallowed(_LOG, u'get_pile_types')
                    
                    pile_options.append(display_name)
                    pile_dict[display_name] = get_id_value(symbol.Id)
            except Exception:
                continue
        
        def sort_key(name):
            try:
                priority = 999
                name_lower = name.lower()
                if 'pile square' in name_lower or 'square piling' in name_lower: priority = 1
                elif 'pile-steel pipe' in name_lower or 'steel pipe' in name_lower: priority = 2
                elif 'square' in name_lower or 'cuadrado' in name_lower: priority = 3
                elif 'pipe' in name_lower or 'round' in name_lower: priority = 4
                
                import re
                numbers = re.findall(r'\d+', name)
                size = int(numbers[0]) if numbers else 0
                return (priority, size)
            except Exception:
                return (999, 0)
        
        pile_options.sort(key=sort_key)
        
    except Exception as e:
        print("Error al obtener tipos de pilotes: {}".format(str(e)))
        import traceback
        traceback.print_exc()
    
    return pile_options, pile_dict

def get_pile_size_from_symbol(pile_family_symbol):
    """Obtiene el tamano del pilote (diametro o lado) en mm."""
    try:
        # Width
        for param in pile_family_symbol.Parameters:
            param_name = param.Definition.Name.lower()
            if param_name == 'width' and param.HasValue:
                param_value = param.AsDouble()
                if 50 < param_value < 10000: return param_value
                else: return feet_to_mm(param_value)
        
        # Diameter
        for param in pile_family_symbol.Parameters:
            param_name = param.Definition.Name.lower()
            if ('diameter' in param_name or 'diametro' in param_name or param_name == 'd') and param.HasValue:
                param_value = param.AsDouble()
                if 50 < param_value < 10000: return param_value
                else: return feet_to_mm(param_value)
        
        # BuiltInParameter Width
        width_param = pile_family_symbol.get_Parameter(DB.BuiltInParameter.FAMILY_WIDTH_PARAM)
        if width_param and width_param.HasValue:
            return feet_to_mm(width_param.AsDouble())
            
        # BuiltInParameter Depth
        depth_param = pile_family_symbol.get_Parameter(DB.BuiltInParameter.FAMILY_DEPTH_PARAM)
        if depth_param and depth_param.HasValue:
            return feet_to_mm(depth_param.AsDouble())
            
    except Exception as e:
        print("ERROR al obtener tamano del pilote: {}".format(str(e)))
    return None

def get_pile_height(pile_family_symbol):
    """Obtiene la altura de un pilote desde su FamilySymbol en pies."""
    try:
        height_param = pile_family_symbol.get_Parameter(DB.BuiltInParameter.FAMILY_HEIGHT_PARAM)
        if height_param and height_param.HasValue:
            return height_param.AsDouble()
        
        for param in pile_family_symbol.Parameters:
            param_name = param.Definition.Name.lower()
            if any(kw in param_name for kw in ['height', 'altura', 'length', 'longitud', 'profundidad', 'depth']):
                if param.HasValue:
                    return param.AsDouble()
    except Exception:
        log_swallowed(_LOG, u'get_pile_height')
    return None

def get_pile_min_embedment(pile_family_symbol):
    """
    Obtiene el valor del parametro 'Minimum Embedment' si existe.
    Retorna 0.0 si no se encuentra.
    """
    try:
        # Buscar por nombre exacto o variaciones
        for param in pile_family_symbol.Parameters:
            name = param.Definition.Name.lower()
            if 'minimum embedment' in name or 'embebido minimo' in name:
                if param.HasValue and param.StorageType == DB.StorageType.Double:
                    return feet_to_mm(param.AsDouble())
    except Exception:
        log_swallowed(_LOG, u'get_pile_min_embedment')
    return 0.0
