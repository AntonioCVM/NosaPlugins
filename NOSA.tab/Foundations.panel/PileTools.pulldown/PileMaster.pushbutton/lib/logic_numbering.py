# -*- coding: utf-8 -*-
from Autodesk.Revit import DB
from pyrevit import revit
import sys
import re
from collections import defaultdict, OrderedDict

from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.pilecap_utils import ungroup_targets as _ungroup_targets
from nosa_utils.pilecap_utils import regroup_restore as _regroup_restore
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'pilemaster'


class NumberingLogic:
    def __init__(self, doc):
        self.doc = doc

    def is_pilecap(self, family_name):
        """Check if family name looks like a pilecap (for UI defaults)."""
        # Unified keywords for Pilecaps/Foundations
        cap_keywords = ["cap", "slab", "raft", "foundation", "enc", "zapat"]
        f = family_name.lower()
        
        # If it matches any cap keyword, it's a cap
        if any(k in f for k in cap_keywords):
            return True
            
        # If it has "pile" but isn't a cap, it's a pile
        if "pile" in f:
            return False 
            
        # Default fallback (if neither pile nor keywords found)
        return False

    def get_element_center(self, element):
        """Get element center (cached by caller ideally, but here simple)."""
        loc = element.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
        bbox = element.get_BoundingBox(None)
        if bbox:
            return (bbox.Min + bbox.Max) / 2.0
        return DB.XYZ.Zero

    def sort_spatially(self, elements):
        """Sort elements Top-Left to Bottom-Right."""
        # Top-Bottom (Desc Y), Left-Right (Asc X)
        return sorted(elements, key=lambda e: (-self.get_element_center(e).Y, self.get_element_center(e).X))

    def get_param_value(self, element, param_names):
        """Helper to try getting a parameter value from a list of names."""
        for name in param_names:
            p = element.LookupParameter(name)
            if not p:
                # Try Type parameter
                type_id = element.GetTypeId()
                if type_id != DB.ElementId.InvalidElementId:
                    type_elem = self.doc.GetElement(type_id)
                    p = type_elem.LookupParameter(name)
            
            if p:
                if p.StorageType == DB.StorageType.Double:
                    # Return formatted string to avoid float precision issues in keys
                    # Round to 1 decimal place (mm often)
                    val = p.AsDouble()
                    return "{:.2f}".format(val)
                elif p.StorageType == DB.StorageType.String:
                    return p.AsString()
                elif p.StorageType == DB.StorageType.Integer:
                    return str(p.AsInteger())
        return "?"

    def get_element_key(self, element, is_pile):
        """
        Generate a grouping key.
        Piles: Family Name (or Type Name if relevant for prefixing).
        Caps: Family Name + Dims (Width, Length, Thickness).
        """
        try:
            type_id = element.GetTypeId()
            type_elem = self.doc.GetElement(type_id)
            fam_name = type_elem.FamilyName
            type_name = element_name(type_elem)
            
            if is_pile:
                # Piles: Group by Family + Type (for Prefixing)
                # User wants different prefixes for "Square" vs "Circular"
                return "{} : {}".format(fam_name, type_name)
            else:
                # Caps: Group by Geometry
                # "deben ser iguales si las dimensiones o el espesor son los mismos"
                
                # Try common dimension parameters
                width = self.get_param_value(element, ["Width", "Anchura", "Width (default)", "B"])
                length = self.get_param_value(element, ["Length", "Longitud", "Length (default)", "L", "Depth"]) 
                thick = self.get_param_value(element, ["Thickness", "Grosor", "Espesor", "Foundation Thickness", "Canto", "Depth"])
                
                # If "Depth" was picked up for Length, handle thickness carefully. 
                # This is heuristic.
                
                return "{} : [{}x{}x{}]".format(fam_name, width, length, thick)
        except Exception:
            return "Unknown"

    def group_by_logic(self, elements):
        """
        Group elements based on the new logic.
        Returns two dicts: piles_groups, caps_groups
        """
        # First, classify roughly
        # We need to reuse classify_elements logic but it expects a list.
        # Let's do it inline here more efficiently.
        
        piles_grouped = defaultdict(list)
        caps_grouped = defaultdict(list)
        
        # Keywords
        # Keywords - Unified with is_pilecap
        cap_keywords = ["cap", "slab", "raft", "foundation", "enc", "zapat"]
        
        for el in elements:
            try:
                type_elem = self.doc.GetElement(el.GetTypeId())
                if not type_elem: continue
                fam_name_lower = type_elem.FamilyName.lower()
                
                is_cap = any(k in fam_name_lower for k in cap_keywords)
                is_pile = "pile" in fam_name_lower and not is_cap
                
                if is_pile:
                    key = self.get_element_key(el, is_pile=True)
                    piles_grouped[key].append(el)
                elif is_cap:
                    key = self.get_element_key(el, is_pile=False)
                    caps_grouped[key].append(el)
            except Exception:
                continue
                
        return piles_grouped, caps_grouped

    def group_by_type(self, elements):
        """Group elements by their Family name only."""
        grouped = defaultdict(list)
        
        for el in elements:
            try:
                # Get element type
                type_id = el.GetTypeId()
                if type_id == DB.ElementId.InvalidElementId:
                    continue
                    
                elem_type = self.doc.GetElement(type_id)
                if not elem_type:
                    continue
                
                # Get Family Name - try multiple methods
                fam_name = None
                try:
                    # Method 1: Direct property (works for FamilyInstance types)
                    fam_name = elem_type.FamilyName
                except Exception:
                    # Method 2: Via parameter
                    try:
                        fam_param = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
                        if fam_param:
                            fam_name = fam_param.AsString()
                    except Exception:
                        log_swallowed(_LOG, u'NumberingLogic.group_by_type')
                
                # Only group by Family Name (not Type)
                if fam_name:
                    grouped[fam_name].append(el)
                    
            except Exception as e:
                # Silent fail but continue processing other elements
                continue
                
        return grouped

    def extract_number(self, value, prefix=""):
        """Extract number from a string marking."""
        if not value: return 0
        # If prefix provided, strip it first? 
        # Or just regex find the last number
        match = re.search(r'(\d+)$', value)
        if match:
            return int(match.group(1))
        return 0

    def classify_elements(self, elements):
        """Classify elements into Piles and Pilecaps using robust logic."""
        piles = defaultdict(list)
        caps = defaultdict(list)
        
        # Keywords from original scripts
        pile_keywords = ["pile"]
        cap_keywords = ["cap", "slab", "raft", "foundation", "enc", "zapat"]
        
        for el in elements:
            try:
                # Get Family Name
                type_el = self.doc.GetElement(el.GetTypeId())
                if not type_el: continue
                
                fam_param = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
                fam_name = fam_param.AsString() if fam_param else ""
                fam_name_lower = fam_name.lower()
                
                type_name = type_el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                full_key = "{} : {}".format(fam_name, type_name)
                
                # Logic from PilecapNumber.py: Exclude "pile" if not "cap"/"slab"
                if "pile" in fam_name_lower and not any(k in fam_name_lower for k in cap_keywords):
                    # It's likely a PILE
                    piles[full_key].append(el)
                elif any(k in fam_name_lower for k in cap_keywords):
                    # It's a CAP
                    caps[full_key].append(el)
            except Exception:
                continue
                
        return piles, caps


        
    def apply_numbering(self, grouped_elements, config_map, modes, only_empty=False):
        """
        Apply numbering to elements using the configuration map.
        
        SIMPLIFIED LOGIC:
        1. Get all elements
        2. Classify each element as pile or cap
        3. Get FamilyName directly (same method as group_by_type for consistency)
        4. Look up prefix/suffix from config_map using FamilyName
        5. Apply the numbering
        
        config_map: { "FamilyName": (Prefix, Suffix) }
        """
        from pyrevit import script
        output = script.get_output()
        
        count = 0
        piles_count = 0
        caps_count = 0
        
        # Keywords for classification
        cap_keywords = ["cap", "slab", "raft", "foundation", "enc", "zapat"]
        
        # 1. Flatten all elements
        all_elements = []
        for elems in grouped_elements.values():
            all_elements.extend(elems)
        
        output.print_md("---")
        output.print_md("## apply_numbering - DEBUG")
        output.print_md("- Total elements to process: **{}**".format(len(all_elements)))
        output.print_md("- Modes: **{}**".format(modes))
        output.print_md("- Config Map keys: **{}**".format(list(config_map.keys())))
        
        # 2. Build a cache: element -> (fam_name, is_pile, is_cap)
        element_info = {}
        for el in all_elements:
            try:
                type_id = el.GetTypeId()
                if type_id == DB.ElementId.InvalidElementId:
                    continue
                elem_type = self.doc.GetElement(type_id)
                if not elem_type:
                    continue
                
                # Get Family Name - MUST be same method as group_by_type!
                fam_name = None
                try:
                    fam_name = elem_type.FamilyName
                except Exception:
                    try:
                        fam_param = elem_type.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
                        if fam_param:
                            fam_name = fam_param.AsString()
                    except Exception:
                        log_swallowed(_LOG, u'NumberingLogic.apply_numbering')
                
                if not fam_name:
                    continue

                fam_lower = fam_name.lower()
                is_cap = any(k in fam_lower for k in cap_keywords)
                # If the family is explicitly in config_map, trust the user's
                # classification over keyword heuristics.  This avoids the
                # "pile" vs "piling" substring mismatch ("piling" does NOT
                # contain the substring "pile" in Python).
                if fam_name in config_map:
                    is_pile = not is_cap
                else:
                    is_pile = "pil" in fam_lower and not is_cap
                
                eid_val = get_id_value(el.Id)
                
                element_info[eid_val] = (fam_name, is_pile, is_cap, el)
                
            except Exception as e:
                output.print_md("- ERROR processing element: {}".format(e))
                continue
        
        output.print_md("- Elements classified: **{}**".format(len(element_info)))
        
        # 3. Group elements by (fam_name, is_pile/is_cap) for numbering
        # Piles: sequential per prefix
        # Caps: grouped by family + dimensions (simplified: same family = same number for all)
        
        with nosa_tx.revit_transaction(u"NOSA — Batch Numbering"):

            # Ungroup any Model Groups that contain target elements so their
            # instance parameters (Mark, Comments) become writable.
            _all_targets = [el for (_, _, _, el) in element_info.values()]
            _restore_data = _ungroup_targets(self.doc, _all_targets, output)
            if _restore_data:
                output.print_md(u'- **{} model group(s) temporarily ungrouped**'.format(len(_restore_data)))

            # --- PROCESS PILES ---
            if "Pile" in modes:
                # Collect all piles with their family info
                all_piles = []
                for el_id, (fam_name, is_pile, is_cap, el) in element_info.items():
                    if is_pile:
                        all_piles.append((fam_name, el))
                
                output.print_md("### Piles - Global Sequential Numbering:")
                output.print_md("- Total piles to process: **{}**".format(len(all_piles)))
                
                # If only_empty mode, find the highest existing number across ALL piles
                global_counter = 1
                if only_empty and all_piles:
                    max_existing = 0
                    for fam_name, el in all_piles:
                        p_mark = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                        if p_mark:
                            current = p_mark.AsString()
                            if current:
                                # Extract number from the mark (e.g., "P-45" -> 45)
                                num = self.extract_number(current)
                                if num > max_existing:
                                    max_existing = num
                    
                    global_counter = max_existing + 1
                    output.print_md("- Only Empty mode: Starting from **{}** (highest existing: {})".format(global_counter, max_existing))
                
                # Group by family and sort each group spatially
                piles_by_family = defaultdict(list)
                for fam_name, el in all_piles:
                    piles_by_family[fam_name].append(el)
                
                for fam, els in sorted(piles_by_family.items()):
                    output.print_md("- `{}`: {} elements".format(fam, len(els)))
                
                # Process families in sorted order, using GLOBAL counter
                for fam_name in sorted(piles_by_family.keys()):
                    elements_list = piles_by_family[fam_name]
                    
                    # Get config for this family
                    cfg = config_map.get(fam_name)
                    if cfg is None:
                        output.print_md("  - **WARNING**: No config for family `{}`, using default P-".format(fam_name))
                        prefix, suffix = "P-", ""
                    else:
                        prefix, suffix = cfg
                        output.print_md("  - Config for `{}`: Prefix=`{}`, Suffix=`{}`".format(fam_name, prefix, suffix))
                    
                    # Sort spatially (top-left to bottom-right)
                    sorted_elems = self.sort_spatially(elements_list)
                    
                    for el in sorted_elems:
                        # Check only_empty mode - skip elements that already have a value
                        p_mark = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                        if p_mark and not p_mark.IsReadOnly:
                            if only_empty:
                                current = p_mark.AsString()
                                if current and current.strip():
                                    continue  # Skip - already has value
                            
                            # Create the numbering value using GLOBAL counter
                            val = "{}{:02d}{}".format(prefix, global_counter, suffix)
                            
                            try:
                                p_mark.Set(val)
                                count += 1
                                piles_count += 1
                                global_counter += 1  # Increment global counter
                            except Exception as e:
                                output.print_md("    - ERROR setting Mark: {}".format(e))
                        
                        # Clear Comments for piles
                        p_comm = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if p_comm and not p_comm.IsReadOnly:
                            try:
                                p_comm.Set("")
                            except Exception:
                                log_swallowed(_LOG, u'NumberingLogic.apply_numbering')
                
                output.print_md("- Final global counter: **{}**".format(global_counter))
            
            # --- PROCESS PILECAPS ---
            if "Pilecap" in modes:
                # Group caps by FamilyName
                caps_by_family = defaultdict(list)
                for el_id, (fam_name, is_pile, is_cap, el) in element_info.items():
                    if is_cap:
                        caps_by_family[fam_name].append(el)
                
                output.print_md("### Caps by Family:")
                for fam, els in caps_by_family.items():
                    output.print_md("- `{}`: {} elements".format(fam, len(els)))
                
                # Sequential counters per PREFIX
                cap_seq_counters = defaultdict(int)
                
                for fam_name in sorted(caps_by_family.keys()):
                    elements_list = caps_by_family[fam_name]
                    
                    # Get config for this family
                    cfg = config_map.get(fam_name)
                    if cfg is None:
                        output.print_md("  - **WARNING**: No config for family `{}`, using default PC-".format(fam_name))
                        prefix, suffix = "PC-", ""
                    else:
                        prefix, suffix = cfg
                        output.print_md("  - Found config for `{}`: Prefix=`{}`, Suffix=`{}`".format(fam_name, prefix, suffix))
                    
                    # Sort spatially
                    sorted_elems = self.sort_spatially(elements_list)
                    
                    # Get current counter for this prefix
                    if prefix not in cap_seq_counters:
                        cap_seq_counters[prefix] = 1
                    
                    num = cap_seq_counters[prefix]
                    val = "{}{:02d}{}".format(prefix, num, suffix)
                    
                    # Check only_empty for caps (check first element)
                    skip_group = False
                    if only_empty and sorted_elems:
                        p_check = sorted_elems[0].get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if p_check:
                            current = p_check.AsString()
                            if current and current.strip():
                                skip_group = True
                    
                    if skip_group:
                        continue
                    
                    for el in sorted_elems:
                        # Set Comments for caps
                        p_comm = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if p_comm and not p_comm.IsReadOnly:
                            try:
                                p_comm.Set(val)
                                count += 1
                                caps_count += 1
                            except Exception as e:
                                output.print_md("    - ERROR setting Comments: {}".format(e))
                        
                        # Clear Mark for caps
                        p_mark = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                        if p_mark and not p_mark.IsReadOnly:
                            try:
                                p_mark.Set("")
                            except Exception:
                                log_swallowed(_LOG, u'NumberingLogic.apply_numbering')
                    
                    cap_seq_counters[prefix] += 1
        
            # Restore all groups that were ungrouped at the start
            if _restore_data:
                _regroup_restore(self.doc, _restore_data, output)

        output.print_md("---")
        output.print_md("## RESULT: {} elements numbered (Piles: {}, Caps: {})".format(count, piles_count, caps_count))
        return count, piles_count, caps_count

