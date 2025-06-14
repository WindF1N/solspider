#!/usr/bin/env python3
"""
Быстрый экспорт авторов твитов с их последним токеном в Excel
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict
import re

# Добавляем путь к модулям проекта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import get_db_manager, TwitterAuthor, TweetMention, Token
from sqlalchemy import desc, func, text

def clean_excel_text(text):
    """Очищает текст от символов, недопустимых в Excel"""
    if not isinstance(text, str):
        return text
    
    # Удаляем null символы и другие управляющие символы
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Заменяем emoji и другие специальные символы
    text = re.sub(r'[^\x20-\x7E\u00A0-\uFFFF]', '?', text)
    
    # Ограничиваем длину строки
    if len(text) > 32000:
        text = text[:32000] + "..."
    
    return text

def export_authors_to_excel_fast():
    """Быстрый экспорт всех авторов с их последним токеном в Excel"""
    
    print("📊 Быстрый экспорт авторов твитов с последними токенами в Excel")
    print("=" * 60)
    
    try:
        # Подключаемся к базе данных
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Оптимизированный запрос: получаем авторов с их последними твитами одним запросом
        print("🔍 Получаю данные авторов из базы данных...")
        
        # SQL запрос для получения авторов с последними твитами
        query = text("""
            SELECT 
                ta.username,
                ta.display_name,
                ta.followers_count,
                ta.following_count,
                ta.tweets_count,
                ta.likes_count,
                ta.is_verified,
                ta.join_date,
                ta.bio,
                ta.website,
                ta.first_seen,
                ta.last_updated,
                COUNT(tm.id) as total_mentions,
                (SELECT tm2.tweet_text FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_tweet_text,
                (SELECT tm2.discovered_at FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_tweet_date,
                (SELECT tm2.mint FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_mint,
                (SELECT tm2.mention_type FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_mention_type,
                (SELECT tm2.search_query FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_search_query,
                (SELECT tm2.likes FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_tweet_likes,
                (SELECT tm2.retweets FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_tweet_retweets,
                (SELECT tm2.replies FROM tweet_mentions tm2 
                 WHERE tm2.author_username = ta.username 
                 ORDER BY tm2.discovered_at DESC LIMIT 1) as last_tweet_replies
            FROM twitter_authors ta
            LEFT JOIN tweet_mentions tm ON ta.username = tm.author_username
            GROUP BY ta.username
            ORDER BY ta.followers_count DESC
        """)
        
        result = session.execute(query)
        authors_data = []
        
        # Кэш для токенов
        tokens_cache = {}
        
        print("📊 Обрабатываю данные авторов...")
        
        for row in result:
            # Получаем информацию о токене если есть упоминание
            token_symbol = 'N/A'
            token_name = 'N/A'
            
            if row.last_mint:
                if row.last_mint in tokens_cache:
                    token = tokens_cache[row.last_mint]
                else:
                    token = session.query(Token).filter_by(mint=row.last_mint).first()
                    tokens_cache[row.last_mint] = token
                
                if token:
                    token_symbol = token.symbol or 'N/A'
                    token_name = token.name or 'N/A'
            
            # Формируем данные для Excel
            author_data = {
                'Автор': f"@{row.username}",
                'Отображаемое имя': clean_excel_text(row.display_name or 'N/A'),
                'Подписчики': row.followers_count or 0,
                'Подписки': row.following_count or 0,
                'Твиты': row.tweets_count or 0,
                'Лайки': row.likes_count or 0,
                'Верифицирован': 'Да' if row.is_verified else 'Нет',
                'Дата регистрации': clean_excel_text(row.join_date or 'N/A'),
                'Био': clean_excel_text((row.bio or '')[:150] + '...' if row.bio and len(row.bio) > 150 else row.bio or 'N/A'),
                'Сайт': clean_excel_text(row.website or 'N/A'),
                'Первое обнаружение': row.first_seen.strftime('%Y-%m-%d %H:%M:%S') if row.first_seen else 'N/A',
                'Последнее обновление': row.last_updated.strftime('%Y-%m-%d %H:%M:%S') if row.last_updated else 'N/A',
                'Всего упоминаний токенов': row.total_mentions or 0,
                'Последний токен - Символ': clean_excel_text(token_symbol),
                'Последний токен - Название': clean_excel_text(token_name),
                'Последний токен - Контракт': row.last_mint or 'N/A',
                'Последний твит - Текст': clean_excel_text(row.last_tweet_text[:200] + '...' if row.last_tweet_text and len(row.last_tweet_text) > 200 else row.last_tweet_text or 'Нет твитов'),
                'Последний твит - Дата': row.last_tweet_date.strftime('%Y-%m-%d %H:%M:%S') if row.last_tweet_date else 'N/A',
                'Последний твит - Тип упоминания': clean_excel_text(row.last_mention_type or 'N/A'),
                'Последний твит - Поиск': clean_excel_text(row.last_search_query or 'N/A'),
                'Последний твит - Лайки': row.last_tweet_likes or 0,
                'Последний твит - Ретвиты': row.last_tweet_retweets or 0,
                'Последний твит - Ответы': row.last_tweet_replies or 0,
                'Профиль': f"https://nitter.tiekoetter.com/{row.username}",
                'Категория по подписчикам': categorize_by_followers(row.followers_count or 0),
                'Ratio подписчики/подписки': f"{((row.followers_count or 0) / max(row.following_count or 1, 1)):.2f}" if (row.following_count or 0) > 0 else 'N/A',
                'Engagement rate': f"{((row.likes_count or 0) / max(row.tweets_count or 1, 1)):.2f}" if (row.tweets_count or 0) > 0 else 'N/A'
            }
            
            authors_data.append(author_data)
        
        print(f"📊 Обработано {len(authors_data)} авторов")
        
        # Создаем DataFrame
        df = pd.DataFrame(authors_data)
        
        # Получаем дополнительную статистику
        print("📊 Формирую статистику...")
        
        total_authors = len(authors_data)
        authors_with_tweets = len([a for a in authors_data if a['Всего упоминаний токенов'] > 0])
        verified_authors = len([a for a in authors_data if a['Верифицирован'] == 'Да'])
        avg_followers = sum(a['Подписчики'] for a in authors_data) / total_authors if total_authors > 0 else 0
        total_mentions = sum(a['Всего упоминаний токенов'] for a in authors_data)
        
        stats_data = [
            {'Метрика': 'Всего авторов в базе', 'Значение': total_authors},
            {'Метрика': 'Авторов с твитами', 'Значение': authors_with_tweets},
            {'Метрика': 'Авторов без твитов', 'Значение': total_authors - authors_with_tweets},
            {'Метрика': 'Верифицированных авторов', 'Значение': verified_authors},
            {'Метрика': '% верифицированных', 'Значение': f"{(verified_authors / total_authors * 100):.1f}%"},
            {'Метрика': 'Средние подписчики', 'Значение': f"{avg_followers:,.0f}"},
            {'Метрика': 'Всего упоминаний токенов', 'Значение': total_mentions},
            {'Метрика': 'Среднее упоминаний на автора', 'Значение': f"{(total_mentions / authors_with_tweets):.1f}" if authors_with_tweets > 0 else '0'},
            {'Метрика': 'Дата экспорта', 'Значение': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        ]
        
        # Статистика по категориям подписчиков
        categories = {}
        for author in authors_data:
            cat = author['Категория по подписчикам']
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1
        
        for category, count in categories.items():
            stats_data.append({
                'Метрика': f'Авторов в категории "{category}"',
                'Значение': f"{count} ({(count / total_authors * 100):.1f}%)"
            })
        
        stats_df = pd.DataFrame(stats_data)
        
        # Топ авторов по упоминаниям
        top_authors = df[df['Всего упоминаний токенов'] > 0].head(20)[
            ['Автор', 'Отображаемое имя', 'Подписчики', 'Всего упоминаний токенов', 'Верифицирован', 'Категория по подписчикам']
        ]
        
        # Топ авторов по подписчикам
        top_by_followers = df.head(20)[
            ['Автор', 'Отображаемое имя', 'Подписчики', 'Всего упоминаний токенов', 'Верифицирован', 'Последний токен - Символ', 'Последний твит - Текст']
        ]
        
        # Сохраняем в Excel
        print("💾 Сохраняю в Excel файл...")
        
        filename = f"authors_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Основная таблица всех авторов
            df.to_excel(writer, sheet_name='Все авторы', index=False)
            
            # Топ авторов по упоминаниям
            if not top_authors.empty:
                top_authors.to_excel(writer, sheet_name='Топ по упоминаниям', index=False)
            
            # Топ авторов по подписчикам
            top_by_followers.to_excel(writer, sheet_name='Топ по подписчикам', index=False)
            
            # Статистика
            stats_df.to_excel(writer, sheet_name='Статистика', index=False)
            
            # Авторы только с твитами
            authors_with_tweets_df = df[df['Всего упоминаний токенов'] > 0]
            if not authors_with_tweets_df.empty:
                authors_with_tweets_df.to_excel(writer, sheet_name='Авторы с твитами', index=False)
            
            # Верифицированные авторы
            verified_df = df[df['Верифицирован'] == 'Да']
            if not verified_df.empty:
                verified_df.to_excel(writer, sheet_name='Верифицированные', index=False)
        
        print(f"\n✅ Экспорт завершен!")
        print(f"📁 Файл сохранен: {filename}")
        print(f"📊 Всего авторов: {total_authors}")
        print(f"📱 Авторов с твитами: {authors_with_tweets}")
        print(f"✅ Верифицированных: {verified_authors}")
        print(f"💬 Всего упоминаний токенов: {total_mentions}")
        
        # Показываем топ-10 авторов
        print(f"\n🏆 ТОП-10 АВТОРОВ ПО ПОДПИСЧИКАМ:")
        print("-" * 80)
        for i, author in enumerate(df.head(10).itertuples(), 1):
            print(f"{i:2d}. {author.Автор:<20} | {author.Подписчики:>8,} | {author._17:<15} | Твитов: {author._13}")
        
        session.close()
        return filename
        
    except Exception as e:
        print(f"❌ Ошибка экспорта: {e}")
        import traceback
        traceback.print_exc()
        return None

def categorize_by_followers(followers_count):
    """Категоризирует авторов по количеству подписчиков"""
    if followers_count >= 100000:
        return "Инфлюенсер (100K+)"
    elif followers_count >= 10000:
        return "Популярный (10K-100K)"
    elif followers_count >= 1000:
        return "Активный (1K-10K)"
    elif followers_count >= 100:
        return "Начинающий (100-1K)"
    else:
        return "Новичок (<100)"

if __name__ == "__main__":
    export_authors_to_excel_fast() 