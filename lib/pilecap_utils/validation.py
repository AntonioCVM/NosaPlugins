# -*- coding: utf-8 -*-
"""
Validation utilities for pilecap creation.
"""

def validate_cutoff(cut_off_mm, slab_thickness_mm):
    """
    Valida que el cut-off sea razonable respecto al espesor de la losa.
    
    Args:
        cut_off_mm: Cut-off en mm
        slab_thickness_mm: Espesor de la losa en mm
        
    Returns:
        tuple: (es_valido, mensaje_error)
    """
    if cut_off_mm <= 0:
        return False, "El cut-off debe ser mayor que 0."
    
    if cut_off_mm >= slab_thickness_mm:
        return False, "El cut-off ({:.0f} mm) no puede ser mayor o igual al espesor de la losa ({:.0f} mm).".format(
            cut_off_mm, slab_thickness_mm
        )
    
    if cut_off_mm > slab_thickness_mm * 0.8:
        return True, "Advertencia: El cut-off ({:.0f} mm) es muy cercano al espesor de la losa ({:.0f} mm).".format(
            cut_off_mm, slab_thickness_mm
        )
    
    return True, None

def validate_dimensions(width_mm, length_mm, num_piles, min_clearance_mm=200):
    """
    Valida que las dimensiones sean razonables.
    
    Args:
        width_mm: Ancho en mm
        length_mm: Largo en mm
        num_piles: Numero de pilotes
        min_clearance_mm: Clearance minimo en mm
        
    Returns:
        tuple: (es_valido, mensaje_error)
    """
    if width_mm < min_clearance_mm * 2:
        return False, "El ancho es demasiado pequeno (minimo {} mm).".format(min_clearance_mm * 2)
    
    if length_mm < min_clearance_mm * 2:
        return False, "El largo es demasiado pequeno (minimo {} mm).".format(min_clearance_mm * 2)
    
    return True, None
