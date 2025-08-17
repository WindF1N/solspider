#!/usr/bin/env python3
"""
Тестирование поснапшотной логики анализа токенов
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_snapshot_analysis():
    """Тестируем анализ каждого снапшота отдельно"""
    tester = TokenFilterTester()
    
    # Проверяем директорию tokens_logs
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем файлы для демо
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    
    if not log_files:
        print(f"❌ В директории {tokens_logs_dir} нет .log файлов")
        return
    
    # Тестируем на первых 5 токенах
    test_files = log_files[:5]
    
    print(f"🔬 ТЕСТИРОВАНИЕ ПОСНАПШОТНОЙ ЛОГИКИ АНАЛИЗА")
    print(f"="*60)
    print(f"📊 Тестируем {len(test_files)} токенов")
    print(f"🎯 Каждый снапшот проверяется как потенциальная точка уведомления")
    print()
    
    for i, log_file in enumerate(test_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i}. 🔍 АНАЛИЗ ТОКЕНА: {token_id}")
        print("-" * 50)
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', 'Нет причины')
            snapshots_checked = result.get('snapshots_checked', 0)
            total_snapshots = result.get('total_snapshots', 0)
            snapshot_number = result.get('snapshot_number', None)
            
            if decision == 'WOULD_SEND':
                print(f"✅ РЕЗУЛЬТАТ: {decision}")
                print(f"🎯 ПРОШЕЛ НА СНАПШОТЕ: #{snapshot_number} из {total_snapshots}")
                print(f"📊 ПРОВЕРЕНО СНАПШОТОВ: {snapshots_checked}")
                print(f"💡 ПРИЧИНА: {reason}")
            elif decision == 'WOULD_REJECT':
                print(f"❌ РЕЗУЛЬТАТ: {decision}")
                print(f"📊 ПРОВЕРЕНО СНАПШОТОВ: {snapshots_checked} из {total_snapshots}")
                print(f"💡 ПРИЧИНА: {reason}")
            elif decision == 'BLACKLISTED':
                print(f"⚫ РЕЗУЛЬТАТ: {decision}")
                print(f"💡 ПРИЧИНА: {reason}")
            elif decision == 'ERROR':
                print(f"💥 РЕЗУЛЬТАТ: {decision}")
                print(f"💡 ПРИЧИНА: {reason}")
            elif decision == 'NO_DATA':
                print(f"📊 РЕЗУЛЬТАТ: {decision}")
                print(f"💡 ПРИЧИНА: {reason}")
            else:
                print(f"❓ РЕЗУЛЬТАТ: {decision}")
                print(f"💡 ПРИЧИНА: {reason}")
                
        except Exception as e:
            print(f"💥 ОШИБКА: {e}")
        
        print()
    
    print("="*60)
    print("🎯 ЛОГИКА ПОСНАПШОТНОГО АНАЛИЗА:")
    print("1. Читаем лог строка за строкой")
    print("2. При каждом обновлении метрик создаем снапшот")  
    print("3. Проверяем activity_conditions на каждом снапшоте")
    print("4. Первый прошедший снапшот = WOULD_SEND")
    print("5. Если ни один не прошел = WOULD_REJECT")
    print()
    print("📈 ПРЕИМУЩЕСТВА:")
    print("✅ Имитирует реальное время bundle_analyzer.py")
    print("✅ Находит точный момент когда токен стал 'хорошим'")
    print("✅ Учитывает динамику изменения метрик")
    print("✅ Более точная фильтрация")

if __name__ == "__main__":
    asyncio.run(test_snapshot_analysis())