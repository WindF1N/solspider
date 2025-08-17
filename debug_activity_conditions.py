#!/usr/bin/env python3
"""
Детальная диагностика почему токены не проходят activity фильтрацию
"""

import asyncio
import os
import logging
from test_filter import TokenFilterTester

# Включаем DEBUG логирование
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('debug_activity.log', mode='w', encoding='utf-8')
    ]
)

async def debug_activity_conditions():
    """Детальная диагностика activity условий"""
    tester = TokenFilterTester()
    
    # Проверяем директорию tokens_logs
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем файлы для диагностики
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    
    if not log_files:
        print(f"❌ В директории {tokens_logs_dir} нет .log файлов")
        return
    
    # Диагностируем первые 3 токена подробно
    debug_files = log_files[:3]
    
    print(f"🔬 ДЕТАЛЬНАЯ ДИАГНОСТИКА ACTIVITY CONDITIONS")
    print(f"="*80)
    print(f"📊 Диагностируем {len(debug_files)} токенов")
    print(f"📄 Подробные логи сохраняются в: debug_activity.log")
    print()
    
    for i, log_file in enumerate(debug_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i}. 🔍 ДИАГНОСТИКА ТОКЕНА: {token_id}")
        print("-" * 60)
        
        try:
            # Включаем подробное логирование для этого токена
            print(f"📋 Анализ начинается...")
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', 'Нет причины')
            snapshots_checked = result.get('snapshots_checked', 0)
            total_snapshots = result.get('total_snapshots', 0)
            
            print(f"📊 РЕЗУЛЬТАТ АНАЛИЗА:")
            print(f"   Решение: {decision}")
            print(f"   Проверено снапшотов: {snapshots_checked}/{total_snapshots}")
            print(f"   Причина: {reason}")
            
            if decision == 'WOULD_REJECT' and snapshots_checked > 0:
                print(f"🔍 Подробная диагностика сохранена в debug_activity.log")
                print(f"💡 Проверьте какие именно условия не выполняются")
            
        except Exception as e:
            print(f"💥 ОШИБКА: {e}")
        
        print()
    
    print("="*80)
    print("📋 ТИПИЧНЫЕ ПРИЧИНЫ ОТКЛОНЕНИЯ:")
    print("❌ holders_min: < 30 холдеров")
    print("❌ holders_max: > 130 холдеров") 
    print("❌ min_liquidity: < $10,000 ликвидности")
    print("❌ holders_growth: < 2900 холдеров/мин")
    print("❌ dev_percent_ok: > 2% у дева")
    print("❌ snipers_ok: > 20 снайперов или > 3.5%")
    print("❌ insiders_ok: > 15% инсайдеров")
    print("❌ bundlers_ok: недостаточно бандлеров")
    print("❌ корреляции: подозрительные паттерны")
    print()
    print(f"📄 Проверьте файл debug_activity.log для детальной диагностики!")

if __name__ == "__main__":
    asyncio.run(debug_activity_conditions())