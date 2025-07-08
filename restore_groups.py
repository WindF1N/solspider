#!/usr/bin/env python3
"""
Скрипт для восстановления групп дубликатов из Google Sheets
и создания новых сообщений с кнопками
"""
import asyncio
import logging
import os
from duplicate_groups_manager import get_duplicate_groups_manager, initialize_duplicate_groups_manager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def restore_groups():
    """Восстанавливает группы из Google Sheets и создает новые сообщения"""
    try:
        # Получаем токен Telegram бота
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not telegram_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN не установлен")
            return False
        
        # Инициализируем менеджер групп дубликатов
        initialize_duplicate_groups_manager(telegram_token)
        manager = get_duplicate_groups_manager()
        
        if not manager:
            logger.error("❌ Не удалось инициализировать менеджер групп")
            return False
        
        logger.info("🔄 Начинаем восстановление групп из Google Sheets...")
        
        # Восстанавливаем группы
        restored_groups = await manager.restore_groups_from_sheets_and_update_messages()
        
        if not restored_groups:
            logger.warning("⚠️ Не удалось восстановить группы")
            return False
        
        logger.info(f"✅ Восстановлено {len(restored_groups)} групп")
        
        # Создаем новые сообщения с кнопками
        chat_id = -1002680160752  # ID группы
        thread_id = 14  # ID темы для дубликатов
        
        logger.info("🔄 Создаем новые сообщения с кнопками Google Sheets...")
        
        updated_messages = await manager.update_existing_messages_with_buttons(chat_id, thread_id)
        
        if updated_messages:
            logger.info(f"✅ Создано {len(updated_messages)} новых сообщений с кнопками")
        else:
            logger.warning("⚠️ Не удалось создать новые сообщения")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления групп: {e}")
        return False

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск восстановления групп дубликатов...")
    
    success = await restore_groups()
    
    if success:
        logger.info("✅ Восстановление групп завершено успешно!")
    else:
        logger.error("❌ Восстановление групп завершилось с ошибками")

if __name__ == "__main__":
    asyncio.run(main()) 