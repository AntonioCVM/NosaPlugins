# -*- coding: utf-8 -*-
__title__ = "Halftone\nSelection"
__author__ = "NOSA"
__version__ = "1.1"
__doc__ = """Apply halftone override to selected elements in current view."""

from pyrevit import revit, forms, DB


def main():
    doc = revit.doc
    view = doc.ActiveView
    try:
        sel_obj = revit.get_selection()
        selection = list(sel_obj.elements) if hasattr(sel_obj, 'elements') else list(sel_obj)
    except Exception:
        selection = []

    if not view:
        forms.alert("No active view found.", exitscript=True)
        return

    if not selection:
        forms.alert("Select one or more elements first.", exitscript=True)
        return

    mode = forms.CommandSwitchWindow.show(
        ["Apply Halftone", "Remove Halftone"],
        message="Choose operation:"
    )
    if not mode:
        forms.alert("Operation cancelled.", exitscript=True)
        return

    apply_halftone = mode == "Apply Halftone"
    if len(selection) > 20:
        if not forms.alert(
            "{} halftone for {} selected elements?".format(
                "Apply" if apply_halftone else "Remove", len(selection)
            ),
            ok=False,
            yes=True,
            no=True,
        ):
            forms.alert("Operation cancelled.", exitscript=True)
            return

    overrides = DB.OverrideGraphicSettings()
    overrides.SetHalftone(apply_halftone)

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
            "Halftone applied" if apply_halftone else "Halftone removed",
            updated,
            failed
        ),
        title="Halftone Selection",
    )


if __name__ == "__main__":
    main()
