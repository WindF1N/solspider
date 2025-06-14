#!/usr/bin/env python3
"""
Экспорт авторов твитов с их последним токеном в Excel
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
from sqlalchemy import desc, func

def clean_excel_text(text):
    """Очищает текст от символов, недопустимых в Excel"""
    if not isinstance(text, str):
        return text
    
    # Удаляем null символы и другие управляющие символы
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Заменяем emoji и другие специальные символы
    text = re.sub(r'[^\x20-\x7E\u00A0-\uFFFF]', '?', text)
    
    # Ограничиваем длину строки (Excel имеет лимит 32767 символов на ячейку)
    if len(text) > 32000:
        text = text[:32000] + "..."
    
    return text

def export_authors_to_excel():
    """Экспортирует всех авторов с их последним токеном в Excel"""
    
    print("📊 Экспорт авторов твитов с последними токенами в Excel")
    print("=" * 60)
    
    try:
        # Подключаемся к базе данных
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Получаем всех авторов
        authors = session.query(TwitterAuthor).all()
        
        if not authors:
            print("❌ Авторы Twitter не найдены в базе данных")
            return
            
        print(f"📊 Найдено {len(authors)} авторов в базе данных")
        
        # Подготавливаем данные для Excel
        authors_data = []
        tokens_cache = {}  # Кэш для токенов
        
        for i, author in enumerate(authors, 1):
            print(f"🔍 Обрабатываю автора {i}/{len(authors)}: @{author.username}")
            
            # Получаем последний твит этого автора
            last_mention = session.query(TweetMention)\
                .filter_by(author_username=author.username)\
                .order_by(desc(TweetMention.discovered_at))\
                .first()
            
            if not last_mention:
                # Автор без твитов (только профиль)
                authors_data.append({
                    'Автор': f"@{author.username}",
                    'Отображаемое имя': clean_excel_text(author.display_name or 'N/A'),
                    'Подписчики': author.followers_count,
                    'Подписки': author.following_count,
                    'Твиты': author.tweets_count,
                    'Лайки': author.likes_count,
                    'Верифицирован': 'Да' if author.is_verified else 'Нет',
                    'Дата регистрации': clean_excel_text(author.join_date or 'N/A'),
                    'Био': clean_excel_text((author.bio or '')[:150] + '...' if author.bio and len(author.bio) > 150 else author.bio or 'N/A'),
                    'Сайт': clean_excel_text(author.website or 'N/A'),
                    'Первое обнаружение': author.first_seen.strftime('%Y-%m-%d %H:%M:%S') if author.first_seen else 'N/A',
                    'Последнее обновление': author.last_updated.strftime('%Y-%m-%d %H:%M:%S') if author.last_updated else 'N/A',
                    'Всего упоминаний токенов': 0,
                    'Последний токен - Символ': 'Нет твитов',
                    'Последний токен - Название': 'N/A',
                    'Последний токен - Контракт': 'N/A',
                    'Последний твит - Текст': 'Нет твитов',
                    'Последний твит - Дата': 'N/A',
                    'Последний твит - Тип упоминания': 'N/A',
                    'Последний твит - Поиск': 'N/A',
                    'Последний твит - Лайки': 'N/A',
                    'Последний твит - Ретвиты': 'N/A',
                    'Последний твит - Ответы': 'N/A',
                    'Профиль': f"https://nitter.tiekoetter.com/{author.username}",
                    'Категория по подписчикам': categorize_by_followers(author.followers_count),
                    'Ratio подписчики/подписки': f"{(author.followers_count / max(author.following_count, 1)):.2f}" if author.following_count > 0 else 'N/A',
                    'Engagement rate': f"{(author.likes_count / max(author.tweets_count, 1)):.2f}" if author.tweets_count > 0 else 'N/A'
                })
                continue
            
            # Получаем общее количество упоминаний этого автора
            total_mentions = session.query(TweetMention)\
                .filter_by(author_username=author.username)\
                .count()
            
            # Получаем информацию о токене
            token = None
            if last_mention.mint:
                # Проверяем кэш
                if last_mention.mint in tokens_cache:
                    token = tokens_cache[last_mention.mint]
                else:
                    token = session.query(Token).filter_by(mint=last_mention.mint).first()
                    tokens_cache[last_mention.mint] = token
            
            # Формируем данные для Excel
            authors_data.append({
                'Автор': f"@{author.username}",
                'Отображаемое имя': clean_excel_text(author.display_name or 'N/A'),
                'Подписчики': author.followers_count,
                'Подписки': author.following_count,
                'Твиты': author.tweets_count,
                'Лайки': author.likes_count,
                'Верифицирован': 'Да' if author.is_verified else 'Нет',
                'Дата регистрации': clean_excel_text(author.join_date or 'N/A'),
                'Био': clean_excel_text((author.bio or '')[:150] + '...' if author.bio and len(author.bio) > 150 else author.bio or 'N/A'),
                'Сайт': clean_excel_text(author.website or 'N/A'),
                'Первое обнаружение': author.first_seen.strftime('%Y-%m-%d %H:%M:%S') if author.first_seen else 'N/A',
                'Последнее обновление': author.last_updated.strftime('%Y-%m-%d %H:%M:%S') if author.last_updated else 'N/A',
                'Всего упоминаний токенов': total_mentions,
                'Последний токен - Символ': clean_excel_text(token.symbol if token else 'N/A'),
                'Последний токен - Название': clean_excel_text(token.name if token else 'N/A'),
                'Последний токен - Контракт': last_mention.mint or 'N/A',
                'Последний твит - Текст': clean_excel_text(last_mention.tweet_text[:200] + '...' if len(last_mention.tweet_text) > 200 else last_mention.tweet_text),
                'Последний твит - Дата': last_mention.discovered_at.strftime('%Y-%m-%d %H:%M:%S') if last_mention.discovered_at else 'N/A',
                'Последний твит - Тип упоминания': clean_excel_text(last_mention.mention_type or 'N/A'),
                'Последний твит - Поиск': clean_excel_text(last_mention.search_query or 'N/A'),
                'Последний твит - Лайки': last_mention.likes,
                'Последний твит - Ретвиты': last_mention.retweets,
                'Последний твит - Ответы': last_mention.replies,
                'Профиль': f"https://nitter.tiekoetter.com/{author.username}",
                'Категория по подписчикам': categorize_by_followers(author.followers_count),
                'Ratio подписчики/подписки': f"{(author.followers_count / max(author.following_count, 1)):.2f}" if author.following_count > 0 else 'N/A',
                'Engagement rate': f"{(author.likes_count / max(author.tweets_count, 1)):.2f}" if author.tweets_count > 0 else 'N/A'
            })
        
        # Создаем DataFrame
        df = pd.DataFrame(authors_data)
        
        # Сортируем по количеству подписчиков (убывание)
        df = df.sort_values('Подписчики', ascending=False)
        
        # Получаем дополнительную статистику
        stats_data = []
        
        # Общая статистика
        total_authors = len(authors_data)
        authors_with_tweets = len([a for a in authors_data if a['Всего упоминаний токенов'] > 0])
        verified_authors = len([a for a in authors_data if a['Верифицирован'] == 'Да'])
        avg_followers = sum(a['Подписчики'] for a in authors_data) / total_authors if total_authors > 0 else 0
        total_mentions = sum(a['Всего упоминаний токенов'] for a in authors_data)
        
        stats_data.extend([
            {'Метрика': 'Всего авторов в базе', 'Значение': total_authors},
            {'Метрика': 'Авторов с твитами', 'Значение': authors_with_tweets},
            {'Метрика': 'Авторов без твитов', 'Значение': total_authors - authors_with_tweets},
            {'Метрика': 'Верифицированных авторов', 'Значение': verified_authors},
            {'Метрика': '% верифицированных', 'Значение': f"{(verified_authors / total_authors * 100):.1f}%"},
            {'Метрика': 'Средние подписчики', 'Значение': f"{avg_followers:,.0f}"},
            {'Метрика': 'Всего упоминаний токенов', 'Значение': total_mentions},
            {'Метрика': 'Среднее упоминаний на автора', 'Значение': f"{(total_mentions / authors_with_tweets):.1f}" if authors_with_tweets > 0 else '0'}
        ])
        
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
        
        stats_data.append({
            'Метрика': 'Дата экспорта',
            'Значение': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
        stats_df = pd.DataFrame(stats_data)
        
        # Топ авторов по упоминаниям
        top_authors = df[df['Всего упоминаний токенов'] > 0].head(20)[
            ['Автор', 'Отображаемое имя', 'Подписчики', 'Всего упоминаний токенов', 'Верифицирован', 'Категория по подписчикам']
        ]
        
        # Сохраняем в Excel
        filename = f"authors_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Основная таблица всех авторов
            df.to_excel(writer, sheet_name='Все авторы', index=False)
            
            # Топ авторов по упоминаниям
            top_authors.to_excel(writer, sheet_name='Топ авторы', index=False)
            
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
    export_authors_to_excel() 