#!/usr/bin/env python3
"""
Скрипт для запуска SolSpider с фоновым мониторингом
"""

import asyncio
import logging
import signal
import sys
from pump_bot import main as pump_main
from background_monitor import BackgroundTokenMonitor
from logger_config import setup_logging

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

class SolSpiderManager:
    """Менеджер для управления основным ботом и фоновым мониторингом"""
    
    def __init__(self):
        self.monitor = BackgroundTokenMonitor()
        self.running = False
        
    async def start_all(self):
        """Запуск всех компонентов SolSpider"""
        self.running = True
        logger.info("🚀 Запуск SolSpider с полным функционалом...")
        
        try:
            # Запускаем оба процесса параллельно
            await asyncio.gather(
                self.run_pump_bot(),           # Основной бот для новых токенов
                self.run_background_monitor(), # Фоновый мониторинг существующих токенов
                return_exceptions=True
            )
        except Exception as e:
            logger.error(f"❌ Критическая ошибка SolSpider: {e}")
        finally:
            self.running = False
    
    async def run_pump_bot(self):
        """Запуск основного бота"""
        try:
            logger.info("🕷️ Запуск основного бота pump_bot...")
            await pump_main()
        except Exception as e:
            logger.error(f"❌ Ошибка основного бота: {e}")
            raise
    
    async def run_background_monitor(self):
        """Запуск фонового мониторинга"""
        try:
            # Небольшая задержка перед запуском мониторинга
            await asyncio.sleep(10)
            logger.info("📡 Запуск фонового мониторинга...")
            await self.monitor.start_monitoring()
        except Exception as e:
            logger.error(f"❌ Ошибка фонового мониторинга: {e}")
            raise
    
    def stop_all(self):
        """Остановка всех компонентов"""
        logger.info("🛑 Остановка SolSpider...")
        self.running = False
        self.monitor.stop_monitoring()

async def main():
    """Основная функция"""
    manager = SolSpiderManager()
    
    # Обработчик для корректного завершения
    def signal_handler(signum, frame):
        logger.info(f"🛑 Получен сигнал {signum}, завершение работы...")
        manager.stop_all()
        sys.exit(0)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("=" * 60)
        logger.info("🕷️ SOLSPIDER - ADVANCED TOKEN MONITORING SYSTEM")
        logger.info("=" * 60)
        logger.info("✅ Мониторинг новых токенов в реальном времени")
        logger.info("✅ Анализ Twitter активности")
        logger.info("✅ Фоновый поиск растущих токенов")
        logger.info("✅ Умная фильтрация по контрактам")
        logger.info("✅ База данных для хранения всех данных")
        logger.info("=" * 60)
        
        await manager.start_all()
        
    except KeyboardInterrupt:
        logger.info("🛑 SolSpider остановлен пользователем")
        manager.stop_all()
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка SolSpider: {e}")
        manager.stop_all()

if __name__ == "__main__":
    # Проверяем, что запущен правильный Python
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 SolSpider остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1) 