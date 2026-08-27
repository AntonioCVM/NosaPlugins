# -*- coding: utf-8 -*-
"""
Tests puros para rebar_schedule.py (F5).
Verifican lógica de agrupación, cálculos y export (sin Revit).
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys
import os
import tempfile

# Agregar lib/ al path
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from rebar_schedule import SchedulePosition, get_summary_stats


def test_schedule_position_init():
    """Verifica que SchedulePosition se inicializa correctamente."""
    pos = SchedulePosition(u'F1-01')
    assert pos.mark == u'F1-01'
    assert pos.count == 0
    assert pos.bars == []
    assert pos.total_length_mm == 0.0
    print('[PASS] SchedulePosition initializes correctly')


def test_schedule_position_add_bar():
    """Verifica que add_bar() incrementa count."""
    pos = SchedulePosition(u'F1-01')
    pos.add_bar(123)
    pos.add_bar(124)
    assert pos.count == 2
    assert len(pos.bars) == 2
    assert pos.bars == [123, 124]
    print('[PASS] add_bar() increments count')


def test_schedule_position_compute_totals():
    """Verifica cálculo de longitud total."""
    pos = SchedulePosition(u'F1-01')
    pos.unit_length_mm = 2500.0
    pos.add_bar(123)
    pos.add_bar(124)
    pos.add_bar(125)
    pos.compute_totals()
    assert pos.count == 3
    assert pos.total_length_mm == 7500.0
    print('[PASS] compute_totals() calculates correctly')


def test_get_summary_stats():
    """Verifica estadísticas sumarias."""
    schedule_data = [
        {
            'mark': u'F1-01',
            'host_mark': u'F1',
            'layer': u'bottom_x',
            'diameter_mm': 12,
            'shape_code': u'00',
            'shape_params': u'A=2000',
            'count': 10,
            'unit_length_mm': 2000.0,
            'total_length_mm': 20000.0
        },
        {
            'mark': u'F1-02',
            'host_mark': u'F1',
            'layer': u'bottom_y',
            'diameter_mm': 12,
            'shape_code': u'00',
            'shape_params': u'A=2500',
            'count': 8,
            'unit_length_mm': 2500.0,
            'total_length_mm': 20000.0
        },
        {
            'mark': u'F1-03',
            'host_mark': u'F1',
            'layer': u'top_x',
            'diameter_mm': 16,
            'shape_code': u'51',
            'shape_params': u'A=300;B=2000;C=300;R=50',
            'count': 5,
            'unit_length_mm': 2700.0,
            'total_length_mm': 13500.0
        }
    ]
    
    stats = get_summary_stats(schedule_data)
    
    assert stats['total_positions'] == 3
    assert stats['total_bars'] == 23  # 10 + 8 + 5
    assert stats['total_length_m'] == 53.5  # (20000 + 20000 + 13500) / 1000
    
    # Por diámetro
    assert 12 in stats['by_diameter']
    assert 16 in stats['by_diameter']
    assert stats['by_diameter'][12]['count'] == 18  # 10 + 8
    assert stats['by_diameter'][12]['length_m'] == 40.0  # (20000 + 20000) / 1000
    assert stats['by_diameter'][16]['count'] == 5
    assert stats['by_diameter'][16]['length_m'] == 13.5
    
    print('[PASS] get_summary_stats() calculates correctly')


def test_export_csv_creates_file():
    """Verifica que export_csv() crea un archivo válido."""
    schedule_data = [
        {
            'mark': u'F1-01',
            'host_mark': u'F1',
            'layer': u'bottom_x',
            'diameter_mm': 12,
            'shape_code': u'00',
            'shape_params': u'A=2000',
            'count': 10,
            'unit_length_mm': 2000.0,
            'total_length_mm': 20000.0
        }
    ]
    
    # Crear archivo temporal
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    try:
        from rebar_schedule import export_csv
        result = export_csv(schedule_data, temp_path)
        assert result == True
        
        # Verificar que el archivo existe y tiene contenido
        assert os.path.exists(temp_path)
        with open(temp_path, 'rb') as f:
            content = f.read()
            assert b'mark' in content
            assert b'F1-01' in content
            assert b'2000' in content
        
        print('[PASS] export_csv() creates valid file')
    
    finally:
        # Limpiar
        if os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == '__main__':
    test_schedule_position_init()
    test_schedule_position_add_bar()
    test_schedule_position_compute_totals()
    test_get_summary_stats()
    test_export_csv_creates_file()
    print('\n[SUCCESS] All rebar_schedule tests passed (5/5)')
