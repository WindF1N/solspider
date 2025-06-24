#!/usr/bin/env python3
"""
Тест интеграции Axiom трейдера с основной системой SolSpider
"""

import asyncio
import logging
from pump_bot import execute_automatic_purchase

async def test_integration():
    """Тестирует интеграцию автоматической покупки"""
    
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    logger = logging.getLogger(__name__)
    
    logger.info("🧪 ТЕСТ ИНТЕГРАЦИИ AXIOM ТРЕЙДЕРА")
    logger.info("="*50)
    
    # Тестовые данные
    test_contract = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK
    test_username = "MoriCoinCrypto"
    test_tweet = "Проверяем новый токен BONK! 🚀"
    
    logger.info(f"📍 Контракт: {test_contract}")
    logger.info(f"👤 Пользователь: @{test_username}")
    logger.info(f"📱 Твит: {test_tweet}")
    
    try:
        # Выполняем тест автоматической покупки
        result = await execute_automatic_purchase(
            contract_address=test_contract,
            twitter_username=test_username,
            tweet_text=test_tweet
        )
        
        logger.info(f"\n📊 РЕЗУЛЬТАТ ТЕСТА:")
        logger.info(f"   ✅ Успех: {result['success']}")
        logger.info(f"   ⏱️  Время: {result.get('execution_time', 0):.2f}с")
        
        if result['success']:
            logger.info(f"   💰 Сумма: ${result.get('amount_usd', 0)}")
            logger.info(f"   🪙 SOL: {result.get('sol_amount', 0):.6f}")
            logger.info(f"   📊 Статус: {result.get('response', {}).get('status', 'N/A')}")
        else:
            logger.error(f"   ❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
        
        logger.info("\n" + "="*50)
        logger.info("📊 ТЕСТ ЗАВЕРШЕН")
        
        return result['success']
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка теста: {e}")
        return False

if __name__ == "__main__":
    print("🚀 ТЕСТ ИНТЕГРАЦИИ AXIOM ТРЕЙДЕРА С SOLSPIDER")
    print("="*55)
    print("⚠️  ВНИМАНИЕ: Это тест с реальными покупками!")
    print("💰 Сумма: ~$1062.5 (настроена для @MoriCoinCrypto)")
    print("🪙 Токен: BONK (тестовый)")
    print("⚡ Платформа: Axiom.trade")
    print("="*55)
    
    confirm = input("\nПродолжить тест интеграции? (yes/no): ").lower().strip()
    
    if confirm in ['yes', 'y', 'да', 'д']:
        print("\n🚀 Запускаем тест интеграции...\n")
        
        success = asyncio.run(test_integration())
        
        if success:
            print("\n✅ Тест интеграции прошел успешно!")
            print("🎉 Axiom трейдер успешно интегрирован в SolSpider!")
        else:
            print("\n❌ Тест интеграции завершился с ошибками")
    else:
        print("❌ Тест отменен пользователем") 