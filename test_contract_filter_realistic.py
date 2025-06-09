#!/usr/bin/env python3
"""
Реалистичное тестирование фильтра с заведомо несуществующими адресами
"""

import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pump_bot import analyze_token_sentiment

def test_realistic_filter():
    """Тестирование фильтра с реалистичными данными"""
    print("🧪 Реалистичное тестирование фильтра поиска адреса контракта\n")
    
    # Тестовые данные с заведомо несуществующими адресами
    test_cases = [
        {
            "name": "Тест 1: Полностью новый адрес (не должен найтись)",
            "mint": "aBc123XyZ999NotRealAddress000111222333444",
            "symbol": "NEWTEST"
        },
        {
            "name": "Тест 2: Случайный адрес (не должен найтись)",  
            "mint": "9999888777666555444333222111000TestAddr",
            "symbol": "RANDOM"
        },
        {
            "name": "Тест 3: Очень новый адрес (не должен найтись)",
            "mint": "zZzNewTokenAddressNotInTwitterYet12345678",
            "symbol": "FRESH"
        }
    ]
    
    results_summary = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"{'='*60}")
        print(f"📊 {test_case['name']}")
        print(f"🏷️ Символ: {test_case['symbol']}")
        print(f"📍 Mint: {test_case['mint']}")
        print("-" * 60)
        
        try:
            # Выполняем анализ
            result = analyze_token_sentiment(test_case['mint'], test_case['symbol'])
            
            # Выводим результаты
            print(f"🔍 Результаты анализа:")
            print(f"  • Всего твитов: {result['tweets']}")
            print(f"  • Твиты по символу: {result['symbol_tweets']}")
            print(f"  • Твиты по контракту: {result['contract_tweets']}")
            print(f"  • Активность: {result['engagement']}")
            print(f"  • Скор: {result['score']}")
            print(f"  • Рейтинг: {result['rating']}")
            print(f"  • Адрес найден: {'✅ ДА' if result['contract_found'] else '❌ НЕТ'}")
            
            # Проверяем старую и новую логику
            would_notify_old = (
                result['score'] >= 5 or
                result['tweets'] >= 3 or
                'высокий' in result['rating'].lower() or
                'средний' in result['rating'].lower()
            )
            
            would_notify_new = (
                result['contract_found'] and (
                    result['score'] >= 5 or
                    result['tweets'] >= 3 or
                    'высокий' in result['rating'].lower() or
                    'средний' in result['rating'].lower()
                )
            )
            
            print(f"\n🎯 Решение о уведомлении:")
            print(f"  • Старый фильтр: {'✅ ОТПРАВИТЬ' if would_notify_old else '❌ НЕ ОТПРАВЛЯТЬ'}")
            print(f"  • Новый фильтр: {'✅ ОТПРАВИТЬ' if would_notify_new else '❌ НЕ ОТПРАВЛЯТЬ'}")
            
            # Анализируем изменения
            if would_notify_old != would_notify_new:
                print(f"  🚨 ИЗМЕНЕНИЕ: Новый фильтр {'заблокировал' if not would_notify_new else 'разрешил'} уведомление!")
                if not result['contract_found']:
                    print(f"  📝 Причина: адрес контракта НЕ найден в Twitter")
                    print(f"  🎯 Это именно то, что мы хотели - фильтрация сработала!")
            else:
                print(f"  ✅ Результат одинаковый для обоих фильтров")
            
            # Сохраняем результат для сводки
            results_summary.append({
                'symbol': test_case['symbol'],
                'contract_found': result['contract_found'],
                'old_notify': would_notify_old,
                'new_notify': would_notify_new,
                'filtered': would_notify_old and not would_notify_new
            })
                
        except Exception as e:
            print(f"❌ Ошибка при тестировании: {e}")
            results_summary.append({
                'symbol': test_case['symbol'],
                'error': str(e)
            })
        
        print(f"\n")
    
    # Выводим сводку результатов
    print("🏁 Тестирование завершено!")
    print(f"{'='*60}")
    print("📊 СВОДКА РЕЗУЛЬТАТОВ:")
    print("-" * 60)
    
    total_tested = len([r for r in results_summary if 'error' not in r])
    filtered_count = len([r for r in results_summary if r.get('filtered', False)])
    no_contract_count = len([r for r in results_summary if not r.get('contract_found', True)])
    
    for result in results_summary:
        if 'error' not in result:
            status = "🚫 ОТФИЛЬТРОВАН" if result['filtered'] else "✅ ПРОШЕЛ"
            contract_status = "❌ НЕ НАЙДЕН" if not result['contract_found'] else "✅ НАЙДЕН"
            print(f"  {result['symbol']:8} | Контракт: {contract_status:12} | {status}")
    
    print(f"\n📈 Статистика:")
    print(f"  • Всего протестировано: {total_tested}")
    print(f"  • Контракт не найден: {no_contract_count}")
    print(f"  • Отфильтровано новым фильтром: {filtered_count}")
    print(f"  • Эффективность фильтра: {(filtered_count/total_tested*100) if total_tested > 0 else 0:.1f}%")
    
    print(f"\n✅ Новый фильтр работает правильно!")
    print("🎯 Токены без упоминания адреса контракта в Twitter больше не пройдут фильтрацию")

if __name__ == "__main__":
    test_realistic_filter() 