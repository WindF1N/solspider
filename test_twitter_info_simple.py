#!/usr/bin/env python3
"""
Упрощенный тест для проверки TwitterProfileParser напрямую
"""
import asyncio
import logging
from twitter_profile_parser import TwitterProfileParser

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_twitter_profile_parser():
    """Тестирует TwitterProfileParser напрямую"""
    try:
        test_twitter = "mst1287"  # Пример из вашего сообщения
        
        logger.info(f"🔍 Тестируем получение информации о @{test_twitter}")
        
        # Создаем парсер с контекстным менеджером
        async with TwitterProfileParser() as parser:
            # Получаем профиль
            result = await parser.get_profile_with_replies_multi_page(test_twitter, max_pages=1)
            
            # Проверяем что получили правильное количество значений
            if result and len(result) == 3:
                profile_data, all_tweets, tweets_with_contracts = result
            elif result and len(result) == 2:
                profile_data, all_tweets = result
                tweets_with_contracts = []
            else:
                logger.warning(f"⚠️ Неожиданный результат от парсера для @{test_twitter}: {result}")
                return False
            
            if profile_data:
                logger.info(f"✅ Получена информация о @{test_twitter}:")
                logger.info(f"   📋 Имя: {profile_data.get('display_name', 'N/A')}")
                logger.info(f"   📝 Био: {profile_data.get('bio', 'N/A')[:100]}...")
                logger.info(f"   👥 Подписчики: {profile_data.get('followers_count', 0)}")
                logger.info(f"   📅 Регистрация: {profile_data.get('join_date', 'N/A')}")
                logger.info(f"   ✅ Верифицирован: {profile_data.get('is_verified', False)}")
                logger.info(f"   🐦 Твиты: {profile_data.get('tweets_count', 0)}")
                logger.info(f"   🔗 Подписки: {profile_data.get('following_count', 0)}")
                logger.info(f"   ❤️ Лайки: {profile_data.get('likes_count', 0)}")
                
                # Тестируем форматирование числа
                def format_number(number: int) -> str:
                    """Форматирует число в читаемый вид (1.2K, 15M и т.д.)"""
                    if number >= 1_000_000:
                        return f"{number / 1_000_000:.1f}M"
                    elif number >= 1_000:
                        return f"{number / 1_000:.1f}K"
                    else:
                        return str(number)
                
                logger.info(f"\n🎨 Форматированная статистика:")
                logger.info(f"   📊 {format_number(profile_data.get('tweets_count', 0))} твитов")
                logger.info(f"   👥 {format_number(profile_data.get('followers_count', 0))} подписчиков")
                logger.info(f"   🔗 {format_number(profile_data.get('following_count', 0))} подписок")
                logger.info(f"   ❤️ {format_number(profile_data.get('likes_count', 0))} лайков")
                
                # Симулируем форматирование для сообщения
                display_name = profile_data.get('display_name', test_twitter)
                bio = profile_data.get('bio', 'Нет описания')
                join_date = profile_data.get('join_date', 'Неизвестно')
                is_verified = profile_data.get('is_verified', False)
                
                tweets = format_number(profile_data.get('tweets_count', 0))
                followers = format_number(profile_data.get('followers_count', 0))
                following = format_number(profile_data.get('following_count', 0))
                likes = format_number(profile_data.get('likes_count', 0))
                
                verified_badge = "✅" if is_verified else ""
                
                print(f"\n🎯 Пример форматирования для главного аккаунта:")
                print(f"🐦 ГЛАВНЫЙ TWITTER: @{test_twitter} {verified_badge}")
                print(f"📋 Имя: {display_name}")
                
                if bio and bio != 'Нет описания':
                    bio_short = bio[:200] + "..." if len(bio) > 200 else bio
                    print(f"📝 Описание:")
                    print(f"<blockquote>{bio_short}</blockquote>")
                
                print(f"📅 Регистрация: {join_date}")
                print(f"📊 Статистика: {tweets} твитов • {followers} подписчиков • {following} подписок • {likes} лайков")
                
                return True
            else:
                logger.warning(f"⚠️ Не удалось получить информацию о @{test_twitter}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {e}")
        return False

async def main():
    """Основная функция"""
    logger.info("🚀 Запуск упрощенного тестирования TwitterProfileParser")
    
    success = await test_twitter_profile_parser()
    
    if success:
        logger.info("✅ Тестирование завершено успешно!")
    else:
        logger.error("❌ Тестирование завершено с ошибками")

if __name__ == "__main__":
    asyncio.run(main()) 