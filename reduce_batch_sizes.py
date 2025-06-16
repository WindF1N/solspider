#!/usr/bin/env python3
"""
УМЕНЬШЕНИЕ РАЗМЕРОВ БАТЧЕЙ - оптимизация для публичных Nitter серверов
"""

import re
import os
from datetime import datetime

def reduce_batch_sizes():
    """Уменьшает размеры батчей для снижения нагрузки на Nitter"""
    
    print("🔧 УМЕНЬШАЕМ РАЗМЕРЫ БАТЧЕЙ ДО 30...")
    
    # 1. Обновляем background_monitor.py
    if os.path.exists('background_monitor.py'):
        with open('background_monitor.py', 'r', encoding='utf-8') as f:
            bg_content = f.read()
        
        # Уменьшаем батчи до 30 (основной размер)
        bg_content = re.sub(
            r'batch_size = 150',
            'batch_size = 30',
            bg_content
        )
        
        # Уменьшаем батчи при ошибках до 20
        bg_content = re.sub(
            r'batch_size = 100',
            'batch_size = 20',
            bg_content
        )
        
        with open('background_monitor.py', 'w', encoding='utf-8') as f:
            f.write(bg_content)
        
        print("✅ background_monitor.py: батчи уменьшены до 30 (обычно) / 20 (при ошибках)")
    
    # 2. Обновляем pump_bot.py пороги очередей
    if os.path.exists('pump_bot.py'):
        with open('pump_bot.py', 'r', encoding='utf-8') as f:
            pump_content = f.read()
        
        # Уменьшаем пороги пакетного режима
        pump_content = re.sub(
            r'if queue_size > 30:',
            'if queue_size > 20:',
            pump_content
        )
        
        # Уменьшаем пороги очистки очереди
        pump_content = re.sub(
            r'if queue_size > 50:.*?# Уменьшено с 100 до 50',
            'if queue_size > 30:  # Уменьшено с 50 до 30',
            pump_content
        )
        
        pump_content = re.sub(
            r'if queue_size > 100:.*?# Уменьшено с 200 до 100',
            'if queue_size > 50:  # Уменьшено с 100 до 50',
            pump_content
        )
        
        with open('pump_bot.py', 'w', encoding='utf-8') as f:
            f.write(pump_content)
        
        print("✅ pump_bot.py: пороги очередей уменьшены (пакетный режим при 20+, очистка при 30+)")
    
    # 3. Обновляем emergency_speed_boost.py
    if os.path.exists('emergency_speed_boost.py'):
        with open('emergency_speed_boost.py', 'r', encoding='utf-8') as f:
            emergency_content = f.read()
        
        # Обновляем регулярные выражения в emergency_speed_boost
        emergency_content = re.sub(
            r"r'elif queue_size > 30:'",
            "r'elif queue_size > 20:'",
            emergency_content
        )
        
        emergency_content = re.sub(
            r"'elif queue_size > 20:',  # Пакетный режим при 20\+ токенах",
            "'elif queue_size > 15:',  # Пакетный режим при 15+ токенах",
            emergency_content
        )
        
        # Добавляем обновление новых порогов
        emergency_content = re.sub(
            r'# Уменьшаем размеры батчей до оптимального размера',
            '''# Уменьшаем размеры батчей до оптимального размера
    bg_content = re.sub(
        r'batch_size = 30',
        'batch_size = 20',  # Экстренно уменьшаем батчи
        bg_content
    )''',
            emergency_content
        )
        
        with open('emergency_speed_boost.py', 'w', encoding='utf-8') as f:
            f.write(emergency_content)
        
        print("✅ emergency_speed_boost.py: обновлены пороги для экстренного режима")
    
    print("\n🎯 ИТОГИ ОПТИМИЗАЦИИ:")
    print("• background_monitor: батчи 30 → 20 при ошибках")
    print("• pump_bot: пакетный режим при 20+ токенах (было 30+)")
    print("• pump_bot: очистка очереди при 30+ токенах (было 50+)")
    print("• pump_bot: критическая очистка при 50+ токенах (было 100+)")
    print("\n🚀 ЭФФЕКТ:")
    print("• Меньшая нагрузка на публичные Nitter серверы")
    print("• Снижение вероятности блокировок")
    print("• Более стабильная работа при высокой нагрузке")
    print("\n⚠️ РЕКОМЕНДАЦИЯ: перезапустите боты для активации изменений")

if __name__ == "__main__":
    reduce_batch_sizes() 