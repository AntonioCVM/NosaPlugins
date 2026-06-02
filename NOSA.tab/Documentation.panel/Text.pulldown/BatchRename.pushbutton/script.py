# -*- coding: utf-8 -*-
__title__ = "Batch\nRename"
__version__ = "1.0"
__doc__ = """Batch rename elements with find/replace, prefix/suffix, or sequential numbering.

FEATURES:
✓ Find and replace in element names
✓ Add prefix or suffix to Mark parameter
✓ Sequential numbering with custom pattern
✓ Works on selected elements or by category
✓ Preview changes before applying
"""
__author__ = "Antonio Viñas"

from pyrevit import revit, DB, forms, script
import re
import sys
import os

# Import NOSA utils
extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
lib_path = os.path.join(extension_root, "lib")
if lib_path not in sys.path:
    sys.path.append(lib_path)
from nosa_utils import ui_helpers, geometry
from nosa_utils.revit_helpers import get_id_value

doc = revit.doc
output = script.get_output()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_element_mark(element):
    """Get the Mark parameter value of an element."""
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    if param:
        return param.AsString() or ""
    return ""


def set_element_mark(element, value):
    """Set the Mark parameter value of an element."""
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    if param and not param.IsReadOnly:
        param.Set(value)
        return True
    return False


def get_element_comments(element):
    """Get the Comments parameter value."""
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if param:
        return param.AsString() or ""
    return ""


def set_element_comments(element, value):
    """Set the Comments parameter value."""
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if param and not param.IsReadOnly:
        param.Set(value)
        return True
    return False


def get_element_display_name(element):
    """Get a display name for an element."""
    try:
        if hasattr(element, 'Symbol') and element.Symbol:
            family_name = element.Symbol.Family.Name if element.Symbol.Family else ""
            type_name = element.Name if hasattr(element, 'Name') else ""
            return "{} : {}".format(family_name, type_name)
        elif hasattr(element, 'Name'):
            return element.Name
        else:
            return "Element {}".format(get_id_value(element.Id))
    except Exception:
        return "Element {}".format(get_id_value(element.Id))


def get_available_categories():
    """Get categories that have placed elements."""
    categories = []
    skip_categories = [
        DB.BuiltInCategory.OST_Views,
        DB.BuiltInCategory.OST_Sheets,
        DB.BuiltInCategory.OST_Levels,
        DB.BuiltInCategory.OST_Grids,
    ]
    
    for cat in doc.Settings.Categories:
        try:
            if cat.CategoryType != DB.CategoryType.Model:
                continue
            _cat_id_val = cat.Id.Value if hasattr(cat.Id, 'Value') else (cat.Id.IntegerValue if hasattr(cat.Id, 'IntegerValue') else int(str(cat.Id)))
            if _cat_id_val in [int(c) for c in skip_categories]:
                continue
            
            # Check if category has elements
            collector = DB.FilteredElementCollector(doc)\
                .OfCategoryId(cat.Id)\
                .WhereElementIsNotElementType()
            
            if collector.GetElementCount() > 0:
                categories.append((cat.Name, cat))
        except Exception:
            pass
    
    return sorted(categories, key=lambda x: x[0])


def sort_elements_spatially(elements):
    """Sort elements by location (top-to-bottom, left-to-right)."""
    def get_location(elem):
        try:
            center = geometry.get_element_center(elem)
            if center:
                return (-center.Y, center.X)  # Top to bottom, left to right
        except Exception:
            pass
        return (0, 0)
    
    return sorted(elements, key=get_location)


# =============================================================================
# MAIN SCRIPT
# =============================================================================

output.print_md("## 🔠 Batch Rename Elements")
output.print_md("")

# Choose rename mode
rename_mode = forms.CommandSwitchWindow.show(
    ["Find & Replace", "Add Prefix/Suffix", "Sequential Numbering"],
    message="Select rename mode:"
)

if not rename_mode:
    forms.alert("Cancelled.", exitscript=True)

# Choose parameter to modify
param_choice = forms.CommandSwitchWindow.show(
    ["Mark", "Comments"],
    message="Which parameter to modify?"
)

if not param_choice:
    forms.alert("Cancelled.", exitscript=True)

# Choose elements source
source_choice = forms.CommandSwitchWindow.show(
    ["Selected Elements", "By Category"],
    message="Which elements to rename?"
)

if not source_choice:
    forms.alert("Cancelled.", exitscript=True)

# Get elements
if source_choice == "Selected Elements":
    selection = revit.get_selection()
    elements = list(selection.elements)
    
    if not elements:
        forms.alert("No elements selected.", exitscript=True)
    
else:  # By Category
    categories = get_available_categories()
    
    if not categories:
        forms.alert("No categories with elements found.", exitscript=True)
    
    cat_options = {name: cat for name, cat in categories}
    
    selected_cat_name = forms.SelectFromList.show(
        sorted(cat_options.keys()),
        title="Select Category",
        multiselect=False
    )
    
    if not selected_cat_name:
        forms.alert("No category selected.", exitscript=True)
    
    selected_cat = cat_options[selected_cat_name]
    
    collector = DB.FilteredElementCollector(doc)\
        .OfCategoryId(selected_cat.Id)\
        .WhereElementIsNotElementType()
    
    elements = list(collector)

