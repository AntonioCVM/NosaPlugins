# -*- coding: utf-8 -*-
__title__   = "Batch\nRename"
__version__ = "1.0"
__doc__     = "Find and replace text in element names, view names, or string parameters across the model."
__author__  = "A. Viñas"

import re
import sys
import os

from Autodesk.Revit import DB
from pyrevit import revit, forms, script

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils import ui_helpers, geometry
from nosa_utils.revit_helpers import get_id_value

doc = revit.doc
output = script.get_output()


def get_element_mark(element):
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    if param:
        return param.AsString() or u''
    return u''


def set_element_mark(element, value):
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    if param and not param.IsReadOnly:
        param.Set(value)
        return True
    return False


def get_element_comments(element):
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if param:
        return param.AsString() or u''
    return u''


def set_element_comments(element, value):
    param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if param and not param.IsReadOnly:
        param.Set(value)
        return True
    return False


def get_element_display_name(element):
    try:
        if hasattr(element, 'Symbol') and element.Symbol:
            family_name = element.Symbol.Family.Name if element.Symbol.Family else u''
            type_name = element.Name if hasattr(element, 'Name') else u''
            return u'{} : {}'.format(family_name, type_name)
        if hasattr(element, 'Name'):
            return element.Name
        return u'Element {}'.format(get_id_value(element.Id))
    except Exception:
        return u'Element {}'.format(get_id_value(element.Id))


def get_available_categories():
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
            _cat_id_val = get_id_value(cat.Id)
            if _cat_id_val in [int(c) for c in skip_categories]:
                continue

            collector = (DB.FilteredElementCollector(doc)
                         .OfCategoryId(cat.Id)
                         .WhereElementIsNotElementType())

            if collector.GetElementCount() > 0:
                categories.append((cat.Name, cat))
        except Exception:
            pass

    return sorted(categories, key=lambda x: x[0])


def sort_elements_spatially(elements):
    def get_location(elem):
        try:
            center = geometry.get_element_center(elem)
            if center:
                return (-center.Y, center.X)
        except Exception:
            pass
        return (0, 0)

    return sorted(elements, key=get_location)


output.print_md(u'## Batch Rename Elements')
output.print_md(u'')

rename_mode = forms.CommandSwitchWindow.show(
    [u'Find & Replace', u'Add Prefix/Suffix', u'Sequential Numbering'],
    message=u'Select rename mode:'
)

if not rename_mode:
    forms.alert(u'Cancelled.', exitscript=True)

param_choice = forms.CommandSwitchWindow.show(
    [u'Mark', u'Comments'],
    message=u'Which parameter to modify?'
)

if not param_choice:
    forms.alert(u'Cancelled.', exitscript=True)

source_choice = forms.CommandSwitchWindow.show(
    [u'Selected Elements', u'By Category'],
    message=u'Which elements to rename?'
)

if not source_choice:
    forms.alert(u'Cancelled.', exitscript=True)

if source_choice == u'Selected Elements':
    selection = revit.get_selection()
    elements = list(selection.elements)

    if not elements:
        forms.alert(u'No elements selected.', exitscript=True)

else:
    categories = get_available_categories()

    if not categories:
        forms.alert(u'No categories with elements found.', exitscript=True)

    cat_options = {name: cat for name, cat in categories}

    selected_cat_name = forms.SelectFromList.show(
        sorted(cat_options.keys()),
        title=u'Select Category',
        multiselect=False
    )

    if not selected_cat_name:
        forms.alert(u'No category selected.', exitscript=True)

    selected_cat = cat_options[selected_cat_name]

    collector = (DB.FilteredElementCollector(doc)
                 .OfCategoryId(selected_cat.Id)
                 .WhereElementIsNotElementType())

    elements = list(collector)

output.print_md(u'**Elements to process:** {}'.format(len(elements)))
output.print_md(u'**Parameter:** {}'.format(param_choice))
output.print_md(u'**Mode:** {}'.format(rename_mode))
output.print_md(u'')

get_value = get_element_mark if param_choice == u'Mark' else get_element_comments
set_value = set_element_mark if param_choice == u'Mark' else set_element_comments

changes = []

