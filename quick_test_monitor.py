#!/usr/bin/env python3
"""
Быстрый тест исправлений Token Behavior Monitor
"""

import asyncio
import logging
from token_behavior_monitor import TokenBehaviorMonitor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def quick_test():
    """Быстрый тест на 10 секунд"""
    test_token = "6KqRm1oxMgTaoN2tNYSiNE1NeUTRiP6NZsMxNS3KzrzB"
    
    logger.info("🚀 Быстрый тест Token Behavior Monitor...")
    
    try:
        async with TokenBehaviorMonitor() as monitor:
            # Запускаем мониторинг
            success = await monitor.start_monitoring(test_token, "TEST")
            logger.info(f"✅ Мониторинг запущен: {success}")
            
            # Ждем 10 секунд
            logger.info("⏳ Ждем 10 секунд...")
            await asyncio.sleep(10)
            
            # Останавливаем
            logger.info("⏹️ Останавливаем...")
            stopped = await monitor.stop_monitoring(test_token)
            logger.info(f"✅ Остановка успешна: {stopped}")
            
        logger.info("🎉 Тест завершен успешно!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {str(e)}")

if __name__ == "__main__":
    asyncio.run(quick_test()) 