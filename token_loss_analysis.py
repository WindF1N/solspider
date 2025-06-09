#!/usr/bin/env python3
"""
Анализ возможных потерь токенов при переподключении WebSocket
"""

import time
import datetime

def analyze_token_loss_risk():
    """Анализирует риски потери токенов"""
    print("📊 АНАЛИЗ РИСКОВ ПОТЕРИ ТОКЕНОВ\n")
    print("=" * 60)
    
    # Данные для анализа
    scenarios = [
        {
            "name": "С задержками переподключения (старая версия)",
            "reconnect_delay": 5,  # 5 секунд задержка
            "detection_delay": 3,  # 3 секунды на обнаружение разрыва
            "total_delay": 8
        },
        {
            "name": "Мгновенное переподключение (новая версия)", 
            "reconnect_delay": 0,  # без задержки
            "detection_delay": 3,  # 3 секунды на обнаружение разрыва
            "total_delay": 3
        }
    ]
    
    # Статистика pump.fun
    tokens_per_minute = 15  # примерно 15 новых токенов в минуту в активное время
    
    for scenario in scenarios:
        print(f"\n🔸 {scenario['name']}")
        print("-" * 50)
        
        downtime = scenario['total_delay']
        potential_loss = (tokens_per_minute / 60) * downtime
        
        print(f"📊 Время простоя: {downtime} секунд")
        print(f"⚠️ Потенциальная потеря: ~{potential_loss:.1f} токенов")
        print(f"📈 Вероятность потери (%): {(potential_loss / tokens_per_minute * 60) * 100:.1f}%")
        
        # Расчет для разных частот разрывов
        print(f"\n📋 При разных частотах разрывов:")
        frequencies = [
            ("1 раз в час", 1/60),
            ("1 раз в 30 минут", 2/60), 
            ("1 раз в 10 минут", 6/60),
            ("1 раз в 5 минут", 12/60)
        ]
        
        for freq_name, freq_per_min in frequencies:
            daily_disconnects = freq_per_min * 60 * 24  # разрывов в день
            daily_loss = daily_disconnects * potential_loss
            print(f"   • {freq_name}: ~{daily_loss:.1f} токенов/день")
    
    print(f"\n" + "=" * 60)
    print("🎯 ВЫВОДЫ:")
    print("✅ Мгновенное переподключение снижает потери в 2.67 раза")
    print("✅ Критичны первые секунды после разрыва соединения")
    print("⚠️ Полностью избежать потерь при разрывах невозможно")
    print("💡 WebSocket - потоковый протокол, буферизации нет")
    
    print(f"\n🛡️ СПОСОБЫ МИНИМИЗАЦИИ РИСКОВ:")
    print("1. ⚡ Мгновенное переподключение (реализовано)")
    print("2. 🔄 Стабильное интернет-соединение")
    print("3. 📡 Мониторинг качества соединения")
    print("4. 🎯 Фильтрация токенов (меньше спама = меньше потерь)")
    print("5. 📊 Логирование для анализа пропусков")
    
    print(f"\n⚖️ КОМПРОМИССЫ:")
    print("✅ Быстрое переподключение VS Нагрузка на сервер")
    print("✅ Мгновенность VS Стабильность")
    print("✅ Минимальные потери VS Ресурсы")
    
    # Симуляция реального сценария
    print(f"\n🔬 РЕАЛЬНЫЙ ПРИМЕР (24 часа):")
    print("-" * 30)
    
    daily_tokens = tokens_per_minute * 60 * 24  # токенов в день
    connection_issues_per_day = 10  # предполагаем 10 разрывов в день
    
    old_system_loss = connection_issues_per_day * 8 * (tokens_per_minute / 60)
    new_system_loss = connection_issues_per_day * 3 * (tokens_per_minute / 60)
    
    print(f"📊 Всего токенов в день: ~{daily_tokens}")
    print(f"🔌 Предполагаемых разрывов: {connection_issues_per_day}")
    print(f"❌ Потери (старая система): ~{old_system_loss:.1f} токенов ({(old_system_loss/daily_tokens)*100:.2f}%)")
    print(f"✅ Потери (новая система): ~{new_system_loss:.1f} токенов ({(new_system_loss/daily_tokens)*100:.2f}%)")
    print(f"🎯 Улучшение: {old_system_loss - new_system_loss:.1f} токенов сохранено!")

if __name__ == "__main__":
    analyze_token_loss_risk() 