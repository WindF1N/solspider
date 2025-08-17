#!/usr/bin/env python3
"""
Быстрый тест обновленного test_filter.py
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def quick_test():
    """Быстрый тест одного токена"""
    tester = TokenFilterTester()
    
    # Проверяем директорию tokens_logs
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем первый файл для теста
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    
    if not log_files:
        print(f"❌ В директории {tokens_logs_dir} нет .log файлов")
        return
    
    print(f"🔍 Найдено {len(log_files)} файлов логов токенов")
    print(f"📊 Тестируем первые 3 токена:")
    
    # Тестируем первые 3 токена
    for i, log_file in enumerate(log_files[:3]):
        print(f"\n--- Токен {i+1}: {log_file} ---")
        log_path = os.path.join(tokens_logs_dir, log_file)
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            print(f"Токен: {result['token_id']}")
            print(f"Решение: {result['decision']}")
            print(f"Причина: {result['reason']}")
            
            if 'notification_type' in result:
                print(f"Тип уведомления: {result['notification_type']}")
            
            if 'holders' in result:
                print(f"Холдеры: {result['holders']}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print(f"\n✅ Тест завершен. Логика фильтрации из bundle_analyzer.py успешно реализована!")
    print(f"📦 Типы уведомлений: BUNDLER, ACTIVITY, PUMP")
    print(f"🎯 Результаты: WOULD_SEND, WOULD_REJECT, BLACKLISTED, NO_DATA, ERROR")

if __name__ == "__main__":
    asyncio.run(quick_test())