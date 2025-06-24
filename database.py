import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import pymysql

# Установка pymysql как драйвера по умолчанию для MySQL
pymysql.install_as_MySQLdb()

logger = logging.getLogger(__name__)

Base = declarative_base()

class Token(Base):
    """Модель для хранения информации о токенах"""
    __tablename__ = 'tokens'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    mint = Column(String(44), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    symbol = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    creator = Column(String(44), nullable=True, index=True)
    bonding_curve_key = Column(String(44), nullable=True)
    
    # Финансовые данные
    initial_buy = Column(Float, default=0.0)
    market_cap = Column(Float, default=0.0)
    creator_percentage = Column(Float, default=0.0)
    
    # Социальные сети
    twitter = Column(String(255), nullable=True)
    telegram = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)
    uri = Column(String(255), nullable=True)
    
    # Twitter анализ
    twitter_tweets = Column(Integer, default=0)
    twitter_symbol_tweets = Column(Integer, default=0)
    twitter_contract_tweets = Column(Integer, default=0)
    twitter_engagement = Column(Integer, default=0)
    twitter_score = Column(Float, default=0.0)
    twitter_rating = Column(String(50), nullable=True)
    twitter_contract_found = Column(Boolean, default=False)
    
    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notification_sent = Column(Boolean, default=False)
    last_twitter_notification = Column(DateTime, nullable=True)  # Время последнего уведомления о Twitter активности
    
    # Индексы для оптимизации запросов
    __table_args__ = (
        Index('idx_token_created_at', 'created_at'),
        Index('idx_token_market_cap', 'market_cap'),
        Index('idx_token_twitter_score', 'twitter_score'),
    )

class Trade(Base):
    """Модель для хранения торговых операций"""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    signature = Column(String(88), unique=True, nullable=False, index=True)
    mint = Column(String(44), nullable=False, index=True)
    trader = Column(String(44), nullable=False, index=True)
    
    # Торговые данные
    is_buy = Column(Boolean, nullable=False)
    sol_amount = Column(Float, nullable=False)
    token_amount = Column(Float, nullable=False)
    market_cap = Column(Float, default=0.0)
    bonding_curve_key = Column(String(44), nullable=True)
    
    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    notification_sent = Column(Boolean, default=False)
    
    # Индексы для оптимизации запросов
    __table_args__ = (
        Index('idx_trade_created_at', 'created_at'),
        Index('idx_trade_sol_amount', 'sol_amount'),
        Index('idx_trade_is_buy', 'is_buy'),
        Index('idx_mint_trader', 'mint', 'trader'),
    )

class Migration(Base):
    """Модель для хранения миграций на Raydium"""
    __tablename__ = 'migrations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    signature = Column(String(88), unique=True, nullable=False, index=True)
    mint = Column(String(44), nullable=False, index=True)
    bonding_curve_key = Column(String(44), nullable=True)
    
    # Миграционные данные
    liquidity_sol = Column(Float, default=0.0)
    liquidity_tokens = Column(Float, default=0.0)
    market_cap = Column(Float, default=0.0)
    
    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    notification_sent = Column(Boolean, default=False)
    
    # Индексы
    __table_args__ = (
        Index('idx_migration_created_at', 'created_at'),
        Index('idx_migration_liquidity', 'liquidity_sol'),
    )

class TwitterAuthor(Base):
    """Модель для хранения информации об авторах твитов"""
    __tablename__ = 'twitter_authors'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    
    # Метрики аккаунта
    tweets_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    followers_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    
    # Дополнительная информация
    bio = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    join_date = Column(String(100), nullable=True)
    is_verified = Column(Boolean, default=False)
    avatar_url = Column(String(500), nullable=True)
    
    # Метаданные
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Индексы
    __table_args__ = (
        Index('idx_author_followers', 'followers_count'),
        Index('idx_author_tweets', 'tweets_count'),
        Index('idx_author_verified', 'is_verified'),
    )

