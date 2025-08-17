#!/usr/bin/env python3
"""
Тест логики анализа паттернов холдеров после прохождения activity conditions
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_holder_patterns_logic():
    """Тестируем правильную последовательность: сначала activity_conditions, потом паттерны холдеров"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Тестируем успешный токен и несколько других
    test_files = ['26YJjHymy3aS.log']  # Токен который отправлял уведомления
    
    # Добавляем еще несколько для тестирования
    all_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    test_files.extend(all_files[:3])  # Еще 3 случайных
    
    print(f"🔬 ТЕСТ ЛОГИКИ АНАЛИЗА ПАТТЕРНОВ ХОЛДЕРОВ")
    print(f"="*80)
    print(f"📊 Тестируем {len(test_files)} токенов")
    print(f"🎯 Проверяем: activity_conditions → holder_patterns → decision")
    print()
    
    results_summary = {
        'WOULD_SEND': 0,
        'WOULD_REJECT_CONDITIONS': 0,
        'WOULD_REJECT_PATTERNS': 0,
        'OTHER': 0
    }
    
    for i, log_file in enumerate(test_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        if not os.path.exists(log_path):
            continue
            
        token_id = log_file.replace('.log', '')
        
        print(f"{i}. 🔍 АНАЛИЗ: {token_id}")
        print("-" * 70)
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', 'Нет причины')
            all_conditions_passed = result.get('all_conditions_passed', False)
            healthy_patterns = result.get('healthy_holder_patterns', False)
            analyzed_snapshots = result.get('analyzed_snapshots', 0)
            
            print(f"📊 РЕЗУЛЬТАТ: {decision}")
            
            if decision == 'WOULD_SEND':
                results_summary['WOULD_SEND'] += 1
                print(f"🎉 ПОЛНЫЙ УСПЕХ!")
                print(f"   ✅ Activity conditions: ПРОШЛИ")
                print(f"   ✅ Holder patterns: ЗДОРОВЫЕ")
                if healthy_patterns:
                    print(f"   🔍 Проанализировано снапшотов: {analyzed_snapshots}")
                
            elif decision == 'WOULD_REJECT':
                if all_conditions_passed:
                    results_summary['WOULD_REJECT_PATTERNS'] += 1
                    print(f"🚨 ОТКЛОНЕН ПО ПАТТЕРНАМ ХОЛДЕРОВ")
                    print(f"   ✅ Activity conditions: ПРОШЛИ")
                    print(f"   ❌ Holder patterns: ПОДОЗРИТЕЛЬНЫЕ")
                    print(f"   🔍 Проанализировано снапшотов: {analyzed_snapshots}")
                    
                    suspicious_patterns = result.get('suspicious_patterns', [])
                    if suspicious_patterns:
                        print(f"   ⚠️ Подозрительные паттерны: {suspicious_patterns[:2]}")
                else:
                    results_summary['WOULD_REJECT_CONDITIONS'] += 1
                    print(f"❌ ОТКЛОНЕН ПО ACTIVITY CONDITIONS")
                    print(f"   ❌ Activity conditions: НЕ ПРОШЛИ")
                    print(f"   📊 Анализ паттернов: НЕ ПРОВОДИЛСЯ")
                    
                    snapshots_checked = result.get('snapshots_checked', 0)
                    best_snapshot = result.get('best_snapshot', {})
                    if best_snapshot:
                        print(f"   🏆 Лучший снапшот: #{best_snapshot.get('snapshot_number', '?')}")
                        print(f"   ✅ Макс. условий: {best_snapshot.get('passed_conditions', 0)}")
            else:
                results_summary['OTHER'] += 1
                print(f"❓ ДРУГОЙ РЕЗУЛЬТАТ: {decision}")
            
            print(f"💡 Причина: {reason[:100]}{'...' if len(reason) > 100 else ''}")
            
        except Exception as e:
            print(f"💥 ОШИБКА: {e}")
            results_summary['OTHER'] += 1
        
        print()
    
    print("="*80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"🎉 ПОЛНЫЙ УСПЕХ (activity + patterns): {results_summary['WOULD_SEND']}")
    print(f"❌ Отклонены по activity conditions: {results_summary['WOULD_REJECT_CONDITIONS']}")  
    print(f"🚨 Отклонены по паттернам холдеров: {results_summary['WOULD_REJECT_PATTERNS']}")
    print(f"❓ Другие результаты: {results_summary['OTHER']}")
    print()
    print("🎯 ЛОГИКА РАБОТАЕТ ПРАВИЛЬНО ЕСЛИ:")
    print("✅ Есть токены в категории 'ПОЛНЫЙ УСПЕХ'")
    print("✅ Есть токены отклоненные по паттернам (показывает что фильтр работает)")
    print("✅ Логи показывают '🚨 ACTIVITY REJECT (HOLDER PATTERNS)' для подозрительных")

if __name__ == "__main__":
    asyncio.run(test_holder_patterns_logic())