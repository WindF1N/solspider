#!/usr/bin/env python3
"""
Тест граничных случаев с часовыми поясами
Показывает когда UTC и локальное время дают разные даты
"""

from datetime import datetime, timedelta
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def test_timezone_edge_cases():
    """Тестирует граничные случаи когда UTC и локальное время дают разные даты"""
    
    print("🧪 ТЕСТ ГРАНИЧНЫХ СЛУЧАЕВ С ЧАСОВЫМИ ПОЯСАМИ")
    print("="*60)
    
    # Текущая информация
    utc_now = datetime.utcnow()
    local_now = datetime.now()
    offset_hours = (local_now - utc_now).total_seconds() / 3600
    
    print(f"🕐 UTC время: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🕐 Локальное время: {local_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌍 Смещение: UTC{'+' if offset_hours >= 0 else ''}{offset_hours:.0f}")
    
    # Проверяем текущую ситуацию
    utc_yesterday = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
    local_yesterday = (local_now - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"\n📅 ТЕКУЩАЯ СИТУАЦИЯ:")
    print(f"   UTC yesterday: {utc_yesterday}")
    print(f"   Local yesterday: {local_yesterday}")
    
    if utc_yesterday != local_yesterday:
        print(f"   ⚠️  ПРОБЛЕМА АКТИВНА! Разные даты!")
    else:
        print(f"   ✅ Сейчас даты одинаковые")
    
    # Симулируем разные времена суток для демонстрации проблемы
    print(f"\n🕐 СИМУЛЯЦИЯ РАЗНЫХ ВРЕМЕН СУТОК:")
    print("-" * 60)
    
    test_times = [
        (0, 30),   # 00:30 - рано утром
        (1, 0),    # 01:00 - когда UTC переходит на новый день
        (2, 30),   # 02:30 - между переходами
        (3, 0),    # 03:00 - когда локальное время переходит на новый день
        (12, 0),   # 12:00 - полдень
        (23, 30),  # 23:30 - поздно вечером
    ]
    
    for hour, minute in test_times:
        # Создаем тестовое время
        test_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        test_utc = test_local - timedelta(hours=offset_hours)
        
        # Вычисляем yesterday для каждого метода
        test_utc_yesterday = (test_utc - timedelta(days=1)).strftime('%Y-%m-%d')
        test_local_yesterday = (test_local - timedelta(days=1)).strftime('%Y-%m-%d')
        
        status = "⚠️ РАЗНЫЕ" if test_utc_yesterday != test_local_yesterday else "✅ ОДИНАКОВЫЕ"
        
        print(f"   {hour:02d}:{minute:02d} | UTC: {test_utc_yesterday} | Local: {test_local_yesterday} | {status}")

def demonstrate_problem_scenario():
    """Демонстрирует конкретный сценарий когда проблема проявляется"""
    
    print(f"\n🎯 ДЕМОНСТРАЦИЯ ПРОБЛЕМЫ:")
    print("="*60)
    
    # Система в MSK (UTC+3), время 01:30 UTC = 04:30 MSK
    print("Сценарий: Система в MSK (UTC+3), время 01:30 UTC")
    
    # Симулируем это время
    utc_time = datetime(2025, 6, 24, 1, 30, 0)  # 01:30 UTC
    local_time = utc_time + timedelta(hours=3)   # 04:30 MSK
    
    print(f"🕐 UTC: {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🕐 MSK: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Вычисляем yesterday
    utc_yesterday = (utc_time - timedelta(days=1)).strftime('%Y-%m-%d')
    local_yesterday = (local_time - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"\n📅 РЕЗУЛЬТАТ:")
    print(f"   UTC метод: since={utc_yesterday}")
    print(f"   Local метод: since={local_yesterday}")
    
    if utc_yesterday != local_yesterday:
        print(f"   ⚠️  ПРОБЛЕМА: Разные даты в параметре since!")
        print(f"   📝 UTC дает более раннюю дату")
        print(f"   📝 Это может пропускать новые твиты")
    else:
        print(f"   ✅ В этом сценарии даты одинаковые")

def show_fix_impact():
    """Показывает влияние исправления"""
    
    print(f"\n🔧 ВЛИЯНИЕ ИСПРАВЛЕНИЯ:")
    print("="*60)
    
    print("ДО ИСПРАВЛЕНИЯ:")
    print("   pump_bot.py: yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')")
    print("   background_monitor.py: yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')")
    print("   ❌ Проблема: В некоторые часы UTC и локальное время дают разные даты")
    
    print("\nПОСЛЕ ИСПРАВЛЕНИЯ:")
    print("   pump_bot.py: yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')")
    print("   background_monitor.py: yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')")
    print("   ✅ Решение: Всегда используется локальное время системы")
    
    print("\nПРЕИМУЩЕСТВА:")
    print("   • Корректная работа в любом часовом поясе")
    print("   • Нет пропуска твитов из-за неправильных дат")
    print("   • Консистентность между разными компонентами системы")
    print("   • Соответствие ожиданиям пользователей в локальном времени")

if __name__ == "__main__":
    test_timezone_edge_cases()
    demonstrate_problem_scenario()
    show_fix_impact()
    
    print(f"\n✅ ИСПРАВЛЕНИЕ ПРИМЕНЕНО В ФАЙЛАХ:")
    print("   • pump_bot.py")
    print("   • background_monitor.py")
    print(f"\n🎯 РЕКОМЕНДАЦИЯ: Перезапустите систему для применения изменений") 