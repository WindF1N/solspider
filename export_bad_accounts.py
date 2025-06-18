#!/usr/bin/env python3
"""
Скрипт для выгрузки аккаунтов с плохой оценкой
"""

import json
import csv
from datetime import datetime, timedelta
from decimal import Decimal
from database import get_db_manager, TwitterAuthor, TweetMention
from sqlalchemy import and_, or_, func

def calculate_author_metrics(session, author):
    """Вычисляет метрики автора на основе его активности"""
    
    # Подсчитываем общее количество упоминаний контрактов
    total_mentions = session.query(func.count(TweetMention.id))\
        .filter(TweetMention.author_username == author.username)\
        .scalar() or 0
    
    # Подсчитываем количество уникальных контрактов
    unique_contracts = session.query(func.count(func.distinct(TweetMention.mint)))\
        .filter(TweetMention.author_username == author.username)\
        .scalar() or 0
    
    # Подсчитываем активность за последние 7 дней
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_mentions = session.query(func.count(TweetMention.id))\
        .filter(TweetMention.author_username == author.username)\
        .filter(TweetMention.discovered_at >= week_ago)\
        .scalar() or 0
    
    # Подсчитываем среднее количество подписчиков
    avg_followers_result = session.query(func.avg(TweetMention.author_followers_at_time))\
        .filter(TweetMention.author_username == author.username)\
        .filter(TweetMention.author_followers_at_time.isnot(None))\
        .scalar()
    
    # Конвертируем Decimal в float для JSON
    if isinstance(avg_followers_result, Decimal):
        avg_followers = float(avg_followers_result)
    else:
        avg_followers = avg_followers_result or author.followers_count or 0
    
    # Рассчитываем spam_score (много упоминаний контрактов относительно подписчиков)
    if avg_followers > 0:
        spam_score = min(total_mentions / max(avg_followers / 1000, 1), 1.0)
    else:
        spam_score = 1.0 if total_mentions > 10 else 0.0
    
    # Рассчитываем diversity_score (много разных контрактов)
    if total_mentions > 0:
        diversity_score = min(unique_contracts / max(total_mentions, 1), 1.0)
    else:
        diversity_score = 0.0
    
    # Рассчитываем activity_score (высокая активность за последнюю неделю)
    activity_score = min(recent_mentions / 50, 1.0)  # 50+ упоминаний в неделю = подозрительно
    
    return {
        'total_mentions': int(total_mentions),
        'unique_contracts': int(unique_contracts),
        'recent_mentions': int(recent_mentions),
        'avg_followers': int(avg_followers),
        'spam_score': round(float(spam_score), 3),
        'diversity_score': round(float(diversity_score), 3),
        'activity_score': round(float(activity_score), 3)
    }

def analyze_author_quality(author, metrics):
    """Анализирует качество автора и возвращает оценку"""
    spam_score = metrics['spam_score']
    diversity_score = metrics['diversity_score']
    activity_score = metrics['activity_score']
    total_mentions = metrics['total_mentions']
    
    # Критерии плохой оценки:
    # 1. Высокий spam_score (>= 0.6) - много упоминаний относительно подписчиков
    # 2. Высокий diversity_score (>= 0.4) - много разных контрактов
    # 3. Высокий activity_score (>= 0.6) - подозрительно высокая активность
    # 4. Малое количество подписчиков при большой активности
    
    is_spam = spam_score >= 0.6
    is_diverse_spammer = diversity_score >= 0.4 and total_mentions >= 5
    is_hyperactive = activity_score >= 0.6
    is_low_quality = metrics['avg_followers'] < 100 and total_mentions >= 10
    
    # Определяем категорию
    if is_spam and is_diverse_spammer:
        category = "СПАМЕР + МНОЖЕСТВО КОНТРАКТОВ"
        severity = "КРИТИЧЕСКИЙ"
    elif is_spam and is_hyperactive:
        category = "СПАМЕР + ГИПЕРАКТИВНОСТЬ"
        severity = "КРИТИЧЕСКИЙ"
    elif is_spam:
        category = "СПАМЕР"
        severity = "ВЫСОКИЙ"
    elif is_diverse_spammer:
        category = "МНОЖЕСТВО КОНТРАКТОВ"
        severity = "СРЕДНИЙ"
    elif is_hyperactive:
        category = "ГИПЕРАКТИВНОСТЬ"
        severity = "СРЕДНИЙ"
    elif is_low_quality:
        category = "НИЗКОЕ КАЧЕСТВО АККАУНТА"
        severity = "НИЗКИЙ"
    else:
        category = "НОРМАЛЬНЫЙ"
        severity = "МИНИМАЛЬНЫЙ"
    
    is_bad = is_spam or is_diverse_spammer or is_hyperactive or is_low_quality
    
    return {
        'category': category,
        'severity': severity,
        'is_bad': is_bad,
        'metrics': metrics
    }

