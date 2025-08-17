#!/usr/bin/env python3
"""
Тест исправления логики time_ok
Проверяет что на первых снапшотах time_ok не вызывает ложных отклонений
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_time_ok_fix():
    """Тест что time_ok работает корректно на исторических логах"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем несколько токенов для проверки time_ok
    all_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    test_files = all_files[:5]
    
    print(f"🔧 ТЕСТ ИСПРАВЛЕНИЯ ЛОГИКИ TIME_OK")
    print(f"="*70)
    print(f"📊 Тестируем {len(test_files)} токенов")
    print(f"🎯 Проверяем что time_ok больше не отклоняет на первых снапшотах")
    print()
    print(f"✅ ИСПРАВЛЕНИЯ:")
    print(f"   • Используется время первого снапшота как время создания рынка")
    print(f"   • time_ok проверяется относительно первого снапшота")
    print(f"   • Если времена неизвестны, считаем time_ok=True")
    print()
    
    results = {
        'total': 0,
        'time_ok_failures': 0,
        'time_ok_passes': 0,
        'other_failures': 0
    }
    
    for i, log_file in enumerate(test_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i:2d}. 🔍 {token_id[:20]}...")
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            results['total'] += 1
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', '')
            
            # Анализируем провал time_ok в лучшем снапшоте
            if 'time_ok' in reason and 'провалились' in reason:
                results['time_ok_failures'] += 1
                snap_num = reason.find('снапшот #')
                if snap_num != -1:
                    snap_str = reason[snap_num:snap_num+20]
                    print(f"     ❌ time_ok ВСЕ ЕЩЕ ПРОВАЛЕН: {snap_str}")
                else:
                    print(f"     ❌ time_ok провален в лучшем снапшоте")
            else:
                results['time_ok_passes'] += 1
                if decision == 'WOULD_SEND':
                    snap_num = result.get('snapshot_number', 0)
                    print(f"     ✅ УСПЕХ на снапшоте #{snap_num} (time_ok прошел)")
                elif decision == 'WOULD_REJECT':
                    print(f"     ⚠️ Отклонен по другим причинам (НЕ time_ok)")
                else:
                    print(f"     ℹ️ {decision}")
                    
        except Exception as e:
            print(f"     💥 ОШИБКА: {e}")
    
    print()
    print("="*70)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТА TIME_OK:")
    print(f"📈 Всего токенов: {results['total']}")
    print(f"✅ time_ok прошел: {results['time_ok_passes']}")
    print(f"❌ time_ok провален: {results['time_ok_failures']}")
    
    if results['time_ok_failures'] == 0:
        print(f"\n🎉 ИСПРАВЛЕНИЕ УСПЕШНО!")
        print(f"✅ time_ok больше не вызывает ложных отклонений")
        print(f"✅ Логика корректно работает с историческими логами")
        print(f"✅ Первый снапшот используется как время создания рынка")
    else:
        print(f"\n⚠️ ТРЕБУЕТСЯ ДОПОЛНИТЕЛЬНАЯ ОТЛАДКА")
        print(f"❌ time_ok все еще вызывает ложные отклонения")
        print(f"🔧 Возможно нужно более точное извлечение времени")
    
    success_rate = (results['time_ok_passes'] / results['total'] * 100) if results['total'] > 0 else 0
    print(f"\n📊 Успешность time_ok: {success_rate:.1f}%")
    
    return results['time_ok_failures'] == 0

if __name__ == "__main__":
    success = asyncio.run(test_time_ok_fix())
    exit(0 if success else 1)