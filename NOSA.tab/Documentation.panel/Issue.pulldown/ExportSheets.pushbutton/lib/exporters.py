# -*- coding: utf-8 -*-
import os
import time
from System.Collections.Generic import List
from Autodesk.Revit import DB
from nosa_utils.logging import Logger
from config import Config
from utils import Utils
try:
    from pyrevit import script
    output = script.get_output()
except Exception:
    output = None

def debug_print(msg):
    pass
    # if output:
    #     output.print_md(str(msg))
    # else:
    #     print(msg)
        
logger = Logger()

class ExportManager:
    """Gestor de exportación optimizado - PDF y DWG solamente - Supports Sheets and Views"""
    
    def __init__(self, doc, elements, naming_builder, output_folder, export_formats, preset, project_params=None, is_views=False):
        self.doc = doc
        self.elements = elements  # Can be sheets or views
        self.is_views = is_views  # Flag to indicate if exporting views
        self.naming_builder = naming_builder
        self.output_folder = output_folder
        self.export_formats = export_formats
        self.force_black = export_formats.get('force_black', False)
        self.preset = preset
        self.project_params = project_params or {}
        
        self.results = {
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'total': len(elements),
            'start_time': time.time(),
            'elapsed_time': 0,
            'by_format': {'pdf': 0, 'dwg': 0, 'dxf': 0}
        }
        
        self.pdf_files = []
        self.preset_config = self._get_preset_config()
    
    def _get_preset_config(self):
        """Obtiene configuración del preset seleccionado"""
        if self.preset == "Quick":
            return Config.PRESET_QUICK
        elif self.preset == "Standard":
            return Config.PRESET_STANDARD
        elif self.preset == "Print":
            return Config.PRESET_PRINT
        else:
            return Config.PRESET_STANDARD
    
    def export_all(self, progress_callback=None, cancellation_token=None, batch_size=50):
        """Exporta todos los elementos (sheets o views) en formatos PDF y/o DWG"""
        self.progress_callback = progress_callback
        try:
            # Limpiar caché al inicio para asegurar datos frescos
            Utils.clear_cache()
            
            start_time = time.time()
            total_elements = len(self.elements)
            
            # Procesar en lotes para mejor gestión de memoria
            for batch_start in range(0, total_elements, batch_size):
                # Verificar cancelación antes de cada lote
                if cancellation_token and hasattr(cancellation_token, 'CancellationPending') and cancellation_token.CancellationPending:
                    logger.info("Export cancelled by user")
                    return False, "Export cancelled"
                
                batch_end = min(batch_start + batch_size, total_elements)
                batch = self.elements[batch_start:batch_end]
                
                if progress_callback:
                    progress_callback("Processing batch {}-{} of {}...".format(
                        batch_start + 1, batch_end, total_elements
                    ))
                
                # Procesar lote
                for idx, element in enumerate(batch):
                    global_idx = batch_start + idx
                    
                    # Verificar cancelación
                    if cancellation_token and hasattr(cancellation_token, 'CancellationPending') and cancellation_token.CancellationPending:
                        logger.info("Export cancelled by user")
                        return False, "Export cancelled"
                    
                    try:
                        element_name = element.Name if self.is_views else (element.SheetNumber if hasattr(element, 'SheetNumber') else str(element.Id))
                        
                        if progress_callback:
                            title = "{} [{}]".format(element_name, element.Name) if hasattr(element, 'SheetNumber') else element_name
                            progress_callback("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                            progress_callback("PROCESSING {}/{} : **{}**".format(global_idx + 1, total_elements, title))
                    
                        debug_print("  - Processing: **{}**".format(element_name))
                    
                        filename = self.naming_builder.build_filename(element, self.project_params, is_view=self.is_views)
                        # debug_print("    - Generated Filename: `{}`".format(filename))
                        
                        element_success = True
                        
                        # Exportar PDF si está seleccionado
                        do_pdf = self.export_formats.get('pdf', False)
                        debug_print("    - Export PDF selected: **{}**".format(do_pdf))
                        
                        if do_pdf:
                            if self.is_views:
                                if self.export_view_pdf(element, filename):
                                    self.results['by_format']['pdf'] += 1
                                    debug_print("    - PDF Export: **SUCCESS**")
                                else:
                                    element_success = False
                                    debug_print("    - PDF Export: **FAILED**")
                            else:
                                if self.export_sheet_pdf(element, filename):
                                    self.results['by_format']['pdf'] += 1
                                    debug_print("    - PDF Export: **SUCCESS**")
                                else:
                                    element_success = False
                                    debug_print("    - PDF Export: **FAILED**")
                        
                        # Exportar DWG si está seleccionado
                        do_dwg = self.export_formats.get('dwg', False)
                        debug_print("    - Export DWG selected: **{}**".format(do_dwg))
                        
                        if do_dwg:
                            if self.is_views:
                                if self.export_view_dwg(element, filename):
                                    self.results['by_format']['dwg'] += 1
                                    debug_print("    - DWG Export: **SUCCESS**")
                                else:
                                    element_success = False
                                    debug_print("    - DWG Export: **FAILED**")
                            else:
                                if self.export_sheet_dwg(element, filename):
                                    self.results['by_format']['dwg'] += 1
                                    debug_print("    - DWG Export: **SUCCESS**")
                                else:
                                    element_success = False
                                    debug_print("    - DWG Export: **FAILED**")
                            
                        # Exportar DXF si está seleccionado (independiente de DWG)
                        do_dxf = self.export_formats.get('dxf', False)
                        debug_print("    - Export DXF selected: **{}**".format(do_dxf))
                        if do_dxf:
                            if self.is_views:
                                if self.export_view_dxf(element, filename):
                                    self.results['by_format']['dxf'] += 1
                                else:
                                    element_success = False
                            else:
                                if self.export_sheet_dxf(element, filename):
                                    self.results['by_format']['dxf'] += 1
                                else:
                                    element_success = False
                        
                        if element_success:
                            self.results['success'] += 1
                        else:
                            self.results['failed'] += 1
                        
                        # Permitir que la UI se actualice periódicamente (Windows Forms)
                        # We use System.Windows.Forms.Application.DoEvents() usually
                        try:
                            import System.Windows.Forms
                            System.Windows.Forms.Application.DoEvents()
                        except Exception:
                            pass
                        
                        # Limpieza de memoria cada 10 elementos
                        if (global_idx + 1) % 10 == 0:
                            import gc
                            gc.collect()
                    
                    except Exception as e:
                        element_name = element.Name if self.is_views else (element.SheetNumber if hasattr(element, 'SheetNumber') else str(element.Id))
                        if progress_callback:
                            progress_callback("✗ Error in {}: {}".format(element_name, str(e)))
                        self.results['failed'] += 1
                        logger.error("Error exportando elemento {}".format(element_name), e)
                
                # Limpieza de memoria después de cada lote
                import gc
                gc.collect()
            
            self.results['elapsed_time'] = time.time() - start_time
            
            return True, "Export complete"
            
        except Exception as e:
            return False, "Error: {}".format(str(e))
    
    def export_sheet_pdf(self, sheet, filename):
        """Exporta sheet a PDF"""
        try:
            # logger.info("Starting PDF export for: {}".format(filename))
            if self.progress_callback:
                self.progress_callback("  📄 PDF Generating...")
            
            pdf_options = DB.PDFExportOptions()
            pdf_options.RasterQuality = self.preset_config['pdf_raster_quality']

            if self.force_black:
                try:
                    pdf_options.ColorDepth = DB.ColorDepthType.BlackLine
                except Exception:
                    try:
                        pdf_options.ColorDepth = DB.ColorDepthType.GrayScale
                    except Exception:
                        pass
            elif 'pdf_color_depth' in self.preset_config:
                pdf_options.ColorDepth = self.preset_config['pdf_color_depth']
            
            pdf_options.HideCropBoundaries = True
            pdf_options.HideReferencePlane = True
            pdf_options.HideScopeBoxes = True
            pdf_options.HideUnreferencedViewTags = True
            pdf_options.MaskCoincidentLines = False
            pdf_options.StopOnError = False
            pdf_options.Combine = False
            
            view_ids = List[DB.ElementId]()
            view_ids.Add(sheet.Id)
            
            before_files = set([f for f in os.listdir(self.output_folder) 
                               if f.lower().endswith('.pdf')])
            
            # logger.info("Calling doc.Export for PDF...")
            success = self.doc.Export(self.output_folder, view_ids, pdf_options)
            # logger.info("doc.Export returned: {}".format(success))
            # debug_print("      - doc.Export(PDF) returned: {}".format(success))
            
            if not success:
                logger.warning("PDF export returned False for {}".format(filename))
                debug_print("      - PDF Export Failed (API returned False)")
                return False

            # Poll until Revit finishes writing the file (max 3 s)
            deadline = time.time() + 3.0
            new_pdf = None
            while time.time() < deadline:
                new_pdf = self._find_newest_pdf(before_files)
                if new_pdf:
                    break
                time.sleep(0.15)

            if new_pdf is None:
                new_pdf = self._find_newest_pdf(before_files)
            
            if not new_pdf:
                logger.warning("No se detectó PDF creado para {}".format(filename))
                debug_print("      - PDF Created but file not found in folder.")
                return False
            
            old_path = os.path.join(self.output_folder, new_pdf)
            new_path = os.path.join(self.output_folder, "{}.pdf".format(filename))
            
            try:
                if old_path != new_path:
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                # debug_print("      - PDF Renamed: `{}` -> `{}`".format(os.path.basename(old_path), os.path.basename(new_path)))
                if self.progress_callback:
                    self.progress_callback("     ✅ PDF Exported: **{}**".format(os.path.basename(new_path)))
            except Exception as rename_err:
                logger.warning("No se pudo renombrar PDF temporal {} -> {} ({})".format(
                    new_pdf, new_path, str(rename_err)
                ))
                if self.progress_callback:
                    self.progress_callback("     ❌ Error renaming PDF: {}".format(str(rename_err)))
            
            return True
            
        except Exception as e:
            logger.error("Error exportando PDF {}: {}".format(filename, str(e)), e)
            debug_print("      - **ERROR in PDF Export**: {}".format(str(e)))
            return False
    
    def _find_newest_pdf(self, before_files):
        """Encuentra el PDF más reciente en la carpeta"""
        try:
            after_files = set([f for f in os.listdir(self.output_folder) 
                               if f.lower().endswith('.pdf')])
            
            new_files = after_files - before_files
            
            if not new_files:
                return None
            
            if len(new_files) == 1:
                return list(new_files)[0]
            
            newest = None
            newest_time = 0
            
            for f in new_files:
                full_path = os.path.join(self.output_folder, f)
                mtime = os.path.getmtime(full_path)
                if mtime > newest_time:
                    newest_time = mtime
                    newest = f
            
            return newest
            
        except Exception as e:
            logger.warning("Error buscando PDF más reciente", e)
            return None
    
    def export_view_pdf(self, view, filename):
        """Exporta view a PDF"""
        try:
            debug_print("    - Starting PDF export for view: **{}**".format(filename))
            pdf_options = DB.PDFExportOptions()
            pdf_options.RasterQuality = self.preset_config['pdf_raster_quality']

            if self.force_black:
                try:
                    pdf_options.ColorDepth = DB.ColorDepthType.BlackLine
                except Exception:
                    try:
                        pdf_options.ColorDepth = DB.ColorDepthType.GrayScale
                    except Exception:
                        pass
            elif 'pdf_color_depth' in self.preset_config:
                pdf_options.ColorDepth = self.preset_config['pdf_color_depth']
            
            pdf_options.HideCropBoundaries = True
            pdf_options.HideReferencePlane = True
            pdf_options.HideScopeBoxes = True
            pdf_options.HideUnreferencedViewTags = True
            pdf_options.MaskCoincidentLines = False
            pdf_options.StopOnError = False
            pdf_options.Combine = False
            
            view_ids = List[DB.ElementId]()
            view_ids.Add(view.Id)
            
            before_files = set([f for f in os.listdir(self.output_folder) 
                               if f.lower().endswith('.pdf')])
            
            success = self.doc.Export(self.output_folder, view_ids, pdf_options)
            debug_print("      - doc.Export(PDF) returned: {}".format(success))
            
            if not success:
                logger.warning("PDF export returned False for view {}".format(filename))
                debug_print("      - PDF Export Failed (API returned False)")
                return False

            # Poll until Revit finishes writing the file (max 3 s)
            deadline = time.time() + 3.0
            new_pdf = None
            while time.time() < deadline:
                new_pdf = self._find_newest_pdf(before_files)
                if new_pdf:
                    break
                time.sleep(0.15)
            if new_pdf is None:
                new_pdf = self._find_newest_pdf(before_files)

            if not new_pdf:
                logger.warning("No PDF detected for view {}".format(filename))
                debug_print("      - PDF Created but file not found in folder.")
                return False
            
            old_path = os.path.join(self.output_folder, new_pdf)
            new_path = os.path.join(self.output_folder, "{}.pdf".format(filename))
            
            try:
                if old_path != new_path:
                    if os.path.exists(new_path):
                        os.remove(new_path)
                    os.rename(old_path, new_path)
                debug_print("      - PDF Renamed: `{}` -> `{}`".format(os.path.basename(old_path), os.path.basename(new_path)))
            except Exception as rename_err:
                logger.warning("No se pudo renombrar PDF temporal {} -> {} ({})".format(
                    new_pdf, new_path, str(rename_err)
                ))
                debug_print("      - **ERROR Renaming PDF**: {}".format(str(rename_err)))
            
            return True
            
        except Exception as e:
            logger.error("Error exportando PDF de vista {}: {}".format(filename, str(e)), e)
            debug_print("      - **ERROR in PDF Export**: {}".format(str(e)))
            return False
    
    def export_view_dwg(self, view, filename):
        """Exporta view a DWG"""
        try:
            debug_print("    - Starting DWG export for view: **{}**".format(filename))
            dwg_options = DB.DWGExportOptions()
            dwg_options.MergedViews = True
            dwg_options.FileVersion = self.preset_config['dwg_version']
            dwg_options.Colors = self.preset_config['dwg_colors']
            dwg_options.PropOverrides = DB.PropOverrideMode.ByEntity
            dwg_options.SharedCoords = True
            dwg_options.TargetUnit = DB.ExportUnit.Default
            
            try:
                if hasattr(dwg_options, 'LayerSettings'):
                    dwg_options.LayerSettings = DB.ExportLayerOptions.AIA
            except Exception:
                pass
            
            view_set = List[DB.ElementId]()
            view_set.Add(view.Id)
            
            # Note: doc.Export for DWG needs filename without extension?
            # Revit API signature: Export(folder, name, views, options)
            success = self.doc.Export(self.output_folder, filename, view_set, dwg_options)
            debug_print("      - doc.Export(DWG) returned: {}".format(success))
            
            # Check existence
            expected_file = os.path.join(self.output_folder, "{}.dwg".format(filename))
            
            # Revit sometimes adds prefixes/suffixes if multiple views? Here only 1.
            # But sometimes "Sheet Number" logic applies if it's a sheet. For View, it uses View Name?
            # We explicitly pass filename.
            
            result = os.path.exists(expected_file)
            debug_print("      - DWG Export Result (File Exists): {}".format(result))
            return result
            
        except Exception as e:
            logger.error("Error exporting view DWG {}".format(filename), e)
            debug_print("      - **ERROR in DWG Export**: {}".format(str(e)))
            return False
            
    def export_view_dxf(self, view, filename):
        """Exporta view a DXF"""
        try:
            # Ensure folder exists
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)

            dxf_path = os.path.join(self.output_folder, "{}.dxf".format(filename))
            # Pre-cleanup
            if os.path.exists(dxf_path):
                try:
                    os.remove(dxf_path)
                except Exception:
                    pass

            # Setup Options
            dxf_options = DB.DXFExportOptions()
            # dxf_options.MergedViews = True # Not property of DXF
            try:
                dxf_options.FileVersion = self.preset_config.get('dwg_version', DB.ACADVersion.R2013)
            except Exception:
                dxf_options.FileVersion = DB.ACADVersion.R2013
                
            dxf_options.Colors = self.preset_config.get('dwg_colors', DB.ExportColorMode.TrueColor)
            dxf_options.PropOverrides = DB.PropOverrideMode.ByEntity
            dxf_options.SharedCoords = False # Safest option
            dxf_options.TargetUnit = DB.ExportUnit.Default
            
            view_set = List[DB.ElementId]()
            view_set.Add(view.Id)
            
            # Execute
            success = self.doc.Export(self.output_folder, filename, view_set, dxf_options)
            
            if not success:
                logger.warning("Revit API return False for DXF export: {}".format(filename))
                return False
                
            if os.path.exists(dxf_path):
                return True
            else:
                 logger.warning("DXF file not found after 'success' export: {}".format(dxf_path))
                 return False
            
        except Exception as e:
            logger.error("Error exporting view DXF {}: {}".format(filename, str(e)), e)
            return False

    def export_sheet_dwg(self, sheet, filename):
        """Exporta sheet a DWG"""
        try:
            if self.progress_callback:
                self.progress_callback("  📐 DWG Generating...")
            
            dwg_path = os.path.join(self.output_folder, "{}.dwg".format(filename))
            if os.path.exists(dwg_path):
                try: os.remove(dwg_path)
                except Exception: pass

            dwg_options = DB.DWGExportOptions()
            dwg_options.MergedViews = True
            dwg_options.FileVersion = self.preset_config['dwg_version']
            dwg_options.Colors = DB.ExportColorMode.IndexColors if self.force_black else self.preset_config['dwg_colors']
            dwg_options.PropOverrides = DB.PropOverrideMode.ByEntity
            dwg_options.SharedCoords = True
            dwg_options.TargetUnit = DB.ExportUnit.Default
            
            view_set = List[DB.ElementId]()
            view_set.Add(sheet.Id)
            
            success = self.doc.Export(self.output_folder, filename, view_set, dwg_options)
            # debug_print("      - doc.Export(DWG) returned: {}".format(success))
        
            result = os.path.exists(dwg_path)
            if result and self.progress_callback:
                 self.progress_callback("     ✅ DWG Exported: **{}.dwg**".format(filename))
                 
            return result
        except Exception as e:
            logger.error("Error exportando DWG {}".format(filename), e)
            if self.progress_callback:
                self.progress_callback("     ❌ Error DWG: {}".format(str(e)))
            return False
    
    def export_sheet_dxf(self, sheet, filename):
        """Exporta sheet a DXF"""
        try:
            # logger.info("Starting DXF export for: {}".format(filename))
            if self.progress_callback:
                self.progress_callback("  ✖ DXF Generating...")
            # Ensure folder exists
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)

            dxf_path = os.path.join(self.output_folder, "{}.dxf".format(filename))
            # Pre-cleanup
            if os.path.exists(dxf_path):
                try:
                    os.remove(dxf_path)
                except Exception:
                    pass

            # Setup Options
            dxf_options = DB.DXFExportOptions()
            # dxf_options.MergedViews = True # Not property of DXF
            try:
                dxf_options.FileVersion = self.preset_config.get('dwg_version', DB.ACADVersion.R2013)
            except Exception:
                 dxf_options.FileVersion = DB.ACADVersion.R2013
                 
            dxf_options.Colors = self.preset_config.get('dwg_colors', DB.ExportColorMode.TrueColor)
            dxf_options.PropOverrides = DB.PropOverrideMode.ByEntity
            dxf_options.SharedCoords = False # Safest option
            dxf_options.TargetUnit = DB.ExportUnit.Default
            
            view_set = List[DB.ElementId]()
            view_set.Add(sheet.Id)
            
            # Execute
            # if self.progress_callback:
            #    self.progress_callback("  - Calling doc.Export(DXF)...")
                
            success = self.doc.Export(self.output_folder, filename, view_set, dxf_options)
            
            # if self.progress_callback:
            #    self.progress_callback("  - doc.Export(DXF) returned: {}".format(success))
            
            if not success:
                 logger.warning("Revit API return False for DXF export: {}".format(filename))
                 return False

            if os.path.exists(dxf_path):
                if self.progress_callback:
                    self.progress_callback("     ✅ DXF Exported: **{}.dxf**".format(filename))
                return True
            else:
                 logger.warning("DXF file not found after 'success' export: {}".format(dxf_path))
                 return False
            
        except Exception as e:
            logger.error("Error exportando DXF {}: {}".format(filename, str(e)), e)
            if self.progress_callback:
                self.progress_callback("  - **ERROR in DXF Export**: {}".format(str(e)))
            return False
