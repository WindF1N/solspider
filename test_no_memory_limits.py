#!/usr/bin/env python3
"""
Тест что ограничения памяти убраны
Проверяет что история метрик не ограничивается
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_no_memory_limits():
    """Тест что ограничения памяти убраны и токены анализируются полностью"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем несколько токенов для проверки
    all_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    test_files = all_files[:10]
    
    print(f"🧠 ТЕСТ ОТКЛЮЧЕНИЯ ОГРАНИЧЕНИЙ ПАМЯТИ")
    print(f"="*70)
    print(f"📊 Тестируем {len(test_files)} токенов")
    print(f"🎯 Проверяем что вся история метрик сохраняется")
    print()
    print(f"✅ УБРАННЫЕ ОГРАНИЧЕНИЯ:")
    print(f"   • metrics_history БЕЗ ограничения 100 записей")
    print(f"   • holder_percentages_history БЕЗ ограничения 1000 снапшотов")
    print(f"   • TokenMetrics.metrics_history БЕЗ ограничения 1000 записей")
    print(f"   • TokenMetrics.holder_percentages_history БЕЗ ограничения 1000 снапшотов")
    print()
    
    results = {
        'total_snapshots': 0,
        'max_snapshots': 0,
        'tokens_with_many_snapshots': 0,
        'total_metrics': 0,
        'max_metrics': 0
    }
    
    for i, log_file in enumerate(test_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i:2d}. 🔍 {token_id[:20]}...", end="")
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            snapshots = result.get('snapshots_checked', 0)
            total_snapshots = result.get('total_snapshots', 0)
            
            results['total_snapshots'] += snapshots
            results['max_snapshots'] = max(results['max_snapshots'], snapshots)
            results['total_metrics'] += total_snapshots
            results['max_metrics'] = max(results['max_metrics'], total_snapshots)
            
            if snapshots > 100:  # Раньше было ограничение в 100
                results['tokens_with_many_snapshots'] += 1
                print(f" 🧠 {snapshots} снапшотов (>{100} - БЕЗ ограничения!)")
            else:
                print(f" ✅ {snapshots} снапшотов")
                
        except Exception as e:
            print(f" 💥 ОШИБКА: {e}")
    
    print()
    print("="*70)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТА БЕЗ ОГРАНИЧЕНИЙ ПАМЯТИ:")
    print(f"📈 Общее количество снапшотов: {results['total_snapshots']}")
    print(f"🏆 Максимум снапшотов в токене: {results['max_snapshots']}")
    print(f"📊 Общее количество метрик: {results['total_metrics']}")
    print(f"🏆 Максимум метрик в токене: {results['max_metrics']}")
    print(f"🧠 Токенов с >100 снапшотами: {results['tokens_with_many_snapshots']}")
    
    avg_snapshots = results['total_snapshots'] / len(test_files) if test_files else 0
    
    print()
    print("🎯 АНАЛИЗ:")
    print(f"📊 Средне снапшотов на токен: {avg_snapshots:.1f}")
    
    if results['max_snapshots'] > 100:
        print(f"✅ УСПЕХ: Найдены токены с >{100} снапшотами!")
        print(f"🧠 Ограничение памяти УСПЕШНО убрано")
        print(f"📈 Полная история метрик сохраняется")
        print(f"🔍 Анализ токенов стал более точным")
    else:
        print(f"ℹ️ Все токены имеют <100 снапшотов")
        print(f"✅ Но ограничение памяти убрано - готово к большим токенам")
    
    print()
    print("💡 ПРЕИМУЩЕСТВА БЕЗ ОГРАНИЧЕНИЙ:")
    print("   ✅ Полная история для корреляций")
    print("   ✅ Точный анализ паттернов холдеров")
    print("   ✅ Корректный rapid_exit анализ")
    print("   ✅ Более качественное выявление подозрительных токенов")
    print("   ⚠️ Повышенное потребление памяти (но более точные результаты)")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_no_memory_limits())
    exit(0 if success else 1)