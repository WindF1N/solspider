#!/usr/bin/env python3
"""
🔥 TELEGRAM VIP CONFIG 🔥
Конфигурация VIP Telegram чатов для мониторинга контрактов Solana
"""

# TELEGRAM API CREDENTIALS
TELEGRAM_API_CREDENTIALS = {
    'api_id': 15942015,
    'api_hash': '341d19fee1184dfb0939c0d8935cfff4',
    'session_name': 'solspider_telegram_vip'
}

# VIP TELEGRAM ЧАТЫ для мониторинга
VIP_TELEGRAM_CHATS = {
    'chat_-1002605341782': {
        'chat_id': -1002605341782,
        'enabled': True,
        'description': 'VIP Telegram чат - мгновенные сигналы',
        'priority': 'VIP',  # VIP приоритет газа 0.38 SOL
        'auto_buy': True,  # Автоматическая покупка активирована
        'buy_amount_sol': 6.4,  # VIP автопокупка: 6.4 SOL (~$896 при $140/SOL)
        'check_interval': 0.1,  # Мгновенная обработка сообщений
        'notify_unknown_contracts': True,  # Уведомлять о неизвестных контрактах
        'bypass_filters': True,  # Обходить все фильтры
        'monitor_edits': True,  # Мониторить редактирование сообщений
        'monitor_forwards': False,  # Игнорировать пересланные сообщения
        'min_message_length': 10  # Минимальная длина сообщения для обработки
    }
}

# НАСТРОЙКИ TELEGRAM VIP МОНИТОРИНГА
TELEGRAM_MONITOR_SETTINGS = {
    'check_interval': 0.1,  # Мгновенная обработка
    'max_retries': 3,  # Максимум попыток при ошибках
    'cache_cleanup_threshold': 1000,  # Очистка кэша при превышении
    'request_timeout': 15,  # Таймаут запросов
    'log_level': 'INFO',  # Уровень логирования
    'enable_detailed_logging': True,  # Детальное логирование
    'send_startup_notification': True,  # Уведомление о запуске
    'send_error_notifications': True,  # Уведомления об ошибках
    'reconnect_delay': 10,  # Задержка перед переподключением (сек)
    'max_message_age': 300,  # Максимальный возраст сообщения для обработки (сек)
    'flood_protection': True  # Защита от флуда
}

# ФИЛЬТРЫ СООБЩЕНИЙ
MESSAGE_FILTERS = {
    'ignore_bots': True,  # Игнорировать сообщения от ботов
    'ignore_forwards': True,  # Игнорировать пересланные сообщения
    'min_length': 10,  # Минимальная длина сообщения
    'max_length': 4096,  # Максимальная длина сообщения
    'require_contract': True,  # Требовать наличие контракта в сообщении
    'ignore_keywords': [  # Ключевые слова для игнорирования
        'test', 'тест', 'spam', 'спам', 'fake', 'фейк'
    ],
    'priority_keywords': [  # Приоритетные ключевые слова
        'token', 'токен', 'contract', 'контракт', 'solana', 'pump',
        'launch', 'запуск', 'new', 'новый', 'buy', 'покупать'
    ]
}

# TELEGRAM BOT для уведомлений (используем тот же что в VIP Twitter)
TELEGRAM_NOTIFICATION_CONFIG = {
    'bot_token': "8001870018:AAGwL4GiMC9TTKRMKfqghE6FAP4uBgGHXLU",
    'chat_id_env_var': 'VIP_CHAT_ID',  # Переменная окружения для VIP chat ID
    'parse_mode': 'HTML',
    'disable_web_page_preview': False,
    'timeout': 10,
    'retry_attempts': 3,
    'message_prefix': '📱 TELEGRAM VIP СИГНАЛ!'
}

# ШАБЛОНЫ СООБЩЕНИЙ для Telegram уведомлений
TELEGRAM_MESSAGE_TEMPLATES = {
    'contract_found': """📱 <b>TELEGRAM VIP СИГНАЛ!</b> 📱

🔥 <b>{description}</b>
💬 <b>Чат ID:</b> <code>{chat_id}</code>
👤 <b>От:</b> {author_name}

📍 <b>Контракт:</b> <code>{contract}</code>
💬 <b>Сообщение:</b>
<blockquote>{message_text}</blockquote>

⚡ <b>МГНОВЕННЫЙ TELEGRAM СИГНАЛ!</b>
🎯 <b>Приоритет:</b> {priority}
🚀 <b>Время действовать СЕЙЧАС!</b>
🕐 <b>Время:</b> {timestamp}""",

    'auto_buy_success': """

💰 <b>АВТОМАТИЧЕСКАЯ ПОКУПКА ВЫПОЛНЕНА!</b>
✅ <b>Статус:</b> {status}
⚡ <b>Сумма:</b> {sol_amount:.6f} SOL
⏱️ <b>Время:</b> {execution_time:.2f}с
🔗 <b>TX:</b> <code>{tx_hash}</code>
🔥 <b>Газ:</b> {gas_fee} SOL (~${gas_usd:.2f})""",

    'auto_buy_error': """

❌ <b>ОШИБКА АВТОМАТИЧЕСКОЙ ПОКУПКИ</b>
⚠️ <b>Ошибка:</b> {error}""",

    'startup': """📱 <b>TELEGRAM VIP MONITOR ЗАПУЩЕН!</b>

📊 <b>Активных чатов:</b> {active_chats}
⚡ <b>Режим мониторинга:</b> МГНОВЕННЫЙ (ULTRA приоритет)
🤖 <b>Автопокупка активна для:</b> {auto_buy_chats}
🔥 <b>Газ:</b> $5.00 (ULTRA приоритет)

✅ <b>Система готова к работе!</b>
🕐 <b>Время запуска:</b> {timestamp}""",

    'connection_error': """

🚫 <b>ОШИБКА ПОДКЛЮЧЕНИЯ К TELEGRAM</b>
⚠️ <b>Детали:</b> {error}
🔄 <b>Попытка переподключения через {delay} сек...</b>""",

    'message_processed': """

📨 <b>Сообщение обработано</b>
💬 <b>Чат:</b> {chat_id}
👤 <b>Автор:</b> {author}
🔍 <b>Найдено контрактов:</b> {contracts_count}
⏱️ <b>Время обработки:</b> {processing_time:.2f}с"""
}

