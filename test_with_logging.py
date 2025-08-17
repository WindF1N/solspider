#!/usr/bin/env python3
"""
Демонстрация детального логирования результатов в test_filter.log
"""

import asyncio
import os
import time
from test_filter import TokenFilterTester

async def demo_logging():
    """Демонстрация логирования результатов"""
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
    
    # Ограничиваем для демонстрации
    demo_files = log_files[:20]  # Берем первые 20 для демо
    
    print(f"📄 ДЕМО ДЕТАЛЬНОГО ЛОГИРОВАНИЯ В test_filter.log")
    print(f"🔍 Обрабатываем {len(demo_files)} токенов для демонстрации")
    
    # Создаем временную директорию для демо
    demo_dir = '/tmp/demo_tokens_logs'
    os.makedirs(demo_dir, exist_ok=True)
    
    # Копируем файлы для демо
    for log_file in demo_files:
        src = os.path.join(tokens_logs_dir, log_file)
        dst = os.path.join(demo_dir, log_file)
        if not os.path.exists(dst):
            os.symlink(src, dst)
    
    print(f"🚀 Запуск с логированием в test_filter.log...")
    
    start_time = time.time()
    
    # Запускаем анализ с логированием
    results = await tester.analyze_all_tokens_with_full_criteria(demo_dir)
    
    total_time = time.time() - start_time
    
    print(f"\n✅ ДЕМО ЗАВЕРШЕНО!")
    print(f"⏱️ Время: {total_time:.1f} секунд")
    print(f"📊 Обработано: {len(results)} токенов")
    
    # Статистика
    activity_passed = sum(1 for r in results if r.get('decision') == 'WOULD_SEND')
    activity_rejected = sum(1 for r in results if r.get('decision') == 'WOULD_REJECT')
    blacklisted = sum(1 for r in results if r.get('decision') == 'BLACKLISTED')
    errors = sum(1 for r in results if r.get('decision') == 'ERROR')
    no_data = sum(1 for r in results if r.get('decision') == 'NO_DATA')
    
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    print(f"🚀 ACTIVITY прошли: {activity_passed}")
    print(f"❌ Отклонены: {activity_rejected}")
    print(f"⚫ Черный список: {blacklisted}")
    print(f"💥 Ошибки: {errors}")
    print(f"📊 Нет данных: {no_data}")
    
    # Показываем примеры из лога
    if os.path.exists('test_filter.log'):
        print(f"\n📄 СОДЕРЖИМОЕ test_filter.log (последние 10 строк):")
        with open('test_filter.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(f"   {line.strip()}")
    
    # Очищаем демо директорию
    import shutil
    shutil.rmtree(demo_dir, ignore_errors=True)
    
    print(f"\n🎯 ДЕМО ИНФОРМАЦИЯ:")
    print(f"📄 Все результаты записаны в: test_filter.log")
    print(f"📊 Формат записи: TOKEN_ID | DECISION | TYPE | METRICS | REASON")
    print(f"✅ Прошедшие: PREFIX '✅ ACTIVITY PASS'")
    print(f"❌ Отклоненные: PREFIX '❌ ACTIVITY REJECT'")
    print(f"⚫ Черный список: PREFIX '⚫ BLACKLISTED'")
    print(f"💥 Ошибки: PREFIX '💥 ERROR'")

if __name__ == "__main__":
    asyncio.run(demo_logging())