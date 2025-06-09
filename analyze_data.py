#!/usr/bin/env python3
"""
Скрипт для анализа данных SolSpider из MySQL базы данных
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Добавляем возможность импорта модулей проекта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import get_db_manager
from logger_config import setup_logging

def print_separator(title=""):
    """Печать разделителя с заголовком"""
    if title:
        print(f"\n{'='*20} {title} {'='*20}")
    else:
        print("="*60)

def analyze_tokens():
    """Анализ токенов"""
    print_separator("АНАЛИЗ ТОКЕНОВ")
    
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        from database import Token
        
        # Общая статистика
        total_tokens = session.query(Token).count()
        print(f"📊 Всего токенов в базе: {total_tokens:,}")
        
        if total_tokens == 0:
            print("❌ Нет данных о токенах")
            return
        
        # Токены за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_tokens = session.query(Token).filter(Token.created_at >= yesterday).count()
        print(f"📈 Токенов за последние 24ч: {recent_tokens:,}")
        
        # Токены с высоким Twitter скором
        high_score_tokens = session.query(Token).filter(Token.twitter_score >= 10).count()
        print(f"🔥 Токенов с высоким Twitter скором (≥10): {high_score_tokens:,}")
        
        # Топ 10 токенов по Twitter скору
        top_tokens = session.query(Token)\
            .filter(Token.twitter_score > 0)\
            .order_by(Token.twitter_score.desc())\
            .limit(10)\
            .all()
        
        if top_tokens:
            print(f"\n🏆 ТОП-10 токенов по Twitter активности:")
            for i, token in enumerate(top_tokens, 1):
                print(f"{i:2}. {token.symbol:8} | Score: {token.twitter_score:6.1f} | "
                      f"Tweets: {token.twitter_tweets:3} | MC: ${token.market_cap:10,.0f}")
        
        # Токены с социальными сетями
        tokens_with_social = session.query(Token).filter(
            (Token.twitter.isnot(None)) | 
            (Token.telegram.isnot(None)) | 
            (Token.website.isnot(None))
        ).count()
        print(f"\n🌐 Токенов с социальными сетями: {tokens_with_social:,}")
        
        # Средний market cap
        avg_market_cap = session.query(Token.market_cap).filter(Token.market_cap > 0).all()
        if avg_market_cap:
            avg_mc = sum(mc[0] for mc in avg_market_cap) / len(avg_market_cap)
            print(f"💰 Средний Market Cap: ${avg_mc:,.0f}")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка анализа токенов: {e}")

def analyze_trades():
    """Анализ торговых операций"""
    print_separator("АНАЛИЗ ТОРГОВЫХ ОПЕРАЦИЙ")
    
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        from database import Trade
        
        # Общая статистика
        total_trades = session.query(Trade).count()
        print(f"📊 Всего торговых операций: {total_trades:,}")
        
        if total_trades == 0:
            print("❌ Нет данных о торговых операциях")
            return
        
        # Разделение на покупки и продажи
        buys = session.query(Trade).filter(Trade.is_buy == True).count()
        sells = session.query(Trade).filter(Trade.is_buy == False).count()
        print(f"📈 Покупок: {buys:,} ({buys/total_trades*100:.1f}%)")
        print(f"📉 Продаж: {sells:,} ({sells/total_trades*100:.1f}%)")
        
        # Операции за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_trades = session.query(Trade).filter(Trade.created_at >= yesterday).count()
        print(f"⏰ Операций за последние 24ч: {recent_trades:,}")
        
        # Крупные сделки (>5 SOL)
        big_trades = session.query(Trade).filter(Trade.sol_amount >= 5.0).count()
        print(f"💎 Крупных сделок (≥5 SOL): {big_trades:,}")
        
        # Общий объем торгов в SOL
        total_volume = session.query(Trade.sol_amount).all()
        if total_volume:
            total_sol = sum(vol[0] for vol in total_volume)
            print(f"💰 Общий объем торгов: {total_sol:,.2f} SOL")
            
            avg_trade_size = total_sol / total_trades
            print(f"📊 Средний размер сделки: {avg_trade_size:.4f} SOL")
        
        # Топ трейдеры по объему
        from sqlalchemy import func
        top_traders = session.query(
            Trade.trader,
            func.sum(Trade.sol_amount).label('total_volume'),
            func.count(Trade.id).label('trade_count')
        ).group_by(Trade.trader)\
         .order_by(func.sum(Trade.sol_amount).desc())\
         .limit(5)\
         .all()
        
        if top_traders:
            print(f"\n🏆 ТОП-5 трейдеров по объему:")
            for i, (trader, volume, count) in enumerate(top_traders, 1):
                print(f"{i}. {trader[:8]}... | Объем: {volume:8.2f} SOL | Сделок: {count:3}")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка анализа торговых операций: {e}")

def analyze_migrations():
    """Анализ миграций"""
    print_separator("АНАЛИЗ МИГРАЦИЙ")
    
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        from database import Migration
        
        # Общая статистика
        total_migrations = session.query(Migration).count()
        print(f"📊 Всего миграций на Raydium: {total_migrations:,}")
        
        if total_migrations == 0:
            print("❌ Нет данных о миграциях")
            return
        
        # Миграции за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_migrations = session.query(Migration).filter(Migration.created_at >= yesterday).count()
        print(f"⏰ Миграций за последние 24ч: {recent_migrations:,}")
        
        # Общая ликвидность
        total_liquidity = session.query(Migration.liquidity_sol).all()
        if total_liquidity:
            total_liq_sol = sum(liq[0] for liq in total_liquidity if liq[0])
            print(f"💰 Общая ликвидность: {total_liq_sol:,.2f} SOL")
            
            avg_liquidity = total_liq_sol / total_migrations
            print(f"📊 Средняя ликвидность: {avg_liquidity:.2f} SOL")
        
        # Топ миграции по ликвидности
        top_migrations = session.query(Migration)\
            .filter(Migration.liquidity_sol > 0)\
            .order_by(Migration.liquidity_sol.desc())\
            .limit(5)\
            .all()
        
        if top_migrations:
            print(f"\n🏆 ТОП-5 миграций по ликвидности:")
            for i, migration in enumerate(top_migrations, 1):
                print(f"{i}. {migration.mint[:8]}... | "
                      f"Ликвидность: {migration.liquidity_sol:8.2f} SOL | "
                      f"MC: ${migration.market_cap:10,.0f}")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка анализа миграций: {e}")

def analyze_time_periods():
    """Анализ по временным периодам"""
    print_separator("АНАЛИЗ ПО ВРЕМЕНИ")
    
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        from database import Token, Trade
        from sqlalchemy import func
        
        # Активность по дням за последнюю неделю
        print("📅 Активность за последние 7 дней:")
        
        for days_ago in range(7):
            start_date = datetime.utcnow() - timedelta(days=days_ago+1)
            end_date = datetime.utcnow() - timedelta(days=days_ago)
            
            tokens_count = session.query(Token).filter(
                Token.created_at >= start_date,
                Token.created_at < end_date
            ).count()
            
            trades_count = session.query(Trade).filter(
                Trade.created_at >= start_date,
                Trade.created_at < end_date
            ).count()
            
            date_str = start_date.strftime('%m-%d')
            print(f"  {date_str}: Токенов: {tokens_count:3} | Сделок: {trades_count:4}")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка анализа по времени: {e}")

def main():
    """Главная функция"""
    print("🚀 SolSpider - Анализ данных")
    print(f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Проверяем подключение к БД
        db_manager = get_db_manager()
        print("✅ Подключение к базе данных установлено")
        
        # Выполняем анализ
        analyze_tokens()
        analyze_trades()
        analyze_migrations()
        analyze_time_periods()
        
        print_separator("АНАЛИЗ ЗАВЕРШЕН")
        print("📈 Все данные проанализированы успешно!")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 