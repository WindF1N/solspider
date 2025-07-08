#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой функциональности
получения детальной информации о Twitter профилях
"""
import asyncio
import logging
import os
from duplicate_groups_manager import DuplicateGroupsManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_twitter_info():
    """Тестирует получение информации о Twitter профилях"""
    try:
        # Получаем токен Telegram бота
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not telegram_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN не установлен")
            return False
        
        # Создаем менеджер групп дубликатов
        manager = DuplicateGroupsManager(telegram_token)
        
        # Тестируем получение информации о Twitter профиле
        test_twitter = "mst1287"  # Пример из вашего сообщения
        
        logger.info(f"🔍 Тестируем получение информации о @{test_twitter}")
        
        # Тестируем основную функцию
        profile_info = await manager._get_twitter_profile_info(test_twitter)
        
        if profile_info:
            logger.info(f"✅ Получена информация о @{test_twitter}:")
            logger.info(f"   📋 Имя: {profile_info.get('display_name', 'N/A')}")
            logger.info(f"   📝 Био: {profile_info.get('bio', 'N/A')[:100]}...")
            logger.info(f"   👥 Подписчики: {profile_info.get('followers_count', 0)}")
            logger.info(f"   📅 Регистрация: {profile_info.get('join_date', 'N/A')}")
            logger.info(f"   ✅ Верифицирован: {profile_info.get('is_verified', False)}")
            
            # Тестируем форматирование для главного аккаунта
            logger.info(f"\n🎨 Тестируем форматирование для главного аккаунта:")
            main_info = await manager._format_twitter_profile_info(test_twitter, is_main=True)
            print(f"\nГлавный аккаунт:\n{main_info}")
            
            # Тестируем форматирование для дополнительного аккаунта
            logger.info(f"\n🎨 Тестируем форматирование для дополнительного аккаунта:")
            additional_info = await manager._format_twitter_profile_info(test_twitter, is_main=False)
            print(f"\nДополнительный аккаунт:\n{additional_info}")
            
        else:
            logger.warning(f"⚠️ Не удалось получить информацию о @{test_twitter}")
        
        # Останавливаем менеджер
        manager.stop()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {e}")
        return False

async def main():
    """Основная функция"""
    logger.info("🚀 Запуск тестирования новой функциональности Twitter профилей")
    
    success = await test_twitter_info()
    
    if success:
        logger.info("✅ Тестирование завершено успешно!")
    else:
        logger.error("❌ Тестирование завершено с ошибками")

if __name__ == "__main__":
    asyncio.run(main()) 