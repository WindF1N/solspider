#!/usr/bin/env python3
"""
Тест исправленного парсинга метрик из логов
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_successful_token_parsing():
    """Тестируем парсинг токена который реально отправлял уведомления"""
    tester = TokenFilterTester()
    
    # Токен который реально отправлял уведомления
    successful_token = 'tokens_logs/26YJjHymy3aS.log'
    
    if not os.path.exists(successful_token):
        print(f"❌ Файл {successful_token} не найден")
        return
    
    print(f"🔍 ТЕСТ ИСПРАВЛЕННОГО ПАРСИНГА")
    print(f"="*70)
    print(f"📊 Анализируем токен который РЕАЛЬНО получал уведомления")
    print(f"🎯 Файл: {successful_token}")
    print()
    
    try:
        result = await tester.analyze_token_with_full_criteria(successful_token)
        
        decision = result.get('decision', 'UNKNOWN')
        reason = result.get('reason', 'Нет причины')
        token_address = result.get('token_address', 'UNKNOWN')
        snapshots_checked = result.get('snapshots_checked', 0)
        total_snapshots = result.get('total_snapshots', 0)
        
        print(f"📊 РЕЗУЛЬТАТ АНАЛИЗА:")
        print(f"   Токен: {token_address}")
        print(f"   Решение: {decision}")
        print(f"   Снапшотов проверено: {snapshots_checked}/{total_snapshots}")
        print()
        
        if decision == 'WOULD_SEND':
            snapshot_num = result.get('snapshot_number', '?')
            print(f"🎉 УСПЕХ! Токен прошел бы фильтрацию на снапшоте #{snapshot_num}")
            print(f"✅ Причина: {reason}")
            
            # Показываем метрики успешного снапшота
            if 'holders' in result:
                print(f"📊 Метрики успешного снапшота:")
                print(f"   👥 Холдеры: {result.get('holders', 0)}")
                print(f"   💧 Ликвидность: ${result.get('liquidity', 0):,.0f}")
                print(f"   💰 Market Cap: ${result.get('market_cap', 0):,.0f}")
                print(f"   🎯 Снайперы: {result.get('snipers_percent', 0):.1f}%")
                print(f"   👨‍💼 Инсайдеры: {result.get('insiders_percent', 0):.1f}%")
                print(f"   👨‍💼 Dev: {result.get('dev_percent', 0):.1f}%")
        
        elif decision == 'WOULD_REJECT':
            best_snapshot = result.get('best_snapshot', {})
            print(f"❌ ТОКЕН ОТКЛОНЕН (но это неправильно!)")
            print(f"💡 Причина: {reason}")
            
            if best_snapshot.get('passed_conditions', 0) > 0:
                print(f"\n🏆 Лучший снапшот #{best_snapshot['snapshot_number']}:")
                print(f"   ✅ Прошло условий: {best_snapshot['passed_conditions']}")
                print(f"   ❌ Провалилось: {', '.join(best_snapshot.get('failed_conditions', [])[:3])}")
                
                metrics = best_snapshot.get('metrics', {})
                if metrics:
                    print(f"   📊 Метрики:")
                    if 'holders' in metrics:
                        print(f"      👥 Холдеры: {metrics['holders']}")
                    if 'liquidity' in metrics:
                        print(f"      💧 Ликвидность: ${metrics['liquidity']:,.0f}")
        
        else:
            print(f"❓ ДРУГОЙ РЕЗУЛЬТАТ: {decision}")
            print(f"💡 Причина: {reason}")
            
    except Exception as e:
        print(f"💥 ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("="*70)
    print("🎯 ЦЕЛЬ ТЕСТА:")
    print("✅ Токен который реально отправлял уведомления должен показать WOULD_SEND")
    print("✅ Исправленный парсер должен правильно извлекать метрики")
    print("✅ Снапшот должен быть намного позже начального (не #22)")

if __name__ == "__main__":
    asyncio.run(test_successful_token_parsing())