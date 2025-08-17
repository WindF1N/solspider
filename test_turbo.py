#!/usr/bin/env python3
"""
ТУРБО-тест параллельной обработки ACTIVITY фильтрации
"""

import asyncio
import os
import time
from test_filter import TokenFilterTester

async def turbo_test():
    """Турбо-тест только первых 50 токенов для демонстрации скорости"""
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
    
    # Ограничиваем для демонстрации
    test_files = log_files[:100]  # Берем первые 100 для демо
    
    print(f"🚀 ТУРБО-ТЕСТ ACTIVITY ФИЛЬТРАЦИИ")
    print(f"⚡ Параллельная обработка {len(test_files)} токенов")
    print(f"🔧 Процессоров: доступно ядер - будет использовано максимум")
    
    # Создаем временную директорию для теста
    test_dir = '/tmp/test_tokens_logs'
    os.makedirs(test_dir, exist_ok=True)
    
    # Копируем файлы для теста (символические ссылки для скорости)
    for log_file in test_files:
        src = os.path.join(tokens_logs_dir, log_file)
        dst = os.path.join(test_dir, log_file)
        if not os.path.exists(dst):
            os.symlink(src, dst)
    
    start_time = time.time()
    
    print(f"⏱️ Запуск турбо-обработки...")
    
    # Запускаем турбо-анализ
    results = await tester.analyze_all_tokens_with_full_criteria(test_dir)
    
    total_time = time.time() - start_time
    
    print(f"\n🎯 ТУРБО-РЕЗУЛЬТАТЫ:")
    print(f"⏱️ Время: {total_time:.1f} секунд")
    print(f"⚡ Скорость: {len(results)/total_time:.1f} токенов/сек")
    
    # Статистика
    activity_passed = sum(1 for r in results if r.get('decision') == 'WOULD_SEND')
    activity_rejected = sum(1 for r in results if r.get('decision') == 'WOULD_REJECT')
    blacklisted = sum(1 for r in results if r.get('decision') == 'BLACKLISTED')
    errors = sum(1 for r in results if r.get('decision') == 'ERROR')
    
    print(f"\n📊 РЕЗУЛЬТАТЫ ФИЛЬТРАЦИИ:")
    print(f"🚀 ACTIVITY прошли: {activity_passed}")
    print(f"❌ Отклонены: {activity_rejected}")
    print(f"⚫ Черный список: {blacklisted}")
    print(f"💥 Ошибки: {errors}")
    
    if activity_passed > 0:
        print(f"\n✅ Примеры прошедших ACTIVITY:")
        passed_examples = [r for r in results if r.get('decision') == 'WOULD_SEND'][:3]
        for example in passed_examples:
            print(f"   • {example['token_id']}: {example['reason']}")
    
    # Очищаем тестовую директорию
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    
    print(f"\n🎉 ТУРБО-ТЕСТ ЗАВЕРШЕН!")
    print(f"💪 Параллельная обработка работает на максимальной скорости!")

if __name__ == "__main__":
    asyncio.run(turbo_test())