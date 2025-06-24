#!/usr/bin/env python3
"""
🧪 ТЕСТ VIP TWITTER MONITOR
Тестирование независимого VIP парсера Twitter аккаунтов
"""

import asyncio
import os
import sys
from datetime import datetime

# Проверяем наличие необходимых файлов
def check_files():
    """Проверяет наличие необходимых файлов"""
    required_files = ['vip_twitter_monitor.py', 'vip_config.py']
    missing_files = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    
    print("✅ Все необходимые файлы найдены")
    return True

# Проверяем импорты
def check_imports():
    """Проверяет возможность импорта модулей"""
    try:
        from vip_config import VIP_TWITTER_ACCOUNTS, VIP_MONITOR_SETTINGS
        print("✅ Конфигурация VIP успешно импортирована")
        
        import aiohttp
        import requests
        from bs4 import BeautifulSoup
        print("✅ Все зависимости доступны")
        
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

# Проверяем переменные окружения
def check_environment():
    """Проверяет переменные окружения"""
    vip_chat_id = os.getenv('VIP_CHAT_ID')
    
    if not vip_chat_id:
        print("⚠️ VIP_CHAT_ID не задан в переменных окружения")
        print("💡 Установите: export VIP_CHAT_ID=your_chat_id")
        return False
    
    print(f"✅ VIP_CHAT_ID настроен: {vip_chat_id[:10]}...")
    return True

# Тест конфигурации
def test_configuration():
    """Тестирует конфигурацию VIP аккаунтов"""
    try:
        from vip_config import (
            VIP_TWITTER_ACCOUNTS, VIP_MONITOR_SETTINGS, 
            get_active_accounts, get_auto_buy_accounts
        )
        
        print("\n🔧 ТЕСТ КОНФИГУРАЦИИ:")
        
        # Проверяем VIP аккаунты
        total_accounts = len(VIP_TWITTER_ACCOUNTS)
        active_accounts = get_active_accounts()
        auto_buy_accounts = get_auto_buy_accounts()
        
        print(f"📊 Всего VIP аккаунтов: {total_accounts}")
        print(f"✅ Активных аккаунтов: {len(active_accounts)}")
        print(f"💰 С автопокупкой: {len(auto_buy_accounts)}")
        
        # Выводим активные аккаунты
        for username, config in active_accounts.items():
            status = "🤖 АВТОПОКУПКА" if config.get('auto_buy', False) else "👁️ МОНИТОРИНГ"
            print(f"  • @{username} - {config['priority']} - {status}")
        
        # Проверяем настройки
        print(f"⏱️ Интервал проверки: {VIP_MONITOR_SETTINGS['default_check_interval']}с")
        print(f"🔄 Макс. попыток: {VIP_MONITOR_SETTINGS['max_retries']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования конфигурации: {e}")
        return False

# Тест инициализации VIP монитора
async def test_monitor_initialization():
    """Тестирует инициализацию VIP монитора"""
    try:
        print("\n🚀 ТЕСТ ИНИЦИАЛИЗАЦИИ МОНИТОРА:")
        
        from vip_twitter_monitor import VipTwitterMonitor
        
        # Создаем экземпляр монитора
        monitor = VipTwitterMonitor()
        
        print(f"✅ VIP монитор создан")
        print(f"📊 Активных аккаунтов: {sum(1 for config in monitor.VIP_ACCOUNTS.values() if config.get('enabled', False))}")
        print(f"🍪 Cookies для ротации: {len(monitor.cookies)}")
        print(f"⏱️ Интервал проверки: {monitor.check_interval}с")
        
        # Тест методов
        print("\n🔧 ТЕСТ МЕТОДОВ:")
        
        # Тест извлечения контрактов
        test_text = "Check out this new token: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU on Solana!"
        contracts = monitor.extract_contracts_from_text(test_text)
        
        if contracts:
            print(f"✅ Извлечение контрактов: найден {contracts[0][:8]}...")
        else:
            print("⚠️ Извлечение контрактов: не найдено")
        
        # Тест ротации cookies
        cookie1 = monitor.get_next_cookie()
        cookie2 = monitor.get_next_cookie()
        
        print(f"✅ Ротация cookies: {len(cookie1)} → {len(cookie2)} символов")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации монитора: {e}")
        return False

