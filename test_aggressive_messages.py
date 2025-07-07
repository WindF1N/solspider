#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🐛💰 ТЕСТИРОВАНИЕ АГРЕССИВНЫХ СООБЩЕНИЙ WORMSTER'А
Демонстрация новых крипто-агрессивных фраз в духе червяка-трейдера
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from duplicate_groups_manager import DuplicateGroupsManager
from pump_bot import format_new_token
from config import Config

async def test_duplicate_group_message():
    """🐛 Тест агрессивного сообщения о группе дубликатов"""
    print("🐛🔥 ТЕСТ: Агрессивное сообщение о группе дубликатов")
    print("=" * 60)
    
    # Создаем тестовую группу
    manager = DuplicateGroupsManager(Config.TELEGRAM_BOT_TOKEN)
    
    # Создаем тестовые данные группы
    group = manager.GroupData("test_key", "PEPE", "Pepe the Frog")
    group.main_twitter = "pepecoin_sol"
    group.tokens = [
        {
            "id": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0",
            "symbol": "PEPE",
            "name": "Pepe the Frog",
            "twitter": "https://twitter.com/pepecoin_sol",
            "website": "https://pepe.com",
            "telegram": "https://t.me/pepechat"
        },
        {
            "id": "B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1",
            "symbol": "PEPE",
            "name": "Pepe Coin",
            "twitter": "https://twitter.com/pepe_official"
        },
        {
            "id": "C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2",
            "symbol": "PEPE",
            "name": "Pepe Token"
        }
    ]
    
    # Добавляем официальный анонс
    group.official_announcement = {
        "text": "🐸 Встречайте PEPE - мем-токен, который покорит весь мир! Готовьтесь к луне! 🚀",
        "date": "16.06.2024 18:30:15"
    }
    
    # Добавляем последний токен
    group.latest_added_token = {
        "id": "C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2",
        "firstPool": {"createdAt": "2024-06-16T18:30:15.000Z"}
    }
    
    group.last_updated = datetime.now()
    
    # Тестируем разные сценарии
    print("\n🎯 СЦЕНАРИЙ 1: Группа БЕЗ официального контракта")
    group.official_contract = None
    message = await manager._format_group_message(group)
    print(message)
    
    print("\n" + "=" * 60)
    print("\n🎉 СЦЕНАРИЙ 2: Группа С найденным официальным контрактом")
    group.official_contract = {
        "address": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0",
        "date": "16.06.2024 19:45:30"
    }
    message = await manager._format_group_message(group)
    print(message)
    
    manager.stop()

