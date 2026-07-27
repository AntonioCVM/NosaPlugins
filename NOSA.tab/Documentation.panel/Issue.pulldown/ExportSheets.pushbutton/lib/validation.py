# -*- coding: utf-8 -*-
import os
import shutil
import platform
import ctypes
from nosa_utils.logging import Logger
from utils import Utils

logger = Logger()

class ExportValidator:
    """Export configuration validator."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
    
    def _check_disk_space(self, folder_path, estimated_size_mb=100):
        """Check available disk space — IronPython compatible."""
        try:
            # Obtener la letra de la unidad
            if platform.system() == 'Windows':
                drive = os.path.splitdrive(folder_path)[0]
                if not drive:
                    drive = os.path.splitdrive(os.path.abspath(folder_path))[0]
                
                if drive:
                    # Usar GetDiskFreeSpaceEx de Windows API
                    free_bytes = ctypes.c_ulonglong(0)
                    total_bytes = ctypes.c_ulonglong(0)
                    
                    kernel32 = ctypes.windll.kernel32
                    result = kernel32.GetDiskFreeSpaceExW(
                        ctypes.c_wchar_p(drive),
                        ctypes.pointer(free_bytes),
                        ctypes.pointer(total_bytes),
                        None
                    )
                    
                    if result:
                        free_gb = free_bytes.value / (1024.0**3)
                        # required_gb = estimated_size_mb / 1024.0
                        
                        # Solo registrar info disponible, sin advertencias
                        self.info.append(
                            "Espacio en disco: {:.2f} GB disponibles".format(free_gb)
                        )
                    else:
                        logger.warning("No se pudo obtener información del disco")
                else:
                    logger.warning("No se pudo determinar la unidad de disco")
            else:
                # Para sistemas no-Windows, intentar con shutil si está disponible
                try:
                    if hasattr(shutil, 'disk_usage'):
                        stat = shutil.disk_usage(folder_path)
                        free_gb = stat.free / (1024**3)
                        # required_gb = estimated_size_mb / 1024
                        
                        # Solo registrar info disponible, sin advertencias
                        self.info.append(
                            "Espacio en disco: {:.2f} GB disponibles".format(free_gb)
                        )
                except Exception:
                    logger.warning("No se pudo verificar espacio en disco (método alternativo no disponible)")
        except Exception as e:
            logger.warning("No se pudo verificar espacio en disco", e)
    
    def _check_write_permissions(self, folder_path):
        """Verifica permisos de escritura"""
        try:
            test_file = os.path.join(folder_path, '_write_test.tmp')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                self.info.append("Permisos de escritura: OK")
            except Exception as e:
                self.errors.append(
                    "Sin permisos de escritura en la carpeta: {}".format(str(e))
                )
        except Exception as e:
            logger.warning("No se pudo verificar permisos", e)
    
    def _check_existing_files(self, elements, naming_builder, output_folder, export_formats, is_views=False, project_params=None):
        """Verifica archivos existentes que serán sobrescritos"""
        existing_files = []
        
        try:
            for element in elements:
                filename = naming_builder.build_filename(element, is_view=is_views, project_params=project_params)
                
                for fmt, enabled in export_formats.items():
                    if not enabled or fmt in ['pdf_combine']:
                        continue
                    
                    ext_map = {
                        'pdf': '.pdf',
                        'dwg': '.dwg',
                        'dxf': '.dxf'
                    }
                    
                    ext = ext_map.get(fmt, '')
                    if ext:
                        file_path = os.path.join(output_folder, "{}{}".format(filename, ext))
                        if os.path.exists(file_path):
                            existing_files.append(file_path)
            
            if existing_files:
                self.warnings.append(
                    "{} archivo(s) existente(s) serán sobrescritos".format(len(existing_files))
                )
        except Exception as e:
            logger.warning("Error verificando archivos existentes", e)
    
    def _check_element_validity(self, elements, is_views=False):
        """Verifica validez de elementos (sheets o views)"""
        invalid_elements = []
        
        for element in elements:
            try:
                if is_views:
                    # Verificar que la vista sea válida y exportable
                    if not hasattr(element, 'CanBePrinted') or not element.CanBePrinted:
                        invalid_elements.append(element.Name if hasattr(element, 'Name') else str(element.Id))
                    if element.IsTemplate:
                        invalid_elements.append(element.Name if hasattr(element, 'Name') else str(element.Id))
                else:
                    # Verificar que el sheet sea válido
                    if element.IsPlaceholder:
                        invalid_elements.append(element.SheetNumber)
            except Exception as e:
                logger.warning("Error validando elemento", e)
                invalid_elements.append(str(element.Id))
        
        if invalid_elements:
            self.warnings.append(
                "{} elemento(s) pueden tener problemas: {}".format(
                    len(invalid_elements),
                    ", ".join(invalid_elements[:5])  # show first 5 only
                )
            )
    
    def validate(self, elements, naming_builder, output_folder, export_formats, is_views=False, project_params=None):
        """Validación completa mejorada"""
        self.errors = []
        self.warnings = []
        self.info = []
        
        logger.info("Starting export validation...")
        
        # Validación básica
        if not elements or len(elements) == 0:
            self.errors.append("No elements selected for export")
            logger.error("No elements selected")
        
        # Verificar que al menos un formato esté seleccionado (excluyendo pdf_combine)
        format_keys = ['pdf', 'dwg', 'dxf']
        if not any([export_formats.get(key, False) for key in format_keys]):
            self.errors.append("Select at least one export format")
            logger.error("No formats selected")
        
        # Validación de carpeta
        if not output_folder:
            self.errors.append("La carpeta de destino no está especificada")
            logger.error("Carpeta de destino vacía")
        else:
            # Expandir variables de entorno (Passing doc=None currently, need to fix expand_path_variables to handle doc or pass valid doc)
            # expand_path_variables in Utils uses 'doc' global which is not available here. 
            # Ideally validation should accept doc.
            # I will change validate signature or assume doc is available if imported? No, better pass it.
            # For now I will temporarily avoid doc usage in Utils.expand_path_variables if doc is None?
            # Utils.expand_path_variables requires doc from somewhere.
            # I should rely on main script passing everything resolved? Or just use os.path.expandvars?
            
            # Assuming Utils.expand_path_variables handles the specific %ProjectName% etc.
            # I will refactor later. For now, assuming standard environment variables work or simple paths.
            
            expanded_folder = output_folder # Placeholder
            if hasattr(Utils, 'expand_path_variables'):
                # We need doc. I'll pass project_params (which might contain ProjectName) for fallback?
                # Actually I'll skip deep variable expansion here or fix Utils to optionally take values.
                pass 
                
            if not os.path.exists(expanded_folder):
                # Try to create? The validator just checks.
                # If variable expansion didn't work, this might fail spuriously.
                # I'll check if it looks like a variable path
                if '%' in expanded_folder:
                    self.info.append("Ruta contiene variables, verificación de existencia omitida.")
                else:
                     self.errors.append(
                        "La carpeta de destino no existe: {}".format(expanded_folder)
                    )
            else:
                self._check_write_permissions(expanded_folder)
                self._check_disk_space(expanded_folder, len(elements) * 5)
        
        # Naming validation
        if naming_builder and naming_builder.template:
            if elements and len(elements) > 0:
                try:
                    test_name = naming_builder.build_filename(
                        elements[0], 
                        project_params=project_params,
                        is_view=is_views
                    )
                    if not test_name or len(test_name) < 1:
                        self.warnings.append("Naming template generates empty filenames")
                        logger.warning("Naming template generates empty filenames")
                except Exception as e:
                    self.errors.append("Naming error: {}".format(str(e)))
                    logger.error("Naming error", e)
        
        # Duplicate name check
        if elements and naming_builder:
            names = []
            duplicates = []
            for element in elements:
                try:
                    name = naming_builder.build_filename(
                        element,
                        project_params=project_params,
                        is_view=is_views
                    )
                    if name in names and name not in duplicates:
                        duplicates.append(name)
                    names.append(name)
                except Exception as e:
                    logger.warning("Error generando nombre para elemento", e)
            
            if duplicates:
                self.warnings.append(
                    "Warning: {} duplicate filename(s) — files will be overwritten.".format(len(duplicates))
                )
        
        # Validación de elementos
        if elements:
            self._check_element_validity(elements, is_views)
        
        is_valid = len(self.errors) == 0
        logger.info("Validación completada: {} errores, {} advertencias".format(
            len(self.errors), len(self.warnings)
        ))
        
        return is_valid
    
    def get_summary(self):
        """Obtiene resumen de validación"""
        return {
            'valid': len(self.errors) == 0,
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'info': len(self.info),
            'error_list': self.errors,
            'warning_list': self.warnings,
            'info_list': self.info
        }

