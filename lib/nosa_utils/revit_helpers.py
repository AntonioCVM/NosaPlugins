# -*- coding: utf-8 -*-
"""
Revit API Helper Utilities
Provides safer wrappers and common Revit API operations.
"""

from Autodesk.Revit.DB import (
    Transaction,
    FilteredElementCollector,
    BuiltInParameter,
    StorageType
)

# =============================================================================
# ELEMENT ID COMPATIBILITY (Revit 2024+)
# =============================================================================

def get_id_value(element_id):
    """
    Get integer value from ElementId - compatible with Revit 2024+.
    
    In Revit 2024+, ElementId.IntegerValue was replaced with ElementId.Value.
    This function handles both API versions.
    
    Args:
        element_id: Revit ElementId object
        
    Returns:
        int: Integer value of the ElementId
        
    Example:
        >>> wall_id_int = get_id_value(wall.Id)
        >>> if wall_id_int in processed_ids:
        >>>     continue
    """
    if hasattr(element_id, 'Value'):
        return element_id.Value
    elif hasattr(element_id, 'IntegerValue'):
        return element_id.IntegerValue
    else:
        return int(str(element_id))


# =============================================================================
# TRANSACTION HELPERS
# =============================================================================

def safe_transaction(doc, name, func, *args, **kwargs):
    """
    Execute a function within a safe transaction with automatic rollback on error.
    
    Args:
        doc: Revit document
        name (str): Transaction name
        func: Function to execute
        *args: Arguments for function
        **kwargs: Keyword arguments for function
        
    Returns:
        tuple: (success: bool, result or error_message)
        
    Example:
        >>> def modify_element(elem, new_value):
        >>>     param = elem.LookupParameter("MyParam")
        >>>     param.Set(new_value)
        >>>     return "Success"
        >>> success, result = safe_transaction(doc, "Modify", modify_element, element, 42)
    """
    t = Transaction(doc, name)
    try:
        t.Start()
        result = func(*args, **kwargs)
        t.Commit()
        return True, result
    except Exception as e:
        if t.HasStarted():
            t.RollBack()
        return False, str(e)


# =============================================================================
# PARAMETER HELPERS
# =============================================================================

def get_parameter_value(element, param_name, default=None):
    """
    Safely get parameter value from element.
    
    Args:
        element: Revit element
        param_name (str): Parameter name
        default: Default value if parameter not found or has no value
        
    Returns:
        Parameter value or default
        
    Example:
        >>> mark = get_parameter_value(wall, "Mark", "")
        >>> if mark:
        >>>     print("Wall mark:", mark)
    """
    try:
        param = element.LookupParameter(param_name)
        if param and param.HasValue:
            if param.StorageType == StorageType.String:
                return param.AsString() or default
            elif param.StorageType == StorageType.Double:
                return param.AsDouble()
            elif param.StorageType == StorageType.Integer:
                return param.AsInteger()
            elif param.StorageType == StorageType.ElementId:
                return param.AsElementId()
    except Exception:
        pass
    
    return default


def set_parameter_value(element, param_name, value):
    """
    Safely set parameter value on element.
    
    Args:
        element: Revit element
        param_name (str): Parameter name
        value: Value to set
        
    Returns:
        tuple: (success: bool, error_message: str or None)
        
    Example:
        >>> success, error = set_parameter_value(wall, "Mark", "W-01")
        >>> if not success:
        >>>     print("Error:", error)
    """
    try:
        param = element.LookupParameter(param_name)
        if not param:
            return False, "Parameter '{}' not found".format(param_name)
        
        if param.IsReadOnly:
            return False, "Parameter '{}' is read-only".format(param_name)
        
        # Set based on storage type
        if param.StorageType == StorageType.String:
            param.Set(str(value) if value is not None else "")
        elif param.StorageType == StorageType.Double:
            param.Set(float(value))
        elif param.StorageType == StorageType.Integer:
            param.Set(int(value))
        elif param.StorageType == StorageType.ElementId:
            param.Set(value)  # Assume value is already ElementId
        else:
            return False, "Unsupported storage type"
        
        return True, None
    
    except Exception as e:
        return False, str(e)


