# -*- coding: utf-8 -*-
"""
Unit Conversion Utilities
Provides standard conversion functions between Revit internal units and metric system.
"""

from Autodesk.Revit.DB import UnitUtils, UnitTypeId

# =============================================================================
# CONSTANTS
# =============================================================================

MM_TO_FT = 1.0 / 304.8
FT_TO_MM = 304.8

# =============================================================================
# CONVERSION FUNCTIONS
# =============================================================================

def mm_to_feet(mm_value):
    """
    Convert millimeters to feet (Revit internal units).
    
    Args:
        mm_value (float): Value in millimeters
        
    Returns:
        float: Value in feet
        
    Example:
        >>> mm_to_feet(1000)  # Returns ~3.28 feet
    """
    return mm_value * MM_TO_FT


def feet_to_mm(ft_value):
    """
    Convert feet (Revit internal units) to millimeters.
    
    Args:
        ft_value (float): Value in feet
        
    Returns:
        float: Value in millimeters
        
    Example:
        >>> feet_to_mm(1.0)  # Returns 304.8mm
    """
    return ft_value * FT_TO_MM


def mm_to_internal(mm_value):
    """
    Convert millimeters to Revit internal units using UnitUtils.
    This is the recommended method for Revit 2024+.
    
    Args:
        mm_value (float): Value in millimeters
        
    Returns:
        float: Value in Revit internal units
    """
    try:
        return UnitUtils.ConvertToInternalUnits(mm_value, UnitTypeId.Millimeters)
    except Exception:
        # Fallback for older Revit versions
        return mm_value * MM_TO_FT


def internal_to_mm(internal_value):
    """
    Convert Revit internal units to millimeters using UnitUtils.
    This is the recommended method for Revit 2024+.
    
    Args:
        internal_value (float): Value in Revit internal units
        
    Returns:
        float: Value in millimeters
    """
    try:
        return UnitUtils.ConvertFromInternalUnits(internal_value, UnitTypeId.Millimeters)
    except Exception:
        # Fallback for older Revit versions
        return internal_value * FT_TO_MM


def meters_to_feet(m_value):
    """
    Convert meters to feet.
    
    Args:
        m_value (float): Value in meters
        
    Returns:
        float: Value in feet
    """
    return m_value * 3.28084


def feet_to_meters(ft_value):
    """
    Convert feet to meters.
    
    Args:
        ft_value (float): Value in feet
        
    Returns:
        float: Value in meters
    """
    return ft_value / 3.28084


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_dimension(value_mm, min_mm=0, max_mm=None, name="dimension"):
    """
    Validate that a dimension is within acceptable range.
    
    Args:
        value_mm (float): Value to validate in millimeters
        min_mm (float): Minimum acceptable value
        max_mm (float, optional): Maximum acceptable value
        name (str): Name of dimension for error messages
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
        
    Example:
        >>> validate_dimension(1500, min_mm=100, max_mm=10000, name="spacing")
        (True, None)
        >>> validate_dimension(50, min_mm=100, max_mm=10000, name="spacing")
        (False, "spacing must be at least 100mm (current: 50mm)")
    """
    if value_mm < min_mm:
        return False, "{} must be at least {}mm (current: {:.0f}mm)".format(
            name, min_mm, value_mm
        )
    
    if max_mm is not None and value_mm > max_mm:
        return False, "{} cannot exceed {}mm (current: {:.0f}mm)".format(
            name, max_mm, value_mm
        )
    
    return True, None
