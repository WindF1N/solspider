#!/usr/bin/env python3
"""
Продвинутая система управления группами дубликатов токенов
Интеграция с Google Sheets, умные Telegram сообщения, отслеживание официальных контрактов
"""
import logging
import requests
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import Counter
import json
import re
import time

# Импорты проекта
from google_sheets_manager import sheets_manager
from database import get_db_manager, DuplicateToken

logger = logging.getLogger(__name__)

class DuplicateGroupsManager:
    """Менеджер для управления группами дубликатов с умными функциями"""
    
    def __init__(self, telegram_token: str):
        """Инициализация с токеном Telegram бота"""
        self.telegram_token = telegram_token
        self.telegram_url = f"https://api.telegram.org/bot{telegram_token}"
        
        # Группы дубликатов {group_key: GroupData}
        self.groups = {}
        
        # Отслеживание официальных контрактов {group_key: official_contract_info}
        self.official_contracts = {}
        
        # Настройки
        self.target_chat_id = -1002680160752  # ID группы
        self.message_thread_id = 14  # ID темы для дубликатов
    
    class GroupData:
        """Данные группы дубликатов"""
        def __init__(self, group_key: str, symbol: str, name: str):
            self.group_key = group_key
            self.symbol = symbol
            self.name = name
            self.tokens = []  # Список всех токенов в группе
            self.message_id = None  # ID сообщения в Telegram
            self.sheet_url = None  # URL Google Sheets таблицы
            self.main_twitter = None  # Главный Twitter аккаунт
            self.official_contract = None  # Официальный контракт если найден
            self.created_at = datetime.now()
            self.last_updated = datetime.now()
    
    def create_group_key(self, token_data: Dict) -> str:
        """Создает ключ группы для токена"""
        name = token_data.get('name', '').strip().lower()
        symbol = token_data.get('symbol', '').strip().upper()
        return f"{name}_{symbol}"
    
    def extract_twitter_accounts(self, token_data: Dict) -> List[str]:
        """Извлекает все Twitter аккаунты из данных токена"""
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
    
    def determine_main_twitter(self, tokens: List[Dict]) -> Optional[str]:
        """Определяет главный Twitter аккаунт на основе частоты встречаемости"""
        try:
            twitter_counter = Counter()
            
            for token in tokens:
                twitter_accounts = self.extract_twitter_accounts(token)
                for account in twitter_accounts:
                    twitter_counter[account.lower()] += 1
            
            if not twitter_counter:
                return None
            
            # Возвращаем самый часто встречающийся аккаунт
            most_common = twitter_counter.most_common(1)[0]
            main_twitter = most_common[0]
            frequency = most_common[1]
            
            logger.info(f"🎯 Главный Twitter определен: @{main_twitter} (встречается {frequency} раз)")
            return main_twitter
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения главного Twitter: {e}")
            return None
    
    async def add_token_to_group(self, token_data: Dict, reason: str = "Обнаружен дубликат") -> bool:
        """Добавляет токен в группу дубликатов"""
        try:
            group_key = self.create_group_key(token_data)
            token_id = token_data.get('id')
            symbol = token_data.get('symbol', 'Unknown')
            name = token_data.get('name', 'Unknown')
            
            # Проверяем, существует ли группа
            if group_key not in self.groups:
                # Создаем новую группу
                logger.info(f"🆕 Создаем новую группу дубликатов: {symbol}")
                
                # Загружаем все токены этого символа из БД
                db_tokens = self._load_tokens_from_db(symbol)
                
                # Создаем группу
                group = self.GroupData(group_key, symbol, name)
                group.tokens = db_tokens + [token_data] if token_data not in db_tokens else db_tokens
                
                # Определяем главный Twitter аккаунт
                group.main_twitter = self.determine_main_twitter(group.tokens)
                
                # ⚠️ КРИТИЧЕСКАЯ ПРОВЕРКА: Если главный Twitter не определен, НЕ создаем группу
                if not group.main_twitter:
                    logger.warning(f"🚫 Группа {symbol} НЕ создана: главный Twitter не определен")
                    return False
                
                # 🚀 ПОЛНОСТЬЮ АСИНХРОННАЯ ЛОГИКА: сообщение БЕЗ кнопки, затем таблица в фоне
                logger.info(f"📊 Группа {symbol} создается асинхронно...")
                
                # Сначала отправляем сообщение БЕЗ кнопки (не тормозим поток)
                group.sheet_url = None  # Пока нет таблицы
                group.message_id = await self._send_group_message(group)
                
                # Сохраняем группу
                self.groups[group_key] = group
                
                # Запускаем создание таблицы асинхронно (в фоновом потоке)
                self._create_sheet_and_update_message_async(group_key, group.tokens, group.main_twitter)
                
                logger.info(f"✅ Группа дубликатов {symbol} создана, таблица формируется в фоне")
                return True
                
            else:
                # Обновляем существующую группу
                group = self.groups[group_key]
                
                # Проверяем, не добавлен ли уже этот токен
                existing_ids = [t.get('id') for t in group.tokens]
                if token_id in existing_ids:
                    logger.debug(f"🔄 Токен {token_id[:8]}... уже в группе {group_key}")
                    return True
                
                # Добавляем новый токен
                group.tokens.append(token_data)
                group.last_updated = datetime.now()
                
                # Пересчитываем главный Twitter аккаунт
                new_main_twitter = self.determine_main_twitter(group.tokens)
                if new_main_twitter != group.main_twitter:
                    group.main_twitter = new_main_twitter
                    # Обновляем статусы в Google Sheets асинхронно
                    sheets_manager.update_main_twitter_async(group_key, new_main_twitter)
                
                # Добавляем токен в Google Sheets асинхронно
                sheets_manager.add_single_token_fast_async(group_key, token_data, group.main_twitter)
                
                # 🔧 ИСПРАВЛЕНИЕ: Если таблица еще не создана, создаем ее асинхронно
                if not group.sheet_url:
                    logger.info(f"📊 Таблица для группы {symbol} еще не создана, запускаем создание...")
                    self._create_sheet_and_update_message_async(group_key, group.tokens, group.main_twitter)
                else:
                    # Если таблица уже есть, просто обновляем сообщение
                    await self._update_group_message(group)
                
                logger.info(f"✅ Токен {symbol} добавлен в существующую группу (всего: {len(group.tokens)})")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления токена в группу: {e}")
            return False
    
    def _load_tokens_from_db(self, symbol: str) -> List[Dict]:
        """Загружает все токены символа из базы данных"""
        try:
            db_manager = get_db_manager()
            session = db_manager.Session()
            
            # Получаем все токены этого символа
            tokens = session.query(DuplicateToken).filter(
                DuplicateToken.normalized_symbol == symbol.lower()
            ).all()
            
            session.close()
            
            # Конвертируем в словари
            token_list = []
            for token in tokens:
                token_dict = {
                    'id': token.mint,
                    'name': token.name,
                    'symbol': token.symbol,
                    'icon': token.icon,
                    'twitter': token.twitter,
                    'telegram': token.telegram,
                    'website': token.website,
                    'firstPool': {
                        'createdAt': token.created_at.isoformat() if token.created_at else None
                    }
                }
                token_list.append(token_dict)
            
            logger.info(f"📊 Загружено {len(token_list)} токенов {symbol} из БД")
            return token_list
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки токенов из БД: {e}")
            return []
    
    async def _send_group_message(self, group: 'GroupData') -> Optional[int]:
        """Отправляет новое сообщение группы в Telegram"""
        try:
            message_text = self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)
            
            payload = {
                "chat_id": self.target_chat_id,
                "message_thread_id": self.message_thread_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }
            
            response = requests.post(f"{self.telegram_url}/sendMessage", json=payload)
            
            if response.status_code == 200:
                result = response.json()
                message_id = result['result']['message_id']
                logger.info(f"✅ Сообщение группы {group.symbol} отправлено (ID: {message_id})")
                return message_id
            else:
                logger.error(f"❌ Ошибка отправки сообщения группы: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки группового сообщения: {e}")
            return None
    
    async def _update_group_message(self, group: 'GroupData') -> bool:
        """Обновляет существующее сообщение группы"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления")
                return False
            
            message_text = self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)
            
            payload = {
                "chat_id": self.target_chat_id,
                "message_id": group.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }
            
            response = requests.post(f"{self.telegram_url}/editMessageText", json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ Сообщение группы {group.symbol} обновлено")
                return True
            else:
                logger.error(f"❌ Ошибка обновления сообщения группы: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления группового сообщения: {e}")
            return False
    
    def _format_group_message(self, group: 'GroupData') -> str:
        """Форматирует текст сообщения для группы дубликатов"""
        try:
            # Заголовок
            message = f"🔄 <b>ГРУППА ДУБЛИКАТОВ: {group.symbol.upper()}</b>\n"
            message += f"📝 <b>Название:</b> {group.name}\n\n"
            
            # Информация о главном Twitter аккаунте
            if group.main_twitter:
                message += f"🎯 <b>ГЛАВНЫЙ TWITTER:</b> @{group.main_twitter}\n"
                
                # Проверяем, найден ли официальный контракт
                if group.official_contract:
                    message += f"✅ <b>ОФИЦИАЛЬНЫЙ КОНТРАКТ НАЙДЕН!</b>\n"
                    message += f"📍 <b>Адрес:</b> <code>{group.official_contract['address']}</code>\n"
                    message += f"📅 <b>Дата:</b> {group.official_contract['date']}\n\n"
                else:
                    message += f"🔍 <b>Статус:</b> Официальный контракт НЕ найден в Twitter\n\n"
            else:
                message += f"❓ <b>ГЛАВНЫЙ TWITTER:</b> Не определен\n\n"
            
            # Статистика токенов
            total_tokens = len(group.tokens)
            tokens_with_links = sum(1 for token in group.tokens if self._has_links(token))
            tokens_without_links = total_tokens - tokens_with_links
            
            message += f"📊 <b>СТАТИСТИКА:</b>\n"
            message += f"• Всего токенов: <b>{total_tokens}</b>\n"
            message += f"• С ссылками: <b>{tokens_with_links}</b>\n"
            message += f"• Без ссылок: <b>{tokens_without_links}</b>\n\n"
            
            # Последний добавленный токен
            if group.tokens:
                def safe_get_created_at(token):
                    """Безопасно получает дату создания токена"""
                    created_at = token.get('firstPool', {}).get('createdAt', '')
                    if not created_at:
                        return ''  # Возвращаем пустую строку для None/пустых значений
                    return str(created_at)
                
                try:
                    latest_token = max(group.tokens, key=safe_get_created_at)
                    latest_contract = latest_token.get('id', 'Unknown')
                    latest_created = latest_token.get('firstPool', {}).get('createdAt', '')
                    
                    if latest_created:
                        try:
                            created_date = datetime.fromisoformat(latest_created.replace('Z', '+00:00'))
                            created_display = created_date.strftime('%d.%m.%Y %H:%M')
                        except:
                            created_display = latest_created
                    else:
                        created_display = "Неизвестно"
                    
                    message += f"🆕 <b>ПОСЛЕДНИЙ КОНТРАКТ:</b>\n"
                    message += f"<code>{latest_contract}</code>\n"
                    message += f"📅 Создан: {created_display}\n\n"
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка определения последнего токена: {e}")
                    # Используем первый токен как fallback
                    if group.tokens:
                        fallback_token = group.tokens[0]
                        fallback_contract = fallback_token.get('id', 'Unknown')
                        message += f"🆕 <b>ПОСЛЕДНИЙ КОНТРАКТ:</b>\n"
                        message += f"<code>{fallback_contract}</code>\n"
                        message += f"📅 Создан: Неизвестно\n\n"
            
            # Время обновления
            message += f"🕐 <b>Обновлено:</b> {group.last_updated.strftime('%d.%m.%Y %H:%M:%S')}"
            
            return message
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования сообщения группы: {e}")
            return f"❌ Ошибка форматирования группы {group.symbol}"
    
    def _create_group_keyboard(self, group: 'GroupData') -> Dict:
        """Создает inline клавиатуру для группы дубликатов"""
        try:
            buttons = []
            
            # Кнопка Google Sheets - проверяем что URL не пустой
            if group.sheet_url and group.sheet_url.strip():
                buttons.append([{
                    "text": "📊 Смотреть в Google Sheets",
                    "url": group.sheet_url
                }])
                logger.debug(f"✅ Кнопка Google Sheets добавлена для группы {group.symbol}")
            else:
                logger.debug(f"📊 Кнопка Google Sheets пока не готова для группы {group.symbol} (таблица создается)")
            
            # Кнопка "Окей" появляется только когда найден официальный контракт
            if group.official_contract:
                buttons.append([{
                    "text": "✅ Окей",
                    "callback_data": f"delete_group:{group.group_key}"
                }])
            
            return {"inline_keyboard": buttons}
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры группы: {e}")
            return {"inline_keyboard": []}
    
    def _has_links(self, token_data: Dict) -> bool:
        """Проверяет наличие ссылок у токена"""
        link_fields = ['twitter', 'telegram', 'website']
        return any(token_data.get(field) for field in link_fields)
    
    def _create_sheet_and_update_message_async(self, group_key: str, tokens: List[Dict], main_twitter: str):
        """🔥 СУПЕР БЫСТРОЕ асинхронное создание Google Sheets таблицы батчем"""
        def create_sheet_task():
            try:
                logger.info(f"🔥 Создаем Google Sheets таблицу для группы {group_key} БАТЧЕМ ({len(tokens)} токенов)...")
                
                # 🔥 СУПЕР БЫСТРО: Добавляем ВСЕ токены одним батчем
                if tokens:
                    table_created = sheets_manager.add_tokens_batch(group_key, tokens, main_twitter)
                    
                    if table_created:
                        # Получаем URL таблицы
                        sheet_url = sheets_manager.get_sheet_url(group_key)
                        
                        if sheet_url and group_key in self.groups:
                            # Обновляем группу
                            group = self.groups[group_key]
                            group.sheet_url = sheet_url
                            
                            logger.info(f"🔥 БАТЧЕВАЯ таблица создана для {group_key}, URL: {sheet_url}")
                            
                            # Обновляем сообщение с кнопкой
                            if group.message_id:
                                self._update_message_with_sheet_button(group)
                            else:
                                logger.debug(f"📊 Сообщение для группы {group_key} не отправлено (тест режим)")
                            
                            logger.info(f"✅ БАТЧЕВАЯ обработка таблицы для группы {group_key} завершена за 1 запрос!")
                        else:
                            logger.error(f"❌ Не удалось получить URL таблицы для {group_key}")
                    else:
                        logger.error(f"❌ Не удалось создать таблицу для группы {group_key}")
                        
            except Exception as e:
                logger.error(f"❌ Ошибка создания таблицы в фоне для {group_key}: {e}")
        
        # Запускаем в фоновом потоке Google Sheets
        sheets_manager._queue_task(create_sheet_task)
    
    def _update_message_with_sheet_button(self, group: 'GroupData') -> bool:
        """Обновляет сообщение Telegram с кнопкой Google Sheets (синхронно)"""
        try:
            if not group.message_id:
                logger.warning(f"⚠️ Группа {group.group_key} не имеет message_id для обновления")
                return False
            
            message_text = self._format_group_message(group)
            inline_keyboard = self._create_group_keyboard(group)
            
            payload = {
                "chat_id": self.target_chat_id,
                "message_id": group.message_id,
                "text": message_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "reply_markup": inline_keyboard
            }
            
            response = requests.post(f"{self.telegram_url}/editMessageText", json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ Сообщение группы {group.symbol} обновлено с кнопкой Google Sheets")
                return True
            else:
                logger.error(f"❌ Ошибка обновления сообщения группы: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сообщения с кнопкой: {e}")
            return False
    
    async def check_official_contract(self, group_key: str) -> bool:
        """Проверяет наличие официального контракта в Twitter главного аккаунта"""
        try:
            if group_key not in self.groups:
                return False
            
            group = self.groups[group_key]
            if not group.main_twitter:
                return False
            
            # Здесь будет логика поиска контракта в Twitter
            # Пока что заглушка - вернет False
            # TODO: Интегрировать с системой поиска в Twitter из pump_bot.py
            
            logger.debug(f"🔍 Проверка официального контракта для @{group.main_twitter} - пока не реализовано")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки официального контракта: {e}")
            return False
    
    async def mark_official_contract_found(self, group_key: str, contract_address: str, found_date: str = None) -> bool:
        """Отмечает что официальный контракт найден"""
        try:
            if group_key not in self.groups:
                return False
            
            group = self.groups[group_key]
            
            # Сохраняем информацию об официальном контракте
            group.official_contract = {
                'address': contract_address,
                'date': found_date or datetime.now().strftime('%d.%m.%Y %H:%M'),
                'found_at': datetime.now()
            }
            
            # Обновляем Google Sheets
            if group.main_twitter:
                sheets_manager.check_official_contract_in_twitter(
                    group_key, group.main_twitter, contract_address
                )
            
            # Обновляем Telegram сообщение
            await self._update_group_message(group)
            
            logger.info(f"✅ Официальный контракт {contract_address[:8]}... отмечен для группы {group.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отметки официального контракта: {e}")
            return False
    
    async def delete_group(self, group_key: str) -> bool:
        """Удаляет группу дубликатов (удаляет сообщение в Telegram)"""
        try:
            if group_key not in self.groups:
                return False
            
            group = self.groups[group_key]
            
            # Удаляем сообщение в Telegram
            if group.message_id:
                payload = {
                    "chat_id": self.target_chat_id,
                    "message_id": group.message_id
                }
                
                response = requests.post(f"{self.telegram_url}/deleteMessage", json=payload)
                
                if response.status_code == 200:
                    logger.info(f"✅ Сообщение группы {group.symbol} удалено")
                else:
                    logger.warning(f"⚠️ Не удалось удалить сообщение группы {group.symbol}: {response.text}")
            
            # Удаляем группу из памяти
            del self.groups[group_key]
            
            logger.info(f"✅ Группа дубликатов {group.symbol} удалена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка удаления группы: {e}")
            return False
    
    def get_group_stats(self) -> Dict:
        """Возвращает статистику по всем группам"""
        try:
            total_groups = len(self.groups)
            total_tokens = sum(len(group.tokens) for group in self.groups.values())
            groups_with_official = sum(1 for group in self.groups.values() if group.official_contract)
            
            return {
                'total_groups': total_groups,
                'total_tokens': total_tokens,
                'groups_with_official_contracts': groups_with_official,
                'active_groups': [
                    {
                        'symbol': group.symbol,
                        'tokens_count': len(group.tokens),
                        'main_twitter': group.main_twitter,
                        'has_official': bool(group.official_contract),
                        'sheet_url': group.sheet_url
                    }
                    for group in self.groups.values()
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики групп: {e}")
            return {}

# Глобальный экземпляр для использования в проекте
# Будет инициализирован в main при запуске
_duplicate_groups_manager = None

def get_duplicate_groups_manager():
    """Возвращает текущий экземпляр менеджера групп дубликатов"""
    global _duplicate_groups_manager
    return _duplicate_groups_manager

def initialize_duplicate_groups_manager(telegram_token: str):
    """Инициализирует глобальный менеджер групп дубликатов"""
    global _duplicate_groups_manager
    _duplicate_groups_manager = DuplicateGroupsManager(telegram_token)
    logger.info("✅ Менеджер групп дубликатов инициализирован")

# Обратная совместимость - удалена, используйте get_duplicate_groups_manager() 