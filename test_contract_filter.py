#!/usr/bin/env python3
"""
Тестирование нового фильтра: проверка поиска адреса контракта в Twitter
"""

import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pump_bot import analyze_token_sentiment

def test_contract_filter():
    """Тестирование фильтра поиска адреса контракта"""
    print("🧪 Тестирование нового фильтра поиска адреса контракта в Twitter\n")
    
    # Тестовые данные
    test_cases = [
        {
            "name": "Тест 1: Популярный токен (должен найтись)",
            "mint": "8Ki8DpuWNxu9VsS3kQbarsCWMcFGWkzzA8pUPto9zBd5",  # RETARDIO
            "symbol": "RETARDIO"
        },
        {
            "name": "Тест 2: Новый токен (скорее всего не найдется)",
            "mint": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
            "symbol": "NEWCOIN"
        },
        {
            "name": "Тест 3: Несуществующий токен",
            "mint": "1111111111111111111111111111111111111111111",
            "symbol": "FAKE"
        }
    ]
    
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
            
            # Проверяем новый фильтр
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
            
            if would_notify_old != would_notify_new:
                print(f"  🚨 ИЗМЕНЕНИЕ: Новый фильтр {'заблокировал' if not would_notify_new else 'разрешил'} уведомление!")
                if not result['contract_found']:
                    print(f"  📝 Причина: адрес контракта НЕ найден в Twitter")
            else:
                print(f"  ✅ Результат одинаковый для обоих фильтров")
                
        except Exception as e:
            print(f"❌ Ошибка при тестировании: {e}")
        
        print(f"\n")
    
    print("🏁 Тестирование завершено!")
    print("\n📋 Сводка нового фильтра:")
    print("✅ Токен проходит фильтрацию только если:")
    print("   1. Адрес контракта найден в Twitter (contract_found = True)")
    print("   2. И выполнено одно из условий:")
    print("      • Twitter скор ≥ 5")
    print("      • Количество твитов ≥ 3")
    print("      • Рейтинг 'высокий' или 'средний'")
    print("\n❌ Если адрес контракта НЕ найден в Twitter - уведомление НЕ отправляется")

if __name__ == "__main__":
    test_contract_filter() 