output.print_md("**Elements to process:** {}".format(len(elements)))
output.print_md("**Parameter:** {}".format(param_choice))
output.print_md("**Mode:** {}".format(rename_mode))
output.print_md("")

# Get current values
get_value = get_element_mark if param_choice == "Mark" else get_element_comments
set_value = set_element_mark if param_choice == "Mark" else set_element_comments

# Process based on mode
changes = []

if rename_mode == "Find & Replace":
    find_text = forms.ask_for_string(
        prompt="Text to find:",
        title="Find"
    )
    if find_text is None:
        forms.alert("Cancelled.", exitscript=True)
    
    replace_text = forms.ask_for_string(
        prompt="Replace with:",
        title="Replace",
        default=""
    )
    if replace_text is None:
        forms.alert("Cancelled.", exitscript=True)
    
    use_regex = ui_helpers.confirm_action(
        "Use regular expressions?",
        title="Regex"
    )
    
    for elem in elements:
        old_value = get_value(elem)
        if use_regex:
            try:
                new_value = re.sub(find_text, replace_text, old_value)
            except Exception:
                new_value = old_value
        else:
            new_value = old_value.replace(find_text, replace_text)
        
        if old_value != new_value:
            changes.append((elem, old_value, new_value))

elif rename_mode == "Add Prefix/Suffix":
    prefix = forms.ask_for_string(
        prompt="Prefix (leave empty for none):",
        title="Prefix",
        default=""
    )
    if prefix is None:
        prefix = ""
    
    suffix = forms.ask_for_string(
        prompt="Suffix (leave empty for none):",
        title="Suffix",
        default=""
    )
    if suffix is None:
        suffix = ""
    
    if not prefix and not suffix:
        forms.alert("No prefix or suffix provided.", exitscript=True)
    
    for elem in elements:
        old_value = get_value(elem)
        new_value = prefix + old_value + suffix
        if old_value != new_value:
            changes.append((elem, old_value, new_value))

else:  # Sequential Numbering
    pattern = forms.ask_for_string(
        prompt="Numbering pattern (use # for number):\n\nExamples: P-#, BEAM-##, COL###",
        title="Pattern",
        default="ELEM-###"
    )
    if not pattern:
        forms.alert("Cancelled.", exitscript=True)
    
    start_number = forms.ask_for_string(
        prompt="Start number:",
        title="Start",
        default="1"
    )
    try:
        start_num = int(start_number)
    except Exception:
        start_num = 1
    
    # Sort elements spatially
    sorted_elements = sort_elements_spatially(elements)
    
    # Count # symbols to determine zero-padding
    hash_count = pattern.count('#')
    
    counter = start_num
    for elem in sorted_elements:
        old_value = get_value(elem)
        
        # Generate new value
        num_str = str(counter).zfill(hash_count)
        new_value = pattern.replace('#' * hash_count, num_str)
        
        # Handle patterns with varying # counts
        while '#' in new_value:
            new_value = new_value.replace('#', str(counter), 1)
        
        changes.append((elem, old_value, new_value))
        counter += 1

# Preview
output.print_md("### Preview (first 15 changes)")
output.print_md("")

for elem, old_val, new_val in changes[:15]:
    display = get_element_display_name(elem)[:30]
    output.print_md("- **{}**: '{}' → '{}'".format(display, old_val, new_val))

if len(changes) > 15:
    output.print_md("- ... and {} more changes".format(len(changes) - 15))

if not changes:
    forms.alert("No changes to make.", exitscript=True)

output.print_md("")

# Confirm
if not ui_helpers.confirm_action(
    "Apply {} changes to {} parameter?".format(len(changes), param_choice),
    title="Confirm Rename"
):
    forms.alert("Cancelled.", exitscript=True)

# Apply changes
output.print_md("### Applying changes...")
output.print_md("")

success_count = 0
failed = []

with revit.Transaction("Batch Rename Elements"):
    for elem, old_val, new_val in changes:
        try:
            if set_value(elem, new_val):
                success_count += 1
            else:
                failed.append((elem, "Parameter is read-only"))
        except Exception as e:
            failed.append((elem, str(e)))

# Results
output.print_md("")
output.print_md("---")
output.print_md("## ✅ Rename Complete")
output.print_md("")

ui_helpers.display_results("Results", {
    "Elements Renamed": success_count,
    "Failed": len(failed),
    "Parameter": param_choice,
    "Mode": rename_mode
})

if failed:
    output.print_md("")
    output.print_md("### ⚠️ Failed")
    for elem, error in failed[:5]:
        output.print_md("- Element {}: {}".format(get_id_value(elem.Id), error))

forms.alert(
    "Batch Rename Complete!\n\n"
    "✓ Renamed: {} elements\n"
    "✗ Failed: {}".format(success_count, len(failed)),
    title="Batch Rename"
)
