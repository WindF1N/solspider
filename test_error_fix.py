#!/usr/bin/env python3
"""
Тест исправления ошибки slice
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_error_fix():
    """Тестируем исправление ошибки slice"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')][:3]
    
    print(f"🔧 ТЕСТ ИСПРАВЛЕНИЯ ОШИБКИ SLICE")
    print(f"="*60)
    print(f"📊 Тестируем {len(log_files)} токенов")
    print()
    
    for i, log_file in enumerate(log_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i}. 🔍 ТЕСТ: {token_id}")
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            print(f"   ✅ УСПЕХ: {decision}")
            
            if decision == 'WOULD_REJECT':
                best_snapshot = result.get('best_snapshot', {})
                if best_snapshot:
                    print(f"   📊 Лучший снапшот: #{best_snapshot.get('snapshot_number', '?')}")
                    print(f"   ✅ Прошло условий: {best_snapshot.get('passed_conditions', 0)}")
                    failed = best_snapshot.get('failed_conditions', [])
                    if failed:
                        print(f"   ❌ Провалилось: {failed[:2]}")  # Показываем первые 2
                        
        except Exception as e:
            print(f"   💥 ОШИБКА: {e}")
            if "slice" in str(e):
                print(f"   🚨 Ошибка slice НЕ ИСПРАВЛЕНА!")
            else:
                print(f"   📊 Другая ошибка (не slice)")
        
        print()
    
    print("="*60)
    print("🎯 РЕЗУЛЬТАТ ТЕСТА:")
    print("✅ Если нет ошибок 'unhashable type: slice' - исправление работает")
    print("📊 Проверьте test_filter.log на наличие детальных ошибок")

if __name__ == "__main__":
    asyncio.run(test_error_fix())