def get_active_telegram_chats():
    """Возвращает активные Telegram чаты"""
    return {k: v for k, v in VIP_TELEGRAM_CHATS.items() if v.get('enabled', False)}

def get_auto_buy_telegram_chats():
    """Возвращает чаты с включенной автопокупкой"""
    return {k: v for k, v in VIP_TELEGRAM_CHATS.items() 
            if v.get('enabled', False) and v.get('auto_buy', False)}

def format_telegram_message(template_name, **kwargs):
    """Форматирует Telegram сообщение по шаблону"""
    template = TELEGRAM_MESSAGE_TEMPLATES.get(template_name, "")
    try:
        return template.format(**kwargs)
    except KeyError as e:
        return f"❌ Ошибка форматирования сообщения: отсутствует параметр {e}"

def should_process_message(message_text, chat_config):
    """Определяет, нужно ли обрабатывать сообщение"""
    if not message_text:
        return False
    
    # Проверяем длину
    if len(message_text) < MESSAGE_FILTERS['min_length']:
        return False
    
    if len(message_text) > MESSAGE_FILTERS['max_length']:
        return False
    
    # Проверяем игнорируемые ключевые слова
    message_lower = message_text.lower()
    for keyword in MESSAGE_FILTERS['ignore_keywords']:
        if keyword in message_lower:
            return False
    
    # Если у чата включен bypass_filters, пропускаем дальнейшие проверки
    if chat_config.get('bypass_filters', False):
        return True
    
    # Проверяем приоритетные ключевые слова
    has_priority_keyword = False
    for keyword in MESSAGE_FILTERS['priority_keywords']:
        if keyword in message_lower:
            has_priority_keyword = True
            break
    
    return has_priority_keyword

# СТАТИСТИКА
TELEGRAM_STATS = {
    'messages_processed': 0,
    'contracts_found': 0,
    'auto_purchases_made': 0,
    'successful_purchases': 0,
    'failed_purchases': 0,
    'start_time': None,
    'last_message_time': None
}

def update_telegram_stats(action, **kwargs):
    """Обновляет статистику Telegram мониторинга"""
    import time
    
    current_time = time.time()
    
    if action == 'message_processed':
        TELEGRAM_STATS['messages_processed'] += 1
        TELEGRAM_STATS['last_message_time'] = current_time
    
    elif action == 'contract_found':
        TELEGRAM_STATS['contracts_found'] += 1
    
    elif action == 'purchase_attempt':
        TELEGRAM_STATS['auto_purchases_made'] += 1
    
    elif action == 'purchase_success':
        TELEGRAM_STATS['successful_purchases'] += 1
    
    elif action == 'purchase_failed':
        TELEGRAM_STATS['failed_purchases'] += 1
    
    elif action == 'start':
        TELEGRAM_STATS['start_time'] = current_time

def get_telegram_stats_summary():
    """Возвращает сводку статистики"""
    import time
    
    if not TELEGRAM_STATS['start_time']:
        return "Статистика недоступна"
    
    uptime = time.time() - TELEGRAM_STATS['start_time']
    uptime_hours = uptime / 3600
    
    return f"""📊 СТАТИСТИКА TELEGRAM VIP МОНИТОРИНГА

⏱️ Время работы: {uptime_hours:.1f} часов
📨 Сообщений обработано: {TELEGRAM_STATS['messages_processed']}
🔍 Контрактов найдено: {TELEGRAM_STATS['contracts_found']}
💰 Попыток покупки: {TELEGRAM_STATS['auto_purchases_made']}
✅ Успешных покупок: {TELEGRAM_STATS['successful_purchases']}
❌ Неудачных покупок: {TELEGRAM_STATS['failed_purchases']}

📈 Эффективность: {TELEGRAM_STATS['successful_purchases']/max(TELEGRAM_STATS['auto_purchases_made'], 1)*100:.1f}%""" 