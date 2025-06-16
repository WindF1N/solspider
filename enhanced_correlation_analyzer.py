#!/usr/bin/env python3
"""
Улучшенный анализатор корреляций между метриками авторов твитов и движением рынка
"""

import pandas as pd
import asyncio
from datetime import datetime, timedelta
import logging
import re
from dotenv import load_dotenv
from database import get_db_manager, Token, TwitterAuthor, TweetMention
from twitter_profile_parser import TwitterProfileParser
from logger_config import setup_logging

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

class EnhancedCorrelationAnalyzer:
    """Улучшенный анализатор корреляций твитов и рынка"""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        
    def extract_username_from_tweet(self, tweet_text):
        """Извлекает имя пользователя из текста твита"""
        try:
            # Ищем паттерн @username в тексте твита
            pattern = r'@([a-zA-Z0-9_]+)'
            matches = re.findall(pattern, tweet_text)
            
            # Также ищем в начале твита после "RT "
            if tweet_text.startswith('RT @'):
                rt_match = re.match(r'RT @([a-zA-Z0-9_]+)', tweet_text)
                if rt_match:
                    return rt_match.group(1)
            
            # Возвращаем первое найденное имя пользователя
            if matches:
                return matches[0]
                
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения username: {e}")
            return None
    
    async def analyze_tweets_with_author_metrics(self):
        """Анализирует твиты с метриками авторов"""
        try:
            session = self.db_manager.Session()
            
            logger.info("🔍 Загружаем токены с найденными контрактами...")
            
            # Получаем токены с контрактами для анализа
            tokens = session.query(Token).filter(
                Token.twitter_contract_tweets > 0,
                Token.mint.isnot(None),
                Token.symbol.isnot(None)
            ).order_by(Token.twitter_contract_tweets.desc()).limit(20).all()
            
            logger.info(f"📊 Найдено {len(tokens)} токенов для детального анализа")
            
            results = []
            unique_authors = set()
            
            # Симулируем найденные твиты (в реальности будут из background_monitor)
            simulated_tweets = self.simulate_discovered_tweets(tokens)
            
            async with TwitterProfileParser() as profile_parser:
                for i, tweet_data in enumerate(simulated_tweets, 1):
                    logger.info(f"📱 Анализ твита {i}/{len(simulated_tweets)}")
                    
                    # Извлекаем username автора
                    author_username = self.extract_username_from_tweet(tweet_data['tweet_text'])
                    if not author_username:
                        continue
                    
                    # Загружаем профиль автора если еще не загружали
                    if author_username not in unique_authors:
                        profile_data = await profile_parser.get_profile(author_username)
                        
                        if profile_data:
                            # Сохраняем автора в базу
                            self.db_manager.save_twitter_author(profile_data)
                            unique_authors.add(author_username)
                            
                            logger.info(f"✅ Сохранен профиль @{author_username}: "
                                       f"{profile_data['followers_count']} подписчиков")
                    
                    # Сохраняем твит в базу
                    tweet_mention_data = {
                        'mint': tweet_data['mint'],
                        'author_username': author_username,
                        'tweet_text': tweet_data['tweet_text'],
                        'tweet_created_at': tweet_data['tweet_created_at'],
                        'discovered_at': datetime.utcnow(),
                        'mention_type': 'contract',
                        'search_query': tweet_data['mint']
                    }
                    
                    # Получаем метрики автора на момент твита
                    author = session.query(TwitterAuthor).filter_by(username=author_username).first()
                    if author:
                        tweet_mention_data['author_followers_at_time'] = author.followers_count
                        tweet_mention_data['author_verified_at_time'] = author.is_verified
                    
                    # Сохраняем упоминание
                    mention = self.db_manager.save_tweet_mention(tweet_mention_data)
                    
                    # Добавляем в результаты для анализа
                    result = {
                        'token': next(t for t in tokens if t.mint == tweet_data['mint']),
                        'tweet_data': tweet_data,
                        'author_data': author.__dict__ if author else None,
                        'mention_id': mention.id if mention else None
                    }
                    results.append(result)
                    
                    # Пауза между запросами
                    await asyncio.sleep(1)
            
            session.close()
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа твитов: {e}")
            return []
    
    def simulate_discovered_tweets(self, tokens):
        """Симулирует обнаруженные твиты для тестирования"""
        # В реальности эти данные будут поступать из background_monitor
        simulated_tweets = []
        
        sample_tweet_templates = [
            "🚀 New gem found! Check out {symbol} at {mint} - this could be huge! #crypto #solana",
            "RT @pumpdotfun: {symbol} just launched! Contract: {mint} 🔥",
            "📈 {symbol} is pumping! Contract address: {mint} - get in early!",
            "💎 Found another gem: {symbol} ({mint}) - thank me later 🚀",
            "🎯 New token alert: {symbol} - {mint} - looks promising!"
        ]
        
        for token in tokens[:10]:  # Берем первые 10 токенов
            # Генерируем 1-3 симулированных твита для каждого токена
            for i in range(token.twitter_contract_tweets if token.twitter_contract_tweets <= 3 else 1):
                template = sample_tweet_templates[i % len(sample_tweet_templates)]
                tweet_text = template.format(symbol=token.symbol, mint=token.mint)
                
                # Симулируем время создания твита
                created_time = token.created_at + timedelta(
                    hours=i * 2,  # Твиты через каждые 2 часа
                    minutes=i * 15
                )
                
                simulated_tweets.append({
                    'mint': token.mint,
                    'tweet_text': tweet_text,
                    'tweet_created_at': created_time,
                    'token_symbol': token.symbol
                })
        
        return simulated_tweets
    
    def create_correlation_analysis_excel(self, results):
        """Создает Excel файл с анализом корреляций"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"enhanced_correlation_analysis_{timestamp}.xlsx"
            
            # 1. Основная таблица с твитами и метриками авторов
            tweet_analysis = []
            
            # 2. Сводка по авторам
            author_summary = []
            
            # 3. Корреляции между метриками авторов и реакцией рынка
            correlation_data = []
            
            # Обрабатываем результаты
            for result in results:
                token = result['token']
                tweet_data = result['tweet_data']
                author_data = result['author_data']
                
                if author_data:
                    # Основная таблица твитов
                    tweet_row = {
                        'Символ токена': token.symbol,
                        'Название токена': token.name or 'N/A',
                        'Адрес контракта': token.mint,
                        'Текст твита': tweet_data['tweet_text'][:200] + '...' if len(tweet_data['tweet_text']) > 200 else tweet_data['tweet_text'],
                        'Автор твита': f"@{author_data['username']}",
                        'Отображаемое имя': author_data['display_name'] or 'N/A',
                        'Подписчики автора': author_data['followers_count'],
                        'Твиты автора': author_data['tweets_count'],
                        'Подписки автора': author_data['following_count'],
                        'Лайки автора': author_data['likes_count'],
                        'Верифицирован': 'Да' if author_data['is_verified'] else 'Нет',
                        'Дата регистрации': author_data['join_date'] or 'N/A',
                        'Био автора': (author_data['bio'] or '')[:100] + '...' if author_data['bio'] and len(author_data['bio']) > 100 else author_data['bio'] or 'N/A',
                        'Дата твита': tweet_data['tweet_created_at'].strftime('%Y-%m-%d %H:%M:%S') if tweet_data['tweet_created_at'] else 'N/A',
                        'Возраст токена при твите (ч)': f"{(tweet_data['tweet_created_at'] - token.created_at).total_seconds() / 3600:.1f}" if tweet_data['tweet_created_at'] else 'N/A',
                        
                        # Категории влияния
                        'Категория автора': self.categorize_author_influence(author_data),
                        'Потенциальное влияние': self.estimate_influence_potential(author_data),
                        
                        # Ссылки
                        'Профиль автора': f"https://nitter.tiekoetter.com/{author_data['username']}",
                        'DexScreener': f"https://dexscreener.com/solana/{token.mint}",
                        'Pump.fun': f"https://pump.fun/{token.mint}"
                    }
                    tweet_analysis.append(tweet_row)
            
            # Сводка по уникальным авторам
            unique_authors = {}
            for result in results:
                author_data = result['author_data']
                if author_data and author_data['username'] not in unique_authors:
                    unique_authors[author_data['username']] = author_data
            
            for username, author_data in unique_authors.items():
                # Считаем сколько токенов упоминал этот автор
                mentions_count = sum(1 for r in results if r['author_data'] and r['author_data']['username'] == username)
                
                author_row = {
                    'Имя пользователя': f"@{username}",
                    'Отображаемое имя': author_data['display_name'] or 'N/A',
                    'Подписчики': author_data['followers_count'],
                    'Твиты': author_data['tweets_count'],
                    'Подписки': author_data['following_count'],
                    'Лайки': author_data['likes_count'],
                    'Верифицирован': 'Да' if author_data['is_verified'] else 'Нет',
                    'Дата регистрации': author_data['join_date'] or 'N/A',
                    'Упомянул токенов': mentions_count,
                    'Категория влияния': self.categorize_author_influence(author_data),
                    'Потенциальное влияние': self.estimate_influence_potential(author_data),
                    'Engagement rate': f"{(author_data['likes_count'] / max(author_data['tweets_count'], 1)):.2f}" if author_data['tweets_count'] > 0 else 'N/A',
                    'Follower/Following ratio': f"{(author_data['followers_count'] / max(author_data['following_count'], 1)):.2f}" if author_data['following_count'] > 0 else 'N/A',
                    'Профиль': f"https://nitter.tiekoetter.com/{username}"
                }
                author_summary.append(author_row)
            
            # Анализ корреляций
            if len(results) > 5:
                df_analysis = pd.DataFrame(tweet_analysis)
                
                # Корреляция между подписчиками и различными метриками
                if 'Подписчики автора' in df_analysis.columns:
                    correlation_data.append({
                        'Метрика 1': 'Подписчики автора',
                        'Метрика 2': 'Количество твитов автора',
                        'Корреляция': f"{df_analysis['Подписчики автора'].corr(df_analysis['Твиты автора']):.4f}",
                        'Интерпретация': 'Связь между популярностью автора и его активностью'
                    })
                    
                    # Добавляем больше корреляций по мере накопления данных о влиянии на рынок
            
            # Создаем DataFrame'ы
            tweet_df = pd.DataFrame(tweet_analysis)
            author_df = pd.DataFrame(author_summary)
            correlation_df = pd.DataFrame(correlation_data)
            
            # Сохраняем в Excel
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                tweet_df.to_excel(writer, sheet_name='Анализ твитов', index=False)
                author_df.to_excel(writer, sheet_name='Сводка по авторам', index=False)
                
                if not correlation_df.empty:
                    correlation_df.to_excel(writer, sheet_name='Корреляции', index=False)
                
                # Статистика по категориям
                stats_data = []
                if not author_df.empty:
                    category_stats = author_df['Категория влияния'].value_counts()
                    for category, count in category_stats.items():
                        stats_data.append({
                            'Категория': 'Влияние авторов',
                            'Значение': category,
                            'Количество': count,
                            'Процент': f"{(count/len(author_df)*100):.1f}%"
                        })
                
                if stats_data:
                    stats_df = pd.DataFrame(stats_data)
                    stats_df.to_excel(writer, sheet_name='Статистика', index=False)
                
                # Автоподгонка ширины колонок
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 60)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
                    
                    worksheet.freeze_panes = 'A2'
            
            logger.info(f"✅ Улучшенный анализ корреляций сохранен в {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания Excel: {e}")
            return None
    
    def categorize_author_influence(self, author_data):
        """Категоризирует влияние автора"""
        followers = author_data['followers_count']
        is_verified = author_data['is_verified']
        
        if is_verified and followers > 100000:
            return "Макро-инфлюенсер"
        elif followers > 50000:
            return "Мега-инфлюенсер"
        elif followers > 10000:
            return "Макро-инфлюенсер"
        elif followers > 1000:
            return "Микро-инфлюенсер"
        elif followers > 100:
            return "Нано-инфлюенсер"
        else:
            return "Обычный пользователь"
    
    def estimate_influence_potential(self, author_data):
        """Оценивает потенциал влияния автора"""
        followers = author_data['followers_count']
        tweets = author_data['tweets_count']
        likes = author_data['likes_count']
        is_verified = author_data['is_verified']
        
        # Простая формула оценки влияния
        base_score = 0
        
        # Бонус за подписчиков
        if followers > 100000:
            base_score += 100
        elif followers > 10000:
            base_score += 75
        elif followers > 1000:
            base_score += 50
        elif followers > 100:
            base_score += 25
        
        # Бонус за верификацию
        if is_verified:
            base_score += 25
        
        # Бонус за активность (engagement)
        if tweets > 0:
            engagement_rate = likes / tweets
            if engagement_rate > 10:
                base_score += 20
            elif engagement_rate > 5:
                base_score += 10
            elif engagement_rate > 1:
                base_score += 5
        
        # Категоризация
        if base_score >= 100:
            return "Очень высокое"
        elif base_score >= 75:
            return "Высокое"
        elif base_score >= 50:
            return "Среднее"
        elif base_score >= 25:
            return "Низкое"
        else:
            return "Очень низкое"

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск улучшенного анализа корреляций твитов и рынка")
    
    analyzer = EnhancedCorrelationAnalyzer()
    
    # Анализируем твиты с метриками авторов
    results = await analyzer.analyze_tweets_with_author_metrics()
    
    if not results:
        logger.error("❌ Нет результатов для анализа")
        return
    
    logger.info(f"📊 Проанализировано {len(results)} твитов")
    
    # Создаем отчет
    filename = analyzer.create_correlation_analysis_excel(results)
    
    if filename:
        logger.info(f"📈 УЛУЧШЕННЫЙ АНАЛИЗ КОРРЕЛЯЦИЙ:")
        logger.info(f"  • Файл: {filename}")
        logger.info(f"  • Твитов проанализировано: {len(results)}")
        
        # Статистика по авторам
        unique_authors = set()
        macro_influencers = 0
        verified_authors = 0
        
        for result in results:
            author_data = result['author_data']
            if author_data:
                username = author_data['username']
                if username not in unique_authors:
                    unique_authors.add(username)
                    
                    if author_data['followers_count'] > 10000:
                        macro_influencers += 1
                    
                    if author_data['is_verified']:
                        verified_authors += 1
        
        logger.info(f"  • Уникальных авторов: {len(unique_authors)}")
        logger.info(f"  • Макро-инфлюенсеров (>10k): {macro_influencers}")
        logger.info(f"  • Верифицированных авторов: {verified_authors}")
    
    logger.info("✅ Улучшенный анализ корреляций завершен!")

if __name__ == "__main__":
    asyncio.run(main())
 