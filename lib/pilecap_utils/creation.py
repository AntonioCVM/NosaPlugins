# -*- coding: utf-8 -*-
"""
Creation utilities for pilecaps and piles.
"""
from pyrevit import revit
from Autodesk.Revit import DB
from System.Collections.Generic import List
from Autodesk.Revit.DB import JoinGeometryUtils
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'pilecap_utils.creation'

try:
    from nosa_utils.unit_conversion import mm_to_feet, feet_to_mm
    from . import validation, geometry, data_retrieval
except ImportError:
    # Fallback/Mock just for linting, runtime assumes sys.path is correct
    pass

def _doc():
    return revit.doc


def _uidoc():
    return revit.uidoc

DEFAULT_PILE_HEIGHT_MM = 6000

def create_foundation_slab(width_mm, length_mm, level, center_point, slab_type):
    """Crea una losa de cimentacion rectangular."""
    try:
        if not slab_type: raise ValueError("El tipo de Foundation Slab es None")
        if width_mm <= 0 or length_mm <= 0: raise ValueError("Las dimensiones deben ser mayores que 0")
        
        half_width_ft = mm_to_feet(width_mm / 2.0)
        half_length_ft = mm_to_feet(length_mm / 2.0)
        slab_z = level.Elevation
        
        corner1 = DB.XYZ(center_point.X - half_width_ft, center_point.Y - half_length_ft, slab_z)
        corner2 = DB.XYZ(center_point.X + half_width_ft, center_point.Y - half_length_ft, slab_z)
        corner3 = DB.XYZ(center_point.X + half_width_ft, center_point.Y + half_length_ft, slab_z)
        corner4 = DB.XYZ(center_point.X - half_width_ft, center_point.Y + half_length_ft, slab_z)
        
        curve_loop = DB.CurveLoop()
        curve_loop.Append(DB.Line.CreateBound(corner1, corner2))
        curve_loop.Append(DB.Line.CreateBound(corner2, corner3))
        curve_loop.Append(DB.Line.CreateBound(corner3, corner4))
        curve_loop.Append(DB.Line.CreateBound(corner4, corner1))
        
        curve_loops = List[DB.CurveLoop]()
        curve_loops.Add(curve_loop)
        
        foundation_slab = DB.Floor.Create(_doc(), curve_loops, slab_type.Id, level.Id)
        
        if not foundation_slab: raise Exception("Floor.Create retorno None")
        
        actual_thickness = data_retrieval.get_slab_thickness(slab_type)
        print("[OK] Losa de cimentacion creada: {:.0f}x{:.0f}x{} mm".format(
            width_mm, length_mm, actual_thickness if actual_thickness else "N/A"
        ))
        return foundation_slab
        
    except Exception as e:
        print("Error al crear losa de cimentacion: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        return None

def create_piles_array(center_point, num_horizontal, num_vertical, pile_spacing_mm, 
                       pile_family_symbol, level, cut_off_mm, slab_thickness_mm, width_mm, length_mm,
                       slab_additional_offset_ft=0.0):
    """Crea array de pilotes con cut-off correcto y ajustes dinamicos."""
    piles = []
    try:
        is_valid, warning = validation.validate_cutoff(cut_off_mm, slab_thickness_mm)
        if not is_valid:
            print("ERROR: {}".format(warning))
            return []
        elif warning:
            print("ADVERTENCIA: {}".format(warning))
        
        pile_spacing_ft = mm_to_feet(pile_spacing_mm)
        cut_off_ft = mm_to_feet(cut_off_mm)
        level_elevation = level.Elevation
        slab_thickness_ft = mm_to_feet(slab_thickness_mm)
        
        pile_height_ft = data_retrieval.get_pile_height(pile_family_symbol)
        if not pile_height_ft or pile_height_ft <= 0:
            pile_height_ft = mm_to_feet(DEFAULT_PILE_HEIGHT_MM)
            print("Advertencia: Usando altura por defecto {}mm".format(DEFAULT_PILE_HEIGHT_MM))
            
        start_x = center_point.X - (num_horizontal - 1) * pile_spacing_ft / 2.0
        start_y = center_point.Y - (num_vertical - 1) * pile_spacing_ft / 2.0
        
        # 1. Obtener correccion por parametro "Minimum Embedment" de la familia
        min_embedment_corr_mm = data_retrieval.get_pile_min_embedment(pile_family_symbol)
        correction_ft = mm_to_feet(min_embedment_corr_mm)
        if min_embedment_corr_mm > 0.001:
            print("Correccion por family embedment: {:.0f}mm".format(min_embedment_corr_mm))
        
        # 2. Formula maestra para Height Offset From Level
        # - Espesor Losa (bajar desde top losa)
        # + Cutoff (subir para embeber)
        # - Family Correction (bajar si la familia tiene offset interno)
        # + Slab Offset (subir si la losa esta desplazada del nivel)
        height_offset_from_level = -slab_thickness_ft + cut_off_ft - correction_ft + slab_additional_offset_ft
        
        print("Calculo de Offset Pilote:")
        print("  Base: -{:.0f} (Espesor) + {:.0f} (Cutoff)".format(slab_thickness_mm, cut_off_mm))
        print("  Ajustes: -{:.0f} (Family Min Embed) + {:.0f} (Slab Offset)".format(
            min_embedment_corr_mm, feet_to_mm(slab_additional_offset_ft)
        ))
        
        for i in range(num_horizontal):
            for j in range(num_vertical):
                x = start_x + i * pile_spacing_ft
                y = start_y + j * pile_spacing_ft
                
                try:
                    pile_location = DB.XYZ(x, y, level_elevation)
                    pile = _doc().Create.NewFamilyInstance(
                        pile_location, pile_family_symbol, level, DB.Structure.StructuralType.Footing
                    )
                    
                    if pile:
                        offset_set = False
                        for param in pile.Parameters:
                            p_name = param.Definition.Name.lower()
                            if 'height offset' in p_name and 'level' in p_name:
                                if not param.IsReadOnly and param.StorageType == DB.StorageType.Double:
                                    param.Set(height_offset_from_level)
                                    offset_set = True
                                    break
                        piles.append(pile)
                except Exception as e:
                    print("Error al crear pilote ({}, {}): {}".format(i, j, str(e)))
        
        print("[OK] Creados {} pilotes con cut-off: {:.0f} mm".format(len(piles), cut_off_mm))
        
    except Exception as e:
        print("Error al crear pilotes: {}".format(str(e)))
        import traceback
        traceback.print_exc()
    
    return piles

def create_pilecap_elements(num_horizontal, num_vertical, pile_spacing, 
                            clearance, cut_off, thickness, width, length, 
                            slab_type, pile_family_symbol, level, center_point):
    """Crea los elementos (losa y pilotes) en una transaccion."""
    t = None
    try:
        t = nosa_tx.guard(DB.Transaction(_doc(), u"NOSA — Create Pilecap Elements"))
        t.Start()
        
        foundation_slab = create_foundation_slab(width, length, level, center_point, slab_type)
        if not foundation_slab:
            t.RollBack()
            return None, []
        
        # Detectar offset real de la losa creada
        slab_offset = 0.0
        try:
            offset_param = foundation_slab.get_Parameter(DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if offset_param and offset_param.HasValue:
                slab_offset = offset_param.AsDouble()
        except Exception:
            log_swallowed(_LOG, u'create_pilecap_elements')

        piles = create_piles_array(
            center_point, num_horizontal, num_vertical, pile_spacing,
            pile_family_symbol, level, cut_off, thickness, width, length,
            slab_additional_offset_ft=slab_offset
        )
        
        if not piles:
            t.RollBack()
            return None, []
        
        # Desunir
        slab_element = _doc().GetElement(foundation_slab.Id)
        if slab_element:
            for pile in piles:
                try:
                    if JoinGeometryUtils.AreElementsJoined(_doc(), slab_element, pile):
                        JoinGeometryUtils.UnjoinGeometry(_doc(), slab_element, pile)
                except Exception: log_swallowed(_LOG, u'create_pilecap_elements')
        
        t.Commit()
        return foundation_slab, piles
            
    except Exception as e:
        print("Error al crear elementos: {}".format(str(e)))
        if t and t.HasStarted(): t.RollBack()
        return None, []

def create_and_rename_group(foundation_slab, piles, num_horizontal, num_vertical, 
                            width, length, thickness):
    """Agrupa elementos y renombra el grupo."""
    if not foundation_slab or not piles: return None
    
    t = None
    try:
        t = nosa_tx.guard(DB.Transaction(_doc(), u"NOSA — Create and Rename Group"))
        t.Start()
        
        # Unjoin check
        slab_element = _doc().GetElement(foundation_slab.Id)
        if slab_element:
            for pile in piles:
                try:
                    if JoinGeometryUtils.AreElementsJoined(_doc(), slab_element, pile):
                        JoinGeometryUtils.UnjoinGeometry(_doc(), slab_element, pile)
                except Exception: log_swallowed(_LOG, u'create_and_rename_group')
        
        ids = List[DB.ElementId]([foundation_slab.Id] + [p.Id for p in piles])
        group = _doc().Create.NewGroup(ids)
        
        if not group:
            t.RollBack()
            return None
        
        # Ensure unjoined after group creation
        if slab_element:
            for pile in piles:
                try:
                    if JoinGeometryUtils.AreElementsJoined(_doc(), slab_element, pile):
                        JoinGeometryUtils.UnjoinGeometry(_doc(), slab_element, pile)
                except Exception: log_swallowed(_LOG, u'create_and_rename_group')
        
        # Rename logic
        num_piles = num_horizontal * num_vertical
        group_name = "Pilecap_{:.0f}x{:.0f}x{:.0f}_{}p".format(width, length, thickness, num_piles)
        
        t.Commit()
        
        # Post-commit rename
        rename_success = False
        t2 = nosa_tx.guard(DB.Transaction(_doc(), u"NOSA — Rename Group"))
        t2.Start()
        try:
            gt = group.GroupType
            if hasattr(gt, 'Duplicate'):
                new_type = gt.Duplicate(group_name)
                if new_type:
                    group.GroupType = new_type
                    rename_success = True
            
            if not rename_success:
                try:
                    gt.Name = group_name
                    rename_success = True
                except Exception: log_swallowed(_LOG, u'create_and_rename_group')
        except Exception: log_swallowed(_LOG, u'create_and_rename_group')
        
        if rename_success: 
            t2.Commit()
            print("[OK] Grupo renombrado: {}".format(group_name))
        else:
            t2.RollBack()
            print("No se pudo renombrar automaticamente. Nombre deseado: {}".format(group_name))
            
        return group
        
    except Exception as e:
        print("Error al agrupar: {}".format(str(e)))
        if t and t.HasStarted(): t.RollBack()
        return None

def create_independent_elements(num_horizontal, num_vertical, pile_spacing, clearance, 
                               cut_off, thickness, width, length, slab_type, 
                               pile_family_symbol, level, center_point):
    """Crea elementos independientes."""
    elements = []
    t = None
    try:
        if _doc().IsModifiable: _doc().Regenerate()
        
        t = nosa_tx.guard(DB.Transaction(_doc(), u"NOSA — Create Standalone Pilecap"))
        t.Start()
        
        slab = create_foundation_slab(width, length, level, center_point, slab_type)
        if not slab:
            t.RollBack()
            return []
        elements.append(slab)
        
        # Detectar offset real de la losa creada
        slab_offset = 0.0
        try:
            offset_param = slab.get_Parameter(DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if offset_param and offset_param.HasValue:
                slab_offset = offset_param.AsDouble()
        except Exception:
            log_swallowed(_LOG, u'create_independent_elements')
        
        piles = create_piles_array(
            center_point, num_horizontal, num_vertical, pile_spacing,
            pile_family_symbol, level, cut_off, thickness, width, length,
            slab_additional_offset_ft=slab_offset
        )
        if piles: elements.extend(piles)
        
        # Unjoin
        slab_elem = _doc().GetElement(slab.Id)
        if slab_elem and piles:
            for p in piles:
                try:
                    if JoinGeometryUtils.AreElementsJoined(_doc(), slab_elem, p):
                        JoinGeometryUtils.UnjoinGeometry(_doc(), slab_elem, p)
                except Exception: log_swallowed(_LOG, u'create_independent_elements')
        
        t.Commit()
        _doc().Regenerate()
        
        if elements:
            try:
                ids = List[DB.ElementId]([e.Id for e in elements if e])
                _uidoc().Selection.SetElementIds(ids)
            except Exception: log_swallowed(_LOG, u'create_independent_elements')
            
        return elements
        
    except Exception as e:
        print("Error al crear elementos independientes: {}".format(str(e)))
        if t and t.HasStarted(): t.RollBack()
        return []
