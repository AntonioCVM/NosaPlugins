# -*- coding: utf-8 -*-
"""
Geometry calculations for pilecap creation.
"""

def calculate_pilecap_dimensions(num_horizontal, num_vertical, pile_spacing, clearance):
    """
    Calcula las dimensiones de la losa de cimentacion en milimetros.
    
    Args:
        num_horizontal: Numero de pilotes horizontalmente
        num_vertical: Numero de pilotes verticalmente  
        pile_spacing: Distancia entre ejes de pilotes en mm
        clearance: Distancia desde el centro del pilote mas externo a la cara externa en mm
        
    Returns:
        tuple: (width_mm, length_mm) 
    """
    # Calcular la distancia total ocupada por los pilotes
    width_piles = (num_horizontal - 1) * pile_spacing if num_horizontal > 1 else 0
    length_piles = (num_vertical - 1) * pile_spacing if num_vertical > 1 else 0
    
    # Anadir el clearance en ambos lados
    width = width_piles + 2 * clearance
    length = length_piles + 2 * clearance
    
    return width, length
