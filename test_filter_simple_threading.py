#!/usr/bin/env python3
"""
Простая и надежная мультипоточная версия test_filter.py
Фокус на стабильности и производительности без сложной логики.
"""

import os
import re
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

# Thread-safe счетчики
class ThreadSafeCounters:
    def __init__(self):
        self._lock = threading.Lock()
        self.processed = 0
        self.successful = 0
        self.errors = 0
        self.would_send = 0
        self.would_reject = 0
        self.blacklisted = 0
        self.no_data = 0
        
    def increment_processed(self):
        with self._lock:
            self.processed += 1
    
    def increment_successful(self):
        with self._lock:
            self.successful += 1
    
    def increment_error(self):
        with self._lock:
            self.errors += 1
            
    def increment_would_send(self):
        with self._lock:
            self.would_send += 1
            
    def increment_would_reject(self):
        with self._lock:
            self.would_reject += 1
            
    def increment_blacklisted(self):
        with self._lock:
            self.blacklisted += 1
            
    def increment_no_data(self):
        with self._lock:
            self.no_data += 1
    
    def get_stats(self):
        with self._lock:
            return {
                'processed': self.processed,
                'successful': self.successful,
                'errors': self.errors,
                'would_send': self.would_send,
                'would_reject': self.would_reject,
                'blacklisted': self.blacklisted,
                'no_data': self.no_data
            }

