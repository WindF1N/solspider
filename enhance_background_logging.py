#!/usr/bin/env python3
"""
УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ДЛЯ BACKGROUND MONITOR
Добавляет детальную информацию о причинах ошибок в background_monitor.py
"""

import re
import os
from datetime import datetime

def enhance_background_logging():
    """Добавляет детальное логирование в background_monitor.py"""
    
    print("🔍 ДОБАВЛЯЕМ ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ В BACKGROUND MONITOR...")
    
    if not os.path.exists('background_monitor.py'):
        print("❌ Файл background_monitor.py не найден!")
        return
    
    with open('background_monitor.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Улучшаем обработку TimeoutError
    old_timeout_handling = r'''                except asyncio.TimeoutError:
                    logger.warning\(f"⏰ Таймаут \(8с\) для \{token.symbol\}, пропускаем"\)
                    self.consecutive_errors \+= 1
                    continue'''
    
    new_timeout_handling = '''                except asyncio.TimeoutError:
                    logger.warning(f"⏰ ФОНОВЫЙ МОНИТОРИНГ: ТАЙМАУТ для {token.symbol}")
                    logger.warning(f"📋 ПРИЧИНА: медленный ответ Nitter сервера (>5 секунд)")
                    logger.warning(f"🔧 ДЕЙСТВИЕ: пропускаем токен и переходим к следующему")
                    self.consecutive_errors += 1
                    continue'''
    
    content = re.sub(old_timeout_handling, new_timeout_handling, content, flags=re.MULTILINE)
    
    # 2. Улучшаем обработку 429 ошибок
    old_429_handling = r'''                            elif response.status == 429:
                                logger.warning\(f"⚠️ Rate limit для \{token.symbol\}, быстрый пропуск"\)
                                self.consecutive_errors \+= 1
                                continue'''
    
    new_429_handling = '''                            elif response.status == 429:
                                logger.warning(f"🚫 ФОНОВЫЙ МОНИТОРИНГ: 429 ОШИБКА для {token.symbol}")
                                logger.warning(f"📋 ПРИЧИНА: слишком много запросов к Nitter серверу")
                                logger.warning(f"🔧 ДЕЙСТВИЕ: быстрый пропуск токена")
                                self.consecutive_errors += 1
                                continue'''
    
    content = re.sub(old_429_handling, new_429_handling, content, flags=re.MULTILINE)
    
    # 3. Улучшаем обработку блокировки
    old_blocked_handling = r'''                                if title and 'Making sure you\\'re not a bot!' in title.get_text\(\):
                                    logger.error\(f"🚫 NITTER ЗАБЛОКИРОВАН! Контракт: \{token.mint\} куки '\{cycle_cookie\}'"\)
                                    continue'''
    
    new_blocked_handling = '''                                if title and 'Making sure you\\'re not a bot!' in title.get_text():
                                    logger.error(f"🤖 ФОНОВЫЙ МОНИТОРИНГ: БЛОКИРОВКА для {token.symbol}")
                                    logger.error(f"📋 ПРИЧИНА: защита Nitter от ботов ('Making sure you're not a bot!')")
                                    logger.error(f"🔧 ДЕЙСТВИЕ: требуется обновление cookie")
                                    logger.error(f"🍪 Cookie: {cycle_cookie}")
                                    continue'''
    
    content = re.sub(old_blocked_handling, new_blocked_handling, content, flags=re.MULTILINE)
    
    # 4. Улучшаем общую обработку ошибок
    old_general_error = r'''                except Exception as e:
                    logger.error\(f"❌ Ошибка запроса к \{url\}: \{e\}"\)
                    self.consecutive_errors \+= 1
                    continue'''
    
    new_general_error = '''                except Exception as e:
                    # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ОШИБОК В ФОНОВОМ МОНИТОРЕ
                    error_type = type(e).__name__
                    error_msg = str(e)
                    
                    if "ConnectionError" in error_type:
                        logger.error(f"🔌 ФОНОВЫЙ МОНИТОРИНГ: ОШИБКА СОЕДИНЕНИЯ для {token.symbol}")
                        logger.error(f"📋 ПРИЧИНА: сеть недоступна или Nitter сервер недоступен")
                    elif "SSLError" in error_type:
                        logger.error(f"🔒 ФОНОВЫЙ МОНИТОРИНГ: SSL ОШИБКА для {token.symbol}")
                        logger.error(f"📋 ПРИЧИНА: проблемы с HTTPS сертификатом")
                    elif "HTTPError" in error_type:
                        logger.error(f"🌐 ФОНОВЫЙ МОНИТОРИНГ: HTTP ОШИБКА для {token.symbol}")
                        logger.error(f"📋 ПРИЧИНА: ошибка HTTP протокола")
                    else:
                        logger.error(f"❓ ФОНОВЫЙ МОНИТОРИНГ: НЕИЗВЕСТНАЯ ОШИБКА для {token.symbol}")
                        logger.error(f"📋 ТИП: {error_type}")
                    
                    logger.error(f"📄 ДЕТАЛИ: {error_msg}")
                    logger.error(f"🔧 ДЕЙСТВИЕ: пропускаем токен и переходим к следующему")
                    
                    self.consecutive_errors += 1
                    continue'''
    
    content = re.sub(old_general_error, new_general_error, content, flags=re.MULTILINE | re.DOTALL)
    
    # 5. Добавляем логирование в основную функцию check_contract_mentions
    old_check_function_start = r'''    async def check_contract_mentions\(self, token, cycle_cookie\):
        """Проверяет наличие упоминаний контракта токена в Twitter с авторами"""
        try:'''
    
    new_check_function_start = '''    async def check_contract_mentions(self, token, cycle_cookie):
        """Проверяет наличие упоминаний контракта токена в Twitter с авторами"""
        try:
            # ЛОГИРОВАНИЕ НАЧАЛА ПРОВЕРКИ
            logger.debug(f"🔍 ФОНОВЫЙ МОНИТОРИНГ: начинаем проверку {token.symbol}")'''
    
    content = re.sub(old_check_function_start, new_check_function_start, content, flags=re.MULTILINE)
    
    # 6. Улучшаем логирование успешных результатов
    old_success_log = r'''            if tweets_count > 0:
                logger.info\(f"🔥 КОНТРАКТ НАЙДЕН! \{token.symbol\} - \{tweets_count\} твитов, активность: \{engagement\}"\)'''
    
    new_success_log = '''            if tweets_count > 0:
                logger.info(f"🔥 ФОНОВЫЙ МОНИТОРИНГ: КОНТРАКТ НАЙДЕН!")
                logger.info(f"💎 Токен: {token.symbol} ({token.mint[:8]}...)")
                logger.info(f"📊 Статистика: {tweets_count} твитов, активность: {engagement}")
                logger.info(f"👥 Авторы: {len(authors)} уникальных")
                logger.info(f"🎯 УСПЕХ: отправляем уведомление о найденном контракте")'''
    
    content = re.sub(old_success_log, new_success_log, content, flags=re.MULTILINE)
    
    # 7. Добавляем итоговое логирование производительности
    old_performance_log = r'''        except Exception as e:
            logger.error\(f"❌ Ошибка проверки контракта для \{token.symbol\}: \{e\}"\)
            self.consecutive_errors \+= 1
            return False'''
    
    new_performance_log = '''        except Exception as e:
            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ КРИТИЧЕСКИХ ОШИБОК
            error_type = type(e).__name__
            error_msg = str(e)
            
            logger.error(f"💥 ФОНОВЫЙ МОНИТОРИНГ: КРИТИЧЕСКАЯ ОШИБКА для {token.symbol}")
            logger.error(f"📋 ТИП ОШИБКИ: {error_type}")
            logger.error(f"📄 СООБЩЕНИЕ: {error_msg}")
            logger.error(f"🔧 ДЕЙСТВИЕ: пропускаем токен, продолжаем мониторинг")
            
            self.consecutive_errors += 1
            return False'''
    
    content = re.sub(old_performance_log, new_performance_log, content, flags=re.MULTILINE | re.DOTALL)
    
    # Сохраняем обновленный файл
    with open('background_monitor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ background_monitor.py: добавлено детальное логирование ошибок")
    
    print("\n🎯 ДОБАВЛЕННЫЕ УЛУЧШЕНИЯ:")
    print("• Детальная классификация ошибок фонового мониторинга:")
    print("  - ТАЙМАУТ (медленный ответ >5 секунд)")
    print("  - 429 ОШИБКА (слишком много запросов)")
    print("  - БЛОКИРОВКА (защита от ботов)")
    print("  - ОШИБКА СОЕДИНЕНИЯ (сеть недоступна)")
    print("  - SSL/HTTP ОШИБКИ (проблемы протокола)")
    print("• Логирование каждого этапа проверки")
    print("• Показ конкретных действий при ошибках")
    print("• Детальная информация об успешных находках")
    
    print("\n📊 ПРИМЕРЫ НОВЫХ ЛОГОВ:")
    print("⏰ ФОНОВЫЙ МОНИТОРИНГ: ТАЙМАУТ для TPULSE")
    print("📋 ПРИЧИНА: медленный ответ Nitter сервера (>5 секунд)")
    print("🔧 ДЕЙСТВИЕ: пропускаем токен и переходим к следующему")
    print()
    print("🔥 ФОНОВЫЙ МОНИТОРИНГ: КОНТРАКТ НАЙДЕН!")
    print("💎 Токен: TPULSE (8K7j2m9N...)")
    print("📊 Статистика: 3 твитов, активность: 156")
    print("👥 Авторы: 2 уникальных")
    print("🎯 УСПЕХ: отправляем уведомление о найденном контракте")
    
    print("\n⚠️ РЕКОМЕНДАЦИЯ: перезапустите фоновый мониторинг для активации логирования")

if __name__ == "__main__":
    enhance_background_logging() 