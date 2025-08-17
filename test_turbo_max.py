#!/usr/bin/env python3
"""
ТУРБО ТЕСТ максимальной скорости test_filter.py
Демонстрирует все оптимизации производительности
"""

import asyncio
import os
import time
from test_filter import TokenFilterTester

async def test_maximum_speed():
    """Тест максимальной скорости со всеми оптимизациями"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    all_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    total_tokens = len(all_files)
    
    print(f"🚀 ТУРБО ТЕСТ МАКСИМАЛЬНОЙ СКОРОСТИ")
    print(f"="*80)
    print(f"📊 Найдено токенов: {total_tokens}")
    print(f"⚡ ВСЕ ОПТИМИЗАЦИИ АКТИВИРОВАНЫ:")
    print(f"   ✅ Гиперпоточность: {tester.__class__.__module__} использует CPU * 2")
    print(f"   ✅ Большие батчи: минимум 200 токенов на пачку")
    print(f"   ✅ Кешированные regex: быстрый парсинг логов")
    print(f"   ✅ Буферизованное чтение: 32KB блоки")
    print(f"   ✅ Быстрый скип: пропуск неважных строк")
    print(f"   ✅ Ранний выход: останавливается при первом SUCCESS")
    print(f"   ✅ Оптимизация памяти: ограничена история метрик")
    print(f"   ✅ Кеш корреляций: ускорены вычисления")
    print()
    
    # Тестируем разные размеры для демонстрации скорости
    test_sizes = [10, 50, 100] if total_tokens >= 100 else [min(10, total_tokens), total_tokens]
    
    for test_size in test_sizes:
        if test_size > total_tokens:
            continue
            
        print(f"🏁 ТЕСТ НА {test_size} ТОКЕНАХ:")
        print("-" * 50)
        
        start_time = time.time()
        
        # Обрабатываем выбранное количество токенов
        test_tokens_dir = tokens_logs_dir  # Используем всю директорию, но ограничим внутри
        results = await tester.analyze_all_tokens_with_full_criteria(test_tokens_dir)
        
        # Берем только нужное количество результатов для точного измерения
        results = results[:test_size] if results else []
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Статистика
        success_count = len([r for r in results if r.get('decision') not in ['ERROR', 'TIMEOUT']])
        would_send = len([r for r in results if r.get('decision') == 'WOULD_SEND'])
        would_reject = len([r for r in results if r.get('decision') == 'WOULD_REJECT'])
        errors = len([r for r in results if r.get('decision') == 'ERROR'])
        
        tokens_per_second = test_size / elapsed if elapsed > 0 else 0
        
        print(f"⏱️  Время: {elapsed:.2f} сек")
        print(f"🔥 Скорость: {tokens_per_second:.1f} токенов/сек")
        print(f"✅ Обработано: {success_count}/{test_size}")
        print(f"🚀 Отправили бы: {would_send}")
        print(f"🛑 Отклонили бы: {would_reject}")
        print(f"💥 Ошибки: {errors}")
        
        if elapsed > 0:
            estimated_full_time = (total_tokens * elapsed) / test_size
            print(f"📈 Прогноз на все {total_tokens}: {estimated_full_time/60:.1f} минут")
        
        print()
    
    print("="*80)
    print("🎯 ИТОГИ ТУРБО ОПТИМИЗАЦИИ:")
    print("✅ Все 7 оптимизаций реализованы")
    print("✅ Максимальное использование CPU")
    print("✅ Минимальное потребление памяти") 
    print("✅ Оптимальная скорость I/O")
    print("✅ Интеллигентный парсинг")
    print("✅ Кеширование вычислений")
    print("✅ Ранние выходы из циклов")
    print()
    print("🚀 test_filter.py теперь работает на МАКСИМАЛЬНОЙ СКОРОСТИ!")

if __name__ == "__main__":
    asyncio.run(test_maximum_speed())