# Глобальные счетчики
counters = ThreadSafeCounters()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleTokenAnalyzer:
    """Простой мультипоточный анализатор токенов"""
    
    def __init__(self, max_workers: int = None):
        cpu_count = multiprocessing.cpu_count()
        self.max_workers = max_workers or min(cpu_count * 2, 16)  # Не более 16 потоков для стабильности
        
        # Компилируем regex один раз
        self.regex_patterns = {
            'holders': re.compile(r'👥 Холдеры: (\d+)'),
            'mcap': re.compile(r'💰 Market Cap: \$([0-9,.]+)'),
            'liquidity': re.compile(r'💧 Ликвидность: \$([0-9,]+)'),
            'snipers': re.compile(r'🎯 Снайперы: ([0-9.]+)% \((\d+)\)'),
            'dev': re.compile(r'👨‍💼 Dev %: ([0-9.]+)%'),
            'insiders': re.compile(r'👨‍💼 Инсайдеры: ([0-9.]+)%'),
            'bundlers': re.compile(r'📦 Бандлеры: (\d+) \(([0-9.]+)%\)'),
            'notification': re.compile(r'📢 Отправлено уведомление|notification sent', re.IGNORECASE)
        }
        
        logger.info(f"🚀 Инициализирован простой мультипоточный анализатор:")
        logger.info(f"   • Потоков: {self.max_workers}")
        logger.info(f"   • CPU ядер: {cpu_count}")

    def analyze_single_token(self, log_path: str) -> Dict:
        """Анализирует один токен"""
        token_id = os.path.basename(log_path).replace('.log', '')
        thread_name = threading.current_thread().name
        
        try:
            counters.increment_processed()
            
            # Собираем метрики из файла
            metrics = self.extract_metrics_from_log(log_path)
            
            if not metrics:
                counters.increment_no_data()
                return {
                    'token_id': token_id,
                    'decision': 'NO_DATA',
                    'reason': 'Недостаточно данных',
                    'thread': thread_name
                }
            
            # Простая логика фильтрации (основные критерии)
            decision_result = self.make_decision(metrics, token_id)
            decision_result['thread'] = thread_name
            
            # Обновляем счетчики
            decision = decision_result.get('decision')
            if decision == 'WOULD_SEND':
                counters.increment_would_send()
            elif decision == 'WOULD_REJECT':
                counters.increment_would_reject()
            elif decision == 'BLACKLISTED':
                counters.increment_blacklisted()
            else:
                counters.increment_no_data()
                
            counters.increment_successful()
            return decision_result
            
        except Exception as e:
            counters.increment_error()
            logger.error(f"💥 [{thread_name}] Ошибка для {token_id}: {e}")
            return {
                'token_id': token_id,
                'decision': 'ERROR',
                'reason': f'Ошибка анализа: {str(e)}',
                'thread': thread_name
            }

    def extract_metrics_from_log(self, log_path: str) -> Optional[Dict]:
        """Извлекает метрики из лог-файла"""
        metrics = {}
        
        try:
            with open(log_path, 'r', encoding='utf-8', buffering=8192) as f:
                for line in f:
                    # Ранний выход если найдено уведомление
                    if self.regex_patterns['notification'].search(line):
                        break
                    
                    # Ищем метрики
                    if '👥 Холдеры:' in line:
                        match = self.regex_patterns['holders'].search(line)
                        if match:
                            metrics['holders'] = int(match.group(1))
                    
                    elif '💰 Market Cap:' in line:
                        match = self.regex_patterns['mcap'].search(line)
                        if match:
                            try:
                                mcap_str = match.group(1).replace(',', '')
                                metrics['market_cap'] = float(mcap_str)
                            except ValueError:
                                pass
                    
                    elif '💧 Ликвидность:' in line:
                        match = self.regex_patterns['liquidity'].search(line)
                        if match:
                            try:
                                liquidity_str = match.group(1).replace(',', '')
                                metrics['liquidity'] = float(liquidity_str)
                            except ValueError:
                                pass
                    
                    elif '🎯 Снайперы:' in line:
                        match = self.regex_patterns['snipers'].search(line)
                        if match:
                            try:
                                metrics['snipers_percent'] = float(match.group(1))
                                metrics['snipers_count'] = int(match.group(2))
                            except ValueError:
                                pass
                    
                    elif '👨‍💼 Dev %:' in line:
                        match = self.regex_patterns['dev'].search(line)
                        if match:
                            try:
                                metrics['dev_percent'] = float(match.group(1))
                            except ValueError:
                                pass
                    
                    elif '👨‍💼 Инсайдеры:' in line:
                        match = self.regex_patterns['insiders'].search(line)
                        if match:
                            try:
                                metrics['insiders_percent'] = float(match.group(1))
                            except ValueError:
                                pass
                    
                    elif '📦 Бандлеры:' in line:
                        match = self.regex_patterns['bundlers'].search(line)
                        if match:
                            try:
                                metrics['bundlers_count'] = int(match.group(1))
                                metrics['bundlers_percent'] = float(match.group(2))
                            except ValueError:
                                pass
        
        except Exception as e:
            logger.debug(f"Ошибка чтения {log_path}: {e}")
            return None
        
        return metrics if metrics else None

    def make_decision(self, metrics: Dict, token_id: str) -> Dict:
        """Принимает решение на основе метрик"""
        
        # Базовые значения
        holders = metrics.get('holders', 0)
        liquidity = metrics.get('liquidity', 0)
        dev_percent = metrics.get('dev_percent', 0)
        snipers_percent = metrics.get('snipers_percent', 0)
        snipers_count = metrics.get('snipers_count', 0)
        insiders_percent = metrics.get('insiders_percent', 0)
        market_cap = metrics.get('market_cap', 0)
        
        # Простые критерии для ACTIVITY уведомлений
        reasons = []
        
        # Проверка холдеров
        if holders < 30:
            reasons.append(f"Мало холдеров ({holders} < 30)")
        elif holders > 130:
            reasons.append(f"Много холдеров ({holders} > 130)")
        
        # Проверка ликвидности
        if liquidity < 10000:
            reasons.append(f"Мала ликвидность (${liquidity:,.0f} < $10,000)")
        
        # Проверка dev процента
        if dev_percent > 2:
            reasons.append(f"Высокий dev процент ({dev_percent:.1f}% > 2%)")
        
        # Проверка снайперов
        if snipers_count > 20:
            reasons.append(f"Много снайперов ({snipers_count} > 20)")
        elif snipers_percent > 5.0:
            reasons.append(f"Высокий процент снайперов ({snipers_percent:.1f}% > 5%)")
        
        # Проверка инсайдеров
        if insiders_percent > 22.0:
            reasons.append(f"Высокий процент инсайдеров ({insiders_percent:.1f}% > 22%)")
        
        # Формируем результат
        result = {
            'token_id': token_id,
            'holders': holders,
            'market_cap': market_cap,
            'liquidity': liquidity,
            'dev_percent': dev_percent,
            'snipers_percent': snipers_percent,
            'snipers_count': snipers_count,
            'insiders_percent': insiders_percent
        }
        
        if reasons:
            result.update({
                'decision': 'WOULD_REJECT',
                'reason': '; '.join(reasons[:2]),  # Первые 2 причины
                'notification_type': 'ACTIVITY'
            })
        else:
            result.update({
                'decision': 'WOULD_SEND',
                'reason': 'Соответствует всем критериям activity уведомления',
                'notification_type': 'ACTIVITY'
            })
        
        return result

    def analyze_all_tokens(self, tokens_logs_dir: str) -> List[Dict]:
        """Мультипоточный анализ всех токенов"""
        if not os.path.exists(tokens_logs_dir):
            logger.error(f"❌ Директория {tokens_logs_dir} не найдена")
            return []
        
        log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
        
        if not log_files:
            logger.error(f"❌ В директории {tokens_logs_dir} нет .log файлов")
            return []
        
        log_paths = [os.path.join(tokens_logs_dir, f) for f in log_files]
        
        logger.info(f"🚀 ПРОСТОЙ МУЛЬТИПОТОЧНЫЙ АНАЛИЗ: {len(log_paths)} токенов")
        logger.info(f"⚡ Используем {self.max_workers} потоков")
        
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="token") as executor:
            # Отправляем задачи
            future_to_path = {executor.submit(self.analyze_single_token, path): path for path in log_paths}
            
            # Собираем результаты
            completed_count = 0
            for future in as_completed(future_to_path):
                try:
                    result = future.result(timeout=120)  # 2 минуты на токен
                    results.append(result)
                    completed_count += 1
                    
                    # Прогресс каждые 25 токенов
                    if completed_count % 25 == 0:
                        elapsed = time.time() - start_time
                        speed = completed_count / elapsed if elapsed > 0 else 0
                        eta = (len(log_paths) - completed_count) / speed if speed > 0 else 0
                        
                        stats = counters.get_stats()
                        logger.info(f"⚡ Прогресс: {completed_count}/{len(log_paths)} "
                                  f"({speed:.1f} ток/сек, ETA: {eta/60:.1f} мин) "
                                  f"[✅{stats['successful']} ❌{stats['errors']}]")
                        
                except Exception as e:
                    path = future_to_path[future]
                    token_id = os.path.basename(path).replace('.log', '')
                    logger.error(f"💥 Timeout/ошибка для {token_id}: {e}")
                    
                    error_result = {
                        'token_id': token_id,
                        'decision': 'ERROR',
                        'reason': f'Timeout: {str(e)}'
                    }
                    results.append(error_result)
                    counters.increment_error()
                    completed_count += 1
        
        total_time = time.time() - start_time
        final_speed = len(results) / total_time if total_time > 0 else 0
        
        logger.info(f"🎯 ПРОСТОЙ МУЛЬТИПОТОЧНЫЙ АНАЛИЗ ЗАВЕРШЕН!")
        logger.info(f"⏱️ Время: {total_time:.1f} сек")
        logger.info(f"⚡ Скорость: {final_speed:.1f} токенов/сек")
        
        return results