if rename_mode == u'Find & Replace':
    find_text = forms.ask_for_string(
        prompt=u'Text to find:',
        title=u'Find'
    )
    if find_text is None:
        forms.alert(u'Cancelled.', exitscript=True)

    replace_text = forms.ask_for_string(
        prompt=u'Replace with:',
        title=u'Replace',
        default=u''
    )
    if replace_text is None:
        forms.alert(u'Cancelled.', exitscript=True)

    use_regex = ui_helpers.confirm_action(
        u'Use regular expressions?',
        title=u'Regex'
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

elif rename_mode == u'Add Prefix/Suffix':
    prefix = forms.ask_for_string(
        prompt=u'Prefix (leave empty for none):',
        title=u'Prefix',
        default=u''
    )
    if prefix is None:
        prefix = u''

    suffix = forms.ask_for_string(
        prompt=u'Suffix (leave empty for none):',
        title=u'Suffix',
        default=u''
    )
    if suffix is None:
        suffix = u''

    if not prefix and not suffix:
        forms.alert(u'No prefix or suffix provided.', exitscript=True)

    for elem in elements:
        old_value = get_value(elem)
        new_value = prefix + old_value + suffix
        if old_value != new_value:
            changes.append((elem, old_value, new_value))

else:
    pattern = forms.ask_for_string(
        prompt=(u'Numbering pattern (use # for number):\n\n'
                u'Examples: P-#, BEAM-##, COL###'),
        title=u'Pattern',
        default=u'ELEM-###'
    )
    if not pattern:
        forms.alert(u'Cancelled.', exitscript=True)

    start_number = forms.ask_for_string(
        prompt=u'Start number:',
        title=u'Start',
        default=u'1'
    )
    try:
        start_num = int(start_number)
    except Exception:
        start_num = 1

    sorted_elements = sort_elements_spatially(elements)
    hash_count = pattern.count('#')

    counter = start_num
    for elem in sorted_elements:
        old_value = get_value(elem)
        num_str = str(counter).zfill(hash_count)
        new_value = pattern.replace('#' * hash_count, num_str)
        while '#' in new_value:
            new_value = new_value.replace('#', str(counter), 1)
        changes.append((elem, old_value, new_value))
        counter += 1

output.print_md(u'### Preview (first 15 changes)')
output.print_md(u'')

for elem, old_val, new_val in changes[:15]:
    display = get_element_display_name(elem)[:30]
    output.print_md(u"- **{}**: '{}' → '{}'".format(display, old_val, new_val))

if len(changes) > 15:
    output.print_md(u'- ... and {} more changes'.format(len(changes) - 15))

if not changes:
    forms.alert(u'No changes to make.', exitscript=True)

output.print_md(u'')

if not ui_helpers.confirm_action(
    u'Apply {} changes to {} parameter?'.format(len(changes), param_choice),
    title=u'Confirm Rename'
):
    forms.alert(u'Cancelled.', exitscript=True)

output.print_md(u'### Applying changes...')
output.print_md(u'')

success_count = 0
failed = []

with revit.Transaction(u'NOSA — Batch Rename Elements'):
    for elem, old_val, new_val in changes:
        try:
            if set_value(elem, new_val):
                success_count += 1
            else:
                failed.append((elem, u'Parameter is read-only'))
        except Exception as e:
            failed.append((elem, str(e)))

output.print_md(u'')
output.print_md(u'---')
output.print_md(u'## Rename complete')
output.print_md(u'')

ui_helpers.display_results(u'Results', {
    u'Elements Renamed': success_count,
    u'Failed': len(failed),
    u'Parameter': param_choice,
    u'Mode': rename_mode
})

if failed:
    output.print_md(u'')
    output.print_md(u'### Failed')
    for elem, error in failed[:5]:
        output.print_md(u'- Element {}: {}'.format(get_id_value(elem.Id), error))

forms.alert(
    u'Batch Rename complete.\n\n'
    u'Renamed: {} elements\n'
    u'Failed: {}'.format(success_count, len(failed)),
    title=u'Batch Rename'
)

try:
    import nosa_utils.usage as _ut
    _ut.record('batchrename')
except Exception:
    pass