def export_bad_accounts():
    """Экспортирует аккаунты с плохой оценкой"""
    db_manager = get_db_manager()
    session = db_manager.Session()
    
    try:
        print("🔍 Загружаю всех авторов из базы данных...")
        
        # Получаем всех авторов, у которых есть упоминания контрактов
        authors_with_mentions = session.query(TwitterAuthor)\
            .join(TweetMention, TwitterAuthor.username == TweetMention.author_username)\
            .distinct().all()
        
        print(f"📊 Найдено {len(authors_with_mentions)} авторов с упоминаниями контрактов")
        
        # Анализируем каждого автора
        bad_accounts = []
        stats = {
            'total_authors': len(authors_with_mentions),
            'bad_accounts': 0,
            'categories': {}
        }
        
        for i, author in enumerate(authors_with_mentions):
            if i % 100 == 0:
                print(f"Обработано {i}/{len(authors_with_mentions)} авторов...")
            
            # Вычисляем метрики
            metrics = calculate_author_metrics(session, author)
            analysis = analyze_author_quality(author, metrics)
            
            if analysis['is_bad']:
                bad_account = {
                    'username': author.username,
                    'display_name': author.display_name or '',
                    'followers_count': author.followers_count or 0,
                    'tweets_count': author.tweets_count or 0,
                    'is_verified': author.is_verified or False,
                    'total_contract_mentions': metrics['total_mentions'],
                    'unique_contracts_mentioned': metrics['unique_contracts'],
                    'recent_mentions_7d': metrics['recent_mentions'],
                    'avg_followers': metrics['avg_followers'],
                    'spam_score': metrics['spam_score'],
                    'diversity_score': metrics['diversity_score'],
                    'activity_score': metrics['activity_score'],
                    'category': analysis['category'],
                    'severity': analysis['severity'],
                    'first_seen': author.first_seen.isoformat() if author.first_seen else None,
                    'last_updated': author.last_updated.isoformat() if author.last_updated else None,
                    'bio': (author.bio or '')[:200] + ('...' if len(author.bio or '') > 200 else '')
                }
                
                bad_accounts.append(bad_account)
                stats['bad_accounts'] += 1
                
                # Подсчет по категориям
                category = analysis['category']
                if category not in stats['categories']:
                    stats['categories'][category] = 0
                stats['categories'][category] += 1
        
        # Сортируем по серьезности проблемы
        severity_order = {'КРИТИЧЕСКИЙ': 0, 'ВЫСОКИЙ': 1, 'СРЕДНИЙ': 2, 'НИЗКИЙ': 3, 'МИНИМАЛЬНЫЙ': 4}
        bad_accounts.sort(key=lambda x: (
            severity_order.get(x['severity'], 5), 
            -x['spam_score'], 
            -x['diversity_score'],
            -x['total_contract_mentions']
        ))
        
        # Создаем имя файла с текущей датой
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f'bad_accounts_{timestamp}.json'
        csv_filename = f'bad_accounts_{timestamp}.csv'
        
        # Экспорт в JSON
        export_data = {
            'export_date': datetime.now().isoformat(),
            'statistics': stats,
            'bad_accounts': bad_accounts
        }
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        # Экспорт в CSV
        if bad_accounts:
            with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=bad_accounts[0].keys())
                writer.writeheader()
                writer.writerows(bad_accounts)
        
        # Выводим статистику
        print("\n" + "="*70)
        print("📊 СТАТИСТИКА ПЛОХИХ АККАУНТОВ")
        print("="*70)
        print(f"Всего авторов с упоминаниями: {stats['total_authors']}")
        print(f"Плохих аккаунтов: {stats['bad_accounts']}")
        if stats['total_authors'] > 0:
            print(f"Процент плохих: {(stats['bad_accounts']/stats['total_authors']*100):.1f}%")
        
        print("\n📈 РАСПРЕДЕЛЕНИЕ ПО КАТЕГОРИЯМ:")
        for category, count in sorted(stats['categories'].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / stats['bad_accounts'] * 100) if stats['bad_accounts'] > 0 else 0
            print(f"  {category}: {count} ({percentage:.1f}%)")
        
        print(f"\n💾 ФАЙЛЫ СОЗДАНЫ:")
        print(f"  📄 JSON: {json_filename}")
        print(f"  📊 CSV: {csv_filename}")
        
        # Показываем топ-15 худших аккаунтов
        print("\n🚫 ТОП-15 ХУДШИХ АККАУНТОВ:")
        print("-" * 100)
        print(f"{'USERNAME':<20} {'ПОДПИСЧИКИ':<12} {'КОНТРАКТЫ':<12} {'SPAM':<6} {'DIV':<6} {'ACT':<6} {'КАТЕГОРИЯ':<25}")
        print("-" * 100)
        
        for i, account in enumerate(bad_accounts[:15]):
            print(f"{account['username']:<20} {account['followers_count']:<12} "
                  f"{account['total_contract_mentions']:<12} {account['spam_score']:<6.2f} "
                  f"{account['diversity_score']:<6.2f} {account['activity_score']:<6.2f} "
                  f"{account['category']:<25}")
        
        if len(bad_accounts) > 15:
            print(f"... и еще {len(bad_accounts) - 15} аккаунтов")
        
        return json_filename, csv_filename, stats
        
    except Exception as e:
        print(f"❌ Ошибка при экспорте: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None
    finally:
        session.close()

def show_account_details(username):
    """Показывает детальную информацию об аккаунте"""
    db_manager = get_db_manager()
    session = db_manager.Session()
    
    try:
        author = session.query(TwitterAuthor).filter_by(username=username).first()
        
        if not author:
            print(f"❌ Аккаунт @{username} не найден в базе")
            return
        
        metrics = calculate_author_metrics(session, author)
        analysis = analyze_author_quality(author, metrics)
        
        print(f"\n👤 ДЕТАЛИ АККАУНТА: @{username}")
        print("=" * 60)
        print(f"Общая оценка: {'❌ ПЛОХОЙ' if analysis['is_bad'] else '✅ НОРМАЛЬНЫЙ'}")
        print(f"Категория: {analysis['category']}")
        print(f"Серьезность: {analysis['severity']}")
        print(f"\n📊 МЕТРИКИ:")
        print(f"  Спам-скор: {metrics['spam_score']:.3f}")
        print(f"  Разнообразие: {metrics['diversity_score']:.3f}")
        print(f"  Активность: {metrics['activity_score']:.3f}")
        print(f"  Всего упоминаний: {metrics['total_mentions']}")
        print(f"  Уникальных контрактов: {metrics['unique_contracts']}")
        print(f"  Упоминаний за 7 дней: {metrics['recent_mentions']}")
        print(f"\n👤 ИНФОРМАЦИЯ ОБ АККАУНТЕ:")
        print(f"  Подписчики: {author.followers_count or 0}")
        print(f"  Твиты: {author.tweets_count or 0}")
        print(f"  Верифицирован: {'Да' if author.is_verified else 'Нет'}")
        print(f"  Имя: {author.display_name or 'Не указано'}")
        print(f"  Впервые замечен: {author.first_seen}")
        print(f"  Последнее обновление: {author.last_updated}")
        
        if author.bio:
            print(f"  Биография: {author.bio[:200]}{'...' if len(author.bio) > 200 else ''}")
        
    except Exception as e:
        print(f"❌ Ошибка при получении деталей: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Показать детали конкретного аккаунта
        username = sys.argv[1].replace('@', '')
        show_account_details(username)
    else:
        # Экспорт всех плохих аккаунтов
        print("🚀 Начинаю экспорт плохих аккаунтов...")
        json_file, csv_file, stats = export_bad_accounts()
        
        if json_file:
            print(f"\n✅ Экспорт завершен успешно!")
            print(f"📁 Файлы сохранены в текущей папке")
        else:
            print("\n❌ Экспорт не удался") 