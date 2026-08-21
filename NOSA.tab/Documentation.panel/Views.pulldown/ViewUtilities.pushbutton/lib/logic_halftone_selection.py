# -*- coding: utf-8 -*-
# Extracted from the original HalftoneSelection.pushbutton/script.py (which had
# no lib/ folder — all logic was inline in script.py) as part of the
# ViewUtilities hub consolidation. The Revit API calls, dialog flow and
# messages below are copied verbatim from that script; only the outer
# function wrapper (apply_halftone) and the (doc, uidoc) parameters are new,
# so the hub's "Halftone Selection" quick-action button can call straight
# into it instead of running a standalone script.
from Autodesk.Revit import DB
from pyrevit import revit, forms


def apply_halftone(doc, uidoc):
    """
    Apply or remove a halftone override on the currently selected elements,
    in the active view. Prompts for Apply/Remove and (for large selections)
    a confirmation, exactly as the original HalftoneSelection script did.
    """
    view = doc.ActiveView
    try:
        sel_obj = revit.get_selection()
        selection = list(sel_obj.elements) if hasattr(sel_obj, 'elements') else list(sel_obj)
    except Exception:
        selection = []

    if not view:
        forms.alert("No active view found.")
        return

    if not selection:
        forms.alert("Select one or more elements first.")
        return

    mode = forms.CommandSwitchWindow.show(
        ["Apply Halftone", "Remove Halftone"],
        message="Choose operation:"
    )
    if not mode:
        forms.alert("Operation cancelled.")
        return

    apply_halftone_flag = mode == "Apply Halftone"
    if len(selection) > 20:
        if not forms.alert(
            "{} halftone for {} selected elements?".format(
                "Apply" if apply_halftone_flag else "Remove", len(selection)
            ),
            ok=False,
            yes=True,
            no=True,
        ):
            forms.alert("Operation cancelled.")
            return

    overrides = DB.OverrideGraphicSettings()
    overrides.SetHalftone(apply_halftone_flag)

    updated = 0
    failed = 0

    with revit.Transaction("Apply Halftone to Selection"):
        for element in selection:
            try:
                view.SetElementOverrides(element.Id, overrides)
                updated += 1
            except Exception:
                failed += 1

    forms.alert(
        "{} in active view.\n\n"
        "Updated: {}\n"
        "Failed: {}".format(
            "Halftone applied" if apply_halftone_flag else "Halftone removed",
            updated,
            failed
        ),
        title="Halftone Selection",
    )