async def test_new_token_message():
    """🐛 Тест агрессивного сообщения о новом токене"""
    print("\n🐛🚀 ТЕСТ: Агрессивное сообщение о новом токене")
    print("=" * 60)
    
    # Тестовые данные токена
    token_data = {
        "mint": "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0",
        "name": "Wormster Coin",
        "symbol": "WORM",
        "description": "Самый агрессивный крипто-червяк в Solana! Копаем иксы до луны! 🐛💎",
        "creator": "B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1C2",
        "marketCap": 150000,
        "initialBuy": 5.5,
        "creatorPercentage": 15,
        "dex_source": "pump.fun",
        "pool_type": "pumpfun",
        "twitter": "https://twitter.com/wormster_coin",
        "telegram": "https://t.me/wormster_chat",
        "website": "https://wormster.io"
    }
    
    # Анализ Twitter
    twitter_analysis = {
        "rating": "🔥 ВЫСОКАЯ",
        "tweets": 50,
        "engagement": "Активная",
        "score": 85,
        "symbol_tweets": 25,
        "contract_tweets": 3,
        "contract_found": True,
        "contract_authors": [
            {
                "username": "crypto_whale_hunter",
                "display_name": "Crypto Whale Hunter 🐋",
                "followers_count": 15000,
                "following_count": 2500,
                "tweets_count": 8500,
                "likes_count": 45000,
                "is_verified": True,
                "tweet_text": "🚀 Новый гем найден! $WORM - это следующий 100x! Червяк копает глубоко! 💎🐛 #WORM #PumpFun",
                "tweet_date": "16.06.2024 19:30:15",
                "tweet_type": "Твит",
                "contract_diversity": 65,
                "max_contract_spam": 75,
                "diversity_recommendation": "Высокая концентрация",
                "spam_analysis": "Вспышка активности",
                "is_spam_likely": False,
                "total_contract_tweets": 10,
                "unique_contracts_count": 7,
                "join_date": "Март 2021"
            },
            {
                "username": "solana_degen_ape",
                "display_name": "Solana Degen 🦍",
                "followers_count": 8500,
                "following_count": 1200,
                "tweets_count": 12000,
                "likes_count": 25000,
                "is_verified": False,
                "tweet_text": "АПЕИМ В $WORM! Червяк уже роет туннель к луне! 🚀🐛 Время загружаться!",
                "tweet_date": "16.06.2024 19:45:22",
                "tweet_type": "Ответ",
                "contract_diversity": 45,
                "max_contract_spam": 60,
                "diversity_recommendation": "Умеренная концентрация",
                "spam_analysis": "Умеренная активность",
                "is_spam_likely": False,
                "total_contract_tweets": 8,
                "unique_contracts_count": 5,
                "join_date": "Июнь 2022"
            }
        ]
    }
    
    print("\n🎯 СЦЕНАРИЙ 1: Новый токен на Pump.fun")
    message, keyboard, should_notify, image_url = await format_new_token(token_data, twitter_analysis)
    print(message)
    
    print("\n" + "=" * 60)
    print("\n🎯 СЦЕНАРИЙ 2: Новый токен через Jupiter")
    token_data["dex_source"] = "jupiter"
    token_data["pool_type"] = "raydium"
    message, keyboard, should_notify, image_url = await format_new_token(token_data, twitter_analysis)
    print(message)

def test_log_messages():
    """🐛 Тест агрессивных лог-сообщений"""
    print("\n🐛📝 ТЕСТ: Агрессивные лог-сообщения")
    print("=" * 60)
    
    print("\n🎯 Примеры новых лог-сообщений:")
    
    print("\n1. Создание группы:")
    print("🐛🎉 ЧЕРВЯК СОЗДАЛ НОВУЮ ОХОТНИЧЬЮ СТАЮ PEPE! Теперь копает таблицы в фоне! 📊")
    
    print("\n2. Блокировка токена:")
    print("🐛🚫 ЧЕРВЯК ЗАБЛОКИРОВАЛ ТОКЕН SCAM: Главный Twitter @scam_token светит контракты! Червяк не любит спойлеры! 🤬")
    
    print("\n3. Добавление в группу:")
    print("🐛✅ ЧЕРВЯК ПОПОЛНИЛ КОЛЛЕКЦИЮ! Токен DOGE добавлен в стаю дубликатов (всего жертв: 5) 🎯")
    
    print("\n4. Блокировка группы без анонса:")
    print("🐛❌ ЧЕРВЯК ОТКАЗАЛСЯ СОЗДАВАТЬ ГРУППУ FAKE: Нет официального анонса в @fake_token! Червяк не любит неофициальные подделки! 🚫")
    
    print("\n5. Поиск анонса:")
    print("🐛🔍 ЧЕРВЯК НАШЁЛ ГРУППУ MYSTERY БЕЗ АНОНСА! Копаем глубже в @mystery_coin...")
    
    print("\n6. Удаление группы:")
    print("🐛💥 ЧЕРВЯК УНИЧТОЖИЛ ГРУППУ EXPIRED! Охота завершена! 🎯")

async def main():
    """🐛 Главная функция тестирования"""
    print("🐛💰 WORMSTER - АГРЕССИВНЫЙ КРИПТО-ЧЕРВЯК")
    print("🔥 Тестирование новых эмоциональных сообщений")
    print("=" * 60)
    
    try:
        await test_duplicate_group_message()
        await test_new_token_message()
        test_log_messages()
        
        print("\n🐛🎉 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
        print("💰 Червяк готов к охоте за иксами! 🚀")
        
    except Exception as e:
        print(f"🐛❌ ОШИБКА ТЕСТИРОВАНИЯ: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 