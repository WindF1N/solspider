#!/usr/bin/env python3
"""
Тест детальной диагностики ближайших к успеху снапшотов
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_detailed_diagnosis():
    """Тестируем детальную диагностику лучших снапшотов"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')][:3]
    
    print(f"🔬 ТЕСТ ДЕТАЛЬНОЙ ДИАГНОСТИКИ ЛУЧШИХ СНАПШОТОВ")
    print(f"="*80)
    print(f"📊 Анализируем {len(log_files)} токенов")
    print(f"🎯 Находим снапшоты с максимальным количеством прошедших условий")
    print()
    
    for i, log_file in enumerate(log_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        token_id = log_file.replace('.log', '')
        
        print(f"{i}. 🔍 ДИАГНОСТИКА: {token_id}")
        print("-" * 70)
        
        try:
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', 'Нет причины')
            
            print(f"📊 РЕЗУЛЬТАТ: {decision}")
            
            if decision == 'WOULD_SEND':
                snapshot_num = result.get('snapshot_number', '?')
                print(f"🎉 УСПЕХ на снапшоте #{snapshot_num}")
                print(f"💡 {reason}")
                
            elif decision == 'WOULD_REJECT':
                snapshots_checked = result.get('snapshots_checked', 0)
                best_snapshot = result.get('best_snapshot', {})
                
                print(f"📈 СТАТИСТИКА АНАЛИЗА:")
                print(f"   Всего снапшотов проверено: {snapshots_checked}")
                
                if best_snapshot.get('passed_conditions', 0) > 0:
                    print(f"\n🏆 ЛУЧШИЙ СНАПШОТ #{best_snapshot['snapshot_number']}:")
                    print(f"   ✅ Прошедших условий: {best_snapshot['passed_conditions']}")
                    print(f"   ❌ Провалившихся условий: {len(best_snapshot.get('failed_conditions', []))}")
                    
                    # Показываем что провалилось
                    failed = best_snapshot.get('failed_conditions', [])[:5]  # Первые 5
                    if failed:
                        print(f"   🚫 Главные проблемы: {', '.join(failed)}")
                    
                    # Показываем что прошло
                    passed = best_snapshot.get('passed_conditions_list', [])[:5]  # Первые 5
                    if passed:
                        print(f"   ✅ Что было OK: {', '.join(passed)}")
                    
                    # Показываем метрики лучшего снапшота
                    metrics = best_snapshot.get('metrics', {})
                    if metrics:
                        print(f"   📊 Метрики снапшота:")
                        if 'holders' in metrics:
                            print(f"      👥 Холдеры: {metrics['holders']}")
                        if 'liquidity' in metrics:
                            print(f"      💧 Ликвидность: ${metrics['liquidity']:,.0f}")
                        if 'snipers_percent' in metrics:
                            print(f"      🎯 Снайперы: {metrics['snipers_percent']:.1f}%")
                        if 'insiders_percent' in metrics:
                            print(f"      👨‍💼 Инсайдеры: {metrics['insiders_percent']:.1f}%")
                else:
                    print(f"   😞 Ни один снапшот не прошел даже базовые условия")
            
            else:
                print(f"💡 {reason}")
                
        except Exception as e:
            print(f"💥 ОШИБКА: {e}")
        
        print()
    
    print("="*80)
    print("🎯 ПРЕИМУЩЕСТВА ДЕТАЛЬНОЙ ДИАГНОСТИКИ:")
    print("✅ Видим точно какие условия мешают токену пройти")
    print("✅ Понимаем насколько близко токен был к успеху")
    print("✅ Можем настраивать фильтры на основе статистики")
    print("✅ Логируется лучший снапшот с метриками")
    print()
    print("📋 ПРИМЕР ДЕТАЛЬНОГО ЛОГА:")
    print("❌ ACTIVITY REJECT - TOKEN: ABC123... | SNAPSHOTS: 150/200 |")
    print("   HOLDERS: 45 | LIQUIDITY: $8,500 | SNIPERS: 2.1% |")
    print("   REASON: Лучший снапшот #85: ✅12 условий (напр: holders_min, snipers_ok),")
    print("           ❌ провалились: min_liquidity, holders_max")

if __name__ == "__main__":
    asyncio.run(test_detailed_diagnosis())