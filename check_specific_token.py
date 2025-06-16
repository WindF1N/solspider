#!/usr/bin/env python3
"""
Проверка конкретного токена F4ALfBc8QpkgDJ1KK6YkcqqPUZbJTazAsnD4GGnApump
"""

import asyncio
from pump_bot import search_single_query, analyze_token_sentiment
from datetime import datetime, timedelta

async def check_specific_token():
    """Проверяет конкретный токен который не был обработан"""
    print("🔍 ПРОВЕРКА ТОКЕНА F4ALfBc8QpkgDJ1KK6YkcqqPUZbJTazAsnD4GGnApump")
    print("=" * 80)
    
    mint = "F4ALfBc8QpkgDJ1KK6YkcqqPUZbJTazAsnD4GGnApump"
    
    # Заголовки для Nitter
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Cookie': "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiMGEyOWM0YzcwZGM0YzYxMjE2NTNkMzQwYTU0YTNmNTFmZmJlNDIwOGM4MWZkZmUxNDA4MTY2MGNmMDc3ZGY2IiwiZXhwIjoxNzQ5NjAyOTA3LCJpYXQiOjE3NDg5OTgxMDcsIm5iZiI6MTc0ODk5ODA0Nywibm9uY2UiOiIxMzI4MSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYWEwZjdmMjBjNGQ0MGU5ODIzMWI4MDNmNWZiMGJlMGZjZmZiOGRhOTIzNDUyNDdhZjU1Yjk1MDJlZWE2In0.615N6HT0huTaYXHffqbBWqlpbpUgb7uVCh__TCoIuZLtGzBkdS3K8fGOPkFxHrbIo2OY3bw0igmtgDZKFesjAg",
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    print(f"📍 Mint адрес: {mint}")
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"🔗 Nitter URL: https://nitter.tiekoetter.com/search?f=tweets&q={mint}&since={yesterday}&until=&near=")
    print()
    
    # Тест 1: Прямой поиск по адресу контракта
    print("📋 Тест 1: Прямой поиск по адресу контракта")
    print("-" * 50)
    
    try:
        tweet_data_list = await search_single_query(mint, headers)
        tweets = len(tweet_data_list)
        engagement = sum(tweet.get('engagement', 0) for tweet in tweet_data_list)
        
        print(f"📊 Результат:")
        print(f"   • Найдено твитов: {tweets}")
        print(f"   • Общая активность: {engagement}")
        
        if tweets > 0:
            print(f"✅ КОНТРАКТ НАЙДЕН В TWITTER! ({tweets} твитов)")
        else:
            print(f"❌ Контракт НЕ найден в Twitter")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print()
    
    # Тест 2: Полный анализ токена (если знаем символ)
    # Попробуем разные возможные символы
    possible_symbols = ["UNKNOWN", "TEST", "TOKEN"]
    
    for symbol in possible_symbols:
        print(f"📋 Тест 2: Полный анализ с символом '{symbol}'")
        print("-" * 50)
        
        try:
            result = await analyze_token_sentiment(mint, symbol)
            
            print(f"📊 Результат анализа:")
            print(f"   • Всего твитов: {result['tweets']}")
            print(f"   • Твиты по символу: {result['symbol_tweets']}")
            print(f"   • Твиты по контракту: {result['contract_tweets']}")
            print(f"   • Активность: {result['engagement']}")
            print(f"   • Скор: {result['score']}")
            print(f"   • Рейтинг: {result['rating']}")
            print(f"   • Контракт найден: {'✅' if result['contract_found'] else '❌'}")
            
            if result['contract_found']:
                print(f"🎯 ЭТОТ ТОКЕН ДОЛЖЕН БЫЛ ПОПАСТЬ В УВЕДОМЛЕНИЯ!")
                break
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        print()
    
    print("🔍 ВОЗМОЖНЫЕ ПРИЧИНЫ ПРОБЛЕМЫ:")
    print("1. Токен был создан когда бот был отключен")
    print("2. Ошибка при сохранении в базу данных")
    print("3. Куки Nitter устарели во время обработки")
    print("4. Токен не прошел начальные фильтры активности")
    print("5. WebSocket соединение было прервано")
    
    print(f"\n🛠️ РЕКОМЕНДАЦИИ:")
    print("1. Проверьте логи бота на время создания токена")
    print("2. Убедитесь что бот запущен непрерывно")
    print("3. Проверьте работу фонового мониторинга")
    print("4. Обновите куки если они устарели")

if __name__ == "__main__":
    asyncio.run(check_specific_token()) 