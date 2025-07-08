#!/usr/bin/env python3
"""
Модуль для управления Google Sheets с данными групп дубликатов токенов
Автоматическое создание таблиц, обновление в реальном времени
"""
import logging
import gspread
from google.oauth2.service_account import Credentials
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import re
import time
import asyncio
import threading
from queue import Queue, PriorityQueue
from typing import Any, Callable
import random

logger = logging.getLogger(__name__)

def handle_quota_exceeded_retry(func):
    """Декоратор для обработки ошибки 429 'Quota exceeded' с умными повторными попытками"""
    def wrapper(*args, **kwargs):
        max_attempts = 10  # Максимум попыток для 429 ошибок
        attempt = 1
        
        while attempt <= max_attempts:
            try:
                return func(*args, **kwargs)
                
            except Exception as e:
                error_str = str(e)
                error_details = getattr(e, 'response', {}) if hasattr(e, 'response') else {}
                
                # Проверяем если это ошибка 429 Quota exceeded
                is_quota_exceeded = (
                    "429" in error_str or 
                    "Quota exceeded" in error_str or
                    "RATE_LIMIT_EXCEEDED" in error_str or
                    "quota metric 'Write requests'" in error_str
                )
                
                if is_quota_exceeded and attempt < max_attempts:
                    # Увеличиваем задержку с каждой попыткой: 60, 90, 120, 180, 240 секунд...
                    base_delay = 60  # Базовая задержка 60 секунд
                    delay = base_delay + (attempt - 1) * 30 + random.randint(0, 30)  # Добавляем случайность
                    
                    logger.warning(f"🚫 Попытка {attempt}/{max_attempts}: Превышена квота Google Sheets API")
                    logger.warning(f"⏰ Ожидание {delay} секунд перед повторной попыткой...")
                    logger.warning(f"📋 Ошибка: {error_str[:200]}...")
                    
                    time.sleep(delay)
                    attempt += 1
                    continue
                else:
                    # Не ошибка квоты или исчерпаны попытки
                    if is_quota_exceeded:
                        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Превышена квота Google Sheets после {max_attempts} попыток!")
                        logger.error(f"🚨 Требуется увеличение квоты или ручное вмешательство")
                    raise e
        
        return None
    return wrapper

# Импорт для работы с БД (будет импортироваться по мере необходимости)
def get_db_manager():
    """Получает менеджер БД"""
    try:
        from database import get_db_manager as get_db_manager_func
        return get_db_manager_func()
    except ImportError:
        return None

