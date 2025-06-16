#!/usr/bin/env python3
"""
УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ПРИЧИН БЫСТРОГО ФОЛБЭКА
Добавляет детальную информацию о причинах фолбэка в pump_bot.py
"""

import re
import os
from datetime import datetime

def enhance_fallback_logging():
    """Добавляет детальное логирование причин быстрого фолбэка"""
    
    print("🔍 ДОБАВЛЯЕМ ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ПРИЧИН ФОЛБЭКА...")
    
    if not os.path.exists('pump_bot.py'):
        print("❌ Файл pump_bot.py не найден!")
        return
    
    with open('pump_bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Модифицируем функцию search_single_query для возврата информации об ошибках
    old_search_function = r'async def search_single_query\(query, headers, retry_count=0, use_quotes=False, cycle_cookie=None\):'
    new_search_function = r'async def search_single_query(query, headers, retry_count=0, use_quotes=False, cycle_cookie=None):'
    
    # Находим участок с обработкой ошибок в search_single_query
    old_error_handling = r'''except Exception as e:
        logger.error\(f"Ошибка запроса к Nitter для '\{query\}': \{type\(e\).__name__\}: \{e\}"\)
        
        # Повторная попытка при любых ошибках \(не только 429\)
        if retry_count < 3:
            logger.warning\(f"⚠️ Повторная попытка для '\{query\}' после ошибки \{type\(e\).__name__\} \(попытка \{retry_count \+ 1\}/3\)"\)
            # await asyncio.sleep\(1\)  # УБИРАЕМ ПАУЗЫ
            return await search_single_query\(query, headers, retry_count \+ 1, use_quotes, cycle_cookie\)
        else:
            logger.error\(f"❌ Превышено количество попыток для '\{query\}' - возвращаем пустой результат"\)
            return \[\]'''
    
    new_error_handling = '''except Exception as e:
        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ОШИБОК
        error_type = type(e).__name__
        error_msg = str(e)
        
        # Определяем тип ошибки для детального логирования
        if "TimeoutError" in error_type or "timeout" in error_msg.lower():
            logger.error(f"⏰ ТАЙМАУТ для '{query}': {error_type} - {error_msg}")
            error_category = "TIMEOUT"
        elif "ConnectionError" in error_type or "connection" in error_msg.lower():
            logger.error(f"🔌 ОШИБКА СОЕДИНЕНИЯ для '{query}': {error_type} - {error_msg}")
            error_category = "CONNECTION"
        elif "429" in error_msg or "too many requests" in error_msg.lower():
            logger.error(f"🚫 ПРЕВЫШЕН ЛИМИТ для '{query}': {error_type} - {error_msg}")
            error_category = "RATE_LIMIT"
        elif "blocked" in error_msg.lower() or "bot" in error_msg.lower():
            logger.error(f"🤖 БЛОКИРОВКА для '{query}': {error_type} - {error_msg}")
            error_category = "BLOCKED"
        else:
            logger.error(f"❓ НЕИЗВЕСТНАЯ ОШИБКА для '{query}': {error_type} - {error_msg}")
            error_category = "UNKNOWN"
        
        # Повторная попытка при любых ошибках (не только 429)
        if retry_count < 3:
            logger.warning(f"⚠️ Повторная попытка для '{query}' после {error_category} (попытка {retry_count + 1}/3)")
            return await search_single_query(query, headers, retry_count + 1, use_quotes, cycle_cookie)
        else:
            logger.error(f"❌ Превышено количество попыток для '{query}' после {error_category} - возвращаем пустой результат")
            # Возвращаем информацию об ошибке для анализа
            return {"error": error_category, "message": error_msg, "type": error_type}'''
    
    # Применяем замену обработки ошибок
    content = re.sub(old_error_handling, new_error_handling, content, flags=re.MULTILINE | re.DOTALL)
    
    # 2. Модифицируем analyze_token_sentiment для обработки ошибок от search_single_query
    old_analyze_loop = r'''        # Выполняем запросы последовательно с паузами для избежания блокировки
        results = \[\]
        for i, \(query, use_quotes\) in enumerate\(search_queries\):
            try:
                result = await search_single_query\(query, headers, use_quotes=use_quotes, cycle_cookie=cycle_cookie\)
                results.append\(result\)
            except Exception as e:
                logger.warning\(f"⚠️ Ошибка запроса \{i\+1\}: \{e\}"\)
                results.append\(e\)'''
    
    new_analyze_loop = '''        # Выполняем запросы последовательно с паузами для избежания блокировки
        results = []
        error_details = []
        for i, (query, use_quotes) in enumerate(search_queries):
            try:
                result = await search_single_query(query, headers, use_quotes=use_quotes, cycle_cookie=cycle_cookie)
                
                # Проверяем если результат содержит информацию об ошибке
                if isinstance(result, dict) and "error" in result:
                    error_details.append({
                        "query": query,
                        "error_category": result["error"],
                        "error_message": result["message"],
                        "error_type": result["type"]
                    })
                    logger.warning(f"⚠️ Ошибка запроса {i+1} для '{query}': {result['error']} - {result['message']}")
                    results.append([])  # Пустой результат
                else:
                    results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ Неожиданная ошибка запроса {i+1}: {e}")
                error_details.append({
                    "query": query,
                    "error_category": "UNEXPECTED",
                    "error_message": str(e),
                    "error_type": type(e).__name__
                })
                results.append(e)'''
    
    content = re.sub(old_analyze_loop, new_analyze_loop, content, flags=re.MULTILINE | re.DOTALL)
    
    # 3. Улучшаем логирование в twitter_analysis_worker
    old_fallback_logging = r'''                # Проверяем если анализ провалился из-за Nitter проблем
                if twitter_analysis\['tweets'\] == 0 and twitter_analysis\['engagement'\] == 0:
                    # Возможно Nitter недоступен - устанавливаем дефолтное значение
                    logger.warning\(f"⚡ Быстрый фолбэк для \{symbol\} - Nitter недоступен"\)'''
    
    new_fallback_logging = '''                # Проверяем если анализ провалился из-за Nitter проблем
                if twitter_analysis['tweets'] == 0 and twitter_analysis['engagement'] == 0:
                    # Анализируем причины фолбэка на основе error_details
                    fallback_reason = "НЕИЗВЕСТНАЯ ПРИЧИНА"
                    if 'error_details' in locals() and error_details:
                        # Определяем основную причину
                        error_categories = [err['error_category'] for err in error_details]
                        if 'TIMEOUT' in error_categories:
                            fallback_reason = "ТАЙМАУТ (медленный ответ сервера)"
                        elif 'RATE_LIMIT' in error_categories:
                            fallback_reason = "429 ОШИБКА (слишком много запросов)"
                        elif 'BLOCKED' in error_categories:
                            fallback_reason = "БЛОКИРОВКА ('Making sure you're not a bot!')"
                        elif 'CONNECTION' in error_categories:
                            fallback_reason = "ОШИБКА СОЕДИНЕНИЯ (сервер недоступен)"
                        else:
                            fallback_reason = f"ОШИБКИ: {', '.join(set(error_categories))}"
                        
                        # Детальное логирование
                        logger.warning(f"⚡ БЫСТРЫЙ ФОЛБЭК для {symbol}")
                        logger.warning(f"📋 ПРИЧИНА: {fallback_reason}")
                        for err in error_details:
                            logger.warning(f"   🔸 {err['query']}: {err['error_category']} - {err['error_message']}")
                    else:
                        logger.warning(f"⚡ БЫСТРЫЙ ФОЛБЭК для {symbol} - ПРИЧИНА: {fallback_reason}")'''
    
    content = re.sub(old_fallback_logging, new_fallback_logging, content, flags=re.MULTILINE | re.DOTALL)
    
    # 4. Добавляем детальное логирование для обработки исключений
    old_exception_handling = r'''            except Exception as e:
                logger.error\(f"❌ Ошибка анализа \{symbol\}: \{e\}"\)
                # Быстрый фолбэк при ошибке
                twitter_analysis = \{
                    'tweets': 0,
                    'symbol_tweets': 0,
                    'contract_tweets': 0, 
                    'engagement': 0,
                    'score': 0,
                    'rating': '❓ Ошибка анализа',
                    'contract_found': False,
                    'contract_authors': \[\]
                \}'''
    
    new_exception_handling = '''            except Exception as e:
                # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ИСКЛЮЧЕНИЙ
                error_type = type(e).__name__
                error_msg = str(e)
                
                logger.error(f"❌ ИСКЛЮЧЕНИЕ при анализе {symbol}: {error_type}")
                logger.error(f"📋 ДЕТАЛИ: {error_msg}")
                
                # Определяем причину исключения
                if "TimeoutError" in error_type:
                    fallback_reason = "ГЛОБАЛЬНЫЙ ТАЙМАУТ (превышено время ожидания)"
                elif "ConnectionError" in error_type:
                    fallback_reason = "ОШИБКА ПОДКЛЮЧЕНИЯ (сеть недоступна)"
                elif "HTTPError" in error_type:
                    fallback_reason = "HTTP ОШИБКА (проблема с сервером)"
                else:
                    fallback_reason = f"СИСТЕМНАЯ ОШИБКА ({error_type})"
                
                logger.warning(f"⚡ БЫСТРЫЙ ФОЛБЭК для {symbol}")
                logger.warning(f"📋 ПРИЧИНА: {fallback_reason}")
                
                # Быстрый фолбэк при ошибке
                twitter_analysis = {
                    'tweets': 0,
                    'symbol_tweets': 0,
                    'contract_tweets': 0, 
                    'engagement': 0,
                    'score': 0,
                    'rating': '❓ Ошибка анализа',
                    'contract_found': False,
                    'contract_authors': []
                }'''
    
    content = re.sub(old_exception_handling, new_exception_handling, content, flags=re.MULTILINE | re.DOTALL)
    
    # Сохраняем обновленный файл
    with open('pump_bot.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ pump_bot.py: добавлено детальное логирование причин фолбэка")
    
    print("\n🎯 ДОБАВЛЕННЫЕ УЛУЧШЕНИЯ:")
    print("• Детальная классификация ошибок:")
    print("  - TIMEOUT (медленный ответ)")
    print("  - RATE_LIMIT (429 ошибки)")
    print("  - BLOCKED (защита от ботов)")
    print("  - CONNECTION (проблемы сети)")
    print("  - UNKNOWN (прочие ошибки)")
    print("• Логирование каждого запроса с причиной")
    print("• Показ конкретных ошибок для каждого токена")
    print("• Анализ причин на основе всех запросов")
    
    print("\n📊 ПРИМЕРЫ НОВЫХ ЛОГОВ:")
    print("⚡ БЫСТРЫЙ ФОЛБЭК для TPULSE")
    print("📋 ПРИЧИНА: ТАЙМАУТ (медленный ответ сервера)")
    print("   🔸 $TPULSE: TIMEOUT - Read timeout")
    print("   🔸 8K7j2m9N...w5pX3: TIMEOUT - Connection timeout")
    
    print("\n⚠️ РЕКОМЕНДАЦИЯ: перезапустите бота для активации логирования")

if __name__ == "__main__":
    enhance_fallback_logging() 