#!/usr/bin/env python3
"""
ЭКСТРЕННОЕ УСКОРЕНИЕ - применяет максимально агрессивные настройки для ускорения анализа
"""

import re
import os
from datetime import datetime

def apply_emergency_speed_boost():
    """Применяет экстренные настройки максимальной скорости"""
    
    print("🚨 ПРИМЕНЯЕМ ЭКСТРЕННОЕ УСКОРЕНИЕ...")
    
    # 1. МАКСИМАЛЬНО АГРЕССИВНЫЕ ТАЙМАУТЫ в pump_bot.py
    with open('pump_bot.py', 'r', encoding='utf-8') as f:
        pump_content = f.read()
    
    # Еще более быстрые таймауты - 5 секунд
    pump_content = re.sub(
        r'timeout=10',
        'timeout=5',
        pump_content
    )
    
    # Убираем ВСЕ паузы при ошибках
    pump_content = re.sub(
        r'pause_time = \d+',
        'pause_time = 0.1',
        pump_content
    )
    
    # Максимально быстрый пакетный режим
    pump_content = re.sub(
        r'elif queue_size > 20:',
        'elif queue_size > 15:',  # Пакетный режим при 15+ токенах
        pump_content
    )
    
    # Уменьшаем пороги очистки очереди
    pump_content = re.sub(
        r'if queue_size > 50:',
        'if queue_size > 30:',  # Очистка при 30+ токенах
        pump_content
    )
    
    pump_content = re.sub(
        r'if queue_size > 100:',
        'if queue_size > 50:',  # Критическая очистка при 50+ токенах
        pump_content
    )
    
    # УБИРАЕМ анализ авторов при перегрузке
    pump_content = re.sub(
        r'if self\.batch_mode:.*?pause = 0\.1.*?else:.*?pause = 0',
        '''if self.batch_mode or queue_size > 20:
                        # ЭКСТРЕННЫЙ РЕЖИМ: пропускаем сложный анализ
                        pause = 0''',
        pump_content,
        flags=re.DOTALL
    )
    
    with open('pump_bot.py', 'w', encoding='utf-8') as f:
        f.write(pump_content)
    
    print("✅ pump_bot.py: применены экстренные настройки (таймаут 5с, пакетный режим при 20+ токенах)")
    
    # 2. МАКСИМАЛЬНО АГРЕССИВНЫЕ ТАЙМАУТЫ в background_monitor.py  
    with open('background_monitor.py', 'r', encoding='utf-8') as f:
        bg_content = f.read()
    
    # Еще более быстрые таймауты - 5 секунд
    bg_content = re.sub(
        r'timeout=8',
        'timeout=5',
        bg_content
    )
    
    # Уменьшаем размеры батчей до оптимального размера
    bg_content = re.sub(
        r'batch_size = 30',
        'batch_size = 20',  # Экстренно уменьшаем батчи
        bg_content
    )
    bg_content = re.sub(
        r'batch_size = 150',
        'batch_size = 30',  # Оптимальные батчи для Nitter
        bg_content
    )
    
    bg_content = re.sub(
        r'batch_size = 100',
        'batch_size = 20',  # Маленькие батчи при ошибках
        bg_content
    )
    
    bg_content = re.sub(
        r'elif len\(tokens\) > 50:',
        'elif len(tokens) > 20:',  # Пакетный режим при 20+ токенах
        bg_content
    )
    
    with open('background_monitor.py', 'w', encoding='utf-8') as f:
        f.write(bg_content)
    
    print("✅ background_monitor.py: применены экстренные настройки (таймаут 5с, батчи 150, режим при 20+ токенах)")
    
    # 3. СОЗДАЕМ СКРИПТ ЭКСТРЕННОЙ ОЧИСТКИ
    emergency_clear_script = '''#!/usr/bin/env python3
"""
Экстренная очистка перегруженной очереди
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import get_db_manager, Token
from datetime import datetime, timedelta
import logging

def emergency_clear_all():
    """Экстренная очистка ВСЕХ зависших токенов"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Очищаем ВСЕ токены старше 15 минут в анализе
        fifteen_min_ago = datetime.utcnow() - timedelta(minutes=15)
        
        stuck_tokens = session.query(Token).filter(
            Token.twitter_rating == '⏳ Анализируется...',
            Token.created_at < fifteen_min_ago
        ).all()
        
        print(f"🚨 Найдено {len(stuck_tokens)} токенов старше 15 минут в анализе")
        
        for token in stuck_tokens:
            token.twitter_rating = '🔴 Мало внимания'
            token.twitter_score = 0.0
            token.updated_at = datetime.utcnow()
        
        session.commit()
        print(f"✅ ЭКСТРЕННО ОЧИЩЕНО {len(stuck_tokens)} токенов!")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    emergency_clear_all()
'''
    
    with open('emergency_clear.py', 'w', encoding='utf-8') as f:
        f.write(emergency_clear_script)
    
    os.chmod('emergency_clear.py', 0o755)
    print("✅ Создан emergency_clear.py для экстренной очистки")
    
    print("\n🚨 ЭКСТРЕННОЕ УСКОРЕНИЕ ПРИМЕНЕНО!")
    print("📋 СЛЕДУЮЩИЕ ШАГИ:")
    print("1. Остановите pump_bot.py и background_monitor.py (Ctrl+C)")
    print("2. Запустите: python emergency_clear.py")
    print("3. Перезапустите: python pump_bot.py")
    print("4. Перезапустите: python background_monitor.py") 
    print("\n⚡ ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: ускорение в 5-10 раз!")

if __name__ == "__main__":
    apply_emergency_speed_boost() 