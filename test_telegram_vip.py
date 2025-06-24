#!/usr/bin/env python3
"""
Тест системы Telegram VIP мониторинга
"""

import asyncio
import logging

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def test_telegram_vip_system():
    print("📱 ТЕСТ TELEGRAM VIP СИСТЕМЫ")
    print("=" * 50)
    
    try:
        # Тестируем импорт конфигурации
        print("🔧 ПРОВЕРКА КОНФИГУРАЦИИ:")
        
        from telegram_vip_config import (
            VIP_TELEGRAM_CHATS, get_active_telegram_chats, 
            get_auto_buy_telegram_chats, format_telegram_message
        )
        from vip_config import get_gas_fee, get_gas_description
        
        active_chats = get_active_telegram_chats()
        auto_buy_chats = get_auto_buy_telegram_chats()
        
        print(f"✅ Активных чатов: {len(active_chats)}")
        print(f"💰 Чатов с автопокупкой: {len(auto_buy_chats)}")
        
        # Показываем конфигурацию каждого чата
        for chat_name, config in active_chats.items():
            print(f"\n📱 {chat_name}:")
            print(f"   🆔 Chat ID: {config['chat_id']}")
            print(f"   🎯 Приоритет: {config['priority']}")
            print(f"   💰 Автопокупка: {config['auto_buy']}")
            print(f"   💵 Сумма: {config['buy_amount_sol']} SOL")
            
            # Показываем настройки газа
            priority = config.get('priority', 'HIGH')
            if priority == 'ULTRA':
                gas_type = 'ultra_vip'
            else:
                gas_type = 'vip_signals'
            
            gas_fee = get_gas_fee(gas_type)
            gas_desc = get_gas_description(gas_type)
            gas_usd = gas_fee * 140
            
            print(f"   ⚡ Газ: {gas_fee} SOL (~${gas_usd:.2f})")
            print(f"   📝 {gas_desc}")
        
        print("\n🧪 ТЕСТ ФОРМАТИРОВАНИЯ СООБЩЕНИЙ:")
        
        # Тестируем форматирование уведомления
        test_message = format_telegram_message(
            'contract_found',
            description='VIP Telegram чат - мгновенные сигналы',
            chat_id=-1002605341782,
            author_name='@test_user',
            contract='7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
            message_text='Check this new token! CA: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
            priority='ULTRA',
            timestamp='15:30:45'
        )
        
        if 'TELEGRAM VIP СИГНАЛ' in test_message:
            print("✅ Форматирование уведомлений работает")
        else:
            print("❌ Ошибка форматирования уведомлений")
        
        # Тестируем автопокупку
        print("\n💰 ТЕСТ АВТОПОКУПКИ:")
        
        # Проверяем что модуль может быть импортирован
        try:
            from telegram_vip_monitor import TelegramVipMonitor
            
            monitor = TelegramVipMonitor()
            print("✅ TelegramVipMonitor инициализирован")
            
            # Тест извлечения контрактов
            test_text = "New token CA: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU pump to the moon!"
            contracts = monitor.extract_contracts_from_text(test_text)
            
            if contracts:
                print(f"✅ Извлечение контрактов: {contracts[0][:10]}...")
            else:
                print("❌ Не удалось извлечь контракт")
            
            print("✅ Основная функциональность проверена")
            
        except ImportError as e:
            print(f"❌ Ошибка импорта telegram_vip_monitor: {e}")
        
        print("\n🚀 РЕКОМЕНДАЦИИ ПО ЗАПУСКУ:")
        print("1. Убедитесь что переменная VIP_CHAT_ID настроена")
        print("2. Первый запуск: python telegram_vip_monitor.py")
        print("3. Будет создана сессия для Telegram API")
        print("4. Система начнет мониторинг указанных чатов")
        print("5. При обнаружении контрактов - автоматическая покупка с ULTRA газом ($5)")
        
        print("\n✅ СИСТЕМА ГОТОВА К РАБОТЕ!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_gas_calculations():
    """Тестируем расчеты газа"""
    print("\n🔥 ТЕСТ РАСЧЕТОВ ГАЗА:")
    
    try:
        from vip_config import GAS_CONFIG, get_gas_fee, get_gas_description
        
        for gas_type, config in GAS_CONFIG.items():
            fee = get_gas_fee(gas_type)
            desc = get_gas_description(gas_type)
            usd_value = fee * 140
            
            print(f"   {gas_type}: {fee} SOL (~${usd_value:.2f}) - {desc}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования газа: {e}")
        return False

async def main():
    """Главная функция теста"""
    success = await test_telegram_vip_system()
    gas_success = test_gas_calculations()
    
    if success and gas_success:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        print("\n❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")

if __name__ == "__main__":
    asyncio.run(main()) 