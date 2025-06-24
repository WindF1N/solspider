#!/usr/bin/env python3
"""
Тест интеграции автоматической покупки VIP системы с Axiom.trade
"""

import asyncio
import logging

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def test_auto_buy():
    print("🧪 ТЕСТ АВТОПОКУПКИ VIP СИСТЕМЫ")
    print("=" * 50)
    
    try:
        from vip_twitter_monitor import VipTwitterMonitor
        
        # Создаем VIP монитор
        monitor = VipTwitterMonitor()
        
        # Тестовые данные
        test_contract = 'BzWB9JLNjhfDHoXRvhi6YruEwBVg81ya9peiDwYymwUd'
        test_username = 'MoriCoinCrypto'
        test_tweet = 'Check this awesome token! 🚀'
        test_amount_sol = 0.001
        
        print(f"📍 Контракт: {test_contract}")
        print(f"👤 От: @{test_username}")
        print(f"⚡ Сумма: {test_amount_sol} SOL")
        print(f"📱 Твит: {test_tweet}")
        print()
        
        # Проверяем конфигурацию
        print("🔧 ПРОВЕРКА КОНФИГУРАЦИИ:")
        print(f"   simulate_only: {monitor.auto_buy_config.get('simulate_only', 'N/A')}")
        print(f"   trading_platform: {monitor.auto_buy_config.get('trading_platform', 'N/A')}")
        print(f"   default_amount_sol: {monitor.auto_buy_config.get('default_amount_sol', 'N/A')}")
        print()
        
        # Выполняем тест автопокупки
        print("🚀 ВЫПОЛНЯЕМ АВТОПОКУПКУ...")
        result = await monitor.execute_automatic_purchase(
            test_contract, test_username, test_tweet, test_amount_sol
        )
        
        print()
        print("📊 РЕЗУЛЬТАТ:")
        print("=" * 30)
        print(f"✅ Успех: {result['success']}")
        print(f"⏱️ Время выполнения: {result.get('execution_time', 0):.2f}с")
        
        if result['success']:
            print(f"🔗 TX Hash: {result.get('tx_hash', 'N/A')}")
            print(f"⚡ Сумма SOL: {result.get('sol_amount', 0):.6f}")
            print(f"🏪 Платформа: {result.get('platform', 'N/A')}")
            print(f"📊 Статус: {result.get('status', 'N/A')}")
        else:
            print(f"❌ Ошибка: {result.get('error', 'Unknown')}")
        
        print()
        print("✅ ТЕСТ ЗАВЕРШЕН!")
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА ТЕСТА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_auto_buy()) 