# -*- coding: utf-8 -*-
import os
import time
from System.Collections.Generic import List
from Autodesk.Revit import DB
from nosa_utils.logging import Logger
from nosa_utils.telemetry import log_swallowed
from config import Config
from utils import Utils
_LOG = u'SheetExportHub/exporters'
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

    # Revit's DWG/DXF exporter writes every raster image referenced by the
    # exported view/sheet out as a separate companion file (e.g. a linked
    # or embedded PNG/JPEG becomes its own file next to the .dwg/.dxf) so
    # the CAD file's IMAGE/xref entities have something to point at. NOSA's
    # workflow never wants those loose image files in the delivery folder,
    # so every DWG/DXF export is wrapped in a before/after folder snapshot
    # and any newly-appeared raster file is deleted straight after.
    _AUTO_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif')

    def __init__(self, doc, elements, naming_builder, output_folder, export_formats, preset, project_params=None,
                 is_views=False, dwg_setup_name=None, combined_pdf_name=None):
        self.doc = doc
        self.elements = elements  # Can be sheets or views
        self.is_views = is_views  # Flag to indicate if exporting views
        self.naming_builder = naming_builder
        self.output_folder = output_folder
        self.export_formats = export_formats
        self.force_black = export_formats.get('force_black', False)
        self.preset = preset
        self.project_params = project_params or {}
        # dwg_setup_name: name of a DWGExportOptions setup already saved in
        # the document (Manage > Export Setups > DWG); None = use the fixed
        # NOSA quality preset instead (self.preset_config).
        self.dwg_setup_name = dwg_setup_name
        # combined_pdf_name: filename (no extension) for the single merged
        # PDF produced when export_formats['pdf_combine'] is set — additive
        # to, not a replacement for, per-sheet PDFs.
        self.combined_pdf_name = combined_pdf_name or "Combined Export"
        
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
                    logger.info("Exportación cancelada por el usuario")
                    return False, "Exportación cancelada"
                
                batch_end = min(batch_start + batch_size, total_elements)
                batch = self.elements[batch_start:batch_end]
                
                if progress_callback:
                    progress_callback("Procesando lote {}-{} de {}...".format(
                        batch_start + 1, batch_end, total_elements
                    ))
                
                # Procesar lote
                for idx, element in enumerate(batch):
                    global_idx = batch_start + idx
                    
                    # Verificar cancelación
                    if cancellation_token and hasattr(cancellation_token, 'CancellationPending') and cancellation_token.CancellationPending:
                        logger.info("Exportación cancelada por el usuario")
                        return False, "Exportación cancelada"
                    
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
                        except Exception:  # nosa-lint: disable=NOSA006 - UI message pump during export, called per sheet; failure is harmless
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
            
            # Combine PDF — one merged file covering the whole selection.
            # Additive: runs regardless of whether individual per-sheet
            # PDFs were also produced above, since they're independent
            # checkboxes in the UI.
            if self.export_formats.get('pdf_combine'):
                if progress_callback:
                    progress_callback("\nGenerating combined PDF ({} elements, this can take a "
                                       "while for large selections)...".format(len(self.elements)))
                combined_ok = self.export_combined_pdf(progress_callback)
                if progress_callback:
                    progress_callback("Combined PDF: {}".format("SUCCESS" if combined_ok else "FAILED"))
                self.results['combined_pdf'] = combined_ok

            self.results['elapsed_time'] = time.time() - start_time

            return True, "Exportación completada"

        except Exception as e:
            return False, "Error: {}".format(str(e))

    def export_combined_pdf(self, progress_callback=None):
        """
        One merged PDF covering every element passed to this ExportManager,
        via Revit's native PDFExportOptions.Combine=True — a single
        doc.Export() call producing one file, not a client-side PDF merge.

        Root cause of the "FileName is an empty string or contains only
        whitespace" exception: when Combine=True, Revit itself requires
        PDFExportOptions.FileName to be set up front — that's how it knows
        what to call the merged file, since there's no longer one name per
        view for it to auto-generate. The previous version never set it,
        so Revit's own validation threw before writing anything. Setting it
        also means Revit writes directly to the final name — no more
        polling the folder for "the newest pdf" and renaming after the
        fact, which was a second, independent source of flakiness.
        """
        def _log(msg):
            logger.warning(msg)
            if progress_callback:
                progress_callback("  " + msg)
        try:
            target_name = Utils.sanitize_filename(self.combined_pdf_name)
            if not target_name or not target_name.strip():
                _log("Combined PDF: no valid file name configured — check the 'File name' "
                     "field on the Formats tab (combined_pdf_name resolved to '{}').".format(
                         self.combined_pdf_name))
                return False

            expected_path = os.path.join(self.output_folder, "{}.pdf".format(target_name))
            if not os.path.isabs(expected_path):
                _log("Combined PDF: destination path did not resolve to an absolute path: "
                     "'{}'.".format(expected_path))
                return False

            pdf_options = DB.PDFExportOptions()
            pdf_options.FileName = target_name  # required by Revit whenever Combine=True
            pdf_options.RasterQuality = self.preset_config['pdf_raster_quality']

            if self.force_black:
                try:
                    pdf_options.ColorDepth = DB.ColorDepthType.BlackLine
                except Exception:
                    try:
                        pdf_options.ColorDepth = DB.ColorDepthType.GrayScale
                    except Exception:  # nosa-lint: disable=NOSA006 - last step of a per-version ColorDepth enum fallback
                        pass
            elif 'pdf_color_depth' in self.preset_config:
                pdf_options.ColorDepth = self.preset_config['pdf_color_depth']

            pdf_options.HideCropBoundaries = True
            pdf_options.HideReferencePlane = True
            pdf_options.HideScopeBoxes = True
            pdf_options.HideUnreferencedViewTags = True
            pdf_options.MaskCoincidentLines = False
            pdf_options.StopOnError = False
            pdf_options.Combine = True

            view_ids = List[DB.ElementId]()
            for el in self.elements:
                view_ids.Add(el.Id)

            # Clear a stale file from a previous run so a False/exception
            # below can't be mistaken for success against leftover output.
            if os.path.exists(expected_path):
                try:
                    os.remove(expected_path)
                except Exception as e:
                    _log("Combined PDF: could not remove existing file before export — "
                         "'{}' ({}). It may be open in another program.".format(expected_path, e))
                    return False

            success = self.doc.Export(self.output_folder, view_ids, pdf_options)
            if not success:
                _log("Combined PDF: Document.Export() returned False for {} element(s) — "
                     "Revit rejected the combine request (check that every selected "
                     "sheet/view can actually be printed).".format(len(self.elements)))
                return False

            # Revit writes directly to expected_path now (FileName is set),
            # but a large combined file can still take a while to finish —
            # poll for it instead of trusting the return value alone.
            timeout = max(15.0, len(self.elements) * 2.0)
            deadline = time.time() + timeout
            while time.time() < deadline and not os.path.exists(expected_path):
                time.sleep(0.2)

            if not os.path.exists(expected_path):
                after_files = sorted(f for f in os.listdir(self.output_folder) if f.lower().endswith('.pdf'))
                _log("Combined PDF: expected file '{}' did not appear after waiting {:.0f}s. "
                     "Document.Export() reported success, so Revit may still be writing a very "
                     "large file — try again, or check the destination folder manually. "
                     "PDFs currently there: {}".format(expected_path, timeout, after_files or "(none)"))
                return False

            return True

        except Exception as e:
            _log("Combined PDF: exception during export — {} (FileName was '{}')".format(
                e, self.combined_pdf_name))
            logger.error("Error exporting combined PDF", e)
            return False

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
                    except Exception:  # nosa-lint: disable=NOSA006 - last step of a per-version ColorDepth enum fallback
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

    def _snapshot_folder(self):
        """Set of every filename currently in the output folder."""
        try:
            return set(os.listdir(self.output_folder))
        except Exception:
            return set()

    def _cleanup_auto_images(self, before_files):
        """
        Delete any raster image file that appeared in the output folder
        during a DWG/DXF export (Revit's own side effect — see
        _AUTO_IMAGE_EXTS above). Never touches files that already existed
        before this export call. Returns the number of files removed.
        """
        try:
            after_files = self._snapshot_folder()
        except Exception:
            return 0
        new_files = after_files - before_files
        removed = 0
        for name in new_files:
            if not name.lower().endswith(self._AUTO_IMAGE_EXTS):
                continue
            try:
                os.remove(os.path.join(self.output_folder, name))
                removed += 1
            except Exception as e:
                logger.warning("Could not remove auto-exported image '{}': {}".format(name, e))
        if removed and self.progress_callback:
            self.progress_callback("     🧹 Removed {} auto-exported image file(s)".format(removed))
        return removed

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
                    except Exception:  # nosa-lint: disable=NOSA006 - last step of a per-version ColorDepth enum fallback
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
    
    def _build_dwg_options(self):
        """
        DWGExportOptions for this export run. If self.dwg_setup_name points
        to a DWG Export Setup already saved in the document (Manage >
        Export Setups > DWG), load it as-is — that's the user's own
        AutoCAD layer standard, so we don't override it beyond forcing the
        one behaviour this plugin always wants (merged views). Falls back
        to the fixed NOSA quality preset when no setup is selected, or if
        loading the named setup fails for any reason.
        """
        if self.dwg_setup_name:
            try:
                opts = DB.DWGExportOptions.GetPredefinedOptions(self.doc, self.dwg_setup_name)
                if opts is not None:
                    opts.MergedViews = True
                    return opts
            except Exception as e:
                logger.warning("Could not load DWG export setup '{}', using default preset: {}".format(
                    self.dwg_setup_name, e))

        dwg_options = DB.DWGExportOptions()
        dwg_options.MergedViews = True
        dwg_options.FileVersion = self.preset_config['dwg_version']
        dwg_options.Colors = DB.ExportColorMode.IndexColors if self.force_black else self.preset_config['dwg_colors']
        dwg_options.PropOverrides = DB.PropOverrideMode.ByEntity
        dwg_options.SharedCoords = True
        dwg_options.TargetUnit = DB.ExportUnit.Default
        try:
            if hasattr(dwg_options, 'LayerSettings'):
                dwg_options.LayerSettings = DB.ExportLayerOptions.AIA
        except Exception:
            log_swallowed(_LOG, u'_build_dwg_options')
        return dwg_options

    def export_view_dwg(self, view, filename):
        """Exporta view a DWG"""
        try:
            debug_print("    - Starting DWG export for view: **{}**".format(filename))
            dwg_options = self._build_dwg_options()

            view_set = List[DB.ElementId]()
            view_set.Add(view.Id)

            # Note: doc.Export for DWG needs filename without extension?
            # Revit API signature: Export(folder, name, views, options)
            before_files = self._snapshot_folder()
            success = self.doc.Export(self.output_folder, filename, view_set, dwg_options)
            debug_print("      - doc.Export(DWG) returned: {}".format(success))
            self._cleanup_auto_images(before_files)

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
                    log_swallowed(_LOG, u'export_view_dxf')

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
            before_files = self._snapshot_folder()
            success = self.doc.Export(self.output_folder, filename, view_set, dxf_options)
            self._cleanup_auto_images(before_files)

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
                except Exception: log_swallowed(_LOG, u'export_sheet_dwg')

            dwg_options = self._build_dwg_options()

            view_set = List[DB.ElementId]()
            view_set.Add(sheet.Id)

            before_files = self._snapshot_folder()
            success = self.doc.Export(self.output_folder, filename, view_set, dwg_options)
            # debug_print("      - doc.Export(DWG) returned: {}".format(success))
            self._cleanup_auto_images(before_files)

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
                    log_swallowed(_LOG, u'export_sheet_dxf')

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

            before_files = self._snapshot_folder()
            success = self.doc.Export(self.output_folder, filename, view_set, dxf_options)
            self._cleanup_auto_images(before_files)

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
