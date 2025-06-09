import os
import logging
import logging.handlers
from datetime import datetime
import colorlog

def setup_logging():
    """Настройка системы логирования"""
    
    # Создаем папку для логов если её нет
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        print(f"📁 Создана папка для логов: {log_dir}")
    
    # Удаляем все существующие обработчики
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Устанавливаем базовый уровень логирования
    root_logger.setLevel(logging.DEBUG)
    
    # Форматы для логов
    detailed_format = '[%(asctime)s] %(name)s.%(funcName)s:%(lineno)d %(levelname)s: %(message)s'
    simple_format = '%(asctime)s %(levelname)s: %(message)s'
    color_format = '%(log_color)s[%(asctime)s] %(levelname)s%(reset)s: %(message)s'
    
    # 1. Консольный вывод с цветами
    console_handler = colorlog.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = colorlog.ColoredFormatter(
        color_format,
        datefmt='%H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 2. Общий лог файл (все сообщения)
    general_log_file = os.path.join(log_dir, 'solspider.log')
    general_handler = logging.handlers.RotatingFileHandler(
        general_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    general_handler.setLevel(logging.DEBUG)
    general_formatter = logging.Formatter(detailed_format, datefmt='%Y-%m-%d %H:%M:%S')
    general_handler.setFormatter(general_formatter)
    root_logger.addHandler(general_handler)
    
    # 3. Лог файл для ошибок
    error_log_file = os.path.join(log_dir, 'errors.log')
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(detailed_format, datefmt='%Y-%m-%d %H:%M:%S')
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)
    
    # 4. Лог файл для токенов (новые токены и их анализ)
    tokens_log_file = os.path.join(log_dir, 'tokens.log')
    tokens_handler = logging.handlers.RotatingFileHandler(
        tokens_log_file,
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,
        encoding='utf-8'
    )
    tokens_handler.setLevel(logging.INFO)
    tokens_formatter = logging.Formatter(simple_format, datefmt='%Y-%m-%d %H:%M:%S')
    tokens_handler.setFormatter(tokens_formatter)
    
    # Создаем отдельный логгер для токенов
    tokens_logger = logging.getLogger('tokens')
    tokens_logger.addHandler(tokens_handler)
    tokens_logger.setLevel(logging.INFO)
    tokens_logger.propagate = False  # Не передавать в родительский логгер
    
    # 5. Лог файл для торговых операций
    trades_log_file = os.path.join(log_dir, 'trades.log')
    trades_handler = logging.handlers.RotatingFileHandler(
        trades_log_file,
        maxBytes=20 * 1024 * 1024,  # 20 MB
        backupCount=5,
        encoding='utf-8'
    )
    trades_handler.setLevel(logging.INFO)
    trades_formatter = logging.Formatter(simple_format, datefmt='%Y-%m-%d %H:%M:%S')
    trades_handler.setFormatter(trades_formatter)
    
    # Создаем отдельный логгер для торговли
    trades_logger = logging.getLogger('trades')
    trades_logger.addHandler(trades_handler)
    trades_logger.setLevel(logging.INFO)
    trades_logger.propagate = False
    
    # 6. Лог файл для базы данных
    database_log_file = os.path.join(log_dir, 'database.log')
    database_handler = logging.handlers.RotatingFileHandler(
        database_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
        encoding='utf-8'
    )
    database_handler.setLevel(logging.DEBUG)
    database_formatter = logging.Formatter(detailed_format, datefmt='%Y-%m-%d %H:%M:%S')
    database_handler.setFormatter(database_formatter)
    
    # Создаем отдельный логгер для БД
    database_logger = logging.getLogger('database')
    database_logger.addHandler(database_handler)
    database_logger.setLevel(logging.DEBUG)
    database_logger.propagate = False
    
    # 7. Лог файл для статистики (ежедневный)
    today = datetime.now().strftime('%Y-%m-%d')
    stats_log_file = os.path.join(log_dir, f'stats_{today}.log')
    stats_handler = logging.FileHandler(stats_log_file, encoding='utf-8')
    stats_handler.setLevel(logging.INFO)
    stats_formatter = logging.Formatter(simple_format, datefmt='%Y-%m-%d %H:%M:%S')
    stats_handler.setFormatter(stats_formatter)
    
    # Создаем отдельный логгер для статистики
    stats_logger = logging.getLogger('stats')
    stats_logger.addHandler(stats_handler)
    stats_logger.setLevel(logging.INFO)
    stats_logger.propagate = False
    
    # Логируем успешную настройку
    logging.info("✅ Система логирования настроена успешно")
    logging.info(f"📁 Логи сохраняются в папку: {os.path.abspath(log_dir)}")
    logging.info("📊 Доступные лог-файлы:")
    logging.info(f"  • solspider.log - общий лог")
    logging.info(f"  • errors.log - только ошибки")
    logging.info(f"  • tokens.log - информация о токенах")
    logging.info(f"  • trades.log - торговые операции")
    logging.info(f"  • database.log - операции с БД")
    logging.info(f"  • stats_{today}.log - статистика за день")
    
    return {
        'tokens_logger': tokens_logger,
        'trades_logger': trades_logger,
        'database_logger': database_logger,
        'stats_logger': stats_logger
    }

def get_token_logger():
    """Получение логгера для токенов"""
    return logging.getLogger('tokens')

def get_trades_logger():
    """Получение логгера для торговых операций"""
    return logging.getLogger('trades')

def get_database_logger():
    """Получение логгера для базы данных"""
    return logging.getLogger('database')

def get_stats_logger():
    """Получение логгера для статистики"""
    return logging.getLogger('stats')

def log_token_analysis(token_data, twitter_analysis, should_notify):
    """Специальное логирование анализа токена"""
    tokens_logger = get_token_logger()
    
    symbol = token_data.get('symbol', 'UNK')
    mint = token_data.get('mint', 'Unknown')
    score = twitter_analysis.get('score', 0)
    rating = twitter_analysis.get('rating', 'Unknown')
    contract_found = twitter_analysis.get('contract_found', False)
    contract_tweets = twitter_analysis.get('contract_tweets', 0)
    
    # Определяем причину фильтрации
    filter_reason = "PASSED"
    if not contract_found:
        filter_reason = "FILTERED_NO_CONTRACT"
    elif not should_notify:
        filter_reason = "FILTERED_LOW_ACTIVITY"
    
    log_message = (
        f"TOKEN_ANALYSIS | "
        f"Symbol: {symbol} | "
        f"Mint: {mint[:8]}... | "
        f"Twitter_Score: {score} | "
        f"Rating: {rating} | "
        f"Contract_Found: {'YES' if contract_found else 'NO'} | "
        f"Contract_Tweets: {contract_tweets} | "
        f"Result: {filter_reason} | "
        f"Notified: {'YES' if should_notify else 'NO'} | "
        f"Market_Cap: ${token_data.get('marketCap', 0):,.0f}"
    )
    
    tokens_logger.info(log_message)

def log_trade_activity(trade_data, notification_sent=False):
    """Специальное логирование торговой активности"""
    trades_logger = get_trades_logger()
    
    action = "BUY" if trade_data.get('is_buy', True) else "SELL"
    sol_amount = trade_data.get('sol_amount', 0)
    mint = trade_data.get('mint', 'Unknown')
    trader = trade_data.get('traderPublicKey', 'Unknown')
    
    log_message = (
        f"TRADE_ACTIVITY | "
        f"Action: {action} | "
        f"Amount: {sol_amount:.4f} SOL | "
        f"Mint: {mint[:8]}... | "
        f"Trader: {trader[:8]}... | "
        f"Notified: {'YES' if notification_sent else 'NO'}"
    )
    
    trades_logger.info(log_message)

def log_database_operation(operation, table, result, details=""):
    """Специальное логирование операций с БД"""
    database_logger = get_database_logger()
    
    log_message = f"DB_OPERATION | Operation: {operation} | Table: {table} | Result: {result}"
    if details:
        log_message += f" | Details: {details}"
    
    database_logger.info(log_message)

def log_daily_stats(stats):
    """Логирование ежедневной статистики"""
    stats_logger = get_stats_logger()
    
    stats_message = (
        f"DAILY_STATS | "
        f"Tokens: {stats.get('total_tokens', 0)} | "
        f"Trades: {stats.get('total_trades', 0)} | "
        f"Migrations: {stats.get('total_migrations', 0)} | "
        f"Big_Trades_24h: {stats.get('big_trades_24h', 0)}"
    )
    
    stats_logger.info(stats_message) 