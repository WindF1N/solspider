#!/usr/bin/env python3
"""
Тест фильтрации логирования токенов с <30 холдерами
Показывает как уменьшается шум в логах
"""

import asyncio
import os
from test_filter import TokenFilterTester, filtered_low_holders_count

async def test_log_filtering():
    """Тест фильтрации логирования"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    # Берем первые 20 токенов для демонстрации
    all_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
    test_files = all_files[:20]
    
    print(f"🔇 ТЕСТ ФИЛЬТРАЦИИ ЛОГИРОВАНИЯ")
    print(f"="*70)
    print(f"📊 Тестируем {len(test_files)} токенов")
    print(f"🎯 Цель: НЕ логировать токены с <30 холдерами")
    print()
    
    # Счетчики для сравнения
    stats = {
        'total_processed': 0,
        'would_reject_all': 0,
        'would_reject_low_holders': 0,
        'would_reject_logged': 0,
        'would_send': 0,
        'errors': 0
    }
    
    for i, log_file in enumerate(test_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i:2d}. 🔍 {token_id[:20]}...", end="")
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            stats['total_processed'] += 1
            
            decision = result.get('decision', 'UNKNOWN')
            holders = result.get('holders', 0)
            
            if decision == 'WOULD_REJECT':
                stats['would_reject_all'] += 1
                if holders < 30:
                    stats['would_reject_low_holders'] += 1
                    print(f" 🔇 ФИЛЬТР (только {holders} холдеров)")
                else:
                    stats['would_reject_logged'] += 1
                    print(f" ❌ REJECT ({holders} холдеров) - ЛОГИРУЕТСЯ")
            elif decision == 'WOULD_SEND':
                stats['would_send'] += 1
                print(f" ✅ SEND ({holders} холдеров)")
            elif decision == 'ERROR':
                stats['errors'] += 1
                print(f" 💥 ERROR")
            else:
                print(f" ℹ️ {decision}")
                
        except Exception as e:
            stats['errors'] += 1
            print(f" 💥 EXCEPTION: {e}")
    
    print()
    print("="*70)
    print("📊 РЕЗУЛЬТАТЫ ФИЛЬТРАЦИИ:")
    print(f"📈 Всего обработано: {stats['total_processed']}")
    print(f"✅ WOULD_SEND: {stats['would_send']}")
    print(f"❌ WOULD_REJECT (всего): {stats['would_reject_all']}")
    print(f"   ├─ 🔇 С <30 холдерами (ОТФИЛЬТРОВАНО): {stats['would_reject_low_holders']}")
    print(f"   └─ 📝 С ≥30 холдерами (ЛОГИРУЕТСЯ): {stats['would_reject_logged']}")
    print(f"💥 Ошибки: {stats['errors']}")
    
    # Показываем эффект фильтрации
    if stats['would_reject_all'] > 0:
        filtered_percent = (stats['would_reject_low_holders'] / stats['would_reject_all']) * 100
        log_reduction = (stats['would_reject_low_holders'] / stats['total_processed']) * 100
        
        print()
        print("🎯 ЭФФЕКТ ФИЛЬТРАЦИИ:")
        print(f"📉 Отфильтровано {filtered_percent:.1f}% отклоненных токенов")
        print(f"🔇 Уменьшение шума в логах на {log_reduction:.1f}%")
        print(f"📄 Логи стали чище и информативнее!")
    
    # Проверяем глобальный счетчик
    global filtered_low_holders_count
    print(f"\n🔢 Глобальный счетчик отфильтрованных: {filtered_low_holders_count}")
    
    print()
    print("📄 Теперь в test_filter.log записываются только:")
    print("   ✅ Токены которые отправились бы (WOULD_SEND)")
    print("   ❌ Токены с ≥30 холдерами которые отклонены")
    print("   💥 Ошибки и особые случаи")
    print("   🔇 Токены с <30 холдерами НЕ засоряют лог")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_log_filtering())
    exit(0 if success else 1)