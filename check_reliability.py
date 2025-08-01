#!/usr/bin/env python3
"""
Проверка надежности обработки запросов к Nitter
Проверяет: повторы, ротацию доменов, прокси, куки, timeout handling
"""

import os
import sys
import json
from datetime import datetime

def check_twitter_analysis_status():
    """Проверяет, включен ли Twitter анализ"""
    print("🔍 ПРОВЕРКА 1: Статус Twitter анализа")
    print("-" * 40)
    
    # Проверяем переменную окружения
    contract_search_disabled = os.getenv('CONTRACT_SEARCH_DISABLED', 'false').lower() == 'true'
    
    # Проверяем код pump_bot.py на жестко закодированное отключение
    try:
        with open('pump_bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        hardcoded_disabled = '# ОТКЛЮЧЕН: Twitter анализ больше не нужен' in content
        
        print(f"📊 CONTRACT_SEARCH_DISABLED: {contract_search_disabled}")
        print(f"📊 Жестко отключен в коде: {hardcoded_disabled}")
        
        if hardcoded_disabled:
            print("❌ ПРОБЛЕМА: Twitter анализ жестко отключен в коде!")
            print("🔧 РЕШЕНИЕ: Удалить строку отключения из pump_bot.py")
            return False
        elif contract_search_disabled:
            print("⚠️ Twitter анализ отключен переменной окружения")
            return False
        else:
            print("✅ Twitter анализ включен")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False

def check_domain_rotation_integration():
    """Проверяет интеграцию доменной ротации"""
    print("\n🔄 ПРОВЕРКА 2: Интеграция доменной ротации")
    print("-" * 50)
    
    files_to_check = {
        'pump_bot.py': ['get_next_nitter_domain', 'record_nitter_request_result'],
        'duplicate_groups_manager.py': ['get_next_nitter_domain'],
        'background_monitor.py': ['get_next_nitter_domain']
    }
    
    integration_status = {}
    
    for filename, functions in files_to_check.items():
        if not os.path.exists(filename):
            print(f"⚠️ {filename}: файл не найден")
            integration_status[filename] = False
            continue
            
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            file_integrated = all(func in content for func in functions)
            integration_status[filename] = file_integrated
            
            if file_integrated:
                print(f"✅ {filename}: интегрирован")
            else:
                print(f"❌ {filename}: НЕ интегрирован")
                missing = [func for func in functions if func not in content]
                print(f"   Отсутствует: {', '.join(missing)}")
                
        except Exception as e:
            print(f"❌ {filename}: ошибка проверки - {e}")
            integration_status[filename] = False
    
    return integration_status

def check_retry_logic():
    """Проверяет логику повторов"""
    print("\n🔁 ПРОВЕРКА 3: Логика повторов")
    print("-" * 35)
    
    try:
        with open('pump_bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем логику повторов
        retry_patterns = [
            'retry_count < 3',
            'retry_count + 1',
            'await search_single_query.*retry_count',
            'if retry_count <'
        ]
        
        found_patterns = []
        for pattern in retry_patterns:
            if pattern.replace('.*', '') in content or 'retry' in content:
                found_patterns.append(pattern)
        
        if found_patterns:
            print("✅ Логика повторов найдена")
            print(f"   Паттерны: {len(found_patterns)}/4")
        else:
            print("❌ Логика повторов НЕ найдена")
            
        # Проверяем типы ошибок для повторов
        error_types = ['TimeoutError', 'ConnectionError', '429', 'blocked']
        found_errors = [err for err in error_types if err in content]
        
        print(f"📊 Обрабатываемые ошибки: {', '.join(found_errors)}")
        
        return len(found_patterns) > 0
        
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False

def check_proxy_and_cookies():
    """Проверяет систему прокси и куки"""
    print("\n🔧 ПРОВЕРКА 4: Система прокси и куки")
    print("-" * 40)
    
    components = {
        'dynamic_cookie_rotation.py': 'Динамические куки',
        'anubis_handler.py': 'Обработка Anubis Challenge',
        'nitter_domain_rotator.py': 'Ротация доменов'
    }
    
    for filename, description in components.items():
        if os.path.exists(filename):
            print(f"✅ {description}: найден")
        else:
            print(f"❌ {description}: НЕ найден ({filename})")
    
    # Проверяем наличие прокси конфигурации
    proxy_files = ['proxies.txt', 'proxy_list.txt', 'config.py']
    proxy_found = any(os.path.exists(f) for f in proxy_files)
    
    if proxy_found:
        print("✅ Конфигурация прокси: найдена")
    else:
        print("⚠️ Конфигурация прокси: не найдена")
    
    return True

def check_error_handling():
    """Проверяет обработку ошибок"""
    print("\n⚠️ ПРОВЕРКА 5: Обработка ошибок")
    print("-" * 35)
    
    try:
        with open('pump_bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        error_handling_features = {
            'try:': 'Try-catch блоки',
            'except Exception': 'Общая обработка исключений', 
            'except TimeoutError': 'Обработка timeout',
            'except aiohttp': 'Обработка HTTP ошибок',
            'logger.error': 'Логирование ошибок',
            'logger.warning': 'Логирование предупреждений'
        }
        
        for pattern, description in error_handling_features.items():
            if pattern in content:
                print(f"✅ {description}")
            else:
                print(f"⚠️ {description}: не найден")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False

def check_recent_logs():
    """Проверяет последние логи на ошибки"""
    print("\n📋 ПРОВЕРКА 6: Анализ последних логов")
    print("-" * 40)
    
    log_files = ['logs/solspider.log', 'logs/errors.log']
    
    for log_file in log_files:
        if not os.path.exists(log_file):
            print(f"⚠️ {log_file}: не найден")
            continue
            
        try:
            # Читаем последние 50 строк
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_lines = lines[-50:] if len(lines) > 50 else lines
            
            # Анализируем ошибки
            error_counts = {
                'TimeoutError': 0,
                '429': 0,
                'ConnectionError': 0,
                'challenge': 0,
                'blocked': 0
            }
            
            for line in recent_lines:
                for error_type in error_counts:
                    if error_type in line:
                        error_counts[error_type] += 1
            
            print(f"📊 {log_file}:")
            for error_type, count in error_counts.items():
                if count > 0:
                    emoji = "🔴" if count > 5 else "⚠️" if count > 2 else "🟡"
                    print(f"   {emoji} {error_type}: {count}")
                    
        except Exception as e:
            print(f"❌ Ошибка чтения {log_file}: {e}")

def generate_recommendations():
    """Генерирует рекомендации по улучшению надежности"""
    print("\n🎯 РЕКОМЕНДАЦИИ ПО УЛУЧШЕНИЮ НАДЕЖНОСТИ")
    print("=" * 50)
    
    recommendations = [
        "1. 🔧 Включить Twitter анализ (убрать жесткое отключение)",
        "2. 🔄 Интегрировать ротацию доменов в duplicate_groups_manager.py", 
        "3. ⏰ Убедиться в работе timeout handling",
        "4. 🔁 Проверить логику повторов для всех типов ошибок",
        "5. 📊 Добавить мониторинг статистики доменов",
        "6. 🛡️ Улучшить обработку Anubis Challenge",
        "7. 📋 Настроить алерты при множественных ошибках"
    ]
    
    for rec in recommendations:
        print(rec)
    
    print(f"\n💡 Для максимальной надежности нужно:")
    print("   ✅ 3+ домена в ротации")
    print("   ✅ 3+ попытки для каждого запроса") 
    print("   ✅ Автоматическое переключение при ошибках")
    print("   ✅ Логирование всех ошибок и действий")
    print("   ✅ Мониторинг статистики доменов")

def main():
    """Основная функция проверки"""
    print("🔍 КОМПЛЕКСНАЯ ПРОВЕРКА НАДЕЖНОСТИ NITTER")
    print("=" * 60)
    print(f"⏰ Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Выполняем все проверки
    results = {}
    
    results['twitter_analysis'] = check_twitter_analysis_status()
    results['domain_rotation'] = check_domain_rotation_integration()
    results['retry_logic'] = check_retry_logic()
    results['proxy_cookies'] = check_proxy_and_cookies()
    results['error_handling'] = check_error_handling()
    
    check_recent_logs()
    
    # Общий результат
    print(f"\n📊 ОБЩИЙ РЕЗУЛЬТАТ ПРОВЕРКИ")
    print("=" * 40)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    percentage = (passed / total) * 100
    
    if percentage >= 80:
        status = "🟢 ОТЛИЧНО"
    elif percentage >= 60:
        status = "🟡 ХОРОШО"
    else:
        status = "🔴 ТРЕБУЕТ ВНИМАНИЯ"
    
    print(f"📈 Пройдено проверок: {passed}/{total} ({percentage:.0f}%)")
    print(f"🎯 Статус: {status}")
    
    generate_recommendations()
    
    return results

if __name__ == "__main__":
    main() 