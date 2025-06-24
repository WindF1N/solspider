#!/usr/bin/env python3
"""
СКРИПТ ОЦЕНКИ TWITTER АККАУНТОВ
Анализирует качество Twitter аккаунтов для мониторинга токенов
Использует адаптивные пороги спама в зависимости от количества твитов
"""

import asyncio
import sys
import argparse
from datetime import datetime
import json

# Импортируем функции из существующих модулей
from pump_bot import analyze_author_page_contracts, should_notify_based_on_authors_unified
from logger_config import setup_logging
import logging

# Настройка логирования
setup_logging()
logger = logging.getLogger('twitter_evaluator')

class TwitterAccountEvaluator:
    """Класс для оценки качества Twitter аккаунтов"""
    
    def __init__(self):
        self.results = []
        
    async def evaluate_single_account(self, username, load_from_profile=True):
        """Оценивает один Twitter аккаунт"""
        try:
            logger.info(f"🔍 Начинаем анализ @{username}")
            
            # Анализируем аккаунт через pump_bot функцию
            result = await analyze_author_page_contracts(username, load_from_profile=load_from_profile)
            
            # Добавляем username для унифицированной функции
            result['username'] = username
            
            # ИСПРАВЛЕНИЕ: Преобразуем поля для унифицированной функции
            # Функция ожидает contract_diversity и total_contract_tweets
            unified_author_data = {
                'username': username,
                'contract_diversity': result.get('contract_diversity_percent', 0),
                'total_contract_tweets': result.get('total_tweets_on_page', 0),
                'max_contract_spam': result.get('max_contract_spam_percent', 0),
                'tweet_text': ''  # Пустой текст для избежания спам-бот проверки
            }
            
            # Проверяем через унифицированную логику
            should_notify = should_notify_based_on_authors_unified([unified_author_data])
            
            # Определяем категорию качества
            quality_category = self._get_quality_category(result, should_notify)
            
            # Формируем итоговый результат
            evaluation = {
                'username': username,
                'timestamp': datetime.now().isoformat(),
                'total_tweets': result.get('total_tweets_on_page', 0),
                'unique_contracts': result.get('unique_contracts_on_page', 0),
                'diversity_percent': result.get('contract_diversity_percent', 0),
                'max_spam_percent': result.get('max_contract_spam_percent', 0),
                'is_spam': result.get('is_spam_likely', False),
                'should_notify': should_notify,
                'quality_category': quality_category,
                'recommendation': result.get('recommendation', 'Нет данных'),
                'analysis': result.get('spam_analysis', 'Нет данных'),
                'adaptive_threshold': self._get_adaptive_threshold(result.get('total_tweets_on_page', 0)),
                'top_contracts': result.get('contracts_list', [])[:5]  # Топ-5 контрактов
            }
            
            self.results.append(evaluation)
            return evaluation
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа @{username}: {e}")
            error_result = {
                'username': username,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'quality_category': 'ERROR',
                'should_notify': False
            }
            self.results.append(error_result)
            return error_result
    
    def _get_adaptive_threshold(self, total_tweets):
        """Возвращает адаптивный порог для количества твитов"""
        if total_tweets < 10:
            return 50  # Мягкий порог для малых выборок
        elif total_tweets < 20:
            return 30  # Умеренный порог для средних выборок
        else:
            return 40  # Умеренный порог для больших выборок
    
    def _get_quality_category(self, result, should_notify):
        """Определяет категорию качества аккаунта"""
        if result.get('error'):
            return 'ERROR'
        
        diversity_percent = result.get('contract_diversity_percent', 0)
        total_tweets = result.get('total_tweets_on_page', 0)
        
        if not should_notify:
            return 'SPAM'
        
        if total_tweets == 0:
            return 'NO_DATA'
        
        if diversity_percent == 0:
            return 'NO_CONTRACTS'
        
        if diversity_percent < 10:
            return 'EXCELLENT'  # Очень низкое разнообразие = фокус на одном токене
        elif diversity_percent < 20:
            return 'GOOD'       # Низкое разнообразие = хорошее качество
        elif diversity_percent < 30:
            return 'AVERAGE'    # Среднее разнообразие
        else:
            return 'POOR'       # Высокое разнообразие = низкое качество
    
    async def evaluate_multiple_accounts(self, usernames, load_from_profile=True):
        """Оценивает несколько аккаунтов параллельно"""
        logger.info(f"🔍 Начинаем анализ {len(usernames)} аккаунтов")
        
        # Запускаем анализ параллельно
        tasks = [self.evaluate_single_account(username, load_from_profile) for username in usernames]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    def print_summary(self):
        """Выводит сводку результатов"""
        if not self.results:
            print("❌ Нет результатов для отображения")
            return
        
        print("\n" + "="*100)
        print("📊 СВОДКА РЕЗУЛЬТАТОВ ОЦЕНКИ TWITTER АККАУНТОВ")
        print("="*100)
        
        # Статистика по категориям
        categories = {}
        for result in self.results:
            category = result.get('quality_category', 'UNKNOWN')
            categories[category] = categories.get(category, 0) + 1
        
        print(f"\n📈 СТАТИСТИКА ПО КАТЕГОРИЯМ:")
        category_labels = {
            'EXCELLENT': '🟢 ОТЛИЧНЫЕ',
            'GOOD': '🔵 ХОРОШИЕ', 
            'AVERAGE': '🟡 СРЕДНИЕ',
            'POOR': '🟠 ПЛОХИЕ',
            'SPAM': '🔴 СПАМ',
            'NO_CONTRACTS': '⚪ БЕЗ КОНТРАКТОВ',
            'NO_DATA': '⚫ НЕТ ДАННЫХ',
            'ERROR': '❌ ОШИБКИ'
        }
        
        for category, count in sorted(categories.items()):
            label = category_labels.get(category, category)
            percentage = (count / len(self.results)) * 100
            print(f"   {label}: {count} ({percentage:.1f}%)")
        
        print(f"\n📋 ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ:")
        print("-" * 100)
        
        # Сортируем по качеству (лучшие сначала)
        quality_order = ['EXCELLENT', 'GOOD', 'AVERAGE', 'POOR', 'NO_CONTRACTS', 'NO_DATA', 'SPAM', 'ERROR']
        sorted_results = sorted(self.results, key=lambda x: quality_order.index(x.get('quality_category', 'ERROR')))
        
        for result in sorted_results:
            self._print_account_result(result)
    
    def _print_account_result(self, result):
        """Выводит результат для одного аккаунта"""
        username = result.get('username', 'Unknown')
        category = result.get('quality_category', 'UNKNOWN')
        
        # Эмодзи для категорий
        category_emoji = {
            'EXCELLENT': '🟢',
            'GOOD': '🔵', 
            'AVERAGE': '🟡',
            'POOR': '🟠',
            'SPAM': '🔴',
            'NO_CONTRACTS': '⚪',
            'NO_DATA': '⚫',
            'ERROR': '❌'
        }
        
        emoji = category_emoji.get(category, '❓')
        
        if result.get('error'):
            print(f"{emoji} @{username:20} | {category:12} | ОШИБКА: {result['error']}")
            return
        
        total_tweets = result.get('total_tweets', 0)
        unique_contracts = result.get('unique_contracts', 0)
        diversity = result.get('diversity_percent', 0)
        threshold = result.get('adaptive_threshold', 0)
        should_notify = result.get('should_notify', False)
        
        notify_status = "✅ РАЗРЕШЁН" if should_notify else "🚫 ЗАБЛОКИРОВАН"
        
        print(f"{emoji} @{username:20} | {category:12} | {total_tweets:3} твитов | {unique_contracts:3} контрактов | {diversity:5.1f}% | Порог: {threshold}% | {notify_status}")
        
        # Показываем топ-контракты для интересных случаев
        if category in ['EXCELLENT', 'GOOD'] and result.get('top_contracts'):
            contracts = result['top_contracts'][:3]  # Топ-3
            contract_info = ", ".join([f"{c['contract'][:8]}...({c['mentions']})" for c in contracts])
            print(f"   🔗 Топ-контракты: {contract_info}")
    
    def save_results(self, filename=None):
        """Сохраняет результаты в JSON файл"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"twitter_evaluation_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Результаты сохранены в {filename}")
            print(f"\n💾 Результаты сохранены в: {filename}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения результатов: {e}")
            print(f"❌ Ошибка сохранения: {e}")

async def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='Оценка качества Twitter аккаунтов')
    parser.add_argument('usernames', nargs='+', help='Список username аккаунтов для анализа (без @)')
    parser.add_argument('--no-profile', action='store_true', help='Не загружать профили (быстрый режим)')
    parser.add_argument('--save', type=str, help='Сохранить результаты в файл')
    parser.add_argument('--quiet', '-q', action='store_true', help='Тихий режим (только результаты)')
    
    args = parser.parse_args()
    
    if not args.quiet:
        print("🔍 АНАЛИЗАТОР КАЧЕСТВА TWITTER АККАУНТОВ")
        print("="*50)
        print(f"📋 Аккаунты для анализа: {', '.join('@' + u for u in args.usernames)}")
        print(f"⚡ Режим: {'Быстрый (без профилей)' if args.no_profile else 'Полный (с профилями)'}")
        print()
    
    # Создаём оценщик
    evaluator = TwitterAccountEvaluator()
    
    # Анализируем аккаунты
    load_profiles = not args.no_profile
    await evaluator.evaluate_multiple_accounts(args.usernames, load_from_profile=load_profiles)
    
    # Выводим результаты
    evaluator.print_summary()
    
    # Сохраняем если нужно
    if args.save:
        evaluator.save_results(args.save)
    elif len(args.usernames) > 1:  # Автосохранение для множественного анализа
        evaluator.save_results()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Анализ прерван пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1) 