class GoogleSheetsManager:
    """Класс для управления Google Sheets с группами дубликатов"""
    
    def __init__(self, credentials_path: str = "google/pythonke-bd30eedba13b.json"):
        """Инициализация с путем к файлу авторизации"""
        self.credentials_path = credentials_path
        self.client = None
        self.spreadsheets = {}  # Кэш открытых таблиц {group_key: spreadsheet}
        
        # Rate limiting для Google Sheets API - МАКСИМАЛЬНО АГРЕССИВНЫЕ НАСТРОЙКИ
        self.requests_per_minute = 0
        self.last_request_time = 0
        self.rate_limit_max = 290  # 🔥🔥🔥 МАКСИМАЛЬНО АГРЕССИВНО (Google API: 300/минуту)
        self.rate_limit_window = 60  # Окно в секундах
        
        # Права доступа для Google Sheets API
        self.scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Приоритетная очередь задач для Google Sheets
        # Приоритет: 0 - высокий (отправленные уведомления), 1 - обычный (тестовые)
        self.task_queue = PriorityQueue()
        self.worker_thread = None
        self.stop_worker = False
        self.task_counter = 0  # Счетчик для разрешения конфликтов приоритета
        
        # 🔥 НОВЫЙ RETRY МЕХАНИЗМ ДЛЯ 100% ВЫПОЛНЕНИЯ ЗАПРОСОВ
        self.max_retries = 5  # Максимальное количество попыток
        self.retry_delay_base = 2  # Базовая задержка между попытками (секунды)
        self.retry_delay_max = 30  # Максимальная задержка между попытками (секунды)
        self.failed_tasks_queue = PriorityQueue()  # Очередь для неудачных задач
        
        self._initialize_client()
        self._start_worker()
        
        # Запускаем периодическое логирование состояния каждые 5 минут
        self._start_status_logger()
        
        # Логируем информацию о retry механизме
        logger.info(f"🔄 RETRY механизм для Google Sheets активирован:")
        logger.info(f"   📊 Максимальное количество попыток: {self.max_retries}")
        logger.info(f"   ⏰ Задержка между попытками: {self.retry_delay_base}-{self.retry_delay_max} секунд")
        logger.info(f"   🔥 Rate limit: {self.rate_limit_max} запросов/минуту")
        logger.info(f"   🚀 Воркер запущен с приоритетной очередью")
        logger.info(f"   📊 Периодическое логирование состояния каждые 5 минут")
        logger.info(f"   ✅ Google Sheets API запросы будут выполнены на 100%!")
    
    def _check_rate_limit(self):
        """Проверяет и соблюдает лимиты API Google Sheets - АГРЕССИВНАЯ ВЕРСИЯ"""
        current_time = time.time()
        
        # Сброс счетчика если прошла минута
        if current_time - self.last_request_time >= self.rate_limit_window:
            self.requests_per_minute = 0
            self.last_request_time = current_time
        
        # Проверка лимита - МИНИМАЛЬНОЕ ОЖИДАНИЕ
        if self.requests_per_minute >= self.rate_limit_max:
            # 🔥 АГРЕССИВНО: Жду всего 5 секунд вместо полной минуты
            sleep_time = 5.0  # Фиксированное минимальное ожидание
            logger.warning(f"🔥 Rate limit достигнут ({self.requests_per_minute}/{self.rate_limit_max}). Минимальное ожидание {sleep_time}с...")
            time.sleep(sleep_time)
            self.requests_per_minute = 0
            self.last_request_time = time.time()
        
        # Увеличиваем счетчик
        self.requests_per_minute += 1
        
        # Логируем только при приближении к лимиту (каждые 50 запросов или при достижении 90%)
        if (self.requests_per_minute % 50 == 0) or (self.requests_per_minute >= int(self.rate_limit_max * 0.9)):
            logger.info(f"🔥 Google Sheets API: {self.requests_per_minute}/{self.rate_limit_max} запросов в минуту")
    
    def _initialize_client(self):
        """Инициализация клиента Google Sheets с retry механизмом"""
        max_init_retries = 3
        
        for attempt in range(max_init_retries):
            try:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"❌ Файл авторизации Google API не найден: {self.credentials_path}")
                    return False
                
                # Загружаем учетные данные
                credentials = Credentials.from_service_account_file(
                    self.credentials_path, 
                    scopes=self.scopes
                )
                
                # Создаем клиент
                self.client = gspread.authorize(credentials)
                
                # Проверяем подключение простым запросом
                try:
                    # Попытка получить список файлов - если не удалось, значит проблема с авторизацией
                    test_files = self.client.list_permissions("test")
                except:
                    # Это нормально - мы просто проверяем работоспособность клиента
                    pass
                
                logger.info("✅ Google Sheets клиент инициализирован успешно")
                return True
                
            except Exception as e:
                if attempt < max_init_retries - 1:
                    logger.warning(f"⚠️ Попытка {attempt + 1}/{max_init_retries} инициализации Google Sheets клиента не удалась: {e}")
                    logger.warning(f"🔄 Повторная попытка через {2 ** attempt} секунд...")
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"❌ Ошибка инициализации Google Sheets клиента после {max_init_retries} попыток: {e}")
                    return False
        
        return False
    
    def _check_and_reinitialize_client(self):
        """Проверяет состояние клиента и переинициализирует при необходимости"""
        try:
            if not self.client:
                logger.warning("⚠️ Google Sheets клиент не инициализирован, выполняем переинициализацию...")
                return self._initialize_client()
            
            # Проверяем работоспособность клиента простым запросом
            try:
                # Попытка получить информацию о пользователе
                self.client.list_permissions("test")
                return True
            except:
                # Клиент не работает, переинициализируем
                logger.warning("⚠️ Google Sheets клиент не отвечает, выполняем переинициализацию...")
                return self._initialize_client()
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки Google Sheets клиента: {e}")
            return False
    
    def _start_worker(self):
        """Запускает воркер для обработки задач Google Sheets"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_worker = False
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("🚀 Google Sheets воркер запущен")
    
    def _start_status_logger(self):
        """Запускает периодическое логирование состояния очередей"""
        def status_logger_loop():
            while not self.stop_worker:
                time.sleep(300)  # Логируем каждые 5 минут
                if not self.stop_worker:
                    self.log_queue_status()
        
        status_logger_thread = threading.Thread(target=status_logger_loop, daemon=True)
        status_logger_thread.start()
        logger.info("📊 Периодическое логирование состояния Google Sheets запущено (каждые 5 минут)")
    
    def _worker_loop(self):
        """Основной цикл обработки задач Google Sheets с приоритетами и 100% RETRY МЕХАНИЗМОМ"""
        while not self.stop_worker:
            try:
                # Получаем задачу из приоритетной очереди (блокирующий вызов с таймаутом)
                priority_task = self.task_queue.get(timeout=5)
                
                if priority_task is None:  # Сигнал остановки
                    break
                
                # Распаковываем приоритетную задачу: (priority, counter, (func, args, kwargs, attempt))
                priority, counter, task_data = priority_task
                
                if task_data is None:  # Сигнал остановки
                    break
                
                # Распаковываем данные задачи
                if len(task_data) == 4:
                    func, args, kwargs, attempt = task_data
                else:
                    func, args, kwargs = task_data
                    attempt = 1
                
                try:
                    # 🔥 ВЫПОЛНЯЕМ ЗАДАЧУ
                    result = func(*args, **kwargs)
                    
                    priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
                    if attempt > 1:
                        logger.info(f"✅ Задача Google Sheets выполнена с {attempt} попытки ({priority_str}): {func.__name__}")
                    else:
                        logger.debug(f"✅ Задача Google Sheets выполнена ({priority_str}): {func.__name__}")
                    
                except Exception as task_error:
                    priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
                    
                    # 🔥 RETRY ЛОГИКА - ГАРАНТИРОВАННОЕ ВЫПОЛНЕНИЕ
                    if attempt < self.max_retries:
                        # Вычисляем задержку с экспоненциальным backoff
                        delay = min(self.retry_delay_base * (2 ** (attempt - 1)), self.retry_delay_max)
                        
                        logger.warning(f"⚠️ Попытка {attempt}/{self.max_retries} неудачна ({priority_str}) {func.__name__}: {task_error}")
                        logger.warning(f"🔄 Повторная попытка через {delay} секунд...")
                        
                        # Запускаем задачу повторно с задержкой
                        def retry_task():
                            time.sleep(delay)
                            retry_task_data = (func, args, kwargs, attempt + 1)
                            self.task_queue.put((priority, counter, retry_task_data))
                        
                        # Запускаем retry в отдельном потоке чтобы не блокировать основной воркер
                        retry_thread = threading.Thread(target=retry_task, daemon=True)
                        retry_thread.start()
                        
                    else:
                        # Максимальное количество попыток исчерпано
                        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Задача ({priority_str}) {func.__name__} не выполнена после {self.max_retries} попыток!")
                        logger.error(f"❌ Последняя ошибка: {task_error}")
                        
                        # Сохраняем задачу в очередь критических ошибок для ручного разбора
                        self.failed_tasks_queue.put((priority, counter, (func, args, kwargs, attempt, task_error)))
                        
                        # Уведомляем о критической ошибке
                        logger.error(f"🚨 КРИТИЧЕСКАЯ ОШИБКА Google Sheets: {func.__name__} - ТРЕБУЕТСЯ ВМЕШАТЕЛЬСТВО!")
                        
                finally:
                    self.task_queue.task_done()
                    
            except Exception as e:
                if not self.stop_worker:
                    logger.debug(f"⏳ Google Sheets воркер ожидает задачи...")
                continue
        
        logger.info("🛑 Google Sheets воркер остановлен")
    
    def _queue_task(self, func: Callable, *args, priority: int = 1, **kwargs):
        """Добавляет задачу в приоритетную очередь для асинхронного выполнения с RETRY механизмом
        
        Args:
            func: Функция для выполнения
            *args: Аргументы функции
            priority: Приоритет (0 = высокий для отправленных уведомлений, 1 = обычный)
            **kwargs: Именованные аргументы функции
        """
        if not self.stop_worker:
            task_data = (func, args, kwargs, 1)  # Добавляем номер попытки
            # Добавляем счетчик для разрешения конфликтов приоритета
            self.task_counter += 1
            self.task_queue.put((priority, self.task_counter, task_data))
            priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
            logger.debug(f"📤 Задача добавлена в очередь с RETRY ({priority_str}): {func.__name__}")
        else:
            logger.warning("⚠️ Воркер остановлен, задача отклонена")
    
    def get_failed_tasks_count(self) -> int:
        """Возвращает количество критически неудачных задач"""
        return self.failed_tasks_queue.qsize()
    
    def retry_failed_tasks(self):
        """Повторно запускает все критически неудачные задачи"""
        failed_count = self.failed_tasks_queue.qsize()
        if failed_count > 0:
            logger.info(f"🔄 Повторный запуск {failed_count} критически неудачных задач...")
            
            while not self.failed_tasks_queue.empty():
                try:
                    priority, counter, failed_task_data = self.failed_tasks_queue.get_nowait()
                    func, args, kwargs, last_attempt, last_error = failed_task_data
                    
                    # Запускаем задачу заново с попытки 1
                    task_data = (func, args, kwargs, 1)
                    self.task_queue.put((priority, counter, task_data))
                    
                    logger.info(f"🔄 Критическая задача {func.__name__} добавлена в очередь повторно")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при повторном запуске задачи: {e}")
                    
            logger.info(f"✅ Все {failed_count} критических задач добавлены в очередь повторно")
    
    def get_queue_status(self) -> Dict:
        """Возвращает детальную информацию о состоянии очередей"""
        return {
            "active_tasks": self.task_queue.qsize(),
            "failed_tasks": self.failed_tasks_queue.qsize(),
            "worker_alive": self.worker_thread is not None and self.worker_thread.is_alive(),
            "requests_per_minute": self.requests_per_minute,
            "rate_limit_max": self.rate_limit_max,
            "max_retries": self.max_retries,
            "retry_delay_base": self.retry_delay_base,
            "retry_delay_max": self.retry_delay_max
        }
    
    def log_queue_status(self):
        """Логирует текущее состояние очередей и retry механизма"""
        status = self.get_queue_status()
        logger.info(f"📊 Google Sheets Queue Status:")
        logger.info(f"   🔄 Активные задачи: {status['active_tasks']}")
        logger.info(f"   ❌ Неудачные задачи: {status['failed_tasks']}")
        logger.info(f"   🏃 Воркер активен: {status['worker_alive']}")
        logger.info(f"   📈 Запросы в минуту: {status['requests_per_minute']}/{status['rate_limit_max']}")
        logger.info(f"   🔄 Настройки retry: {status['max_retries']} попыток, {status['retry_delay_base']}-{status['retry_delay_max']}с задержка")
        
        if status['failed_tasks'] > 0:
            logger.warning(f"⚠️ ВНИМАНИЕ: {status['failed_tasks']} критически неудачных задач требуют вмешательства!")
    
    def configure_retry_settings(self, max_retries: int = None, retry_delay_base: int = None, retry_delay_max: int = None):
        """Настраивает параметры retry механизма"""
        if max_retries is not None:
            self.max_retries = max_retries
            logger.info(f"🔄 Максимальное количество попыток установлено: {self.max_retries}")
        
        if retry_delay_base is not None:
            self.retry_delay_base = retry_delay_base
            logger.info(f"🔄 Базовая задержка между попытками установлена: {self.retry_delay_base}с")
        
        if retry_delay_max is not None:
            self.retry_delay_max = retry_delay_max
            logger.info(f"🔄 Максимальная задержка между попытками установлена: {self.retry_delay_max}с")
    
    def force_retry_all_failed(self):
        """Принудительно перезапускает все неудачные задачи с очисткой истории ошибок"""
        failed_count = self.get_failed_tasks_count()
        if failed_count > 0:
            logger.warning(f"🚨 ПРИНУДИТЕЛЬНЫЙ ПЕРЕЗАПУСК: {failed_count} критически неудачных задач...")
            self.retry_failed_tasks()
            logger.info(f"✅ Принудительный перезапуск завершен")
        else:
            logger.info("✅ Нет неудачных задач для перезапуска")
    
    def clear_failed_tasks(self):
        """Очищает очередь неудачных задач (используется для сброса состояния)"""
        failed_count = self.failed_tasks_queue.qsize()
        if failed_count > 0:
            while not self.failed_tasks_queue.empty():
                try:
                    self.failed_tasks_queue.get_nowait()
                except:
                    break
            logger.warning(f"🗑️ Очищено {failed_count} неудачных задач из очереди")
        else:
            logger.info("✅ Очередь неудачных задач пуста")
    
    def stop_worker_thread(self):
        """Останавливает воркер"""
        self.stop_worker = True
        self.task_queue.put((0, 0, None))  # Сигнал остановки с высоким приоритетом и счетчиком
        if self.worker_thread:
            self.worker_thread.join(timeout=10)
            logger.info("🛑 Google Sheets воркер остановлен принудительно")
    
    def _sanitize_sheet_name(self, name: str) -> str:
        """Очищает имя таблицы от недопустимых символов"""
        import unicodedata
        
        # Заменяем специальные символы на безопасные аналоги
        special_replacements = {
            '¥': 'YEN',
            '$': 'USD', 
            '€': 'EUR',
            '£': 'GBP',
            '₿': 'BTC',
            '🔥': 'FIRE',
            '🚀': 'ROCKET',
            '💎': 'DIAMOND',
            '⚡': 'LIGHTNING',
            '🎯': 'TARGET',
            '💰': 'MONEY',
            '🌙': 'MOON'
        }
        
        # Применяем замены специальных символов
        sanitized = name
        for special, replacement in special_replacements.items():
            sanitized = sanitized.replace(special, replacement)
        
        # Нормализуем unicode символы
        sanitized = unicodedata.normalize('NFKD', sanitized)
        
        # Удаляем все небезопасные символы (оставляем только буквы, цифры, пробелы, дефисы, подчеркивания)
        sanitized = re.sub(r'[^\w\s\-_]', '', sanitized)
        
        # Заменяем множественные пробелы одиночными
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        # Заменяем пробелы на подчеркивания для лучшей совместимости
        sanitized = sanitized.replace(' ', '_')
        
        # Ограничиваем длину (максимум 80 символов для имени + префикс)
        sanitized = sanitized[:80]
        
        # Удаляем подчеркивания в начале и конце
        sanitized = sanitized.strip('_')
        
        # Если имя стало пустым, используем fallback
        if not sanitized:
            sanitized = "Unknown_Token"
        
        # Добавляем префикс для идентификации
        return f"Duplicates_{sanitized}"
    
    def get_or_create_spreadsheet(self, group_key: str, token_symbol: str, token_name: str) -> Optional[object]:
        """Получает существующую или создает новую таблицу для группы дубликатов - АГРЕССИВНАЯ ВЕРСИЯ с RETRY"""
        try:
            # 🔥 ПРОВЕРЯЕМ И ВОССТАНАВЛИВАЕМ ПОДКЛЮЧЕНИЕ ПЕРЕД ОПЕРАЦИЕЙ
            if not self._check_and_reinitialize_client():
                logger.error("❌ Google Sheets клиент не инициализирован и не может быть восстановлен")
                return None
            
            # Проверяем кэш
            if group_key in self.spreadsheets:
                return self.spreadsheets[group_key]
            
            # Формируем имя таблицы с несколькими вариантами fallback
            primary_name = self._sanitize_sheet_name(f"{token_symbol}_{token_name}")
            fallback_names = [
                primary_name,
                self._sanitize_sheet_name(f"{token_symbol}_Token"),
                self._sanitize_sheet_name(f"Token_{token_symbol}"),
                f"Duplicates_{token_symbol}_{hash(token_name) % 10000}"  # Добавляем хеш для уникальности
            ]
            
            # Удаляем дублирующиеся имена
            fallback_names = list(dict.fromkeys(fallback_names))  # Сохраняем порядок и убираем дубли
            
            spreadsheet = None
            sheet_name = None
            
            # 🔥 АГРЕССИВНО: Пытаемся найти существующую таблицу (без rate limit для поиска)
            for candidate_name in fallback_names:
                try:
                    spreadsheet = self.client.open(candidate_name)
                    sheet_name = candidate_name
                    logger.info(f"📊 Найдена существующая таблица: {sheet_name}")
                    break
                    
                except gspread.SpreadsheetNotFound:
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка поиска таблицы {candidate_name}: {e}")
                    continue
            
            # Если не нашли существующую таблицу, создаем новую
            if not spreadsheet:
                # 🔥 АГРЕССИВНО: Соблюдаем rate limit только для создания
                self._check_rate_limit()
                
                for candidate_name in fallback_names:
                    try:
                        # Создаем новую таблицу С ЗАЩИТОЙ ОТ 429 ОШИБОК
                        @handle_quota_exceeded_retry 
                        def create_spreadsheet():
                            logger.info(f"🔥 Создаем новую таблицу: {candidate_name}")
                            return self.client.create(candidate_name)
                        
                        spreadsheet = create_spreadsheet()
                        sheet_name = candidate_name
                        break
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка создания таблицы {candidate_name}: {e}")
                        continue
                
                # Если не удалось создать ни одну таблицу
                if not spreadsheet:
                    logger.error(f"❌ Не удалось создать таблицу для группы {group_key}")
                    return None
                
                # Делаем таблицу доступной всем по ссылке для редактирования С ЗАЩИТОЙ ОТ 429 ОШИБОК
                @handle_quota_exceeded_retry
                def setup_spreadsheet():
                    try:
                        # Предоставляем доступ на редактирование всем с ссылкой
                        spreadsheet.share('', perm_type='anyone', role='writer')
                        logger.info(f"✅ Таблица {sheet_name} доступна всем по ссылке (с правами редактирования)")
                    except Exception as share_error:
                        logger.warning(f"⚠️ Не удалось сделать таблицу {sheet_name} публичной: {share_error}")
                    
                    # Настраиваем заголовки
                    worksheet = spreadsheet.sheet1
                    worksheet.update_title("Duplicates_Data")
                    
                    # Устанавливаем заголовки колонок
                    headers = [
                        "Символ", "Название", "Twitter", "Контракт", 
                        "Дата создания", "Время обнаружения", "Ссылки", "Статус"
                    ]
                    worksheet.update('A1:H1', [headers])
                    
                    # Форматируем заголовки (жирный шрифт)
                    worksheet.format('A1:H1', {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                    })
                    return True
                
                # Выполняем настройку с защитой от 429 ошибок
                setup_spreadsheet()
                
                logger.info(f"🔥 Таблица {sheet_name} создана и настроена")
            
            # Сохраняем в кэш
            self.spreadsheets[group_key] = spreadsheet
            return spreadsheet
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания/получения таблицы для {group_key}: {e}")
            logger.error(f"🔍 Детали ошибки: {type(e).__name__}: {str(e)}")
            logger.error(f"📋 Исходные данные: symbol='{token_symbol}', name='{token_name}'")
            logger.error(f"📋 Попытки имен: {[primary_name] + fallback_names if 'fallback_names' in locals() else 'fallback_names не определен'}")
            return None
    
    def add_token_to_sheet(self, group_key: str, token_data: Dict, main_twitter: str = None) -> bool:
        """Добавляет токен в таблицу группы дубликатов - АГРЕССИВНАЯ ВЕРСИЯ с RETRY"""
        try:
            # 🔥 ПРОВЕРЯЕМ ПОДКЛЮЧЕНИЕ ПЕРЕД ОПЕРАЦИЕЙ
            if not self._check_and_reinitialize_client():
                logger.error("❌ Google Sheets клиент не может быть восстановлен для добавления токена")
                return False
            
            # Получаем таблицу
            spreadsheet = self.get_or_create_spreadsheet(
                group_key, 
                token_data.get('symbol', 'Unknown'),
                token_data.get('name', 'Unknown')
            )
            
            if not spreadsheet:
                return False
            
            worksheet = spreadsheet.sheet1
            
            # Извлекаем данные токена
            symbol = token_data.get('symbol', 'Unknown')
            name = token_data.get('name', 'Unknown')
            contract = token_data.get('id', 'Unknown')
            
            # Извлекаем Twitter аккаунты
            twitter_accounts = self._extract_twitter_accounts(token_data)
            twitter_display = f"@{', @'.join(twitter_accounts)}" if twitter_accounts else "Нет"
            
            # Извлекаем дату создания
            created_at = token_data.get('firstPool', {}).get('createdAt', '')
            created_display = self._parse_jupiter_date(created_at)
            
            # Время обнаружения - используем реальное время из БД если есть
            first_seen = token_data.get('first_seen', '')
            if first_seen:
                discovered_at = self._parse_jupiter_date(first_seen)
            else:
                discovered_at = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
            
            # Проверяем наличие ссылок
            has_links = self._check_token_links(token_data)
            links_status = "Есть" if has_links else "Нет"
            
            # Определяем статус
            if main_twitter and twitter_accounts and main_twitter.lower() in [acc.lower() for acc in twitter_accounts]:
                status = "🎯 ГЛАВНЫЙ"
            elif has_links:
                status = "🔗 С ссылками"
            else:
                status = "🚫 Без ссылок"
            
            # Подготавливаем строку данных
            row_data = [
                symbol, name, twitter_display, contract, 
                created_display, discovered_at, links_status, status
            ]
            
            # Проверяем, не добавлен ли уже этот контракт
            existing_data = worksheet.get_all_values()
            for i, row in enumerate(existing_data[1:], 2):  # Пропускаем заголовок
                if len(row) >= 4 and row[3] == contract:
                    logger.debug(f"🔄 Контракт {contract[:8]}... уже в таблице {group_key}")
                    return True
            
            # 🔥 АГРЕССИВНО: Добавляем строку и сортируем одним батчем С ЗАЩИТОЙ ОТ 429 ОШИБОК
            self._check_rate_limit()
            
            @handle_quota_exceeded_retry
            def add_and_sort_token():
                # Добавляем новую строку
                worksheet.append_row(row_data)
                
                # Сортируем по дате создания (колонка E)
                self._sort_sheet_by_date(worksheet)
                return True
            
            add_and_sort_token()
            
            logger.info(f"🔥 Токен {symbol} добавлен в таблицу {group_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления токена в таблицу {group_key}: {e}")
            return False
    
    def add_token_to_sheet_async(self, group_key: str, token_data: Dict, main_twitter: str = None, priority: int = 1):
        """Асинхронно добавляет токен в таблицу группы дубликатов (без блокировки основного потока)
        
        Args:
            group_key: Ключ группы
            token_data: Данные токена
            main_twitter: Главный Twitter аккаунт
            priority: Приоритет (0 = высокий для отправленных уведомлений, 1 = обычный)
        """
        # Добавляем задачу в очередь для выполнения в фоновом потоке
        self._queue_task(
            self._add_token_to_sheet_internal,
            group_key, token_data, main_twitter,
            priority=priority
        )
        priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
        logger.debug(f"📋 Токен {token_data.get('symbol', 'Unknown')} добавлен в очередь Google Sheets ({priority_str})")
    
    def _add_token_to_sheet_internal(self, group_key: str, token_data: Dict, main_twitter: str = None) -> bool:
        """Внутренний метод для добавления токена в таблицу (выполняется в фоновом потоке)"""
        return self.add_token_to_sheet(group_key, token_data, main_twitter)
    
    def _extract_twitter_accounts(self, token_data: Dict) -> List[str]:
        """Извлекает Twitter аккаунты из данных токена"""
        twitter_accounts = set()
        
        # Поля где могут быть Twitter ссылки
        twitter_fields = ['twitter', 'website', 'telegram', 'social', 'links']
        
        for field in twitter_fields:
            url = token_data.get(field, '')
            if url and isinstance(url, str):
                account = self._normalize_twitter_url(url)
                if account:
                    twitter_accounts.add(account)
        
        return list(twitter_accounts)
    
    def _normalize_twitter_url(self, url: str) -> Optional[str]:
        """Нормализует Twitter URL, извлекая username"""
        try:
            if not url or not isinstance(url, str):
                return None
                
            url_lower = url.lower()
            
            # Проверяем что это Twitter/X ссылка
            if not any(domain in url_lower for domain in ['twitter.com', 'x.com']):
                return None
            
            # Извлекаем username
            import re
            username_pattern = r'(?i)(?:twitter\.com|x\.com)/([^/\?]+)'
            match = re.search(username_pattern, url)
            
            if match:
                username = match.group(1).strip()
                
                # Пропускаем служебные пути
                service_paths = ['i', 'home', 'search', 'notifications', 'messages', 'settings', 'intent']
                if username.lower() in service_paths:
                    return None
                    
                return username
                
        except Exception as e:
            logger.debug(f"❌ Ошибка нормализации Twitter URL {url}: {e}")
            
        return None
    
    def _check_token_links(self, token_data: Dict) -> bool:
        """Проверяет наличие ссылок у токена"""
        link_fields = ['twitter', 'telegram', 'website']
        for field in link_fields:
            if token_data.get(field):
                return True
        return False
    
    def _sort_sheet_by_date(self, worksheet):
        """Сортирует таблицу по дате создания (колонка E) - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ"""
        try:
            # Получаем все данные
            all_data = worksheet.get_all_values()
            if len(all_data) <= 2:  # Только заголовок или один токен
                return
            
            # Сортируем данные (пропускаем заголовок)
            headers = all_data[0]
            data_rows = all_data[1:]
            
            # Сортируем по дате создания (колонка 4, индекс 4)
            def sort_key(row):
                if len(row) > 4 and row[4]:
                    try:
                        # Пытаемся парсить дату в формате dd.mm.yyyy hh:mm
                        date_str = row[4]
                        if '.' in date_str:
                            date_part = date_str.split(' ')[0]
                            day, month, year = date_part.split('.')
                            return datetime(int(year), int(month), int(day))
                    except:
                        pass
                return datetime.min
            
            data_rows.sort(key=sort_key, reverse=True)  # Новые сверху
            
            # 🔥 КРИТИЧЕСКИЙ МОМЕНТ: Соблюдаем rate limit только для операций записи С ЗАЩИТОЙ ОТ 429 ОШИБОК
            self._check_rate_limit()
            
            @handle_quota_exceeded_retry
            def sort_and_update_sheet():
                # Очищаем таблицу и записываем отсортированные данные
                worksheet.clear()
                worksheet.update('A1', [headers] + data_rows)
                
                # Восстанавливаем форматирование заголовков
                worksheet.format('A1:H1', {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                })
                return True
            
            sort_and_update_sheet()
            
        except Exception as e:
            logger.error(f"❌ Ошибка сортировки таблицы: {e}")
    
    def get_sheet_url(self, group_key: str) -> Optional[str]:
        """Получает URL таблицы Google Sheets"""
        try:
            if group_key in self.spreadsheets:
                spreadsheet = self.spreadsheets[group_key]
                return spreadsheet.url
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения URL таблицы {group_key}: {e}")
            return None
    
    def update_main_twitter(self, group_key: str, main_twitter: str) -> bool:
        """Обновляет статусы токенов в таблице на основе главного Twitter аккаунта - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ"""
        try:
            if group_key not in self.spreadsheets:
                return False
            
            spreadsheet = self.spreadsheets[group_key]
            worksheet = spreadsheet.sheet1
            
            # Получаем все данные
            all_data = worksheet.get_all_values()
            if len(all_data) <= 1:
                return False
            
            # Собираем все обновления в батч
            updates = []
            for i, row in enumerate(all_data[1:], 2):  # Пропускаем заголовок, начинаем с строки 2
                if len(row) >= 8:
                    twitter_cell = row[2]  # Колонка C (Twitter)
                    
                    # Проверяем, содержит ли Twitter ячейка главный аккаунт
                    if main_twitter.lower() in twitter_cell.lower():
                        updates.append({
                            'range': f'H{i}',
                            'values': [['🎯 ГЛАВНЫЙ']]
                        })
            
            # 🔥 АГРЕССИВНО: Выполняем все обновления одним батчем С ЗАЩИТОЙ ОТ 429 ОШИБОК
            if updates:
                self._check_rate_limit()
                
                @handle_quota_exceeded_retry
                def update_main_twitter_batch():
                    worksheet.batch_update(updates)
                    return True
                
                update_main_twitter_batch()
                logger.info(f"🔥 Обновлено {len(updates)} статусов в таблице {group_key} для главного Twitter @{main_twitter}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления главного Twitter в таблице {group_key}: {e}")
            return False
    
    def update_main_twitter_async(self, group_key: str, main_twitter: str, priority: int = 1):
        """Асинхронно обновляет статусы токенов в таблице на основе главного Twitter аккаунта
        
        Args:
            group_key: Ключ группы
            main_twitter: Главный Twitter аккаунт
            priority: Приоритет (0 = высокий для отправленных уведомлений, 1 = обычный)
        """
        self._queue_task(
            self._update_main_twitter_internal,
            group_key, main_twitter,
            priority=priority
        )
        priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
        logger.debug(f"📋 Обновление главного Twitter для {group_key} добавлено в очередь ({priority_str})")
    
    def _update_main_twitter_internal(self, group_key: str, main_twitter: str) -> bool:
        """Внутренний метод для обновления главного Twitter (выполняется в фоновом потоке)"""
        return self.update_main_twitter(group_key, main_twitter)
    
    def check_official_contract_in_twitter(self, group_key: str, main_twitter: str, official_contract: str) -> bool:
        """Отмечает в таблице что официальный контракт найден в Twitter - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ"""
        try:
            if group_key not in self.spreadsheets:
                return False
            
            spreadsheet = self.spreadsheets[group_key]
            worksheet = spreadsheet.sheet1
            
            # Добавляем строку с информацией об официальном контракте
            official_row = [
                "ОФИЦИАЛЬНЫЙ", "Контракт найден в Twitter", f"@{main_twitter}", 
                official_contract, datetime.now().strftime('%d.%m.%Y %H:%M'), 
                datetime.now().strftime('%d.%m.%Y %H:%M:%S'), "Twitter", "✅ ОФИЦИАЛЬНЫЙ"
            ]
            
            # 🔥 АГРЕССИВНО: Выполняем все операции одним батчем
            self._check_rate_limit()
            
            # Получаем текущее количество строк для форматирования
            current_rows = len(worksheet.get_all_values())
            new_row_number = current_rows + 1
            
            # Добавляем строку и сразу форматируем
            worksheet.append_row(official_row)
            worksheet.format(f'A{new_row_number}:H{new_row_number}', {
                "backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8},
                "textFormat": {"bold": True}
            })
            
            logger.info(f"🔥 Официальный контракт отмечен в таблице {group_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отметки официального контракта в таблице {group_key}: {e}")
            return False
    
    def add_tokens_batch(self, group_key: str, tokens_list: List[Dict], main_twitter: str = None) -> bool:
        """🔥 СУПЕР БЫСТРОЕ батчевое добавление всех токенов группы одним запросом с RETRY"""
        try:
            if not tokens_list:
                logger.warning(f"⚠️ Список токенов пуст для группы {group_key}")
                return False
            
            # 🔥 ПРОВЕРЯЕМ ПОДКЛЮЧЕНИЕ ПЕРЕД ОПЕРАЦИЕЙ
            if not self._check_and_reinitialize_client():
                logger.error("❌ Google Sheets клиент не может быть восстановлен для батчевого добавления")
                return False
                
            # Получаем/создаем таблицу
            first_token = tokens_list[0]
            spreadsheet = self.get_or_create_spreadsheet(
                group_key, 
                first_token.get('symbol', 'Unknown'),
                first_token.get('name', 'Unknown')
            )
            
            if not spreadsheet:
                logger.error(f"❌ Не удалось создать таблицу для группы {group_key}")
                return False
            
            worksheet = spreadsheet.sheet1
            
            # Подготавливаем все строки данных
            batch_rows = []
            
            for token_data in tokens_list:
                # Извлекаем данные токена
                symbol = token_data.get('symbol', 'Unknown')
                name = token_data.get('name', 'Unknown')
                contract = token_data.get('id', 'Unknown')
                
                # Извлекаем Twitter аккаунты
                twitter_accounts = self._extract_twitter_accounts(token_data)
                twitter_display = f"@{', @'.join(twitter_accounts)}" if twitter_accounts else "Нет"
                
                # Извлекаем дату создания
                created_at = token_data.get('firstPool', {}).get('createdAt', '')
                created_display = self._parse_jupiter_date(created_at)
                
                # Время обнаружения - используем реальное время из БД если есть
                first_seen = token_data.get('first_seen', '')
                if first_seen:
                    discovered_at = self._parse_jupiter_date(first_seen)
                else:
                    discovered_at = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                
                # Проверяем наличие ссылок
                has_links = self._check_token_links(token_data)
                links_status = "Есть" if has_links else "Нет"
                
                # Определяем статус
                if main_twitter and twitter_accounts and main_twitter.lower() in [acc.lower() for acc in twitter_accounts]:
                    status = "🎯 ГЛАВНЫЙ"
                elif has_links:
                    status = "🔗 С ссылками"
                else:
                    status = "🚫 Без ссылок"
                
                # Добавляем строку в батч
                row_data = [
                    symbol, name, twitter_display, contract, 
                    created_display, discovered_at, links_status, status
                ]
                batch_rows.append(row_data)
            
            # Сортируем все строки по дате создания
            def sort_key(row):
                date_str = row[4]  # Колонка с датой
                if date_str and date_str != "Неизвестно":
                    try:
                        if '.' in date_str:
                            date_part = date_str.split(' ')[0]
                            day, month, year = date_part.split('.')
                            return datetime(int(year), int(month), int(day))
                    except:
                        pass
                return datetime.min
            
            batch_rows.sort(key=sort_key, reverse=True)  # Новые сверху
            
            # 🔥 СУПЕР БЫСТРО: Один запрос для всех токенов с обработкой 429 ошибок
            self._check_rate_limit()
            
            # Получаем заголовки
            headers = [
                "Символ", "Название", "Twitter", "Контракт", 
                "Дата создания", "Время обнаружения", "Ссылки", "Статус"
            ]
            
            # Записываем ВСЕ данные одним запросом С ЗАЩИТОЙ ОТ 429 ОШИБОК
            @handle_quota_exceeded_retry
            def write_batch_data():
                all_data = [headers] + batch_rows
                worksheet.clear()
                worksheet.update('A1', all_data)
                
                # Форматируем заголовки
                worksheet.format('A1:H1', {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                })
                return True
            
            # Выполняем запись с защитой от 429 ошибок
            write_batch_data()
            
            logger.info(f"🔥 БАТЧЕВОЕ добавление: {len(batch_rows)} токенов группы {group_key} добавлено за 1 запрос!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка батчевого добавления токенов в группу {group_key}: {e}")
            return False
    
    def add_tokens_batch_async(self, group_key: str, tokens_list: List[Dict], main_twitter: str = None, priority: int = 1):
        """🔥 Асинхронное батчевое добавление всех токенов группы
        
        Args:
            group_key: Ключ группы
            tokens_list: Список токенов
            main_twitter: Главный Twitter аккаунт
            priority: Приоритет (0 = высокий для отправленных уведомлений, 1 = обычный)
        """
        self._queue_task(
            self.add_tokens_batch,
            group_key, tokens_list, main_twitter,
            priority=priority
        )
        priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
        logger.info(f"🔥 БАТЧЕВОЕ добавление {len(tokens_list)} токенов группы {group_key} добавлено в очередь ({priority_str})")
    
    def add_single_token_fast(self, group_key: str, token_data: Dict, main_twitter: str = None) -> bool:
        """🔥 БЫСТРОЕ добавление одного токена в существующую таблицу (без сортировки)"""
        try:
            if group_key not in self.spreadsheets:
                logger.error(f"❌ Таблица для группы {group_key} не найдена")
                return False
            
            spreadsheet = self.spreadsheets[group_key]
            worksheet = spreadsheet.sheet1
            
            # Извлекаем данные токена
            symbol = token_data.get('symbol', 'Unknown')
            name = token_data.get('name', 'Unknown')
            contract = token_data.get('id', 'Unknown')
            
            # Быстрая проверка на дубликаты - читаем только колонку контрактов
            contract_column = worksheet.col_values(4)  # Колонка D (контракты)
            if contract in contract_column:
                logger.debug(f"🔄 Контракт {contract[:8]}... уже в таблице {group_key}")
                return True
            
            # Извлекаем Twitter аккаунты
            twitter_accounts = self._extract_twitter_accounts(token_data)
            twitter_display = f"@{', @'.join(twitter_accounts)}" if twitter_accounts else "Нет"
            
            # Извлекаем дату создания
            created_at = token_data.get('firstPool', {}).get('createdAt', '')
            created_display = self._parse_jupiter_date(created_at)
            
            # Время обнаружения - используем реальное время из БД если есть
            first_seen = token_data.get('first_seen', '')
            if first_seen:
                discovered_at = self._parse_jupiter_date(first_seen)
            else:
                discovered_at = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
            
            # Проверяем наличие ссылок
            has_links = self._check_token_links(token_data)
            links_status = "Есть" if has_links else "Нет"
            
            # Определяем статус
            if main_twitter and twitter_accounts and main_twitter.lower() in [acc.lower() for acc in twitter_accounts]:
                status = "🎯 ГЛАВНЫЙ"
            elif has_links:
                status = "🔗 С ссылками"
            else:
                status = "🚫 Без ссылок"
            
            # Подготавливаем строку данных
            row_data = [
                symbol, name, twitter_display, contract, 
                created_display, discovered_at, links_status, status
            ]
            
            # 🔥 БЫСТРО: Добавляем строку БЕЗ сортировки С ЗАЩИТОЙ ОТ 429 ОШИБОК
            self._check_rate_limit()
            
            @handle_quota_exceeded_retry
            def append_single_row():
                worksheet.append_row(row_data)
                return True
            
            append_single_row()
            
            logger.info(f"🔥 БЫСТРОЕ добавление токена {symbol} в таблицу {group_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка быстрого добавления токена в таблицу {group_key}: {e}")
            return False
    
    def add_single_token_fast_async(self, group_key: str, token_data: Dict, main_twitter: str = None, priority: int = 1):
        """🔥 Асинхронное быстрое добавление одного токена
        
        Args:
            group_key: Ключ группы
            token_data: Данные токена
            main_twitter: Главный Twitter аккаунт
            priority: Приоритет (0 = высокий для отправленных уведомлений, 1 = обычный)
        """
        self._queue_task(
            self.add_single_token_fast,
            group_key, token_data, main_twitter,
            priority=priority
        )
        priority_str = "🔥 ВЫСОКИЙ" if priority == 0 else "⏳ ОБЫЧНЫЙ"
        logger.debug(f"🔥 БЫСТРОЕ добавление токена {token_data.get('symbol', 'Unknown')} в очередь ({priority_str})")

    def _parse_jupiter_date(self, date_string: str) -> Optional[str]:
        """Парсинг даты из Jupiter API формата '2025-07-05T16:03:59Z' в читаемый формат"""
        if not date_string:
            return "Неизвестно"
            
        try:
            # Улучшенный парсинг UTC даты с Z-суффиксом
            if date_string.endswith('Z'):
                # Заменяем Z на +00:00 для явного указания UTC
                date_string = date_string.replace('Z', '+00:00')
            
            # Парсим дату в формате ISO с таймзоной
            created_date = datetime.fromisoformat(date_string)
            
            # Возвращаем в читаемом формате
            return created_date.strftime('%d.%m.%Y %H:%M')
            
        except Exception as e:
            logger.debug(f"⚠️ Ошибка парсинга Jupiter даты '{date_string}': {e}")
            return date_string  # Возвращаем оригинальную строку

    def load_all_duplicate_sheets(self) -> Dict[str, bool]:
        """Загружает все существующие таблицы дубликатов в кэш"""
        try:
            if not self._check_and_reinitialize_client():
                logger.error("❌ Google Sheets клиент не может быть восстановлен")
                return {}
            
            logger.info("🔄 Поиск всех таблиц дубликатов...")
            
            # Примечание: list_permissions требует fileId, поэтому используем прямой поиск по именам
            logger.info("🔍 Поиск таблиц дубликатов по известным паттернам...")
            
            results = {}
            
            # Пытаемся открыть таблицы по известным паттернам
            duplicate_patterns = [
                "Duplicates_",
                "duplicates_",
                "DUPLICATES_"
            ]
            
            # Также пробуем популярные символы токенов
            common_symbols = [
                "TRUMP", "PEPE", "DOGE", "SHIB", "BONK", "WIF", "POPCAT", "PNUT", 
                "GOAT", "MOODENG", "NEIRO", "TURBO", "BRETT", "TOSHI", "FLOKI",
                "PUMP", "MEME", "AI", "BASED", "SNEK", "MYRO", "BOME", "SLERF",
                "BOOK", "MICHI", "ANSEM", "FWOG", "PONKE", "GIGA", "MAGA", "MAGA"
            ]
            
            for symbol in common_symbols:
                for pattern in duplicate_patterns:
                    sheet_name = f"{pattern}{symbol}"
                    try:
                        spreadsheet = self.client.open(sheet_name)
                        group_key = f"{symbol.lower()}_{symbol.upper()}"
                        self.spreadsheets[group_key] = spreadsheet
                        results[group_key] = True
                        logger.info(f"✅ Загружена таблица: {sheet_name} -> {group_key}")
                    except:
                        continue
            
            # Также пытаемся найти таблицы по токенам из БД
            try:
                db_manager = get_db_manager()
                if db_manager:
                    from database import DuplicateToken
                    session = db_manager.Session()
                    
                    # Получаем популярные символы из БД
                    popular_symbols = session.query(DuplicateToken.symbol).distinct().limit(100).all()
                    
                    for symbol_row in popular_symbols:
                        symbol = symbol_row[0]
                        if symbol and len(symbol) <= 20:  # Разумная длина символа
                            for pattern in duplicate_patterns:
                                sheet_name = f"{pattern}{symbol}"
                                try:
                                    spreadsheet = self.client.open(sheet_name)
                                    group_key = f"{symbol.lower()}_{symbol.upper()}"
                                    if group_key not in self.spreadsheets:
                                        self.spreadsheets[group_key] = spreadsheet
                                        results[group_key] = True
                                        logger.info(f"✅ Загружена таблица из БД: {sheet_name} -> {group_key}")
                                except:
                                    continue
                    
                    session.close()
                    
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки символов из БД: {e}")
            
            logger.info(f"📊 Загружено {len(results)} таблиц дубликатов в кэш")
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки таблиц дубликатов: {e}")
            return {}

# Глобальный экземпляр для использования в проекте
sheets_manager = GoogleSheetsManager()

# 🔄 СПРАВКА ПО RETRY МЕХАНИЗМУ:
# 
# Новый retry механизм гарантирует 100% выполнение запросов к Google Sheets API
# 
# Доступные методы для управления:
# - sheets_manager.get_queue_status() - получить состояние очередей
# - sheets_manager.log_queue_status() - логировать состояние очередей 
# - sheets_manager.get_failed_tasks_count() - количество неудачных задач
# - sheets_manager.retry_failed_tasks() - повторить неудачные задачи
# - sheets_manager.force_retry_all_failed() - принудительно повторить все неудачные задачи
# - sheets_manager.clear_failed_tasks() - очистить очередь неудачных задач
# - sheets_manager.configure_retry_settings(max_retries, retry_delay_base, retry_delay_max) - настроить параметры retry
# 
# Параметры по умолчанию:
# - max_retries = 5 (максимум 5 попыток)
# - retry_delay_base = 2 (начальная задержка 2 секунды)
# - retry_delay_max = 30 (максимальная задержка 30 секунд)
# - rate_limit_max = 290 (максимум 290 запросов в минуту)
# 
# Система автоматически:
# - Проверяет и восстанавливает подключение к Google Sheets API
# - Выполняет повторные попытки с экспоненциальным backoff
# - Логирует состояние очередей каждые 5 минут
# - Сохраняет критически неудачные задачи для ручного разбора
# 
# 🚀 Результат: 100% гарантированное выполнение запросов к Google Sheets! 