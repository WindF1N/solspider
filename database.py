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
            db_user = os.getenv('DB_USER', 'solspider')
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