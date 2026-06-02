# NOSA Utils Library

Shared utility library for NOSA pyRevit Extension scripts.

## Modules

### 📐 geometry.py
Geometric calculations and element analysis:
- `get_element_center()` - Extract center point from elements
- `get_solid_from_element()` - Get solid geometry
- `point_in_polygon()` - Check if point is inside polygon
- Cached geometry operations for performance

### 📏 unit_conversion.py
Unit conversions between Revit internal units and metric:
- `mm_to_feet()` / `feet_to_mm()` - Simple conversions
- `mm_to_internal()` / `internal_to_mm()` - UnitUtils-based (Revit 2024+)
- `validate_dimension()` - Range validation

### 🎨 ui_helpers.py
User interface utilities:
- `show_progress()` - Progress reporting  
- `ask_for_number()` - Validated numeric input
- `ask_for_choice()` - Option selection
- `ConfigHelper` - Save/load configuration
- `display_results()` - Formatted results display

### 🔧 revit_helpers.py
Safe Revit API wrappers:
- `safe_transaction()` - Auto-rollback on error
- `get_parameter_value()` / `set_parameter_value()` - Null-safe parameters
- `collect_by_category()` - Element collection
- `is_element_valid()` - Element validation

### ⚙️ config_manager.py
Centralized configuration management:
- `ConfigManager` - Load/save JSON configs
- `ConfigSchema` - Validate configuration values
- Persistent user settings

## Usage Example

```python
# Import the library
import sys
sys.path.append(r'c:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\lib')
from nosa_utils import geometry, unit_conversion, ui_helpers

# Use functions
center = geometry.get_element_center(wall)
spacing_ft = unit_conversion.mm_to_feet(1500)
show_progress(10, 100, "Processing walls")
```

## Benefits

✅ **Reusability** - Share code across all scripts  
✅ **Consistency** - Unified error handling and validation  
✅ **Performance** - Cached operations and optimized functions  
✅ **Maintainability** - Single source of truth for common operations
