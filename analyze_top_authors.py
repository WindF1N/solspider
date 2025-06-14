#!/usr/bin/env python3
"""
Анализ топ авторов Twitter по упоминаниям токенов
"""

import sys
import os
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# Добавляем путь к модулям проекта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Загружаем переменные окружения
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import get_db_manager, TwitterAuthor, TweetMention

def analyze_top_authors():
    """Анализирует топ авторов по количеству упоминаний токенов"""
    
    print("🔍 Анализ топ авторов Twitter по упоминаниям токенов")
    print("=" * 60)
    
    try:
        # Подключаемся к базе данных
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Получаем всех авторов с их метриками
        authors = session.query(TwitterAuthor).all()
        
        if not authors:
            print("❌ Авторы Twitter не найдены в базе данных")
            return
            
        print(f"📊 Найдено {len(authors)} авторов в базе данных\n")
        
        # Получаем количество упоминаний для каждого автора
        author_mentions = {}
        author_details = {}
        
        for author in authors:
            # Считаем упоминания этого автора
            mentions_count = session.query(TweetMention).filter_by(author_username=author.username).count()
            
            author_mentions[author.username] = mentions_count
            author_details[author.username] = {
                'display_name': author.display_name or author.username,
                'followers': author.followers_count,
                'verified': author.is_verified,
                'first_seen': author.first_seen,
                'last_updated': author.last_updated,
                'bio': author.bio[:100] + "..." if author.bio and len(author.bio) > 100 else author.bio
            }
        
        # Сортируем по количеству упоминаний
        top_authors = sorted(author_mentions.items(), key=lambda x: x[1], reverse=True)
        
        # Показываем ТОП-20 авторов по упоминаниям
        print("🏆 ТОП-20 АВТОРОВ ПО КОЛИЧЕСТВУ УПОМИНАНИЙ ТОКЕНОВ:")
        print("-" * 80)
        print(f"{'№':<3} {'@Username':<20} {'Имя':<25} {'Упоминания':<12} {'Подписчики':<12} {'✓'}")
        print("-" * 80)
        
        for i, (username, mentions) in enumerate(top_authors[:20], 1):
            details = author_details[username]
            verified_mark = "✅" if details['verified'] else ""
            followers = f"{details['followers']:,}" if details['followers'] else "N/A"
            display_name = details['display_name'][:24] if details['display_name'] else username
            
            print(f"{i:<3} @{username:<19} {display_name:<25} {mentions:<12} {followers:<12} {verified_mark}")
        
        print("\n" + "=" * 60)
        
        # Статистика по верификации
        verified_authors = [a for a in authors if a.is_verified]
        total_mentions_verified = sum(author_mentions[a.username] for a in verified_authors)
        total_mentions_all = sum(author_mentions.values())
        
        print(f"📈 ОБЩАЯ СТАТИСТИКА:")
        print(f"   • Всего авторов: {len(authors)}")
        print(f"   • Верифицированных: {len(verified_authors)} ({len(verified_authors)/len(authors)*100:.1f}%)")
        print(f"   • Всего упоминаний: {total_mentions_all:,}")
        print(f"   • От верифицированных: {total_mentions_verified:,} ({total_mentions_verified/total_mentions_all*100:.1f}%)")
        
        # Анализ по подписчикам
        print(f"\n👥 РАСПРЕДЕЛЕНИЕ ПО ПОДПИСЧИКАМ:")
        followers_ranges = {
            "🔥 1M+": [a for a in authors if a.followers_count and a.followers_count >= 1_000_000],
            "⭐ 100K-1M": [a for a in authors if a.followers_count and 100_000 <= a.followers_count < 1_000_000],
            "📈 10K-100K": [a for a in authors if a.followers_count and 10_000 <= a.followers_count < 100_000],
            "🌱 1K-10K": [a for a in authors if a.followers_count and 1_000 <= a.followers_count < 10_000],
            "🔰 <1K": [a for a in authors if a.followers_count and a.followers_count < 1_000],
            "❓ Неизвестно": [a for a in authors if not a.followers_count]
        }
        
        for range_name, authors_list in followers_ranges.items():
            count = len(authors_list)
            if count > 0:
                total_mentions_range = sum(author_mentions[a.username] for a in authors_list)
                avg_mentions = total_mentions_range / count if count > 0 else 0
                print(f"   • {range_name}: {count} авторов, {total_mentions_range:,} упоминаний (avg: {avg_mentions:.1f})")
        
        # Топ авторы по влиянию (подписчики × упоминания)
        print(f"\n💎 ТОП-10 ПО ВЛИЯНИЮ (подписчики × упоминания):")
        print("-" * 70)
        
        influence_scores = []
        for username, mentions in author_mentions.items():
            details = author_details[username]
            followers = details['followers'] or 0
            influence = followers * mentions
            if influence > 0:
                influence_scores.append((username, influence, followers, mentions))
        
        influence_scores.sort(key=lambda x: x[1], reverse=True)
        
        for i, (username, influence, followers, mentions) in enumerate(influence_scores[:10], 1):
            details = author_details[username]
            verified_mark = "✅" if details['verified'] else ""
            print(f"{i:2}. @{username:<18} {influence:>12,} ({followers:,} × {mentions}) {verified_mark}")
        
        # Недавняя активность (за последние 7 дней)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_mentions = session.query(TweetMention).filter(TweetMention.discovered_at >= week_ago).all()
        
        if recent_mentions:
            print(f"\n📅 АКТИВНОСТЬ ЗА ПОСЛЕДНЮЮ НЕДЕЛЮ ({len(recent_mentions)} упоминаний):")
            print("-" * 50)
            
            recent_authors = Counter(mention.author_username for mention in recent_mentions)
            
            for i, (username, mentions) in enumerate(recent_authors.most_common(10), 1):
                if username in author_details:
                    details = author_details[username]
                    verified_mark = "✅" if details['verified'] else ""
                    print(f"{i:2}. @{username:<18} {mentions:>3} упоминаний {verified_mark}")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}")
        import traceback
        traceback.print_exc()

def analyze_blacklisted_authors():
    """Анализирует активность авторов из черного списка"""
    
    # Черный список из pump_bot.py
    blacklist = {
        'launchonpump', 'pumpdotfun', 'pump_fun', 'pumpfun', 'fake_aio'
    }
    
    print(f"\n🚫 АНАЛИЗ ЧЕРНОГО СПИСКА ({len(blacklist)} авторов):")
    print("-" * 50)
    
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        for username in blacklist:
            author = session.query(TwitterAuthor).filter_by(username=username).first()
            if author:
                mentions_count = session.query(TweetMention).filter_by(author_username=username).count()
                followers = f"{author.followers_count:,}" if author.followers_count else "N/A"
                verified_mark = "✅" if author.is_verified else ""
                
                print(f"   @{username:<15} {mentions_count:>3} упоминаний, {followers:>10} подписчиков {verified_mark}")
            else:
                print(f"   @{username:<15} не найден в БД")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка анализа черного списка: {e}")

if __name__ == "__main__":
    analyze_top_authors()
    analyze_blacklisted_authors() 