def main():
    """Основная функция"""
    analyzer = SimpleTokenAnalyzer()
    
    logger.info("🚀 ПРОСТОЙ МУЛЬТИПОТОЧНЫЙ АНАЛИЗ ACTIVITY УВЕДОМЛЕНИЙ")
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    start_time = time.time()
    
    # Анализируем все токены
    results = analyzer.analyze_all_tokens(tokens_logs_dir)
    
    if not results:
        logger.error("❌ Нет результатов для анализа")
        return
    
    # Статистика
    stats = counters.get_stats()
    total_time = time.time() - start_time
    final_speed = len(results) / total_time if total_time > 0 else 0
    
    logger.info(f"\n📊 СТАТИСТИКА - {len(results)} токенов:")
    logger.info(f"🚀 WOULD_SEND: {stats['would_send']} ({stats['would_send']/len(results)*100:.1f}%)")
    logger.info(f"❌ WOULD_REJECT: {stats['would_reject']} ({stats['would_reject']/len(results)*100:.1f}%)")
    logger.info(f"⚫ BLACKLISTED: {stats['blacklisted']} ({stats['blacklisted']/len(results)*100:.1f}%)")
    logger.info(f"💥 ERRORS: {stats['errors']} ({stats['errors']/len(results)*100:.1f}%)")
    logger.info(f"📊 NO_DATA: {stats['no_data']} ({stats['no_data']/len(results)*100:.1f}%)")
    
    logger.info(f"\n⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:")
    logger.info(f"   • Время: {total_time:.1f} сек")
    logger.info(f"   • Скорость: {final_speed:.1f} токенов/сек")
    logger.info(f"   • Успешных: {stats['successful']}")
    logger.info(f"   • Ошибок: {stats['errors']}")
    
    # Показываем примеры прошедших токенов
    passed_tokens = [r for r in results if r.get('decision') == 'WOULD_SEND']
    if passed_tokens:
        logger.info(f"\n🚀 ПРИМЕРЫ ПРОШЕДШИХ ТОКЕНОВ:")
        for example in passed_tokens[:5]:
            logger.info(f"   • {example['token_id']}: "
                       f"HOLDERS={example.get('holders', '?')}, "
                       f"LIQ=${example.get('liquidity', 0):,.0f}, "
                       f"SNIPERS={example.get('snipers_percent', 0):.1f}%")
    
    # Показываем причины отклонения
    rejected_tokens = [r for r in results if r.get('decision') == 'WOULD_REJECT']
    if rejected_tokens:
        logger.info(f"\n❌ ПРИМЕРЫ ОТКЛОНЕННЫХ ТОКЕНОВ:")
        for example in rejected_tokens[:5]:
            logger.info(f"   • {example['token_id']}: {example.get('reason', 'Неизвестная причина')}")

if __name__ == "__main__":
    main()
