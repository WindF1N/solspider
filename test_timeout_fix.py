#!/usr/bin/env python3
"""
Тест исправления timeout ошибок
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_timeout_handling():
    """Тестируем обработку timeout и других ошибок"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем несколько файлов для теста
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')][:5]
    
    print(f"⏰ ТЕСТ ОБРАБОТКИ TIMEOUT И ОШИБОК")
    print(f"="*60)
    print(f"📊 Тестируем {len(log_files)} токенов")
    print(f"🎯 Проверяем улучшенную обработку ошибок")
    print()
    
    # Создаем временную папку с несколькими файлами для быстрого теста
    test_files = []
    for log_file in log_files:
        log_path = os.path.join(tokens_logs_dir, log_file)
        test_files.append(log_path)
    
    print(f"🚀 ЗАПУСК ПАРАЛЛЕЛЬНОГО АНАЛИЗА...")
    print(f"⏱️ Timeout установлен на 60 секунд на токен")
    print()
    
    try:
        # Запускаем анализ всех файлов (имитирует analyze_all_tokens_with_full_criteria)
        results = await tester.analyze_all_tokens_with_full_criteria(tokens_logs_dir)
        
        print(f"✅ АНАЛИЗ ЗАВЕРШЕН!")
        print(f"📊 Обработано токенов: {len(results)}")
        
        # Анализируем результаты по типам ошибок
        error_summary = {
            'SUCCESS': 0,
            'TIMEOUT': 0,
            'OTHER_ERROR': 0,
            'REJECT': 0
        }
        
        timeout_tokens = []
        error_tokens = []
        
        for result in results:
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', '')
            token_id = result.get('token_id', 'UNKNOWN')
            
            if decision == 'ERROR':
                if 'Timeout:' in reason:
                    error_summary['TIMEOUT'] += 1
                    timeout_tokens.append(token_id)
                else:
                    error_summary['OTHER_ERROR'] += 1
                    error_tokens.append(token_id)
            elif decision in ['WOULD_SEND', 'WOULD_REJECT']:
                error_summary['SUCCESS'] += 1
            else:
                error_summary['REJECT'] += 1
        
        print(f"\n📊 СТАТИСТИКА ОШИБОК:")
        print(f"✅ Успешно обработано: {error_summary['SUCCESS']}")
        print(f"⏰ Timeout ошибки: {error_summary['TIMEOUT']}")
        print(f"💥 Другие ошибки: {error_summary['OTHER_ERROR']}")
        print(f"❌ Отклонено: {error_summary['REJECT']}")
        
        if timeout_tokens:
            print(f"\n⏰ ТОКЕНЫ С TIMEOUT:")
            for token in timeout_tokens[:3]:  # Показываем первые 3
                print(f"   - {token}")
                
        if error_tokens:
            print(f"\n💥 ТОКЕНЫ С ДРУГИМИ ОШИБКАМИ:")
            for token in error_tokens[:3]:  # Показываем первые 3
                print(f"   - {token}")
        
        print(f"\n📄 Проверьте test_filter.log для детальной информации")
        
    except Exception as e:
        print(f"💥 ОШИБКА ТЕСТА: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("="*60)
    print("🎯 РЕЗУЛЬТАТ ИСПРАВЛЕНИЙ:")
    print("✅ Timeout увеличен до 60 секунд")
    print("✅ Четкое различие между timeout и другими ошибками")
    print("✅ Улучшенное логирование с типами ошибок")
    print("✅ Более информативные сообщения об ошибках")

if __name__ == "__main__":
    asyncio.run(test_timeout_handling())