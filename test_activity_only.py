#!/usr/bin/env python3
"""
Тест только ACTIVITY фильтрации из bundle_analyzer.py
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_activity_only():
    """Тест только activity фильтрации"""
    tester = TokenFilterTester()
    
    # Проверяем директорию tokens_logs
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем файлы для теста
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    
    if not log_files:
        print(f"❌ В директории {tokens_logs_dir} нет .log файлов")
        return
    
    print(f"🚀 ТЕСТ ACTIVITY ФИЛЬТРАЦИИ")
    print(f"📊 Найдено {len(log_files)} файлов логов токенов")
    print(f"🔍 Тестируем первые 5 токенов:")
    
    activity_passed = 0
    activity_rejected = 0
    
    # Тестируем первые 5 токенов
    for i, log_file in enumerate(log_files[:5]):
        print(f"\n--- Токен {i+1}: {log_file} ---")
        log_path = os.path.join(tokens_logs_dir, log_file)
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            print(f"Токен: {result['token_id']}")
            print(f"Решение: {result['decision']}")
            print(f"Причина: {result['reason']}")
            
            if result['decision'] == 'WOULD_SEND':
                activity_passed += 1
                print("🚀 ✅ ПРОШЕЛ ACTIVITY ФИЛЬТРАЦИЮ!")
            else:
                activity_rejected += 1
                print("❌ НЕ ПРОШЕЛ ACTIVITY ФИЛЬТРАЦИЮ")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            activity_rejected += 1
    
    print(f"\n📊 ИТОГИ ACTIVITY ТЕСТА:")
    print(f"✅ Прошли фильтрацию: {activity_passed}")
    print(f"❌ Не прошли: {activity_rejected}")
    print(f"🎯 Процент прохождения: {activity_passed/(activity_passed+activity_rejected)*100:.1f}%")
    
    print(f"\n🔧 КРИТЕРИИ ACTIVITY ФИЛЬТРАЦИИ:")
    print(f"   • Холдеры: 30-130")
    print(f"   • Максимум: ≤150 холдеров")
    print(f"   • Ликвидность: ≥$10,000")
    print(f"   • Рост холдеров: ≥2900/мин")
    print(f"   • Dev %: ≤2%")
    print(f"   • Снайперы: ≤20 (≤3.5% или ≤5% с exit)")
    print(f"   • Инсайдеры: ≤15% или ≤22% с exit")
    print(f"   • + проверка подозрительных паттернов")

if __name__ == "__main__":
    asyncio.run(test_activity_only())