class TweetMention(Base):
    """Модель для хранения отдельных твитов с упоминанием контрактов"""
    __tablename__ = 'tweet_mentions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tweet_id = Column(String(50), nullable=True, index=True)  # ID твита если доступен
    mint = Column(String(44), nullable=False, index=True)  # Адрес контракта
    author_username = Column(String(100), nullable=False, index=True)
    
    # Содержимое твита
    tweet_text = Column(Text, nullable=False)
    tweet_created_at = Column(DateTime, nullable=True)  # Дата создания твита
    discovered_at = Column(DateTime, default=datetime.utcnow)  # Дата обнаружения
    
    # Тип упоминания
    mention_type = Column(String(20), default='contract')  # 'contract' или 'symbol'
    search_query = Column(String(200), nullable=True)  # Поисковый запрос
    
    # Метрики твита (если доступны)
    retweets = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    
    # Ссылка на автора
    author_followers_at_time = Column(Integer, nullable=True)  # Подписчики на момент твита
    author_verified_at_time = Column(Boolean, default=False)
    
    # Влияние на рынок (заполняется позже)
    market_impact_1h = Column(Float, nullable=True)  # Изменение цены через 1ч
    market_impact_6h = Column(Float, nullable=True)  # Изменение цены через 6ч
    market_impact_24h = Column(Float, nullable=True)  # Изменение цены через 24ч
    volume_impact_24h = Column(Float, nullable=True)  # Изменение объема через 24ч
    
    # Индексы
    __table_args__ = (
        Index('idx_mention_discovered', 'discovered_at'),
        Index('idx_mention_mint_author', 'mint', 'author_username'),
        Index('idx_mention_author_followers', 'author_followers_at_time'),
        Index('idx_mention_market_impact', 'market_impact_24h'),
    )