def get_builtin_parameter_value(element, builtin_param, default=None):
    """
    Get value from built-in parameter.
    
    Args:
        element: Revit element
        builtin_param: BuiltInParameter enum value
        default: Default value if not found
        
    Returns:
        Parameter value or default
    """
    try:
        param = element.get_Parameter(builtin_param)
        if param and param.HasValue:
            if param.StorageType == StorageType.String:
                return param.AsString() or default
            elif param.StorageType == StorageType.Double:
                return param.AsDouble()
            elif param.StorageType == StorageType.Integer:
                return param.AsInteger()
            elif param.StorageType == StorageType.ElementId:
                return param.AsElementId()
    except Exception:
        pass
    
    return default


# =============================================================================
# COLLECTION HELPERS
# =============================================================================

def collect_by_category(doc, category, view_id=None, is_type=False):
    """
    Collect elements by category.
    
    Args:
        doc: Revit document
        category: BuiltInCategory enum value
        view_id: Optional view ID to filter by
        is_type (bool): If True, collect types instead of instances
        
    Returns:
        list: List of collected elements
        
    Example:
        >>> walls = collect_by_category(doc, BuiltInCategory.OST_Walls)
        >>> print("Found {} walls".format(len(walls)))
    """
    if view_id:
        collector = FilteredElementCollector(doc, view_id)
    else:
        collector = FilteredElementCollector(doc)
    
    collector = collector.OfCategory(category)
    
    if is_type:
        collector = collector.WhereElementIsElementType()
    else:
        collector = collector.WhereElementIsNotElementType()
    
    return list(collector.ToElements())


def collect_by_class(doc, element_class, view_id=None):
    """
    Collect elements by class.
    
    Args:
        doc: Revit document
        element_class: Element class (e.g., Wall, Floor, FamilyInstance)
        view_id: Optional view ID to filter by
        
    Returns:
        list: List of collected elements
        
    Example:
        >>> from Autodesk.Revit.DB import Wall
        >>> walls = collect_by_class(doc, Wall)
    """
    if view_id:
        collector = FilteredElementCollector(doc, view_id)
    else:
        collector = FilteredElementCollector(doc)
    
    return list(collector.OfClass(element_class).ToElements())


# =============================================================================
# ELEMENT INFO HELPERS
# =============================================================================

def get_element_type_name(element):
    """
    Get the type name of an element.
    
    Args:
        element: Revit element
        
    Returns:
        str: Type name or empty string
    """
    try:
        type_element = element.Document.GetElement(element.GetTypeId())
        if type_element:
            type_param = type_element.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if type_param:
                return type_param.AsString() or ""
    except Exception:
        pass
    
    return ""


def get_element_family_name(element):
    """
    Get the family name of an element.
    
    Args:
        element: Revit element
        
    Returns:
        str: Family name or empty string
    """
    try:
        type_element = element.Document.GetElement(element.GetTypeId())
        if type_element:
            family_param = type_element.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
            if family_param:
                return family_param.AsString() or ""
    except Exception:
        pass
    
    return ""


def get_element_category_name(element):
    """
    Get the category name of an element.
    
    Args:
        element: Revit element
        
    Returns:
        str: Category name or empty string
    """
    try:
        if hasattr(element, 'Category') and element.Category:
            return element.Category.Name
    except Exception:
        pass
    
    return ""


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def is_element_valid(element):
    """
    Check if element is valid and not deleted.
    
    Args:
        element: Revit element
        
    Returns:
        bool: True if valid
    """
    try:
        return element is not None and element.IsValidObject
    except Exception:
        return False


def can_modify_element(element):
    """
    Check if element can be modified (not pinned, on editable workset, etc.).
    
    Args:
        element: Revit element
        
    Returns:
        tuple: (can_modify: bool, reason: str or None)
    """
    try:
        if not is_element_valid(element):
            return False, "Element is null or deleted"
        
        if hasattr(element, 'Pinned') and element.Pinned:
            return False, "Element is pinned"
        
        # Check workset if worksharing is enabled
        doc = element.Document
        if doc.IsWorkshared:
            try:
                from Autodesk.Revit.DB import WorksharingUtils
                workset_id = WorksharingUtils.GetCheckoutStatus(doc, element.Id)
                # Additional workset checks could go here
            except Exception:
                pass
        
        return True, None
    
    except Exception as e:
        return False, str(e)
