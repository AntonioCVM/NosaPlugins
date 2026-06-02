# -*- coding: utf-8 -*-
import os
import datetime
import traceback
import sys

class Logger:
    """Sistema de logging mejorado con categorías y archivo persistente"""
    
    LOG_LEVELS = {
        'DEBUG': 0,
        'INFO': 1,
        'WARNING': 2,
        'ERROR': 3,
        'CRITICAL': 4
    }
    
    def __init__(self, log_dir=None, level='INFO', echo_to_console=False):
        self.level = self.LOG_LEVELS.get(level, 1)
        self.logs = []
        self.session_start = datetime.datetime.now()
        self.echo_to_console = echo_to_console
        
        if not log_dir:
             # Default to extension log directory
            log_dir = os.path.join(
                os.getenv('APPDATA'),
                'pyRevit',
                'Extensions',
                'NOSA.extension',
                'Logs'
            )
            
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except (OSError, IOError) as ex:
                sys.stderr.write("nosa_utils.logging: could not create log dir {}: {}\n".format(log_dir, ex))
        
        self.log_file = os.path.join(
            log_dir,
            'nosa_log_{}.txt'.format(
                self.session_start.strftime('%Y%m%d_%H%M%S')
            )
        )
    
    def _should_log(self, level):
        return self.LOG_LEVELS.get(level, 1) >= self.level
    
    def _write_log(self, level, message, exception=None):
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'message': message,
            'exception': str(exception) if exception else None
        }
        
        log_line = "[{}] [{}] {}\n".format(timestamp, level, message)
        if exception:
            log_line += "Exception: {}\n".format(str(exception))
            log_line += "Traceback: {}\n".format(traceback.format_exc())
        
        self.logs.append(log_entry)
        
        if self.echo_to_console:
            print(log_line)
        
        # Write to file
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_line)
        except (OSError, IOError) as ex:
            sys.stderr.write("nosa_utils.logging: could not append log: {}\n".format(ex))
    
    def debug(self, message):
        if self._should_log('DEBUG'):
            self._write_log('DEBUG', message)
    
    def info(self, message):
        if self._should_log('INFO'):
            self._write_log('INFO', message)
    
    def warning(self, message, exception=None):
        if self._should_log('WARNING'):
            self._write_log('WARNING', message, exception)
    
    def error(self, message, exception=None):
        if self._should_log('ERROR'):
            self._write_log('ERROR', message, exception)
    
    def critical(self, message, exception=None):
        if self._should_log('CRITICAL'):
            self._write_log('CRITICAL', message, exception)
    
    def get_log_summary(self):
        """Obtiene resumen de logs de la sesión"""
        summary = {
            'total': len(self.logs),
            'by_level': {},
            'errors': [],
            'warnings': []
        }
        
        for log in self.logs:
            level = log['level']
            summary['by_level'][level] = summary['by_level'].get(level, 0) + 1
            
            if level == 'ERROR' or level == 'CRITICAL':
                summary['errors'].append(log)
            elif level == 'WARNING':
                summary['warnings'].append(log)
        
        return summary
    
    def export_log(self, output_path=None):
        """Exporta log completo a archivo"""
        if not output_path:
            output_path = self.log_file.replace('.txt', '_export.txt')
        
        try:
            with open(output_path, 'w') as f:
                f.write("="*80 + "\n")
                f.write("NOSA EXTENSION - LOG DE SESIÓN\n")
                f.write("="*80 + "\n")
                f.write("Inicio: {}\n".format(self.session_start.strftime('%Y-%m-%d %H:%M:%S')))
                f.write("Fin: {}\n".format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                f.write("="*80 + "\n\n")
                
                summary = self.get_log_summary()
                f.write("RESUMEN:\n")
                f.write("Total de entradas: {}\n".format(summary['total']))
                for level, count in summary['by_level'].items():
                    f.write("  {}: {}\n".format(level, count))
                f.write("\n" + "="*80 + "\n\n")
                
                for log in self.logs:
                    f.write("[{}] [{}] {}\n".format(
                        log['timestamp'],
                        log['level'],
                        log['message']
                    ))
                    if log['exception']:
                        f.write("  Exception: {}\n".format(log['exception']))
                    f.write("\n")
            
            return output_path
        except Exception as e:
            self._write_log('ERROR', "Error exporting log: {}".format(str(e)))
            return None
