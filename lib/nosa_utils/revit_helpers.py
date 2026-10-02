# -*- coding: utf-8 -*-
"""
Revit API Helper Utilities
Provides safer wrappers and common Revit API operations.
"""
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.revit_helpers'

# Revit API imports are local to each function so the module imports outside Revit (unit tests).

# =============================================================================
# ELEMENT ID COMPATIBILITY (Revit 2024–2027)
# =============================================================================
# Revit 2025+ removed ElementId.IntegerValue — use .Value (int64).
# Always use get_id_value() / element_id_from_int() instead of direct API access.

def get_id_value(element_id):
    """Return the integer value of an ElementId (2024–2027 safe)."""
    if element_id is None:
        return 0
    try:
        if hasattr(element_id, 'Value'):
            return int(element_id.Value)
    except Exception:
        log_swallowed(_LOG, u'get_id_value')
    try:
        if hasattr(element_id, 'IntegerValue'):
            return int(element_id.IntegerValue)
    except Exception:
        log_swallowed(_LOG, u'get_id_value')
    return int(str(element_id))


def element_id_from_int(val):
    """Construct an ElementId from an int — uses Int64 on Revit 2024+."""
    from Autodesk.Revit.DB import ElementId
    try:
        from System import Int64
        return ElementId(Int64(int(val)))
    except Exception:
        return ElementId(int(val))  # nosa-lint: disable=NOSA010 (pre-2024 fallback)


def coerce_element_id(val):
    """Return ElementId from an ElementId or int-like value (2024–2027 safe)."""
    if val is None:
        return None
    try:
        if hasattr(val, 'Value') or hasattr(val, 'IntegerValue'):
            return val
    except Exception:
        log_swallowed(_LOG, u'coerce_element_id')
    return element_id_from_int(val)


def element_name(element):
    """Return an element's name, u'' if unreadable (.Name fails on some types in IronPython/pythonnet)."""
    if element is None:
        return u''
    try:
        name = element.Name
    except Exception:
        name = None
    if name is not None:
        return name
    try:
        from Autodesk.Revit.DB import Element
        name = Element.Name.GetValue(element)
    except Exception:
        name = None
    if name is not None:
        return name
    try:
        from Autodesk.Revit.DB import BuiltInParameter as _BIP
        bips = (_BIP.ALL_MODEL_TYPE_NAME, _BIP.SYMBOL_NAME_PARAM)
    except Exception:
        bips = ()
    for bip in bips:
        try:
            param = element.get_Parameter(bip)
            name = param.AsString() if param is not None else None
        except Exception:
            name = None
        if name:
            return name
    return u''


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
    from Autodesk.Revit.DB import Transaction
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
    from Autodesk.Revit.DB import StorageType
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
        log_swallowed(_LOG, u'get_parameter_value')
    
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
    from Autodesk.Revit.DB import StorageType
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
    from Autodesk.Revit.DB import StorageType
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
        log_swallowed(_LOG, u'get_builtin_parameter_value')
    
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
    from Autodesk.Revit.DB import FilteredElementCollector
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
    from Autodesk.Revit.DB import FilteredElementCollector
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
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        type_element = element.Document.GetElement(element.GetTypeId())
        if type_element:
            type_param = type_element.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if type_param:
                return type_param.AsString() or ""
    except Exception:
        log_swallowed(_LOG, u'get_element_type_name')
    
    return ""


def get_element_family_name(element):
    """
    Get the family name of an element.
    
    Args:
        element: Revit element
        
    Returns:
        str: Family name or empty string
    """
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        type_element = element.Document.GetElement(element.GetTypeId())
        if type_element:
            family_param = type_element.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
            if family_param:
                return family_param.AsString() or ""
    except Exception:
        log_swallowed(_LOG, u'get_element_family_name')
    
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
        log_swallowed(_LOG, u'get_element_category_name')
    
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
                log_swallowed(_LOG, u'can_modify_element')
        
        return True, None
    
    except Exception as e:
        return False, str(e)
