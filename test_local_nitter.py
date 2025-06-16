#!/usr/bin/env python3
"""
Тест подключения к локальному Nitter
"""

import asyncio
import aiohttp
import time
from nitter_config import nitter_config, get_nitter_search_url

async def test_nitter_instance(url, test_query="bitcoin"):
    """Тестирует один Nitter инстанс"""
    try:
        # Тестовый поисковый URL
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        search_url = f"{url}/search?f=tweets&q={test_query}&since={yesterday}&until=&near="
        
        print(f"🔍 Тестируем: {url}")
        print(f"📍 URL: {search_url}")
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, timeout=10) as response:
                elapsed = time.time() - start_time
                
                if response.status == 200:
                    html = await response.text()
                    
                    # Проверяем наличие ключевых элементов Nitter
                    if 'timeline-item' in html or 'tweet-content' in html:
                        print(f"✅ {url} - РАБОТАЕТ ({response.status}) за {elapsed:.2f}с")
                        return True, elapsed
                    elif 'Making sure you\'re not a bot!' in html:
                        print(f"🚫 {url} - ЗАБЛОКИРОВАН (требуются cookies)")
                        return False, elapsed
                    else:
                        print(f"❓ {url} - СТРАННЫЙ ОТВЕТ ({len(html)} символов)")
                        return False, elapsed
                else:
                    print(f"❌ {url} - ОШИБКА {response.status} за {elapsed:.2f}с")
                    return False, elapsed
                    
    except asyncio.TimeoutError:
        print(f"⏰ {url} - ТАЙМАУТ (>10с)")
        return False, 10.0
    except Exception as e:
        print(f"❌ {url} - ОШИБКА: {e}")
        return False, 0.0

async def test_all_nitter_instances():
    """Тестирует все доступные Nitter инстансы"""
    print("🚀 ТЕСТИРОВАНИЕ NITTER ИНСТАНСОВ")
    print("=" * 60)
    
    working_instances = []
    
    for i, instance in enumerate(nitter_config.nitter_instances):
        print(f"\n[{i+1}/{len(nitter_config.nitter_instances)}]")
        is_working, response_time = await test_nitter_instance(instance)
        
        if is_working:
            working_instances.append((instance, response_time))
        
        # Небольшая пауза между тестами
        await asyncio.sleep(1)
    
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    
    if working_instances:
        print(f"✅ Работающих инстансов: {len(working_instances)}")
        print("\n🚀 РЕЙТИНГ ПО СКОРОСТИ:")
        
        # Сортируем по времени ответа
        working_instances.sort(key=lambda x: x[1])
        
        for i, (url, response_time) in enumerate(working_instances):
            status = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "⚡"
            is_local = "🏠 ЛОКАЛЬНЫЙ" if "localhost" in url else "🌐 ВНЕШНИЙ"
            print(f"{status} {url} - {response_time:.2f}с {is_local}")
            
        print(f"\n💡 РЕКОМЕНДАЦИЯ:")
        best_url, best_time = working_instances[0]
        if "localhost" in best_url:
            print(f"🎯 Используйте локальный Nitter: {best_url}")
            print(f"⚡ Скорость: {best_time:.2f}с (отлично!)")
        else:
            print(f"🎯 Лучший доступный: {best_url}")
            print(f"⚡ Скорость: {best_time:.2f}с")
            print(f"💡 Для максимальной скорости настройте локальный Nitter!")
    else:
        print("❌ НИ ОДИН ИНСТАНС НЕ РАБОТАЕТ!")
        print("🔧 Проверьте подключение к интернету или настройте локальный Nitter")

async def test_search_functionality():
    """Тестирует функциональность поиска"""
    print("\n🔍 ТЕСТИРОВАНИЕ ПОИСКА ЧЕРЕЗ КОНФИГУРАЦИЮ:")
    print("-" * 40)
    
    test_queries = ["bitcoin", "F4ALfBc8QpkgDJ1KK6YkcqqPUZbJTazAsnD4GGnApump"]
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    for query in test_queries:
        print(f"\n🔍 Поиск: {query}")
        search_url = get_nitter_search_url(query, yesterday)
        print(f"📍 URL: {search_url}")
        
        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, timeout=5) as response:
                    elapsed = time.time() - start_time
                    
                    if response.status == 200:
                        html = await response.text()
                        tweet_count = html.count('timeline-item')
                        print(f"✅ Найдено ~{tweet_count} твитов за {elapsed:.2f}с")
                    else:
                        print(f"❌ Ошибка {response.status} за {elapsed:.2f}с")
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Ошибка: {e} (за {elapsed:.2f}с)")

if __name__ == "__main__":
    from datetime import datetime, timedelta
    
    print("🧪 ТЕСТ NITTER КОНФИГУРАЦИИ")
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 Текущие инстансы: {len(nitter_config.nitter_instances)}")
    
    asyncio.run(test_all_nitter_instances())
    asyncio.run(test_search_functionality()) 