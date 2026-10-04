# -*- coding: utf-8 -*-
"""
Logic for Sheet/Scope Box visibility.
"""
from Autodesk.Revit import DB
from pyrevit import revit
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'pilemaster'
class SheetLogic:
    def __init__(self, doc):
        self.doc = doc

    def get_scope_boxes(self):
        """Get all Scope Boxes."""
        return DB.FilteredElementCollector(self.doc)\
                 .OfCategory(DB.BuiltInCategory.OST_VolumeOfInterest)\
                 .WhereElementIsNotElementType()\
                 .ToElements()

    def map_zones_to_scope_boxes(self, zone_names, scope_boxes):
        """Map generic zone names to actual Scope Box elements."""
        mapping = {}
        for z in zone_names:
            # Simple fuzzy match
            for sb in scope_boxes:
                sb_name = getattr(sb, 'Name', None) or u''
                if z.lower() in sb_name.lower():
                    mapping[z] = sb
                    break
        return mapping

    def ensure_parameters(self, param_names, category_set):
        """
        Ensure the specified Yes/No parameters exist for OST_StructuralFoundation.
        Returns: (created_count, error_message)
        """
        app = self.doc.Application
        
        # 1. Check existing
        iterator = self.doc.ParameterBindings.ForwardIterator()
        existing_names = set()
        while iterator.MoveNext():
            if iterator.Key:
                existing_names.add(iterator.Key.Name)
        
        missing = [n for n in param_names if n not in existing_names]
        if not missing:
            return 0, None

        # 2. Setup Shared Parameter File
        original_file = app.SharedParametersFilename
        temp_file = None
        
        # Use a safe temp path (in user's temp dir)
        import os
        import tempfile
        
        try:
            # If no SP file is set, create a new one
            if not original_file or not os.path.exists(original_file):
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
                tf.close()
                temp_file = tf.name
                app.SharedParametersFilename = temp_file
            
            # Open the file (original or temp)
            def_file = app.OpenSharedParameterFile()
            if not def_file:
                # Fallback: Force create a temp one if original failed to open
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
                tf.close()
                temp_file = tf.name
                app.SharedParametersFilename = temp_file
                def_file = app.OpenSharedParameterFile()
                
            if not def_file:
                return 0, "Could not open any Shared Parameter file."

            # Get/Create Group
            grp = def_file.Groups.get_Item("NOSA_Visibility")
            if not grp:
                grp = def_file.Groups.Create("NOSA_Visibility")
            
            # 3. Create Definitions and Bindings
            with nosa_tx.revit_transaction(u"NOSA — Create Visibility Parameters"):
                # Prepare Category Set
                cats = app.Create.NewCategorySet()
                cat = self.doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_StructuralFoundation)
                cats.Insert(cat)
                
                # Instance Binding
                binding = app.Create.NewInstanceBinding(cats)
                
                # Determine Parameter Type (Revit 2022+ support)
                # Revit 2022 removed ParameterType.YesNo in favor of SpecTypeId.Boolean.YesNo
                use_spec_type_id = False
                try:
                    # check if ExternalDefinitionCreationOptions accepts SpecTypeId (2 arguments, 2nd is ForgeTypeId)
                    # or check if we are in 2022+
                    # A safe check:
                    try:
                        ptype = DB.SpecTypeId.Boolean.YesNo
                        use_spec_type_id = True
                    except AttributeError:
                        # Pre-2022
                        ptype = DB.ParameterType.YesNo
                except Exception:
                     # Fallback
                     ptype = DB.ParameterType.YesNo

                for name in missing:
                    # Check if def exists in group to avoid cleanup errors
                    defn = grp.Definitions.get_Item(name)
                    if not defn:
                        # Create generic options
                        if use_spec_type_id:
                             opt = DB.ExternalDefinitionCreationOptions(name, ptype)
                        else:
                             opt = DB.ExternalDefinitionCreationOptions(name, ptype)
                        
                        defn = grp.Definitions.Create(opt)
                    
                    # Bind
                    if not self.doc.ParameterBindings.Contains(defn):
                        # Revit 2024+ check for GroupTypeId
                        try:
                            # Revit 2024+ uses GroupTypeId
                            # Try to get GroupTypeId.Visibility
                            # Note: GroupTypeId is a static class with static properties in 2024+
                            # But sometimes accessible via DB.GroupTypeId
                            group_id = DB.GroupTypeId.Visibility
                        except AttributeError:
                            # Pre-2024
                            group_id = DB.BuiltInParameterGroup.PG_VISIBILITY
                            
                        self.doc.ParameterBindings.Insert(defn, binding, group_id)
                    
        except Exception as e:
            return 0, str(e)
            
        finally:
            # Cleanup
            try:
                if original_file and os.path.exists(original_file):
                    app.SharedParametersFilename = original_file
                elif temp_file and os.path.exists(temp_file):
                     # If we switched to temp, maybe keep it attached? No, risky. 
                     # But we can't set it to None.
                     pass
                     
                if temp_file and os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                log_swallowed(_LOG, u'SheetLogic.ensure_parameters')
                
        return len(missing), None

    def update_visibility(self, elements, zone_mapping):
        """
        Check which zone each element is in and set 'Show_in_Zone' param.
        Auto-creates parameters if missing.
        """
        # 1. Prepare list of expected parameters
        param_names = ["Show_in_{}".format(z) for z in zone_mapping.keys()]
        
        # 2. Ensure parameters exist
        # result is (count, error_msg)
        p_result = self.ensure_parameters(param_names, None)
        
        # FIX: Ensure parameters allow "Vary by Group Instance"
        if elements:
             # Find ONE valid element for each parameter (efficiently)
             # Ideally one element has them all, but let's be safe.
             sample_el = elements[0]
             
             with nosa_tx.revit_transaction(u"NOSA — Enable Group Variance"):
                 for pname in param_names:
                     # Check if we need to enable it
                     p = sample_el.LookupParameter(pname)
                     if not p:
                         # Try finding one element that has it
                         for el in elements:
                             p = el.LookupParameter(pname)
                             if p: break
                             
                     if p:
                         try:
                             idef = p.Definition
                             if isinstance(idef, DB.InternalDefinition):
                                 # Checking GetAllowVaryBetweenGroups can sometimes throw if not applicable, 
                                 # but setting it logic is safer.
                                 if not idef.GetAllowVaryBetweenGroups(self.doc):
                                     idef.SetAllowVaryBetweenGroups(self.doc, True)
                         except Exception as e:
                             # print("Could not set vary by group for {}: {}".format(pname, e))
                             log_swallowed(_LOG, u'SheetLogic.update_visibility')
        
        updated_count = 0
        outside_count = 0
        
        # Track which elements are "covered" by at least one zone
        covered_ids = set()
        
        with nosa_tx.revit_transaction(u"NOSA — Update Sheet Visibility"):
            for z_name, sb in zone_mapping.items():
                param_name = "Show_in_{}".format(z_name)
                
                # Get bounding box of Scope Box
                bbox = sb.get_BoundingBox(None)
                if not bbox: continue
                
                # Check ALL elements for this zone
                for el in elements:
                    # 1. Get Parameter (Should exist now)
                    p = el.LookupParameter(param_name)
                    if not p: continue
                        
                    # 2. Check Containment (Intersection)
                    el_bbox = el.get_BoundingBox(None)
                    if not el_bbox: continue
                    
                    # Simple AABB Intersection
                    # Max1 >= Min2 and Max2 >= Min1 (for all axes)
                    b1 = el_bbox # Element
                    b2 = bbox    # Scope Box
                    
                    intersects = (
                        b1.Max.X >= b2.Min.X and b2.Max.X >= b1.Min.X and
                        b1.Max.Y >= b2.Min.Y and b2.Max.Y >= b1.Min.Y and
                        b1.Max.Z >= b2.Min.Z and b2.Max.Z >= b1.Min.Z
                    )
                    
                    if intersects:
                        covered_ids.add(el.Id)
                    
                    # 3. Set Value
                    val = 1 if intersects else 0
                    if p.AsInteger() != val:
                        p.Set(val)
                        updated_count += 1
            
            # Count outsiders
            for el in elements:
                if el.Id not in covered_ids:
                    outside_count += 1
                    
        return updated_count, outside_count, p_result
