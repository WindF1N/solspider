#!/usr/bin/env python3
"""
Скрипт для диагностики Google Sheets - проверка доступных таблиц
"""
import logging
from google_sheets_manager import sheets_manager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_google_sheets():
    """Проверяет доступные Google Sheets таблицы"""
    try:
        logger.info("🔍 Проверка доступа к Google Sheets...")
        
        # Проверяем инициализацию клиента
        if not sheets_manager.client:
            logger.error("❌ Google Sheets клиент не инициализирован")
            return False
        
        logger.info("✅ Google Sheets клиент готов")
        
        # Пытаемся открыть несколько известных таблиц
        known_sheet_names = [
            "Duplicates_PUMP",
            "Duplicates_PEPE", 
            "Duplicates_TRUMP",
            "Duplicates_DOGE",
            "Duplicates_BONK",
            "Duplicates_WIF",
            "pump_PUMP",
            "pepe_PEPE",
            "trump_TRUMP",
            "PUMP_Duplicates",
            "PEPE_Duplicates",
            "Token_PUMP",
            "Token_PEPE"
        ]
        
        found_sheets = []
        
        for sheet_name in known_sheet_names:
            try:
                spreadsheet = sheets_manager.client.open(sheet_name)
                found_sheets.append({
                    'name': sheet_name,
                    'url': spreadsheet.url,
                    'id': spreadsheet.id
                })
                logger.info(f"✅ Найдена таблица: {sheet_name}")
                logger.info(f"   📋 URL: {spreadsheet.url}")
                
                # Проверяем содержимое
                try:
                    worksheet = spreadsheet.sheet1
                    data = worksheet.get_all_values()
                    row_count = len(data)
                    logger.info(f"   📊 Строк данных: {row_count}")
                    
                    # Показываем заголовки если есть
                    if data and len(data) > 0:
                        headers = data[0]
                        logger.info(f"   📋 Заголовки: {headers}")
                        
                except Exception as e:
                    logger.warning(f"   ⚠️ Ошибка чтения данных: {e}")
                
            except Exception as e:
                logger.debug(f"❌ Таблица {sheet_name} не найдена: {e}")
        
        if found_sheets:
            logger.info(f"🎉 Найдено {len(found_sheets)} таблиц!")
            return found_sheets
        else:
            logger.warning("⚠️ Ни одной таблицы не найдено")
            
            # Пытаемся создать тестовую таблицу
            logger.info("🔧 Пытаемся создать тестовую таблицу...")
            try:
                test_sheet = sheets_manager.client.create("Test_Duplicates_Check")
                logger.info(f"✅ Тестовая таблица создана: {test_sheet.url}")
                
                # Примечание: Тестовая таблица создана и будет удалена вручную
                logger.info("🗑️ Тестовая таблица оставлена для проверки")
                
                logger.info("✅ Google Sheets API работает, но таблицы дубликатов не найдены")
                return []
                
            except Exception as e:
                logger.error(f"❌ Ошибка создания тестовой таблицы: {e}")
                return False
        
        return found_sheets
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки Google Sheets: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Запуск диагностики Google Sheets...")
    result = check_google_sheets()
    
    if result:
        logger.info("✅ Диагностика завершена успешно!")
    else:
        logger.error("❌ Диагностика выявила проблемы") 