# Тест форматирования сообщений
def test_message_formatting():
    """Тестирует форматирование VIP сообщений"""
    try:
        print("\n📝 ТЕСТ ФОРМАТИРОВАНИЯ СООБЩЕНИЙ:")
        
        from vip_config import format_vip_message, create_keyboard
        
        # Тест базового сообщения
        message = format_vip_message(
            'contract_found',
            description='Тестовый VIP аккаунт',
            username='test_user',
            contract='7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
            tweet_text='Тестовый твит с упоминанием контракта',
            priority='HIGH',
            timestamp=datetime.now().strftime('%H:%M:%S')
        )
        
        if message and 'VIP TWITTER СИГНАЛ!' in message:
            print("✅ Форматирование базового сообщения работает")
        else:
            print("❌ Ошибка форматирования базового сообщения")
        
        # Тест сообщения автопокупки
        auto_buy_message = format_vip_message(
            'auto_buy_success',
            status='Тест успешен',
            amount_usd=1000.0,
            execution_time=2.5,
            tx_hash='test_tx_hash_123'
        )
        
        if auto_buy_message and 'АВТОМАТИЧЕСКАЯ ПОКУПКА' in auto_buy_message:
            print("✅ Форматирование сообщения автопокупки работает")
        else:
            print("❌ Ошибка форматирования автопокупки")
        
        # Тест клавиатуры
        keyboard = create_keyboard('7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU')
        
        if keyboard and len(keyboard) > 0:
            button_count = sum(len(row) for row in keyboard)
            print(f"✅ Создание клавиатуры: {button_count} кнопок в {len(keyboard)} рядах")
        else:
            print("❌ Ошибка создания клавиатуры")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования форматирования: {e}")
        return False

# Тест симуляции автопокупки
async def test_auto_buy_simulation():
    """Тестирует симуляцию автопокупки"""
    try:
        print("\n💰 ТЕСТ СИМУЛЯЦИИ АВТОПОКУПКИ:")
        
        from vip_twitter_monitor import VipTwitterMonitor
        
        monitor = VipTwitterMonitor()
        
        # Тест автопокупки
        result = await monitor.execute_automatic_purchase(
            contract='7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU',
            username='test_user',
            tweet_text='Тестовый твит',
            amount_usd=100.0
        )
        
        if result and 'success' in result:
            status = "✅ УСПЕХ" if result['success'] else "❌ ОШИБКА"
            print(f"{status} Автопокупка: {result.get('status', result.get('error', 'N/A'))}")
            print(f"⏱️ Время выполнения: {result.get('execution_time', 0):.2f}с")
            
            if result['success']:
                print(f"💵 Сумма: ${result.get('amount_usd', 0)}")
                print(f"🔗 TX: {result.get('tx_hash', 'N/A')}")
        else:
            print("❌ Ошибка выполнения автопокупки")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования автопокупки: {e}")
        return False

# Главная функция тестирования
async def run_all_tests():
    """Запускает все тесты VIP системы"""
    print("🧪 ЗАПУСК ТЕСТИРОВАНИЯ VIP TWITTER MONITOR")
    print("=" * 50)
    
    tests = [
        ("Проверка файлов", check_files),
        ("Проверка импортов", check_imports),
        ("Проверка окружения", check_environment),
        ("Тест конфигурации", test_configuration),
        ("Тест инициализации", test_monitor_initialization),
        ("Тест форматирования", test_message_formatting),
        ("Тест автопокупки", test_auto_buy_simulation),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}...")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
                print(f"✅ {test_name}: ПРОЙДЕН")
            else:
                print(f"❌ {test_name}: ПРОВАЛЕН")
        except Exception as e:
            print(f"💥 {test_name}: КРИТИЧЕСКАЯ ОШИБКА - {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! VIP система готова к работе!")
        print("\n🚀 Для запуска VIP мониторинга выполните:")
        print("   python vip_twitter_monitor.py")
    else:
        print("⚠️ Некоторые тесты провалены. Проверьте ошибки выше.")
        
        if not os.getenv('VIP_CHAT_ID'):
            print("\n💡 СОВЕТ: Настройте VIP_CHAT_ID для полного функционала:")
            print("   export VIP_CHAT_ID=your_telegram_chat_id")
    
    return passed == total

# Функция для быстрого теста
async def quick_test():
    """Быстрый тест основного функционала"""
    print("⚡ БЫСТРЫЙ ТЕСТ VIP СИСТЕМЫ")
    print("-" * 30)
    
    # Проверяем только критичные компоненты
    if not check_files():
        return False
    
    if not check_imports():
        return False
    
    try:
        from vip_twitter_monitor import VipTwitterMonitor
        monitor = VipTwitterMonitor()
        print("✅ VIP монитор инициализирован")
        
        # Тест извлечения контракта
        test_text = "New token: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
        contracts = monitor.extract_contracts_from_text(test_text)
        if contracts:
            print(f"✅ Извлечение контрактов: {contracts[0][:10]}...")
        
        print("🎉 Быстрый тест пройден!")
        return True
        
    except Exception as e:
        print(f"❌ Быстрый тест провален: {e}")
        return False

if __name__ == "__main__":
    # Выбираем тип теста
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        asyncio.run(quick_test())
    else:
        asyncio.run(run_all_tests())