# -*- coding: utf-8 -*-
__title__   = "Aa→aa\nCase"
__version__ = "3.0"
__doc__     = """Text Case — Lowercase v3.0

Convert text in TextNotes or any string parameter.

Modes:
  - Sentence case  (Hello world. How are you?)
  - All lowercase  (hello world)
  - Title Case     (Hello World)

Scope: current selection, active view, or whole project.
Target: TextNotes or any named string parameter.
"""
__author__ = "NOSA Engineering"

import sys, os
from pyrevit import revit, DB, script, forms

extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
lib_path = os.path.join(extension_root, 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from nosa_utils import text_utils

doc    = revit.doc
output = script.get_output()

# ── 1. Mode ────────────────────────────────────────────────────────────────────
_MODES = {
    'Sentence case — Hello world. How are you?': text_utils.capitalise_sentences,
    'All lowercase — hello world':               text_utils.to_lowercase,
    'Title Case — Hello World':                  text_utils.to_title_case,
}
mode_label = forms.ask_for_one_item(
    list(_MODES.keys()),
    default='Sentence case — Hello world. How are you?',
    prompt='Choose a transformation:',
    title='Text Transform — Lowercase / Sentence / Title'
)
if not mode_label:
    script.exit()
transform_fn = _MODES[mode_label]

# ── 2. Target ──────────────────────────────────────────────────────────────────
target = forms.ask_for_one_item(
    ['TextNotes', 'String parameter (by name)'],
    default='TextNotes',
    prompt='Apply to:',
    title='Target'
)
if not target:
    script.exit()

param_name = None
if target == 'String parameter (by name)':
    param_name = forms.ask_for_string(
        prompt='Enter the exact parameter name:',
        title='Parameter Name',
        default=''
    )
    if not param_name:
        script.exit()

# ── 3. Scope ───────────────────────────────────────────────────────────────────
selection   = revit.get_selection()
sel_elems   = list(selection.elements)
has_sel     = len(sel_elems) > 0

if has_sel:
    scope_label = 'Current selection ({} elements)'.format(len(sel_elems))
    elements    = sel_elems
else:
    scope = forms.ask_for_one_item(
        ['Active view', 'Entire project'],
        default='Active view',
        prompt='Nothing is selected. Choose scope:',
        title='Scope'
    )
    if not scope:
        script.exit()
    if scope == 'Active view':
        elements = list(
            DB.FilteredElementCollector(doc, doc.ActiveView.Id)
              .WhereElementIsNotElementType()
              .ToElements()
        )
        scope_label = 'Active view ({} elements)'.format(len(elements))
    else:
        elements = list(
            DB.FilteredElementCollector(doc)
              .WhereElementIsNotElementType()
              .ToElements()
        )
        scope_label = 'Entire project ({} elements)'.format(len(elements))

# ── 4. Collect targets ─────────────────────────────────────────────────────────
if param_name is None:
    targets = [e for e in elements if isinstance(e, DB.TextNote)]
    target_label = 'TextNotes'
else:
    targets = []
    for el in elements:
        try:
            p = el.LookupParameter(param_name)
            if p and p.StorageType == DB.StorageType.String and not p.IsReadOnly:
                targets.append(el)
        except Exception:
            pass
    target_label = 'elements with param "{}"'.format(param_name)

if not targets:
    forms.alert(
        'No {} found in scope: {}.\n'
        'Try a different scope or parameter name.'.format(target_label, scope_label),
        title='Nothing to transform'
    )
    script.exit()

# ── 5. Preview & confirm ───────────────────────────────────────────────────────
output.print_md('## Text Case: {}'.format(mode_label.split('—')[0].strip()))
output.print_md('**Scope:** {}  |  **Target:** {}'.format(scope_label, target_label))
output.print_md('')
output.print_md('### Preview (first 5)')

def _get_text(el):
    if param_name is None:
        return el.Text
    return el.LookupParameter(param_name).AsString() or ''

for el in targets[:5]:
    old = _get_text(el)
    new = transform_fn(old)
    arrow = '→ **{}**'.format(new[:50]) if old != new else '(no change)'
    output.print_md('- `{}` {}'.format(old[:50], arrow))

if len(targets) > 5:
    output.print_md('- … and {} more'.format(len(targets) - 5))

if len(targets) > 10:
    if not forms.alert(
        'Apply "{}" to {} {}?'.format(
            mode_label.split('—')[0].strip(), len(targets), target_label),
        yes=True, no=True
    ):
        script.exit()

# ── 6. Apply ───────────────────────────────────────────────────────────────────
changed = 0
with revit.Transaction('Text Case — {}'.format(mode_label.split('—')[0].strip())):
    for el in targets:
        try:
            old = _get_text(el)
            new = transform_fn(old)
            if old != new:
                if param_name is None:
                    el.Text = new
                else:
                    el.LookupParameter(param_name).Set(new)
                changed += 1
        except Exception as ex:
            output.print_md('✗ Element {}: {}'.format(el.Id, ex))

output.print_md('')
output.print_md('---')
output.print_md('## Complete — {} modified / {} unchanged'.format(
    changed, len(targets) - changed))
forms.alert(
    'Modified: {}\nUnchanged: {}'.format(changed, len(targets) - changed),
    title='Text Case Complete'
)
