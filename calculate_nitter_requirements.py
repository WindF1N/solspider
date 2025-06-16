#!/usr/bin/env python3
"""
Расчет оптимального количества Twitter аккаунтов для Nitter
"""

import pymysql
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

def calculate_nitter_requirements():
    """Рассчитывает требования к Nitter аккаунтам"""
    
    try:
        connection = pymysql.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'solspider'),
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        
        print("🔍 АНАЛИЗ НАГРУЗКИ SolSpider...")
        print("=" * 50)
        
        # Токены за последние 24 часа
        cursor.execute("SELECT COUNT(*) FROM tokens WHERE created_at >= NOW() - INTERVAL 24 HOUR")
        tokens_24h = cursor.fetchone()[0]
        
        # Токены за последний час
        cursor.execute("SELECT COUNT(*) FROM tokens WHERE created_at >= NOW() - INTERVAL 1 HOUR")
        tokens_1h = cursor.fetchone()[0]
        
        # Пиковая нагрузка за последние 7 дней
        cursor.execute("""
            SELECT HOUR(created_at) as hour, COUNT(*) as count 
            FROM tokens 
            WHERE created_at >= NOW() - INTERVAL 7 DAY 
            GROUP BY DATE(created_at), HOUR(created_at) 
            ORDER BY count DESC 
            LIMIT 1
        """)
        peak_result = cursor.fetchone()
        peak_tokens_per_hour = peak_result[1] if peak_result else 0
        
        # Средняя нагрузка
        cursor.execute("""
            SELECT AVG(hourly_count) as avg_per_hour FROM (
                SELECT COUNT(*) as hourly_count 
                FROM tokens 
                WHERE created_at >= NOW() - INTERVAL 7 DAY 
                GROUP BY DATE(created_at), HOUR(created_at)
            ) as hourly_stats
        """)
        avg_result = cursor.fetchone()
        avg_tokens_per_hour = int(avg_result[0]) if avg_result and avg_result[0] else 0
        
        print(f"📈 СТАТИСТИКА НАГРУЗКИ:")
        print(f"• Токены за 24ч: {tokens_24h:,}")
        print(f"• Токены за 1ч: {tokens_1h:,}")
        print(f"• Пиковая нагрузка: {peak_tokens_per_hour:,} токенов/час")
        print(f"• Средняя нагрузка: {avg_tokens_per_hour:,} токенов/час")
        print()
        
        # Расчет производительности
        peak_per_second = peak_tokens_per_hour / 3600
        avg_per_second = avg_tokens_per_hour / 3600
        
        print(f"⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:")
        print(f"• Пиковая: {peak_per_second:.2f} токенов/сек")
        print(f"• Средняя: {avg_per_second:.2f} токенов/сек")
        print()
        
        # Twitter API лимиты
        print(f"🚫 ЛИМИТЫ TWITTER API:")
        print(f"• Поиск: 300 запросов / 15 мин = 20 запросов/мин = 0.33 запроса/сек")
        print(f"• Профили: 900 запросов / 15 мин = 60 запросов/мин = 1 запрос/сек")
        print(f"• Общий лимит: ~75 запросов/мин на аккаунт")
        print()
        
        # Расчет для поиска (основная нагрузка)
        # Каждый токен = 2 поиска (с адресом и без кавычек)
        searches_per_second_peak = peak_per_second * 2
        searches_per_second_avg = avg_per_second * 2
        
        # Twitter лимит: 300 поисков за 15 минут = 0.33 поиска/сек на аккаунт
        twitter_search_limit_per_second = 300 / (15 * 60)  # 0.33
        
        accounts_needed_peak = int(searches_per_second_peak / twitter_search_limit_per_second) + 1
        accounts_needed_avg = int(searches_per_second_avg / twitter_search_limit_per_second) + 1
        
        print(f"🎯 РАСЧЕТ АККАУНТОВ ДЛЯ ПОИСКА:")
        print(f"• Поиски в секунду (пик): {searches_per_second_peak:.2f}")
        print(f"• Поиски в секунду (средн): {searches_per_second_avg:.2f}")
        print(f"• Лимит Twitter: {twitter_search_limit_per_second:.2f} поисков/сек/аккаунт")
        print(f"• Нужно аккаунтов (пик): {accounts_needed_peak}")
        print(f"• Нужно аккаунтов (средн): {accounts_needed_avg}")
        print()
        
        # Background Monitor - проверяет токены не старше 1 часа
        cursor.execute("SELECT COUNT(*) FROM tokens WHERE created_at >= NOW() - INTERVAL 1 HOUR")
        tokens_to_monitor = cursor.fetchone()[0]
        
        # Background Monitor делает проверку каждые 5 секунд
        monitor_frequency = 5  # секунд
        tokens_per_check = tokens_to_monitor
        
        # Каждый токен в мониторе = 1 поиск каждые 5 секунд
        monitor_searches_per_second = tokens_per_check / monitor_frequency
        accounts_needed_monitor = int(monitor_searches_per_second / twitter_search_limit_per_second) + 1
        
        print(f"🔄 BACKGROUND MONITOR:")
        print(f"• Токены в мониторе: {tokens_to_monitor:,}")
        print(f"• Частота проверки: каждые {monitor_frequency} сек")
        print(f"• Поиски в секунду: {monitor_searches_per_second:.2f}")
        print(f"• Нужно аккаунтов: {accounts_needed_monitor}")
        print()
        
        # Общий расчет
        total_accounts_peak = max(accounts_needed_peak, accounts_needed_monitor)
        total_accounts_avg = max(accounts_needed_avg, accounts_needed_monitor)
        
        # Добавляем запас 50% для надежности
        safety_margin = 1.5
        recommended_accounts = int(total_accounts_peak * safety_margin)
        
        print(f"📊 ИТОГОВЫЕ РЕКОМЕНДАЦИИ:")
        print(f"• Минимум для пика: {total_accounts_peak} аккаунтов")
        print(f"• Минимум для среднего: {total_accounts_avg} аккаунтов")
        print(f"• РЕКОМЕНДУЕТСЯ: {recommended_accounts} аккаунтов (с запасом 50%)")
        print()
        
        # Расчет стоимости прокси
        print(f"💰 РАСЧЕТ СТОИМОСТИ:")
        print(f"• {recommended_accounts} прокси x $3/месяц = ${recommended_accounts * 3}/месяц")
        print(f"• {recommended_accounts} Twitter аккаунтов (можно создать бесплатно)")
        print()
        
        # Ожидаемая производительность
        max_performance = recommended_accounts * twitter_search_limit_per_second
        print(f"🚀 ОЖИДАЕМАЯ ПРОИЗВОДИТЕЛЬНОСТЬ:")
        print(f"• Максимум поисков: {max_performance:.1f}/сек = {max_performance * 60:.0f}/мин")
        print(f"• Максимум токенов: {max_performance/2:.1f}/сек = {max_performance * 30:.0f}/мин")
        print(f"• УСКОРЕНИЕ в {max_performance/peak_per_second:.0f}x раз!")
        
        connection.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    calculate_nitter_requirements() 