class DatabaseManager:
    """Менеджер для работы с базой данных"""
    
    def __init__(self):
        self.engine = None
        self.Session = None
        self._setup_database()
    
    def _setup_database(self):
        """Настройка подключения к базе данных"""
        try:
            # Получаем параметры подключения из переменных окружения
            db_host = os.getenv('DB_HOST', 'localhost')
            db_port = os.getenv('DB_PORT', '3306')
            db_user = os.getenv('DB_USER', 'root')
            db_password = os.getenv('DB_PASSWORD', 'password')
            db_name = os.getenv('DB_NAME', 'solspider')
            
            # Создаем строку подключения
            connection_string = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"
            
            # Создаем движок базы данных
            self.engine = create_engine(
                connection_string,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False  # Установите True для отладки SQL запросов
            )
            
            # Создаем фабрику сессий
            self.Session = sessionmaker(bind=self.engine)
            
            # Создаем таблицы если их нет
            Base.metadata.create_all(self.engine)
            
            logger.info("✅ Подключение к MySQL базе данных установлено")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к базе данных: {e}")
            raise
    
    def save_token(self, token_data, twitter_analysis):
        """Сохранение данных о токене"""
        session = self.Session()
        try:
            # Проверяем, существует ли токен
            existing_token = session.query(Token).filter_by(mint=token_data.get('mint')).first()
            
            if existing_token:
                # Обновляем существующий токен
                existing_token.name = token_data.get('name', existing_token.name)
                existing_token.symbol = token_data.get('symbol', existing_token.symbol)
                existing_token.description = token_data.get('description', existing_token.description)
                existing_token.market_cap = token_data.get('marketCap', existing_token.market_cap)
                existing_token.twitter_tweets = twitter_analysis.get('tweets', 0)
                existing_token.twitter_score = twitter_analysis.get('score', 0.0)
                existing_token.twitter_rating = twitter_analysis.get('rating', '')
                existing_token.updated_at = datetime.utcnow()
                
                token = existing_token
                logger.info(f"📝 Обновлен токен {token_data.get('symbol')} в БД")
            else:
                # Создаем новый токен
                token = Token(
                    mint=token_data.get('mint'),
                    name=token_data.get('name'),
                    symbol=token_data.get('symbol'),
                    description=token_data.get('description'),
                    creator=token_data.get('traderPublicKey'),
                    bonding_curve_key=token_data.get('bondingCurveKey'),
                    
                    initial_buy=token_data.get('initialBuy', 0.0),
                    market_cap=token_data.get('marketCap', 0.0),
                    creator_percentage=token_data.get('creatorPercentage', 0.0),
                    
                    twitter=token_data.get('twitter'),
                    telegram=token_data.get('telegram'),
                    website=token_data.get('website'),
                    uri=token_data.get('uri'),
                    
                    twitter_tweets=twitter_analysis.get('tweets', 0),
                    twitter_symbol_tweets=twitter_analysis.get('symbol_tweets', 0),
                    twitter_contract_tweets=twitter_analysis.get('contract_tweets', 0),
                    twitter_engagement=twitter_analysis.get('engagement', 0),
                    twitter_score=twitter_analysis.get('score', 0.0),
                    twitter_rating=twitter_analysis.get('rating', ''),
                    twitter_contract_found=twitter_analysis.get('contract_found', False)
                )
                
                session.add(token)
                logger.info(f"💾 Сохранен новый токен {token_data.get('symbol')} в БД")
            
            session.commit()
            return token
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения токена в БД: {e}")
            raise
        finally:
            session.close()
    
    def save_trade(self, trade_data):
        """Сохранение торговой операции"""
        session = self.Session()
        try:
            # Проверяем, существует ли торговая операция
            signature = trade_data.get('signature', '')
            if not signature:
                logger.warning("⚠️ Торговая операция без signature - пропускаем")
                return None
            
            existing_trade = session.query(Trade).filter_by(signature=signature).first()
            if existing_trade:
                logger.info(f"📊 Торговая операция {signature[:8]}... уже существует")
                return existing_trade
            
            # Создаем новую торговую операцию
            trade = Trade(
                signature=signature,
                mint=trade_data.get('mint'),
                trader=trade_data.get('traderPublicKey'),
                is_buy=trade_data.get('is_buy', True),
                sol_amount=float(trade_data.get('sol_amount', 0)),
                token_amount=float(trade_data.get('token_amount', 0)),
                market_cap=float(trade_data.get('market_cap', 0)),
                bonding_curve_key=trade_data.get('bondingCurveKey')
            )
            
            session.add(trade)
            session.commit()
            
            action = "покупка" if trade.is_buy else "продажа"
            logger.info(f"💰 Сохранена {action} {trade.sol_amount:.2f} SOL в БД")
            
            return trade
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения торговой операции в БД: {e}")
            raise
        finally:
            session.close()
    
    def save_migration(self, migration_data):
        """Сохранение миграции на Raydium"""
        session = self.Session()
        try:
            signature = migration_data.get('signature', '')
            if not signature:
                logger.warning("⚠️ Миграция без signature - пропускаем")
                return None
            
            existing_migration = session.query(Migration).filter_by(signature=signature).first()
            if existing_migration:
                logger.info(f"🔄 Миграция {signature[:8]}... уже существует")
                return existing_migration
            
            migration = Migration(
                signature=signature,
                mint=migration_data.get('mint'),
                bonding_curve_key=migration_data.get('bondingCurveKey'),
                liquidity_sol=float(migration_data.get('liquiditySol', 0)),
                liquidity_tokens=float(migration_data.get('liquidityTokens', 0)),
                market_cap=float(migration_data.get('marketCap', 0))
            )
            
            session.add(migration)
            session.commit()
            
            logger.info(f"🚀 Сохранена миграция {migration_data.get('mint', '')[:8]}... в БД")
            
            return migration
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения миграции в БД: {e}")
            raise
        finally:
            session.close()
    
    def get_token_stats(self):
        """Получение статистики по токенам"""
        session = self.Session()
        try:
            total_tokens = session.query(Token).count()
            total_trades = session.query(Trade).count()
            total_migrations = session.query(Migration).count()
            
            # Топ токены по Twitter скору
            top_tokens = session.query(Token)\
                .filter(Token.twitter_score > 0)\
                .order_by(Token.twitter_score.desc())\
                .limit(10)\
                .all()
            
            # Крупные сделки за последние 24 часа
            from datetime import timedelta
            yesterday = datetime.utcnow() - timedelta(days=1)
            big_trades = session.query(Trade)\
                .filter(Trade.created_at >= yesterday)\
                .filter(Trade.sol_amount >= 5.0)\
                .count()
            
            return {
                'total_tokens': total_tokens,
                'total_trades': total_trades,
                'total_migrations': total_migrations,
                'top_tokens': [{'symbol': t.symbol, 'score': t.twitter_score} for t in top_tokens],
                'big_trades_24h': big_trades
            }
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Ошибка получения статистики БД: {e}")
            return None
        finally:
            session.close()
    
    def save_twitter_author(self, author_data):
        """Сохранение данных об авторе твита"""
        session = self.Session()
        try:
            # Проверяем, существует ли автор
            existing_author = session.query(TwitterAuthor).filter_by(username=author_data.get('username')).first()
            
            if existing_author:
                # Обновляем существующего автора
                existing_author.display_name = author_data.get('display_name', existing_author.display_name)
                existing_author.tweets_count = author_data.get('tweets_count', existing_author.tweets_count)
                existing_author.following_count = author_data.get('following_count', existing_author.following_count)
                existing_author.followers_count = author_data.get('followers_count', existing_author.followers_count)
                existing_author.likes_count = author_data.get('likes_count', existing_author.likes_count)
                existing_author.bio = author_data.get('bio', existing_author.bio)
                existing_author.website = author_data.get('website', existing_author.website)
                existing_author.join_date = author_data.get('join_date', existing_author.join_date)
                existing_author.is_verified = author_data.get('is_verified', existing_author.is_verified)
                existing_author.avatar_url = author_data.get('avatar_url', existing_author.avatar_url)
                existing_author.last_updated = datetime.utcnow()
                
                author = existing_author
                logger.info(f"📝 Обновлен автор @{author_data.get('username')} в БД")
            else:
                # Создаем нового автора
                author = TwitterAuthor(
                    username=author_data.get('username'),
                    display_name=author_data.get('display_name'),
                    tweets_count=author_data.get('tweets_count', 0),
                    following_count=author_data.get('following_count', 0),
                    followers_count=author_data.get('followers_count', 0),
                    likes_count=author_data.get('likes_count', 0),
                    bio=author_data.get('bio'),
                    website=author_data.get('website'),
                    join_date=author_data.get('join_date'),
                    is_verified=author_data.get('is_verified', False),
                    avatar_url=author_data.get('avatar_url')
                )
                
                session.add(author)
                logger.info(f"💾 Сохранен новый автор @{author_data.get('username')} в БД")
            
            session.commit()
            return author
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения автора в БД: {e}")
            raise
        finally:
            session.close()
    
    def save_tweet_mention(self, tweet_data):
        """Сохранение упоминания токена в твите"""
        session = self.Session()
        try:
            # Создаем новое упоминание
            mention = TweetMention(
                tweet_id=tweet_data.get('tweet_id'),
                mint=tweet_data.get('mint'),
                author_username=tweet_data.get('author_username'),
                tweet_text=tweet_data.get('tweet_text'),
                tweet_created_at=tweet_data.get('tweet_created_at'),
                discovered_at=tweet_data.get('discovered_at', datetime.utcnow()),
                mention_type=tweet_data.get('mention_type', 'contract'),
                search_query=tweet_data.get('search_query'),
                retweets=tweet_data.get('retweets', 0),
                likes=tweet_data.get('likes', 0),
                replies=tweet_data.get('replies', 0),
                author_followers_at_time=tweet_data.get('author_followers_at_time'),
                author_verified_at_time=tweet_data.get('author_verified_at_time', False)
            )
            
            session.add(mention)
            session.commit()
            
            logger.info(f"📱 Сохранен твит от @{tweet_data.get('author_username')} о {tweet_data.get('mint')}")
            return mention
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"❌ Ошибка сохранения твита в БД: {e}")
            raise
        finally:
            session.close()
    
    def update_market_impact(self, mention_id, impact_data):
        """Обновление влияния твита на рынок"""
        session = self.Session()
        try:
            mention = session.query(TweetMention).filter_by(id=mention_id).first()
            if mention:
                mention.market_impact_1h = impact_data.get('impact_1h')
                mention.market_impact_6h = impact_data.get('impact_6h')
                mention.market_impact_24h = impact_data.get('impact_24h')
                mention.volume_impact_24h = impact_data.get('volume_impact_24h')
                
                session.commit()
                logger.info(f"📈 Обновлено влияние твита {mention_id} на рынок")
                return mention
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"❌ Ошибка обновления влияния на рынок: {e}")
            raise
        finally:
            session.close()

    def get_author_historical_data(self, username):
        """Получение исторических данных автора из базы данных"""
        session = self.Session()
        try:
            # Подсчитываем общее количество упоминаний
            total_mentions = session.query(TweetMention).filter_by(author_username=username).count()
            
            # Подсчитываем уникальные токены
            unique_tokens = session.query(TweetMention.mint).filter_by(author_username=username).distinct().count()
            
            # Получаем дату первого упоминания
            first_mention = session.query(TweetMention).filter_by(author_username=username).order_by(TweetMention.discovered_at.asc()).first()
            first_seen_date = first_mention.discovered_at if first_mention else None
            
            # Подсчитываем упоминания за последние 30 дней
            from datetime import timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_mentions = session.query(TweetMention).filter(
                TweetMention.author_username == username,
                TweetMention.discovered_at >= thirty_days_ago
            ).count()
            
            # Подсчитываем упоминания за последние 7 дней
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            weekly_mentions = session.query(TweetMention).filter(
                TweetMention.author_username == username,
                TweetMention.discovered_at >= seven_days_ago
            ).count()
            
            return {
                'total_mentions': total_mentions,
                'unique_tokens': unique_tokens,
                'first_seen_date': first_seen_date,
                'recent_mentions_30d': recent_mentions,
                'recent_mentions_7d': weekly_mentions
            }
            
        except SQLAlchemyError as e:
            logger.error(f"❌ Ошибка получения исторических данных автора {username}: {e}")
            return {
                'total_mentions': 0,
                'unique_tokens': 0,
                'first_seen_date': None,
                'recent_mentions_30d': 0,
                'recent_mentions_7d': 0
            }
        finally:
            session.close()

    def close(self):
        """Закрытие соединения с базой данных"""
        if self.engine:
            self.engine.dispose()
            logger.info("🔌 Соединение с базой данных закрыто")

# Глобальный экземпляр менеджера БД
db_manager = None

def get_db_manager():
    """Получение экземпляра менеджера БД"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager 