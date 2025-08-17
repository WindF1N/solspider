#!/usr/bin/env python3
"""
Финальный тест исправления всех ошибок slice
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_all_slice_fixes():
    """Финальный тест всех исправлений slice"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем токены которые ранее вызывали ошибки
    problem_tokens = [
        '4twqEgb6KGDRB3UuHFhSkjLrGMqk15qHYTkt44zSpump.log',
        '2u1AMFNttZggLy1mHDAofoNQA8nC56dqnQg5JkaKhgiN.log',
        'EsYns2NH9r5U7VTp2uCkV7TVkmwsu4o1j1gdtbSSmytn.log'
    ]
    
    # Если проблемных токенов нет, берем случайные
    all_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    test_files = []
    
    for token_file in problem_tokens:
        if os.path.exists(os.path.join(tokens_logs_dir, token_file)):
            test_files.append(token_file)
    
    # Добавляем еще несколько случайных
    test_files.extend(all_files[:7])  # Итого до 10 файлов для теста
    test_files = test_files[:10]  # Максимум 10
    
    print(f"🔧 ФИНАЛЬНЫЙ ТЕСТ ИСПРАВЛЕНИЯ ОШИБОК SLICE")
    print(f"="*70)
    print(f"📊 Тестируем {len(test_files)} токенов")
    print(f"🎯 Проверяем что ошибки 'unhashable type: slice' исправлены")
    print()
    
    results = {
        'success': 0,
        'slice_errors': 0,
        'other_errors': 0,
        'timeouts': 0
    }
    
    slice_error_tokens = []
    
    for i, log_file in enumerate(test_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i:2d}. 🔍 {token_id[:20]}...")
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', '')
            
            if decision == 'ERROR':
                if 'slice' in reason.lower():
                    results['slice_errors'] += 1
                    slice_error_tokens.append(token_id)
                    print(f"     🚨 SLICE ERROR: {reason}")
                elif 'timeout' in reason.lower():
                    results['timeouts'] += 1
                    print(f"     ⏰ TIMEOUT")
                else:
                    results['other_errors'] += 1
                    print(f"     💥 OTHER ERROR: {reason[:50]}")
            else:
                results['success'] += 1
                snapshots = result.get('snapshots_checked', 0)
                print(f"     ✅ SUCCESS: {decision} ({snapshots} snapshots)")
                
        except Exception as e:
            if 'slice' in str(e).lower():
                results['slice_errors'] += 1
                slice_error_tokens.append(token_id)
                print(f"     🚨 EXCEPTION SLICE ERROR: {e}")
            else:
                results['other_errors'] += 1
                print(f"     💥 EXCEPTION: {e}")
    
    print()
    print("="*70)
    print("📊 ФИНАЛЬНЫЕ РЕЗУЛЬТАТЫ:")
    print(f"✅ Успешно обработано: {results['success']}")
    print(f"⏰ Timeout ошибки: {results['timeouts']}")
    print(f"💥 Другие ошибки: {results['other_errors']}")
    print(f"🚨 SLICE ОШИБКИ: {results['slice_errors']}")
    
    if slice_error_tokens:
        print(f"\n🚨 ТОКЕНЫ С ОШИБКАМИ SLICE:")
        for token in slice_error_tokens:
            print(f"   - {token}")
        print(f"\n❌ ОШИБКИ SLICE НЕ ПОЛНОСТЬЮ ИСПРАВЛЕНЫ!")
        print(f"🔧 Требуется дополнительная отладка")
    else:
        print(f"\n🎉 ВСЕ ОШИБКИ SLICE ИСПРАВЛЕНЫ!")
        print(f"✅ Все проверенные токены обработались без slice ошибок")
        print(f"🚀 Система готова к полномасштабному тестированию")
    
    print(f"\n📄 Детальные логи в test_filter.log")
    
    # Возвращаем True если нет slice ошибок
    return results['slice_errors'] == 0

if __name__ == "__main__":
    success = asyncio.run(test_all_slice_fixes())
    exit(0 if success else 1)