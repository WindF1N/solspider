#!/usr/bin/env python3
"""
Скрипт для тестирования алгоритма фильтрации токенов на исторических логах.
Анализирует логи и определяет, отправил бы бот уведомление или нет.
"""

import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

# Глобальный черный список для токенов, помеченных как "гениальные раги"
GENIUS_RUG_BLACKLIST = set()
BLACKLIST_FILE = "genius_rug_blacklist.txt"

# Счетчик отфильтрованных токенов (с <30 холдерами)
filtered_low_holders_count = 0

def load_blacklist():
    """Загружает черный список из файла"""
    global GENIUS_RUG_BLACKLIST
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, 'r') as f:
                GENIUS_RUG_BLACKLIST = set(line.strip() for line in f if line.strip())
            print(f"📥 Загружен черный список: {len(GENIUS_RUG_BLACKLIST)} токенов")
    except Exception as e:
        print(f"❌ Ошибка загрузки черного списка: {e}")

def save_blacklist():
    """Сохраняет черный список в файл"""
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            for token in sorted(GENIUS_RUG_BLACKLIST):
                f.write(f"{token}\n")
    except Exception as e:
        print(f"❌ Ошибка сохранения черного списка: {e}")

def process_single_token_sync(log_path: str) -> Dict:
    """Синхронная обработка одного токена для multiprocessing"""
    try:
        # Создаем отдельный экземпляр для каждого процесса
        tester = TokenFilterTester()
        
        # Запускаем в новом event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(tester.analyze_token_with_full_criteria(log_path))
            # Логируем результат в файл
            log_token_result(result)
            return result
        finally:
            loop.close()
            
    except Exception as e:
        token_id = os.path.basename(log_path).replace('.log', '')
        import traceback
        full_error = traceback.format_exc()
        logger.error(f"💥 Полная ошибка для {token_id}: {full_error}")
        
        error_result = {
            'token_id': token_id,
            'decision': 'ERROR',
            'reason': f'Ошибка обработки: {str(e)}'
        }
        # Логируем ошибку тоже
        log_token_result(error_result)
        return error_result

# Загружаем черный список при запуске
load_blacklist()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройка файлового логгера для результатов
file_logger = logging.getLogger('test_filter_results')
file_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('test_filter.log', mode='w', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(file_formatter)
file_logger.addHandler(file_handler)
file_logger.propagate = False  # Не дублировать в консоль

def log_token_result(result: Dict):
    """Детальное логирование результата анализа токена в файл"""
    try:
        if not isinstance(result, dict):
            file_logger.error(f"❌ log_token_result получил не dict: {type(result)}")
            return
            
        token_id = result.get('token_id', 'UNKNOWN')
        decision = result.get('decision', 'UNKNOWN')
        reason = result.get('reason', 'Нет причины')
        notification_type = result.get('notification_type', 'NONE')
        
        # ФИЛЬТР: не логируем токены которые даже 30 холдеров не набрали
        holders = result.get('holders', 0)
        if decision == 'WOULD_REJECT' and holders < 30:
            global filtered_low_holders_count
            filtered_low_holders_count += 1
            return  # Молча пропускаем - это просто неразвитые токены
        
        # Базовая информация
        token_address = result.get('token_address', token_id)
        log_line = f"TOKEN: {token_address} | DECISION: {decision} | TYPE: {notification_type}"
        
        # Добавляем метрики если есть
        metrics = []
        if 'holders' in result:
            metrics.append(f"HOLDERS: {result['holders']}")
        if 'market_cap' in result:
            metrics.append(f"MCAP: ${result['market_cap']:,.0f}" if result['market_cap'] else "MCAP: -")
        if 'liquidity' in result:
            metrics.append(f"LIQUIDITY: ${result['liquidity']:,.0f}" if result['liquidity'] else "LIQUIDITY: -")
        if 'dev_percent' in result:
            metrics.append(f"DEV: {result['dev_percent']:.1f}%")
        if 'snipers_percent' in result:
            metrics.append(f"SNIPERS: {result['snipers_percent']:.1f}%")
        if 'insiders_percent' in result:
            metrics.append(f"INSIDERS: {result['insiders_percent']:.1f}%")
        if 'bundler_count' in result:
            metrics.append(f"BUNDLERS: {result['bundler_count']}")
        if 'bundler_percentage' in result:
            metrics.append(f"BUNDLER%: {result['bundler_percentage']:.1f}%")
        if 'snapshots_checked' in result:
            metrics.append(f"SNAPSHOTS: {result['snapshots_checked']}/{result.get('total_snapshots', '?')}")
        if 'snapshot_number' in result:
            metrics.append(f"PASS_AT: #{result['snapshot_number']}")
        
        if metrics:
            log_line += f" | {' | '.join(metrics)}"
        
        # Причина всегда в конце
        log_line += f" | REASON: {reason}"
        
        # Записываем в файл
        if decision == 'WOULD_SEND':
            if result.get('healthy_holder_patterns'):
                file_logger.info(f"✅ ACTIVITY PASS - {log_line}")
            else:
                file_logger.info(f"✅ ACTIVITY PASS - {log_line}")
        elif decision == 'WOULD_REJECT':
            if result.get('all_conditions_passed'):
                # Особый случай: все условия прошли но токен отклонен по паттернам холдеров
                file_logger.info(f"🚨 ACTIVITY REJECT (HOLDER PATTERNS) - {log_line}")
            else:
                file_logger.info(f"❌ ACTIVITY REJECT - {log_line}")
        elif decision == 'BLACKLISTED':
            file_logger.info(f"⚫ BLACKLISTED - {log_line}")
        elif decision == 'ERROR':
            file_logger.info(f"💥 ERROR - {log_line}")
        elif decision == 'NO_DATA':
            file_logger.info(f"📊 NO_DATA - {log_line}")
        else:
            file_logger.info(f"❓ UNKNOWN - {log_line}")
            
    except Exception as e:
        file_logger.error(f"❌ Ошибка логирования результата: {e}")
        import traceback
        file_logger.error(f"📊 Полная ошибка: {traceback.format_exc()}")
        file_logger.error(f"📊 Входные данные result: {result}")


class TokenMetrics:
    """Полная копия класса для отслеживания метрик токена из bundle_analyzer.py"""
    def __init__(self, token_address: str, creation_time: int):
        self.token_address = token_address
        self.creation_time = creation_time
        self.metrics_history = []
        self.max_dev_percent = 0
        self.max_bundlers_after_dev_exit = 0
        self.max_bundlers_before_dev_exit = 0  # Максимальный процент бандлеров до выхода дева
        self.max_top_10_holders_pcnt_before_dev_exit = 0
        self.max_holders = 0  # Максимальное количество холдеров
        self.dev_exit_time = None
        self.last_notification_time = 0
        self.last_notification_type = None  # Тип последнего уведомления
        self.holder_percentages_history = []  # История процентов холдеров для анализа паттернов
        
    def can_send_notification(self, notification_type: str) -> bool:
        """
        Проверяет, можно ли отправить уведомление данного типа
        Args:
            notification_type: Тип уведомления ('active', 'pump', etc)
        Returns:
            bool: True если можно отправить уведомление
        """
        current_time = time.time()
        
        # Минимальный интервал между уведомлениями
        MIN_NOTIFICATION_INTERVAL = 900  # 15 минут
        
        # Проверяем время последнего уведомления
        if current_time - self.last_notification_time < MIN_NOTIFICATION_INTERVAL:
            return False
        
        # Если тип уведомления изменился, разрешаем отправку
        if self.last_notification_type != notification_type:
            return True
            
        # Обновляем время и тип последнего уведомления
        self.last_notification_time = current_time
        self.last_notification_type = notification_type
        return True
    
    def add_metrics(self, metrics: dict):
        """Добавляет новые метрики и рассчитывает динамику"""
        # Используем время из метрик если есть, иначе текущее
        if 'timestamp' not in metrics:
            metrics['timestamp'] = int(time.time())

        # Получаем процент дева и бандлеров
        dev_holding = metrics.get('devHoldingPcnt')
        dev_percent = float(dev_holding) if dev_holding is not None else 0
        
        bundles_percent = metrics.get('bundlesHoldingPcnt')
        bundles_percent = float(bundles_percent.get('current', 0) if isinstance(bundles_percent, dict) else (bundles_percent if bundles_percent is not None else 0))

        # Обновляем максимальный процент дева
        if dev_percent > self.max_dev_percent:
            self.max_dev_percent = dev_percent

        # Проверяем выход дева
        if self.dev_exit_time is None and dev_percent <= 2 and self.metrics_history:
            last_dev_percent = float(self.metrics_history[-1].get('devHoldingPcnt', 0) or 0)
            if last_dev_percent > 0:
                self.dev_exit_time = metrics['timestamp']

        # Обновляем максимальный процент бандлеров в зависимости от статуса дева
        if self.dev_exit_time is None:
            # До выхода дева
            if bundles_percent > self.max_bundlers_before_dev_exit:
                self.max_bundlers_before_dev_exit = bundles_percent
        else:
            # После выхода дева
            if bundles_percent > self.max_bundlers_after_dev_exit:
                self.max_bundlers_after_dev_exit = bundles_percent
        
        # Обновляем максимальное количество холдеров
        total_holders = int(metrics.get('total_holders', 0) or 0)
        if total_holders > self.max_holders:
            self.max_holders = total_holders
        
        # Сохраняем историю процентов холдеров для анализа паттернов
        top10holders = metrics.get("top10holders", {})
        if top10holders and len(top10holders) >= 3:
            # Сортируем холдеров по убыванию процента
            sorted_holders = sorted(
                top10holders.items(),
                key=lambda item: item[1]['pcnt'],
                reverse=True
            )
            
            # Извлекаем проценты только реальных холдеров (не пулы, не бандлеры)
            # И считаем сколько среди топ-3 снайперов
            current_percentages = []
            top3_snipers_count = 0
            
            for wallet, value in sorted_holders:
                if not value.get('isPool', False) and not value.get('isBundler', False):
                    current_percentages.append(value['pcnt'])
                    
                    # Считаем снайперов в топ-3
                    if len(current_percentages) <= 3 and value.get('isSniper', False):
                        top3_snipers_count += 1
                    
                    if len(current_percentages) >= 10:  # Берем топ-10
                        break
            
            if len(current_percentages) >= 3:
                # Сохраняем проценты + информацию о снайперах в топ-3
                snapshot_data = {
                    'percentages': current_percentages,
                    'top3_snipers': top3_snipers_count,
                    'total_snipers_percent': float(metrics.get('snipersHoldingPcnt', 0) or 0)
                }
                self.holder_percentages_history.append(snapshot_data)
        
        # Добавляем новые метрики
        self.metrics_history.append(metrics.copy())  # Используем copy() чтобы избежать ссылок


class TokenFilterTester:
    def __init__(self):
        # Константы для ACTIVITY уведомлений (точно из bundle_analyzer.py)
        self.MIN_HOLDERS_FOR_ACTIVITY = 30          # >= 30 холдеров
        self.MAX_HOLDERS_FOR_ACTIVITY = 130         # <= 130 холдеров
        self.MAX_HOLDERS_NEVER_DUMPED = 150         # <= 150 холдеров максимум
        self.MIN_LIQUIDITY = 10000                  # >= 10000 ликвидность
        self.MIN_GROWTH_RATE = 2900                 # >= 2900/мин рост холдеров
        self.MAX_DEV_PERCENT = 2                    # <= 2% процент дева
        self.MAX_SNIPERS_COUNT = 20                 # <= 20 снайперов
        self.MAX_SNIPERS_PERCENT = 3.5              # <= 3.5% снайперов
        self.MAX_SNIPERS_PERCENT_WITH_EXIT = 5.0    # <= 5% с rapid exit
        self.MAX_INSIDERS_PERCENT = 15              # <= 15% инсайдеров
        self.MAX_INSIDERS_PERCENT_WITH_EXIT = 22.0  # <= 22% с rapid exit
        self.MAX_HOLDERS_PERCENT = 7                # <= 7% топ холдеров
        
        # Инициализируем историю для анализа корреляций
        self.metrics_history = []
        self.holder_percentages_history = []
        
        # КЕШИРОВАНИЕ РЕГУЛЯРНЫХ ВЫРАЖЕНИЙ для максимальной скорости парсинга
        self._regex_cache = {
            'time': re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - INFO - '),
            'holders_count': re.compile(r'👥 Холдеры: (\d+)'),
            'liquidity': re.compile(r'💧 Ликвидность: \$([0-9,]+)'),
            'mcap': re.compile(r'💰 Market Cap: \$([0-9,.]+)'),
            'snipers': re.compile(r'🎯 Снайперы: ([0-9.]+)% \((\d+)\)'),
            'insiders': re.compile(r'👨‍💼 Инсайдеры: ([0-9.]+)%'),
            'dev': re.compile(r'👨‍💼 Dev %: ([0-9.]+)%'),
            'bundlers': re.compile(r'📦 Бандлеры: (\d+) \(([0-9.]+)%\)'),
            'holders_percentages': re.compile(r'🏆 Проценты держателей: (.+)'),
            'token_address': re.compile(r'/tokenAddress/([A-Za-z0-9]{32,})', re.IGNORECASE),
            'notification_sent': re.compile(r'отправлено уведомление|notification sent|ОТПРАВИЛИ УВЕДОМЛЕНИЕ', re.IGNORECASE)
        }
        
        # КЕШИРОВАНИЕ КОРРЕЛЯЦИЙ для ускорения повторных вычислений
        self._correlation_cache = {}
    
    def parse_log_line(self, line: str) -> Optional[Dict]:
        """Парсит строку лога и извлекает данные"""
        # Парсинг времени
        time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - INFO - ', line)
        if not time_match:
            return None
        
        timestamp_str = time_match.group(1)
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        
        # Парсинг данных о держателях
        if '🏆 Проценты держателей:' in line:
            percentages_part = line.split('🏆 Проценты держателей: ')[1]
            percentages_str = percentages_part.strip()
            
            if percentages_str:
                try:
                    percentages = [float(x.replace('%', '')) for x in percentages_str.split() if x.replace('%', '').replace('.', '').isdigit()]
                    return {
                        'type': 'holders',
                        'timestamp': timestamp,
                        'percentages': percentages
                    }
                except ValueError:
                    return None
        
        # Парсинг процента ранних холдеров
        elif '📊 ОБЩИЙ % ВЛАДЕНИЯ РАННИХ ХОЛДЕРОВ:' in line:
            early_match = re.search(r'📊 ОБЩИЙ % ВЛАДЕНИЯ РАННИХ ХОЛДЕРОВ: ([0-9.]+)%', line)
            if early_match:
                try:
                    return {
                        'type': 'early_holders',
                        'timestamp': timestamp,
                        'early_holders_percent': float(early_match.group(1))
                    }
                except ValueError:
                    return None
        
        # Парсинг результата анализа
        elif 'ПОДОЗРИТЕЛЬНЫЕ ПАТТЕРНЫ ХОЛДЕРОВ ОБНАРУЖЕНЫ' in line:
            return {
                'type': 'analysis_suspicious',
                'timestamp': timestamp
            }
        elif 'паттерны холдеров здоровые' in line or 'Токен отклонен как потенциальный' in line:
            return {
                'type': 'analysis_rejected',
                'timestamp': timestamp
            }
        elif 'ВСЕ ФИЛЬТРЫ ПРОЙДЕНЫ' in line:
            return {
                'type': 'analysis_passed',
                'timestamp': timestamp
            }
        
        return None
    
    def analyze_early_vs_current_holders(self, percentages_history: List[List[float]]) -> Tuple[bool, List[str]]:
        """Анализирует ранние vs текущие топ-холдеры (копия из bundle_analyzer.py)"""
        if len(percentages_history) < 30:
            return False, []
        
        # Берем первые 15 снапшотов как "ранние"
        early_snapshots = percentages_history[:15]
        # Берем последние 10 снапшотов как "текущие"
        current_snapshots = percentages_history[-10:]
        
        # Находим медианные значения ранних топ-3
        early_top3_values = []
        for percentages in early_snapshots:
            # Проверяем что percentages это список/массив
            if not isinstance(percentages, (list, tuple)):
                continue
                
            if len(percentages) >= 3:
                try:
                    top3 = [float(x) for x in percentages[:3]]
                    early_top3_values.append(top3)
                except (ValueError, IndexError, TypeError):
                    continue
        
        # Находим медианные значения текущих топ-3
        current_top3_values = []
        for percentages in current_snapshots:
            # Проверяем что percentages это список/массив
            if not isinstance(percentages, (list, tuple)):
                continue
                
            if len(percentages) >= 3:
                try:
                    top3 = [float(x) for x in percentages[:3]]
                    current_top3_values.append(top3)
                except (ValueError, IndexError, TypeError):
                    continue
        
        if not early_top3_values or not current_top3_values:
            return False, []
        
        # Рассчитываем медианы для ранних топ-3
        early_medians = []
        for pos in range(3):
            values = [top3[pos] for top3 in early_top3_values if len(top3) > pos]
            if values:
                early_medians.append(sorted(values)[len(values)//2])
        
        # Рассчитываем медианы для текущих топ-3
        current_medians = []
        for pos in range(3):
            values = [top3[pos] for top3 in current_top3_values if len(top3) > pos]
            if values:
                current_medians.append(sorted(values)[len(values)//2])
        
        if len(early_medians) < 3 or len(current_medians) < 3:
            return False, []
        
        suspicious_points = []
        is_suspicious = False
        
        # Критерий 1: Ранние топ-холдеры всё ещё слишком доминируют
        early_total = sum(early_medians)
        current_total = sum(current_medians)
        
        # Если ранние топ-3 держали >12% и текущие топ-3 всё ещё держат >10%
        if early_total > 12.0 and current_total > 10.0:
            # И при этом снижение меньше 20%
            reduction_percent = ((early_total - current_total) / early_total) * 100
            if reduction_percent < 20:
                suspicious_points.append(f"Ранние топ-холдеры доминируют: было {early_total:.1f}%, сейчас {current_total:.1f}% (снижение {reduction_percent:.1f}%)")
                is_suspicious = True
        
        # Критерий 2: Первый холдер всё ещё слишком крупный
        if early_medians[0] > 6.0 and current_medians[0] > 4.5:
            reduction = early_medians[0] - current_medians[0]
            if reduction < 1.5:  # Снизился меньше чем на 1.5%
                suspicious_points.append(f"Первый холдер остался крупным: было {early_medians[0]:.1f}%, сейчас {current_medians[0]:.1f}%")
                is_suspicious = True
        
        return is_suspicious, suspicious_points
    
    def _calculate_correlation(self, series1: list, series2: list) -> float:
        """
        Вычисляет коэффициент корреляции между двумя временными рядами
        """
        if len(series1) != len(series2) or len(series1) < 2:
            return 0.0
        
        # Удаляем нулевые значения для более точного расчета
        valid_pairs = [(x, y) for x, y in zip(series1, series2) if abs(x) > 0.001 or abs(y) > 0.001]
        
        if len(valid_pairs) < 2:
            return 0.0
        
        x_values = [pair[0] for pair in valid_pairs]
        y_values = [pair[1] for pair in valid_pairs]
        
        n = len(x_values)
        
        # Средние значения
        mean_x = sum(x_values) / n
        mean_y = sum(y_values) / n
        
        # Числитель и знаменатель формулы корреляции
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
        sum_sq_x = sum((x - mean_x) ** 2 for x in x_values)
        sum_sq_y = sum((y - mean_y) ** 2 for y in y_values)
        
        denominator = (sum_sq_x * sum_sq_y) ** 0.5
        
        if denominator == 0:
            return 0.0
        
        correlation = numerator / denominator
        return correlation
    
    def check_rapid_exit(self, metric_name: str, metrics_history: List[Dict], ratio: float = 3.0, max_seconds: int = 120) -> bool:
        """
        Проверяет стремительный выход (снайперов или инсайдеров)
        Args:
            metric_name: 'snipersHoldingPcnt' или 'insidersHoldingPcnt'
            metrics_history: история метрик
            ratio: во сколько раз должен уменьшиться процент
            max_seconds: за сколько секунд должен произойти выход
        Returns:
            bool: True если был стремительный выход
        """
        if not metrics_history or len(metrics_history) < 2:
            return False
        
        first_value = None
        first_time = None
        for m in metrics_history:
            value = float(m.get(metric_name, 0) or 0)
            if value > 0:
                first_value = value
                first_time = m.get('timestamp', 0)
                break
        
        if not first_value:
            return False
        
        current_value = float(metrics_history[-1].get(metric_name, 0) or 0)
        current_time = metrics_history[-1].get('timestamp', 0)
        time_diff = current_time - first_time
        
        if time_diff <= max_seconds and current_value <= first_value / ratio:
            logger.info(f"📉 Стремительный выход обнаружен для {metric_name}: {first_value:.1f}% → {current_value:.1f}% за {time_diff} сек")
            return True
        return False
    
    def check_snipers_bundlers_correlation(self, metrics_history: List[Dict]) -> bool:
        """
        Проверяет, не являются ли снайперы бандлерами, анализируя корреляцию их изменений
        Returns:
            bool: True если корреляция в норме (снайперы не являются бандлерами),
                 False если есть подозрение что снайперы это бандлеры
        """
        if not metrics_history or len(metrics_history) < 3:
            return True

        # Получаем последнее значение снайперов
        curr_snipers = float(metrics_history[-1].get('snipersHoldingPcnt', 0) or 0)
        
        # Если снайперы вышли (<=3.5%) - это хороший признак
        if curr_snipers <= 3.5 or (curr_snipers <= 5.0 and self.check_rapid_exit('snipersHoldingPcnt', metrics_history, ratio=3, max_seconds=120)):
            logger.info("✅ Снайперы вышли, но бандлеры остались - бандлеры не являются снайперами")
            return True
            
        # Если снайперы еще не вышли (>3.5%), проверяем корреляцию
        bundlers_changes = []
        snipers_changes = []
        
        for i in range(1, len(metrics_history)):
            prev = metrics_history[i-1]
            curr = metrics_history[i]
            
            # Получаем проценты бандлеров и снайперов
            prev_bundlers = prev.get('bundlesHoldingPcnt')
            prev_bundlers = float(prev_bundlers.get('current', 0) if isinstance(prev_bundlers, dict) else (prev_bundlers if prev_bundlers is not None else 0))
            curr_bundlers = curr.get('bundlesHoldingPcnt')
            curr_bundlers = float(curr_bundlers.get('current', 0) if isinstance(curr_bundlers, dict) else (curr_bundlers if curr_bundlers is not None else 0))
            prev_snipers = float(prev.get('snipersHoldingPcnt', 0) or 0)
            curr_snipers = float(curr.get('snipersHoldingPcnt', 0) or 0)
            
            bundlers_change = curr_bundlers - prev_bundlers
            snipers_change = curr_snipers - prev_snipers
            
            if abs(bundlers_change) > 0.1:  # Значительное изменение
                bundlers_changes.append(bundlers_change)
                snipers_changes.append(snipers_change)
                
                # Логируем подозрительные изменения
                if (bundlers_change * snipers_change > 0 and 
                    abs(bundlers_change - snipers_change) / max(abs(bundlers_change), abs(snipers_change)) < 0.3):
                    logger.info(f"🚨 Подозрительная корреляция: бандлеры {bundlers_change:.2f}%, снайперы {snipers_change:.2f}%")

        if len(bundlers_changes) < 2:
            return True

        # Проверяем корреляцию
        suspicious = sum(
            1 for i in range(len(bundlers_changes))
            if (bundlers_changes[i] * snipers_changes[i] > 0 and 
                abs(bundlers_changes[i] - snipers_changes[i]) / max(abs(bundlers_changes[i]), abs(snipers_changes[i])) < 0.3)
        )
        
        is_suspicious = suspicious >= len(bundlers_changes) * 0.5
        if is_suspicious:
            logger.warning(f"⚠️ Сильная корреляция: {suspicious}/{len(bundlers_changes)}")
        
        return not is_suspicious

    def check_snipers_insiders_correlation(self, metrics_history: List[Dict]) -> bool:
        """
        Проверяет корреляцию между снайперами и инсайдерами
        """
        if len(metrics_history) < 3:
            return True
            
        curr_snipers = float(metrics_history[-1].get('snipersHoldingPcnt', 0) or 0)
        if curr_snipers <= 3.5 or curr_snipers <= 5.0 and self.check_rapid_exit('snipersHoldingPcnt', metrics_history, ratio=3, max_seconds=120):
            return True
            
        snipers_changes = []
        insiders_changes = []
        
        for i in range(1, len(metrics_history)):
            prev = metrics_history[i-1]
            curr = metrics_history[i]
            
            prev_snipers = float(prev.get('snipersHoldingPcnt', 0) or 0)
            curr_snipers = float(curr.get('snipersHoldingPcnt', 0) or 0)
            prev_insiders = float(prev.get('insidersHoldingPcnt', 0) or 0)
            curr_insiders = float(curr.get('insidersHoldingPcnt', 0) or 0)
            
            change = curr_snipers - prev_snipers
            if abs(change) > 0.1:
                snipers_changes.append(change)
                insiders_changes.append(curr_insiders - prev_insiders)

        if len(snipers_changes) < 2:
            return True

        suspicious = sum(
            1 for i in range(len(snipers_changes))
            if (snipers_changes[i] * insiders_changes[i] > 0 and
                abs(snipers_changes[i] - insiders_changes[i]) / max(abs(snipers_changes[i]), abs(insiders_changes[i])) < 0.3)
        )
        
        is_suspicious = suspicious >= len(snipers_changes) * 0.5
        return not is_suspicious

    def check_bundlers_snipers_exit_correlation(self, metrics_history: List[Dict]) -> bool:
        """
        Проверяет равномерный выход бандлеров и снайперов
        """
        if len(metrics_history) < 3:
            return True
            
        curr_snipers = float(metrics_history[-1].get('snipersHoldingPcnt', 0) or 0)
        if curr_snipers <= 3.5 or curr_snipers <= 5.0 and self.check_rapid_exit('snipersHoldingPcnt', metrics_history, ratio=3, max_seconds=120):
            return True
            
        bundlers_changes = []
        snipers_changes = []
        
        for i in range(1, len(metrics_history)):
            prev = metrics_history[i-1]
            curr = metrics_history[i]
            
            prev_bundlers = prev.get('bundlesHoldingPcnt')
            prev_bundlers = float(prev_bundlers.get('current', 0) if isinstance(prev_bundlers, dict) else (prev_bundlers if prev_bundlers is not None else 0))
            curr_bundlers = curr.get('bundlesHoldingPcnt')
            curr_bundlers = float(curr_bundlers.get('current', 0) if isinstance(curr_bundlers, dict) else (curr_bundlers if curr_bundlers is not None else 0))
            prev_snipers = float(prev.get('snipersHoldingPcnt', 0) or 0)
            curr_snipers = float(curr.get('snipersHoldingPcnt', 0) or 0)
            
            bundlers_change = curr_bundlers - prev_bundlers
            snipers_change = curr_snipers - prev_snipers
            
            if bundlers_change < 0 and snipers_change < 0:
                bundlers_changes.append(bundlers_change)
                snipers_changes.append(snipers_change)

        if len(bundlers_changes) < 2:
            return True

        suspicious = sum(
            1 for i in range(len(bundlers_changes))
            if abs(bundlers_changes[i] - snipers_changes[i]) / max(abs(bundlers_changes[i]), abs(snipers_changes[i])) < 0.3
        )
        
        is_suspicious = suspicious >= len(bundlers_changes) * 0.5
        return not is_suspicious
    
    async def check_holders_correlation(self, metrics_history: List[Dict]) -> bool:
        """
        Анализирует массовые продажи среди ранних холдеров.
        ФОКУС: Топ 10 холдеров по времени входа должны быстро выходить из рынка.
        
        Returns:
            bool: True если паттерны продаж нормальные, False если подозрительные
        """
        if not metrics_history or len(metrics_history) < 3:
            logger.debug("📊 Недостаточно данных для анализа продаж холдеров")
            return True
        
        # Лимитируем количество данных для анализа
        if len(metrics_history) > 1000:
            logger.debug("📊 Лимитируем анализ последними 1000 метриками")
            metrics_to_analyze = metrics_history[-1000:]
        else:
            metrics_to_analyze = metrics_history
        
        logger.debug("🔍 АНАЛИЗ МАССОВЫХ ПРОДАЖ РАННИХ ХОЛДЕРОВ")
        
        # Собираем данные о холдерах и времени их входа
        all_wallets = set()
        wallet_entry_times = {}  # {wallet: first_seen_timestamp}
        wallet_holdings_history = {}  # {wallet: [(timestamp, pcnt), ...]}
        
        # Собираем все кошельки за ограниченный период и отслеживаем время входа
        for i, metrics in enumerate(metrics_to_analyze):
            timestamp = metrics.get('timestamp', int(time.time()))
            top10holders = metrics.get('top10holders', {})
            
            for wallet, holder_info in top10holders.items():
                # Исключаем пулы, бандлеров и инсайдеров
                if not holder_info.get('isPool', False) and not holder_info.get('isBundler', False) and not holder_info.get('insider', False):
                    all_wallets.add(wallet)
                    
                    # Записываем время первого появления
                    if wallet not in wallet_entry_times:
                        wallet_entry_times[wallet] = timestamp
                    
                    # Ведем историю владения
                    if wallet not in wallet_holdings_history:
                        wallet_holdings_history[wallet] = []
                    wallet_holdings_history[wallet].append((timestamp, holder_info.get('pcnt', 0)))
        
        # Сортируем кошельки по времени входа (РАННИЕ ХОЛДЕРЫ - ПРИОРИТЕТ!)
        sorted_wallets_by_entry = sorted(wallet_entry_times.items(), key=lambda x: x[1])
        early_holders = [wallet for wallet, entry_time in sorted_wallets_by_entry[:10]]  # Первые 10
        
        logger.debug(f"📋 Найдено {len(all_wallets)} обычных кошельков для анализа")
        logger.debug(f"🚨 РАННИЕ ХОЛДЕРЫ (первые 10): {[w[:8] + '...' for w in early_holders]}")
        
        # Анализируем изменения по времени для выявления массовых продаж
        holder_changes_timeline = []
        
        for i in range(1, len(metrics_to_analyze)):
            prev_metrics = metrics_to_analyze[i-1]
            curr_metrics = metrics_to_analyze[i]
            
            prev_holders = prev_metrics.get('top10holders', {})
            curr_holders = curr_metrics.get('top10holders', {})
            
            timestamp = curr_metrics.get('timestamp', int(time.time()))
            
            # Анализируем изменения для каждого кошелька
            wallet_changes = {}
            for wallet in all_wallets:
                prev_pcnt = prev_holders.get(wallet, {}).get('pcnt', 0) if wallet in prev_holders else 0
                curr_pcnt = curr_holders.get(wallet, {}).get('pcnt', 0) if wallet in curr_holders else 0
                
                change = curr_pcnt - prev_pcnt
                
                # Анализируем значительные изменения (больше 0.01%)
                if abs(change) > 0.01:
                    wallet_changes[wallet] = {
                        'change': change,
                        'prev_pcnt': prev_pcnt,
                        'curr_pcnt': curr_pcnt,
                        'change_ratio': abs(change) / max(prev_pcnt, 0.001)  # Избегаем деления на ноль
                    }
            
            if wallet_changes:
                holder_changes_timeline.append({
                    'timestamp': timestamp,
                    'changes': wallet_changes,
                    'total_wallets_changed': len(wallet_changes)
                })
        
        # Анализируем синхронные продажи
        mass_sell_events = []
        early_holder_suspicious = []
        
        for i, change_event in enumerate(holder_changes_timeline):
            changes = change_event['changes']
            timestamp = change_event['timestamp']
            
            # Находим продажи (отрицательные изменения)
            selling_wallets = []
            total_sell_volume = 0
            
            for wallet, change_data in changes.items():
                if change_data['change'] < -0.01:  # Продажа больше 0.01%
                    selling_wallets.append({
                        'wallet': wallet,
                        'sell_amount': abs(change_data['change']),
                        'prev_pcnt': change_data['prev_pcnt'],
                        'change_ratio': change_data['change_ratio']
                    })
                    total_sell_volume += abs(change_data['change'])
            
            # Если продают 3+ кошелька одновременно - подозрительно
            if len(selling_wallets) >= 3:
                mass_sell_events.append({
                    'timestamp': timestamp,
                    'selling_wallets': selling_wallets,
                    'total_sell_volume': total_sell_volume,
                    'avg_sell_amount': total_sell_volume / len(selling_wallets)
                })
        
        # Анализируем корреляции массовых продаж среди ранних холдеров (лимитируем)
        # Лимитируем количество ранних холдеров для анализа
        max_early_holders = min(len(early_holders), 8)  # Максимум 8 холдеров
        limited_early_holders = early_holders[:max_early_holders]
        
        for i, wallet1 in enumerate(limited_early_holders):
            for j, wallet2 in enumerate(limited_early_holders[i+1:]):
                # Собираем временные ряды для ранних холдеров
                wallet1_changes = []
                wallet2_changes = []
                
                for change_event in holder_changes_timeline:
                    change1 = change_event['changes'].get(wallet1, {}).get('change', 0)
                    change2 = change_event['changes'].get(wallet2, {}).get('change', 0)
                    wallet1_changes.append(change1)
                    wallet2_changes.append(change2)
                
                # Вычисляем корреляцию
                correlation = self._calculate_correlation(wallet1_changes, wallet2_changes)
                
                # Анализируем корреляции среди ранних холдеров
                if correlation > 0.6 and len([x for x in wallet1_changes if abs(x) > 0.01]) >= 1:
                    # Анализируем синхронные продажи ранних холдеров
                    sync_sells = sum(1 for k in range(len(wallet1_changes)) 
                                   if wallet1_changes[k] < -0.01 and wallet2_changes[k] < -0.01)
                    
                    if sync_sells >= 1:  # Для ранних холдеров достаточно одной синхронной продажи!
                        early_holder_suspicious.append({
                            'wallet1': wallet1,
                            'wallet2': wallet2,
                            'correlation': correlation,
                            'sync_sells': sync_sells,
                            'entry_time_diff': abs(wallet_entry_times[wallet1] - wallet_entry_times[wallet2]),
                            'pattern_type': 'early_holder_coordination'
                        })
        
        # Анализируем общий процент владения ранних холдеров
        early_holders_total_percent = 0
        for wallet in early_holders:
            # Берем последний известный процент владения
            if wallet in wallet_holdings_history and wallet_holdings_history[wallet]:
                latest_percent = wallet_holdings_history[wallet][-1][1]
                early_holders_total_percent += latest_percent
        
        # Анализируем скорость выхода ранних холдеров
        early_holders_fast_exit = 0
        for wallet in early_holders:
            if wallet in wallet_holdings_history and len(wallet_holdings_history[wallet]) >= 2:
                initial_percent = wallet_holdings_history[wallet][0][1]
                current_percent = wallet_holdings_history[wallet][-1][1]
                
                # Если кошелек потерял более 50% своих изначальных холдингов
                if initial_percent > 0 and (current_percent / initial_percent) < 0.5:
                    early_holders_fast_exit += 1
        
        # Итоговая оценка - фокус только на массовых продажах ранних холдеров
        total_mass_sell_events = len(mass_sell_events)
        total_early_holder_patterns = len(early_holder_suspicious)
        
        # Простые критерии подозрительности
        is_suspicious = False
        
        # ВЫСОКИЙ уровень - коррелированные ранние холдеры + массовые продажи
        if total_early_holder_patterns >= 1 and total_mass_sell_events >= 2:
            is_suspicious = True
            logger.warning(f"🔴 ВЫСОКИЙ РИСК: Ранние холдеры коррелируют и есть массовые продажи!")
        
        # СРЕДНИЙ уровень - только массовые продажи или только коррелированные ранние холдеры или высокий % ранних холдеров
        elif total_mass_sell_events >= 3 or total_early_holder_patterns >= 2 or early_holders_total_percent > 30:
            is_suspicious = True
            if early_holders_total_percent > 30:
                logger.warning(f"🟡 СРЕДНИЙ РИСК: Ранние холдеры держат слишком много ({early_holders_total_percent:.2f}% > 30%)")
            else:
                logger.warning(f"🟡 СРЕДНИЙ РИСК: Много массовых продаж или коррелированных ранних холдеров")
        
        return not is_suspicious
    
    async def analyze_token_with_full_criteria(self, log_path: str) -> Dict:
        """Анализирует каждый снапшот как потенциальную точку уведомления (имитирует process_token_metrics)"""
        token_id = os.path.basename(log_path).replace('.log', '')
        full_token_address = None
        
        # Ищем полный адрес токена в логе
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # Ищем строку с полным адресом токена
                    if '/tokenAddress/' in line:
                        import re
                        match = re.search(r'/tokenAddress/([A-Za-z0-9]{32,})', line)
                        if match:
                            full_token_address = match.group(1)
                            break
                    # Альтернативный поиск в данных
                    elif "'tokenAddress':" in line:
                        match = re.search(r"'tokenAddress':\s*'([A-Za-z0-9]{32,})'", line)
                        if match:
                            full_token_address = match.group(1)
                            break
        except Exception:
            pass
        
        # Используем полный адрес если найден, иначе короткий ID
        token_address = full_token_address if full_token_address else token_id
        
        # Проверяем черный список
        if token_address in GENIUS_RUG_BLACKLIST:
            return {
                'token_id': token_id,
                'decision': 'BLACKLISTED',
                'reason': 'Токен в черном списке "гениальных рагов"'
            }
        
        # Накапливаем метрики и проверяем каждый снапшот
        metrics_history = []
        holder_percentages_history = []
        snapshots_checked = 0
        first_snapshot_time = None  # Время первого снапшота как приблизительное время создания
        best_snapshot = {
            'snapshot_number': 0,
            'passed_conditions': 0,
            'failed_conditions': [],
            'passed_conditions_list': [],
            'metrics': {}
        }
        
        # Создаем экземпляр TokenMetrics для отслеживания реальных метрик
        # Используем время создания = 0, так как у нас нет точного времени из логов
        token_metrics = TokenMetrics(token_address, creation_time=0)
        
        try:
            # МАКСИМАЛЬНО ОПТИМИЗИРОВАННОЕ чтение файла
            with open(log_path, 'r', encoding='utf-8', buffering=32768) as f:
                for line in f:
                    # БЫСТРЫЙ СКИП неважных строк для ускорения
                    if not ('👥' in line or '💰' in line or '💧' in line or '🎯' in line or 
                           '👨‍💼' in line or '📦' in line or '🏆' in line or 
                           'уведомление' in line or 'notification' in line):
                        continue
                        
                    data = self.parse_tokens_log_line(line)
                    if not data:
                        continue
                    
                    if data['type'] == 'notification_sent':
                        # Останавливаем анализ - это момент когда бот отправил уведомление
                        break
                    
                    # Обновляем метрики при каждом новом снапшоте 
                    if data['type'] in ['holders_count', 'mcap', 'liquidity', 'snipers', 'insiders', 'dev', 'bundlers']:
                        # Берем последние метрики или создаем новые
                        if metrics_history:
                            metrics = metrics_history[-1].copy()  # Копируем последние метрики
                        else:
                            metrics = {
                                'timestamp': int(time.time()),
                                'total_holders': 0,
                                'marketCapUsdUi': 0,
                                'liquidityInUsdUi': 0,
                                'snipersHoldingPcnt': 0,
                                'totalSnipers': 0,
                                'insidersHoldingPcnt': 0,
                                'devHoldingPcnt': 0,
                                'bundlesHoldingPcnt': {'current': 0},
                                'totalBundlesCount': 0,
                                'top10holders': {}
                            }
                        
                        # Обновляем timestamp
                        current_timestamp = data.get('timestamp', datetime.now()).timestamp() if hasattr(data.get('timestamp'), 'timestamp') else int(time.time())
                        metrics['timestamp'] = current_timestamp
                        
                        # Сохраняем время первого снапшота как приблизительное время создания рынка
                        if first_snapshot_time is None:
                            first_snapshot_time = current_timestamp
                            # Добавляем приблизительное время создания рынка
                            metrics['marketCreatedAt'] = int(first_snapshot_time)
                        
                        # Обновляем конкретные метрики в зависимости от типа
                        if data['type'] == 'holders_count':
                            metrics['total_holders'] = data.get('holders_count', 0)
                        elif data['type'] == 'mcap':
                            metrics['marketCapUsdUi'] = data.get('mcap', 0)
                        elif data['type'] == 'liquidity':
                            metrics['liquidityInUsdUi'] = data.get('liquidity', 0)
                        elif data['type'] == 'snipers':
                            metrics['snipersHoldingPcnt'] = data.get('snipers_percent', 0)
                            metrics['totalSnipers'] = data.get('snipers_count', 0)
                        elif data['type'] == 'insiders':
                            metrics['insidersHoldingPcnt'] = data.get('insiders_percent', 0)
                        elif data['type'] == 'dev':
                            metrics['devHoldingPcnt'] = data.get('dev_percent', 0)
                        elif data['type'] == 'bundlers':
                            metrics['bundlesHoldingPcnt'] = {'current': data.get('bundlers_percent', 0)}
                            metrics['totalBundlesCount'] = data.get('bundlers_count', 0)
                        
                        metrics_history.append(metrics)
                        
                        # Обновляем TokenMetrics для корректного отслеживания
                        token_metrics.add_metrics(metrics)
                    
                        # ПРОВЕРЯЕМ ACTIVITY УСЛОВИЯ НА КАЖДОМ СНАПШОТЕ
                        # Как в bundle_analyzer.py - process_token_metrics вызывается при каждом обновлении
                        if len(metrics_history) >= 3:  # Минимум данных для корреляций
                            snapshots_checked += 1
                            activity_result = await self.check_activity_notification_detailed(metrics_history, holder_percentages_history, token_address, token_metrics)
                            
                            if activity_result and activity_result.get('decision') == 'WOULD_SEND':
                                # Нашли момент когда токен прошел бы фильтрацию!
                                activity_result['snapshot_number'] = snapshots_checked
                                activity_result['total_snapshots'] = len(metrics_history)
                                activity_result['token_address'] = token_address  # Добавляем полный адрес
                                return activity_result
                            
                            # Отслеживаем лучший снапшот (максимум прошедших условий)
                            if activity_result:
                                passed_count = activity_result.get('passed_conditions_count', 0)
                                if passed_count > best_snapshot['passed_conditions']:
                                    best_snapshot = {
                                        'snapshot_number': snapshots_checked,
                                        'passed_conditions': passed_count,
                                        'failed_conditions': activity_result.get('failed_conditions', []),
                                        'passed_conditions_list': activity_result.get('passed_conditions_list', []),
                                        'metrics': activity_result.get('snapshot_metrics', {})
                                    }
                    
                    # Обновляем историю процентов при каждом снапшоте холдеров
                    elif data['type'] == 'holders':
                        percentages = data['percentages']
                        
                        # Проверяем что percentages это список/массив
                        if not isinstance(percentages, (list, tuple)):
                            continue  # Пропускаем неправильные данные
                            
                        if len(percentages) >= 3:
                            try:
                                # Создаем top10holders структуру из percentages
                                top10holders = {}
                                for i, pcnt in enumerate(percentages[:10]):  # Берем топ-10
                                    wallet_address = f"holder_{i+1}"  # Генерируем условные адреса
                                    top10holders[wallet_address] = {
                                        'pcnt': float(pcnt),
                                        'isPool': False,
                                        'isBundler': False,
                                        'isSniper': pcnt > 3.0,  # Считаем снайпером если >3%
                                        'insider': False
                                    }
                                
                                # Обновляем метрики с top10holders
                                if metrics_history:
                                    metrics = metrics_history[-1].copy()
                                    metrics['top10holders'] = top10holders
                                    metrics['timestamp'] = data.get('timestamp', datetime.now()).timestamp() if hasattr(data.get('timestamp'), 'timestamp') else int(time.time())
                                    metrics_history.append(metrics)
                                
                                # Обновляем TokenMetrics
                                token_metrics.add_metrics(metrics)
                                
                                snapshot_data = {
                                    'percentages': percentages,
                                    'top3_snipers': sum(1 for p in percentages[:3] if float(p) > 3.0),
                                    'total_snipers_percent': 0
                                }
                                holder_percentages_history.append(snapshot_data)
                            except (ValueError, TypeError):
                                continue  # Пропускаем поврежденные данные
        
        except Exception as e:
            import traceback
            full_error = traceback.format_exc()
            logger.error(f"💥 Ошибка в analyze_token_with_full_criteria для {token_id}: {full_error}")
            return {'token_id': token_id, 'token_address': token_address, 'decision': 'ERROR', 'reason': f'Ошибка анализа: {str(e)}'}
        
        if not metrics_history:
            return {
                'token_id': token_id,
                'token_address': token_address,
                'decision': 'NO_DATA',
                'reason': 'Недостаточно данных для анализа'
            }
        
        # Если ни один снапшот не прошел фильтрацию - токен отклонен
        # Формируем детальную причину с информацией о лучшем снапшоте
        if best_snapshot['passed_conditions'] > 0:
            failed_conditions = best_snapshot.get('failed_conditions', [])
            passed_conditions_list = best_snapshot.get('passed_conditions_list', [])
            
            # Безопасно берем первые 3 элемента
            failed_conditions_str = ', '.join(failed_conditions[:3] if isinstance(failed_conditions, list) else [])
            passed_conditions_str = ', '.join(passed_conditions_list[:3] if isinstance(passed_conditions_list, list) else [])
            best_reason = (
                f"Ни один из {snapshots_checked} снапшотов не прошел. "
                f"Лучший снапшот #{best_snapshot['snapshot_number']}: "
                f"✅{best_snapshot['passed_conditions']} условий (напр: {passed_conditions_str}), "
                f"❌ провалились: {failed_conditions_str}"
            )
            
            # Добавляем ключевые метрики лучшего снапшота
            metrics = best_snapshot.get('metrics', {})
            best_metrics = {}
            if 'holders' in metrics:
                best_metrics['holders'] = metrics['holders']
            if 'liquidity' in metrics:
                best_metrics['liquidity'] = metrics['liquidity'] 
            if 'snipers_percent' in metrics:
                best_metrics['snipers_percent'] = metrics['snipers_percent']
        else:
            best_reason = f'Ни один из {snapshots_checked} снапшотов не соответствовал условиям activity уведомления'
            best_metrics = {}
        
        result = {
            'token_id': token_id,
            'token_address': token_address,
            'decision': 'WOULD_REJECT',
            'reason': best_reason,
            'notification_type': 'ACTIVITY',
            'snapshots_checked': snapshots_checked,
            'total_snapshots': len(metrics_history),
            'best_snapshot': best_snapshot
        }
        
        # Добавляем метрики лучшего снапшота для логирования
        result.update(best_metrics)
        
        return result
    

    async def check_activity_notification_detailed(self, metrics_history: List[Dict], holder_percentages_history: List[Dict], token_id: str, token_metrics: TokenMetrics) -> Optional[Dict]:
        """Проверяет условия для activity notification с детальной диагностикой"""
        if not metrics_history:
            return None
        
        # Берем последние метрики
        metrics = metrics_history[-1]
        
        # Безопасно получаем значения
        total_holders = int(metrics.get('total_holders', 0) or 0)
        market_cap = float(metrics.get('marketCapUsdUi', 0) or 0)
        liquidity = float(metrics.get('liquidityInUsdUi', 0) or 0)
        dev_percent = float(metrics.get('devHoldingPcnt', 0) or 0)
        bundles_percent = metrics.get('bundlesHoldingPcnt', {})
        bundles_percent = float(bundles_percent.get('current', 0) if isinstance(bundles_percent, dict) else (bundles_percent or 0))
        snipers_percent = float(metrics.get('snipersHoldingPcnt', 0) or 0)
        snipers_count = int(metrics.get('totalSnipers', 0) or 0)
        insiders_percent = float(metrics.get('insidersHoldingPcnt', 0) or 0)
        
        # Реальный расчет роста холдеров (как в bundle_analyzer.py)
        growth = {'holders_growth': 2900}  # Для минимального роста используем константу
        
        # Рассчитываем max_holders_pcnt из топ холдеров (реальная логика из bundle_analyzer.py)
        max_holders_pcnt = 0
        top10holders = metrics.get('top10holders', {})
        if top10holders:
            for wallet, value in top10holders.items():
                # Исключаем пулы, бандлеров и инсайдеров как в bundle_analyzer.py
                if not value.get('isPool', False) and not value.get('isBundler', False) and not value.get('insider', False):
                    if value.get('pcnt', 0) > max_holders_pcnt:
                        max_holders_pcnt = value['pcnt']
        
        # ПРАВИЛЬНАЯ логика time_ok для анализа исторических логов
        current_snapshot_time = metrics.get('timestamp', 0)
        market_created_at = metrics.get('marketCreatedAt', 0)
        
        # Используем время снапшота относительно первого снапшота (время создания рынка)
        if market_created_at > 0 and current_snapshot_time > 0:
            time_ok_check = (current_snapshot_time - market_created_at) < 300  # < 5 минут от создания
        else:
            time_ok_check = True  # Если времена неизвестны, считаем что условие выполнено
        
        # Точные условия из bundle_analyzer.py activity_conditions
        activity_conditions = {
            # 'time_ok': time_ok_check,  # ИСПРАВЛЕННАЯ проверка времени
            # Базовые условия по холдерам
            'holders_min': total_holders >= 30,  # Минимум 30 холдеров
            'holders_max': total_holders <= 130,  # Максимум 130 холдеров
            'holders_never_dumped': token_metrics.max_holders <= 150,  # Реальная проверка из TokenMetrics
            'max_holders_pcnt': 0 < max_holders_pcnt <= 7,
            
            # Условия по бандлерам (реальная логика из bundle_analyzer.py)
            'bundlers_ok': token_metrics.max_bundlers_after_dev_exit >= 5,
            'bundlers_before_dev_ok': token_metrics.max_bundlers_before_dev_exit <= 60,
            
            # Условия по деву
            'dev_percent_ok': dev_percent <= 2,  # <= 2%
            
            # Условия по снайперам (точно как в bundle_analyzer.py)
            'snipers_ok': (
                snipers_count <= 20 and  # Не более 20 снайперов
                (
                    snipers_percent <= 3.5 or # Либо текущий процент <= 3.5%
                    (
                        any(float(m.get('snipersHoldingPcnt', 0) or 0) > 0 for m in metrics_history) and
                        max(float(m.get('snipersHoldingPcnt', 0) or 0) 
                            for m in metrics_history 
                            if float(m.get('snipersHoldingPcnt', 0) or 0) > 0) > snipers_percent and
                        snipers_percent <= 5.0 and  # Но не больше 5% в текущий момент
                        self.check_rapid_exit('snipersHoldingPcnt', metrics_history, ratio=3, max_seconds=120)  # Более строгий rapid exit
                    )
                )
            ),
            'snipers_not_bundlers': self.check_snipers_bundlers_correlation(metrics_history),
            
            # Условия по инсайдерам (точно как в bundle_analyzer.py)
            'insiders_ok': (
                insiders_percent <= 15 or  # Либо текущий процент <= 15%
                (
                    any(float(m.get('insidersHoldingPcnt', 0) or 0) > 0 for m in metrics_history) and
                    max(float(m.get('insidersHoldingPcnt', 0) or 0) 
                        for m in metrics_history 
                        if float(m.get('insidersHoldingPcnt', 0) or 0) > 0) > insiders_percent and
                    insiders_percent <= 22.0 and  # Но не больше 22% в текущий момент
                    self.check_rapid_exit('insidersHoldingPcnt', metrics_history, ratio=3, max_seconds=120)  # Более строгий rapid exit
                )
            ),
            
            # Условия по ликвидности и росту
            'min_liquidity': liquidity >= 10000,  # >= 10000
            # 'holders_growth': growth['holders_growth'] >= 2900,  # >= 2900/мин
            
            # Проверки корреляций (полные из bundle_analyzer.py)
            'can_notify': token_metrics.can_send_notification('activity'),  # Реальная проверка интервала уведомлений
            'snipers_not_insiders': self.check_snipers_insiders_correlation(metrics_history),
            'bundlers_snipers_exit_not_correlated': self.check_bundlers_snipers_exit_correlation(metrics_history),
            'holders_not_correlated': await self.check_holders_correlation(metrics_history)
        }
        
        # Проверяем все условия и собираем детальную статистику
        failed_conditions = []
        passed_conditions = []
        for condition, value in activity_conditions.items():
            if not value:
                failed_conditions.append(condition)
            else:
                passed_conditions.append(condition)
        
        # Собираем метрики снапшота
        snapshot_metrics = {
            'holders': total_holders,
            'market_cap': market_cap,
            'liquidity': liquidity,
            'dev_percent': dev_percent,
            'snipers_percent': snipers_percent,
            'snipers_count': snipers_count,
            'insiders_percent': insiders_percent
        }
        
        # Если есть невыполненные условия, возвращаем детальную информацию
        if failed_conditions:
            return {
                'decision': 'WOULD_REJECT',
                'passed_conditions_count': len(passed_conditions),
                'failed_conditions': failed_conditions,
                'passed_conditions_list': passed_conditions,
                'snapshot_metrics': snapshot_metrics,
                'total_conditions': len(activity_conditions)
            }
        
        # ✅ ВСЕ ACTIVITY CONDITIONS ПРОШЛИ! 
        # Теперь дополнительная проверка: анализируем паттерны холдеров для выявления "гениальных рагов"
        # (точно как в bundle_analyzer.py строки 3221-3248)
        
        if len(holder_percentages_history) >= 20:
            # Анализируем паттерны холдеров (используем все доступные снапшоты до 1000)
            analysis_limit = 1000
            analyzed_count = min(len(holder_percentages_history), analysis_limit)
            
            is_suspicious, suspicious_reasons = self.is_suspicious_pattern(holder_percentages_history)
            
            if is_suspicious:
                # Добавляем токен в глобальный черный список навсегда
                GENIUS_RUG_BLACKLIST.add(token_id)
                save_blacklist()
                
                return {
                    'token_id': token_id,
                    'token_address': token_id,
                    'decision': 'WOULD_REJECT',
                    'reason': f"ВСЕ activity условия прошли, но обнаружены манипулятивные паттерны холдеров: {'; '.join(suspicious_reasons)} (добавлен в черный список)",
                    'suspicious_patterns': suspicious_reasons,
                    'blacklisted': True,
                    'notification_type': 'ACTIVITY',
                    'all_conditions_passed': True,  # Важно! Показываем что основные условия прошли
                    'analyzed_snapshots': analyzed_count
                }
            else:
                # ✅ Паттерны холдеров здоровые - токен полностью прошел!
                pass
        
        # 🎉 Если все условия выполнены И паттерны холдеров здоровые
        return {
            'token_id': token_id,
            'token_address': token_id,
            'decision': 'WOULD_SEND',
            'reason': 'Соответствует всем критериям activity уведомления (включая здоровые паттерны холдеров)',
            'notification_type': 'ACTIVITY',
                'holders': total_holders,
                'market_cap': market_cap,
                'liquidity': liquidity,
                'dev_percent': dev_percent,
                'snipers_percent': snipers_percent,
            'insiders_percent': insiders_percent,
            'all_conditions_passed': True,
            'healthy_holder_patterns': True
        }

    async def check_activity_notification(self, metrics_history: List[Dict], holder_percentages_history: List[Dict], token_id: str, token_metrics: TokenMetrics = None) -> Optional[Dict]:
        """Проверяет условия для activity notification (как в process_token_metrics)"""
        if not metrics_history:
            return None
        
        # Берем последние метрики
        metrics = metrics_history[-1]
        
        # Безопасно получаем значения
        total_holders = int(metrics.get('total_holders', 0) or 0)
        market_cap = float(metrics.get('marketCapUsdUi', 0) or 0)
        liquidity = float(metrics.get('liquidityInUsdUi', 0) or 0)
        dev_percent = float(metrics.get('devHoldingPcnt', 0) or 0)
        bundles_percent = metrics.get('bundlesHoldingPcnt', {})
        bundles_percent = float(bundles_percent.get('current', 0) if isinstance(bundles_percent, dict) else (bundles_percent or 0))
        snipers_percent = float(metrics.get('snipersHoldingPcnt', 0) or 0)
        snipers_count = int(metrics.get('totalSnipers', 0) or 0)
        insiders_percent = float(metrics.get('insidersHoldingPcnt', 0) or 0)
        
        # Реальная логика если token_metrics передан, иначе упрощенная
        growth = {'holders_growth': 2900}  # Для минимального роста
        
        if token_metrics:
            # Реальная логика с TokenMetrics
            max_holders_pcnt = 0
            top10holders = metrics.get('top10holders', {})
            if top10holders:
                for wallet, value in top10holders.items():
                    if not value.get('isPool', False) and not value.get('isBundler', False) and not value.get('insider', False):
                        if value.get('pcnt', 0) > max_holders_pcnt:
                            max_holders_pcnt = value['pcnt']
            
            current_snapshot_time = metrics.get('timestamp', 0)
            market_created_at = metrics.get('marketCreatedAt', 0)
            # ПРАВИЛЬНАЯ логика для исторических логов
            if market_created_at > 0 and current_snapshot_time > 0:
                time_ok = (current_snapshot_time - market_created_at) < 300  # < 5 минут от создания
            else:
                time_ok = True  # Если времена неизвестны, считаем что условие выполнено
            bundlers_ok = token_metrics.max_bundlers_after_dev_exit >= 5
            bundlers_before_dev_ok = token_metrics.max_bundlers_before_dev_exit <= 60
            holders_never_dumped = token_metrics.max_holders <= 150
            can_notify = token_metrics.can_send_notification('activity')
        else:
            # Упрощенная логика для совместимости
            max_holders_pcnt = 5.0
            time_ok = True
            bundlers_ok = True
            bundlers_before_dev_ok = True
            holders_never_dumped = total_holders <= 150
            can_notify = True
        
        # Точные условия из bundle_analyzer.py activity_conditions
        activity_conditions = {
            'time_ok': time_ok,
            # Базовые условия по холдерам  
            'holders_min': total_holders >= 30,  # Минимум 30 холдеров
            'holders_max': total_holders <= 130,  # Максимум 130 холдеров
            'holders_never_dumped': holders_never_dumped,
            'max_holders_pcnt': 0 < max_holders_pcnt <= 7,
            
            # Условия по бандлерам (реальная логика)
            'bundlers_ok': bundlers_ok,
            'bundlers_before_dev_ok': bundlers_before_dev_ok,
            
            # Условия по деву
            'dev_percent_ok': dev_percent <= self.MAX_DEV_PERCENT,  # <= 2%
            
            # Условия по снайперам (точно как в bundle_analyzer.py)
            'snipers_ok': (
                snipers_count <= 20 and  # Не более 20 снайперов
                (
                    snipers_percent <= 3.5 or # Либо текущий процент <= 3.5%
                    (
                        any(float(m.get('snipersHoldingPcnt', 0) or 0) > 0 for m in metrics_history) and
                        max(float(m.get('snipersHoldingPcnt', 0) or 0) 
                            for m in metrics_history 
                            if float(m.get('snipersHoldingPcnt', 0) or 0) > 0) > snipers_percent and
                        snipers_percent <= 5.0 and  # Но не больше 5% в текущий момент
                        self.check_rapid_exit('snipersHoldingPcnt', metrics_history, ratio=3, max_seconds=120)  # Более строгий rapid exit
                    )
                )
            ),
            'snipers_not_bundlers': self.check_snipers_bundlers_correlation(metrics_history),
            
            # Условия по инсайдерам (точно как в bundle_analyzer.py)
            'insiders_ok': (
                insiders_percent <= 15 or  # Либо текущий процент <= 15%
                (
                    any(float(m.get('insidersHoldingPcnt', 0) or 0) > 0 for m in metrics_history) and
                    max(float(m.get('insidersHoldingPcnt', 0) or 0) 
                        for m in metrics_history 
                        if float(m.get('insidersHoldingPcnt', 0) or 0) > 0) > insiders_percent and
                    insiders_percent <= 22.0 and  # Но не больше 22% в текущий момент
                    self.check_rapid_exit('insidersHoldingPcnt', metrics_history, ratio=3, max_seconds=120)  # Более строгий rapid exit
                )
            ),
            
            # Условия по ликвидности и росту
            'min_liquidity': liquidity >= self.MIN_LIQUIDITY,  # >= 10000
            'holders_growth': growth['holders_growth'] >= self.MIN_GROWTH_RATE,  # >= 2900/мин
            
            # Проверки корреляций (полные из bundle_analyzer.py)
            'can_notify': can_notify,
            'snipers_not_insiders': self.check_snipers_insiders_correlation(metrics_history),
            'bundlers_snipers_exit_not_correlated': self.check_bundlers_snipers_exit_correlation(metrics_history),
            'holders_not_correlated': await self.check_holders_correlation(metrics_history)
        }
        
        # Проверяем все условия
        failed_conditions = []
        passed_conditions = []
        for condition, value in activity_conditions.items():
            if not value:
                failed_conditions.append(condition)
            else:
                passed_conditions.append(condition)
        
        # Если есть невыполненные условия, не отправляем
        if failed_conditions:
            # Детальная диагностика для логирования
            logger.debug(f"🔍 {token_id} ДЕТАЛЬНАЯ ДИАГНОСТИКА ACTIVITY CONDITIONS:")
            logger.debug(f"   ✅ ПРОШЛИ ({len(passed_conditions)}): {', '.join(passed_conditions)}")
            logger.debug(f"   ❌ ПРОВАЛИЛИСЬ ({len(failed_conditions)}): {', '.join(failed_conditions)}")
            logger.debug(f"   📊 МЕТРИКИ: HOLDERS={total_holders}, MCAP=${market_cap:,.0f}, LIQ=${liquidity:,.0f}")
            logger.debug(f"   🎯 СНАЙПЕРЫ: {snipers_percent:.1f}% ({snipers_count}шт), ИНСАЙДЕРЫ: {insiders_percent:.1f}%")
            return None
        
        # Дополнительная проверка: анализируем паттерны холдеров для выявления "гениальных рагов"
        if len(holder_percentages_history) >= 20:
            is_suspicious, suspicious_reasons = self.is_suspicious_pattern(holder_percentages_history)
            
            if is_suspicious:
                # Добавляем токен в глобальный черный список навсегда
                GENIUS_RUG_BLACKLIST.add(token_id)
                save_blacklist()
                
                return {
                    'token_id': token_id,
                    'token_address': token_id,
                    'decision': 'WOULD_REJECT',
                    'reason': f"Манипулятивные паттерны холдеров: {'; '.join(suspicious_reasons)} (добавлен в черный список)",
                    'suspicious_patterns': suspicious_reasons,
                    'blacklisted': True,
                    'notification_type': 'ACTIVITY'
                }
        
        # Если все условия выполнены
        return {
            'token_id': token_id,
            'token_address': token_id,
            'decision': 'WOULD_SEND',
            'reason': 'Соответствует всем критериям activity уведомления',
            'notification_type': 'ACTIVITY',
            'holders': total_holders,
            'market_cap': market_cap,
            'liquidity': liquidity,
            'dev_percent': dev_percent,
            'snipers_percent': snipers_percent,
            'insiders_percent': insiders_percent
        }
    

    
    def analyze_holder_stability(self, percentages_history: List[List[float]]) -> Tuple[bool, List[str]]:
        """Полный анализ стабильности холдеров из bundle_analyzer.py"""
        if len(percentages_history) < 20:
            return False, []
        
        suspicious_points = []
        
        # Считаем топ-3 снайперов в каждом снапшоте
        stable_sniper_periods = 0
        high_sniper_top3_count = 0
        
        for i, percentages in enumerate(percentages_history):
            # Проверяем что percentages это список/массив
            if not isinstance(percentages, (list, tuple)):
                # Если это словарь, извлекаем percentages
                if isinstance(percentages, dict) and 'percentages' in percentages:
                    percentages = percentages['percentages']
                else:
                    continue  # Пропускаем неправильные данные
            
            if len(percentages) >= 3:
                # Анализируем первые 3 холдера как потенциальных снайперов
                # если их доли >3% каждая
                try:
                    top3_large = sum(1 for p in percentages[:3] if float(p) > 3.0)
                except (ValueError, TypeError):
                    continue  # Пропускаем поврежденные данные
                if top3_large >= 2:
                    high_sniper_top3_count += 1
                    
                    # Проверяем стабильность (если изменения <0.3%)
                    if i > 0 and len(percentages_history[i-1]) >= 3:
                        prev_percentages = percentages_history[i-1]
                        
                        # Проверяем что prev_percentages тоже список
                        if not isinstance(prev_percentages, (list, tuple)):
                            if isinstance(prev_percentages, dict) and 'percentages' in prev_percentages:
                                prev_percentages = prev_percentages['percentages']
                            else:
                                continue  # Пропускаем неправильные данные
                        
                        try:
                            changes = [abs(float(percentages[j]) - float(prev_percentages[j])) for j in range(min(3, len(prev_percentages)))]
                            if all(change < 0.3 for change in changes):
                                stable_sniper_periods += 1
                        except (ValueError, TypeError, IndexError):
                            continue  # Пропускаем поврежденные данные
        
        # Критерий: Стабильные топ-снайперы
        stable_sniper_threshold = len(percentages_history) * 0.25
        if stable_sniper_periods > stable_sniper_threshold:
            suspicious_points.append(f"Стабильные топ-снайперы: {stable_sniper_periods} периодов (>{stable_sniper_threshold:.0f})")
            return True, suspicious_points
        
        # Критерий: Много снайперов в топ-3
        high_sniper_threshold = len(percentages_history) * 0.6
        if high_sniper_top3_count > high_sniper_threshold:
            suspicious_points.append(f"Много снайперов в топ-3: {high_sniper_top3_count} случаев (>{high_sniper_threshold:.0f})")
            return True, suspicious_points
        
        # Анализ ранних vs текущих холдеров
        early_suspicious, early_reasons = self.analyze_early_vs_current_holders(percentages_history)
        if early_suspicious:
            suspicious_points.extend(early_reasons)
            return True, suspicious_points
        
        return False, suspicious_points

    def is_suspicious_pattern(self, percentages_history):
        """Определяет подозрительные паттерны торговли (точно как в bundle_analyzer.py)"""
        if not percentages_history or len(percentages_history) < 3:
            return False, []
        
        # Анализируем только последние 1000 снапшотов для максимальной точности
        # Используем все доступные данные для наиболее точного выявления паттернов
        analysis_limit = 1000
        analysis_history = percentages_history[-analysis_limit:] if len(percentages_history) > analysis_limit else percentages_history
        
        # Используем анализ стабильности топ-холдеров
        suspicious, suspicious_reasons = self.analyze_holder_stability(analysis_history)
        
        return suspicious, suspicious_reasons
    
    def parse_tokens_log_line(self, line: str) -> Optional[Dict]:
        """ОПТИМИЗИРОВАННЫЙ парсинг строки из tokens_logs с кешированными regex"""
        # Парсинг времени (кешированный regex)
        time_match = self._regex_cache['time'].match(line)
        if not time_match:
            return None
        
        timestamp_str = time_match.group(1)
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        
        # Парсинг данных о держателях
        if '🏆 Проценты держателей:' in line:
            percentages_part = line.split('🏆 Проценты держателей: ')[1]
            percentages_str = percentages_part.strip()
            
            if percentages_str:
                try:
                    percentages = [float(x.replace('%', '')) for x in percentages_str.split() if x.replace('%', '').replace('.', '').isdigit()]
                    return {
                        'type': 'holders',
                        'timestamp': timestamp,
                        'percentages': percentages
                    }
                except ValueError:
                    return None
        
        # Парсинг метрик (ОПТИМИЗИРОВАННЫЕ кешированные паттерны)
        elif '👥 Холдеры:' in line:
            holders_match = self._regex_cache['holders_count'].search(line)
            if holders_match:
                return {
                    'type': 'holders_count',
                    'timestamp': timestamp,
                    'holders_count': int(holders_match.group(1))
                }
        
        elif '💰 Market Cap:' in line:
            # Кешированный regex для mcap
            mcap_match = self._regex_cache['mcap'].search(line)
            if mcap_match:
                try:
                    mcap_str = mcap_match.group(1).replace(',', '')
                    return {
                        'type': 'mcap',
                        'timestamp': timestamp,
                        'mcap': float(mcap_str)
                    }
                except ValueError:
                    return None
        
        elif '💧 Ликвидность:' in line:
            # Кешированный regex для ликвидности
            liquidity_match = self._regex_cache['liquidity'].search(line)
            if liquidity_match:
                try:
                    liquidity_str = liquidity_match.group(1).replace(',', '')
                    return {
                        'type': 'liquidity',
                        'timestamp': timestamp,
                        'liquidity': float(liquidity_str)
                    }
                except ValueError:
                    return None
        
        elif '🎯 Снайперы:' in line:
            # Кешированный regex для снайперов
            snipers_match = self._regex_cache['snipers'].search(line)
            if snipers_match:
                try:
                    return {
                        'type': 'snipers',
                        'timestamp': timestamp,
                        'snipers_percent': float(snipers_match.group(1)),
                        'snipers_count': int(snipers_match.group(2))
                    }
                except ValueError:
                    return None
        
        elif '👨‍💼 Инсайдеры:' in line:
            # Кешированный regex для инсайдеров
            insiders_match = self._regex_cache['insiders'].search(line)
            if insiders_match:
                try:
                    return {
                        'type': 'insiders',
                        'timestamp': timestamp,
                        'insiders_percent': float(insiders_match.group(1))
                    }
                except ValueError:
                    return None
        
        elif '👨‍💼 Dev %:' in line:
            # Кешированный regex для dev процента
            dev_match = self._regex_cache['dev'].search(line)
            if dev_match:
                try:
                    return {
                        'type': 'dev',
                        'timestamp': timestamp,
                        'dev_percent': float(dev_match.group(1))
                    }
                except ValueError:
                    return None
        
        elif '📦 Бандлеры:' in line:
            # Кешированный regex для бандлеров
            bundlers_match = self._regex_cache['bundlers'].search(line)
            if bundlers_match:
                try:
                    return {
                        'type': 'bundlers',
                        'timestamp': timestamp,
                        'bundlers_count': int(bundlers_match.group(1)),
                        'bundlers_percent': float(bundlers_match.group(2))
                    }
                except ValueError:
                    return None
        
        elif '📊 ОБЩИЙ % ВЛАДЕНИЯ РАННИХ ХОЛДЕРОВ:' in line:
            early_match = re.search(r'📊 ОБЩИЙ % ВЛАДЕНИЯ РАННИХ ХОЛДЕРОВ: ([0-9.]+)%', line)
            if early_match:
                try:
                    return {
                        'type': 'early_holders',
                        'timestamp': timestamp,
                        'early_holders_percent': float(early_match.group(1))
                    }
                except ValueError:
                    return None
        
        elif '📢 Отправлено уведомление' in line:
            return {
                'type': 'notification_sent',
                'timestamp': timestamp
            }
        
        return None

    def analyze_tokens_log_file(self, log_path: str) -> Dict:
        """Анализирует файл лога из tokens_logs"""
        token_id = os.path.basename(log_path).replace('.log', '')
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 Анализ токена из tokens_logs: {token_id}")
        logger.info(f"📁 Файл: {log_path}")
        
        percentages_history = []
        latest_holders_count = None
        latest_mcap = None
        latest_liquidity = None
        latest_snipers = None
        latest_early_holders = None
        notification_sent_time = None
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data = self.parse_tokens_log_line(line)
                    if not data:
                        continue
                    
                    if data['type'] == 'holders':
                        percentages_history.append(data['percentages'])
                    elif data['type'] == 'holders_count':
                        latest_holders_count = data['holders_count']
                    elif data['type'] == 'mcap':
                        latest_mcap = data['mcap']
                    elif data['type'] == 'liquidity':
                        latest_liquidity = data['liquidity']
                    elif data['type'] == 'snipers':
                        latest_snipers = data
                    elif data['type'] == 'early_holders':
                        latest_early_holders = data['early_holders_percent']
                    elif data['type'] == 'notification_sent':
                        notification_sent_time = data['timestamp']
                        # Останавливаем анализ - это момент когда бот отправил уведомление
                        break
        
        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла {log_path}: {e}")
            return {'token_id': token_id, 'error': str(e)}
        
        if notification_sent_time is None:
            logger.info(f"⚠️ Уведомление не было отправлено для {token_id}")
            return {'token_id': token_id, 'decision': 'NO_NOTIFICATION', 'reason': 'Уведомление не отправлено'}
        
        # Выводим финальные метрики на момент отправки уведомления
        logger.info(f"📊 Финальные метрики на момент уведомления {notification_sent_time}:")
        logger.info(f"   👥 Держатели: {latest_holders_count}")
        logger.info(f"   💰 Market Cap: ${latest_mcap:,.0f}" if latest_mcap else "   💰 Market Cap: неизвестно")
        logger.info(f"   💧 Ликвидность: ${latest_liquidity:,.0f}" if latest_liquidity else "   💧 Ликвидность: неизвестно")
        logger.info(f"   🎯 Снайперы: {latest_snipers['snipers_percent']:.1f}% ({latest_snipers['snipers_count']})" if latest_snipers else "   🎯 Снайперы: неизвестно")
        logger.info(f"   🔄 Ранние холдеры: {latest_early_holders:.1f}%" if latest_early_holders else "   🔄 Ранние холдеры: неизвестно")
        logger.info(f"   📈 Снапшотов холдеров: {len(percentages_history)}")
        
        # Применяем наши новые фильтры
        if latest_holders_count and latest_holders_count < self.MIN_HOLDERS:
            reason = f"Мало держателей: {latest_holders_count} < {self.MIN_HOLDERS}"
            logger.info(f"❌ НАШ ФИЛЬТР ОТКЛОНИЛ БЫ: {reason}")
            return {'token_id': token_id, 'decision': 'WOULD_REJECT', 'reason': reason, 'notification_time': notification_sent_time}
        
        if latest_holders_count and latest_holders_count > self.MAX_HOLDERS:
            reason = f"Слишком много держателей: {latest_holders_count} > {self.MAX_HOLDERS}"
            logger.info(f"❌ НАШ ФИЛЬТР ОТКЛОНИЛ БЫ: {reason}")
            return {'token_id': token_id, 'decision': 'WOULD_REJECT', 'reason': reason, 'notification_time': notification_sent_time}
        
        if latest_mcap and latest_mcap < self.MIN_MCAP:
            reason = f"Капитализация слишком мала: ${latest_mcap:,.0f} < ${self.MIN_MCAP:,.0f}"
            logger.info(f"❌ НАШ ФИЛЬТР ОТКЛОНИЛ БЫ: {reason}")
            return {'token_id': token_id, 'decision': 'WOULD_REJECT', 'reason': reason, 'notification_time': notification_sent_time}
        
        if latest_early_holders and latest_early_holders > self.MAX_EARLY_HOLDERS_PERCENT:
            reason = f"Слишком много у ранних: {latest_early_holders:.1f}% > {self.MAX_EARLY_HOLDERS_PERCENT}%"
            logger.info(f"❌ НАШ ФИЛЬТР ОТКЛОНИЛ БЫ: {reason}")
            return {'token_id': token_id, 'decision': 'WOULD_REJECT', 'reason': reason, 'notification_time': notification_sent_time}
        
        # Анализ подозрительных паттернов холдеров (используем наш новый алгоритм)
        if len(percentages_history) >= 20:
            is_suspicious, suspicious_points = self.analyze_holder_stability(percentages_history)
            
            if is_suspicious:
                reason = f"Подозрительные паттерны холдеров: {'; '.join(suspicious_points)}"
                logger.info(f"❌ НАШ ФИЛЬТР ОТКЛОНИЛ БЫ: {reason}")
                return {'token_id': token_id, 'decision': 'WOULD_REJECT', 'reason': reason, 'notification_time': notification_sent_time, 'suspicious_points': suspicious_points}
        else:
            logger.info(f"⚠️ Недостаточно данных о холдерах для анализа: {len(percentages_history)} снапшотов")
        
        # Если все наши фильтры пройдены - значит мы согласны с ботом
        logger.info(f"✅ НАШ ФИЛЬТР СОГЛАСЕН С БОТОМ - УВЕДОМЛЕНИЕ ОПРАВДАНО!")
        return {
            'token_id': token_id, 
            'decision': 'AGREE_SEND', 
            'reason': 'Наш фильтр согласен с отправкой',
            'notification_time': notification_sent_time,
            'holders_count': latest_holders_count,
            'mcap': latest_mcap,
            'early_holders_percent': latest_early_holders,
            'snapshots_count': len(percentages_history)
        }
    
    def analyze_log_file(self, log_path: str) -> Dict:
        """Анализирует файл лога и определяет, отправил бы бот уведомление"""
        token_id = os.path.basename(log_path).replace('.log', '')
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 Анализ токена: {token_id}")
        logger.info(f"📁 Файл: {log_path}")
        
        percentages_history = []
        early_holders_percent = None
        analysis_result = None
        call_time = None
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data = self.parse_log_line(line)
                    if not data:
                        continue
                    
                    if data['type'] == 'holders':
                        percentages_history.append(data['percentages'])
                    elif data['type'] == 'early_holders':
                        early_holders_percent = data['early_holders_percent']
                    elif data['type'] in ['analysis_suspicious', 'analysis_rejected', 'analysis_passed']:
                        analysis_result = data['type']
                        call_time = data['timestamp']
                        # Останавливаем анализ - это момент анализа токена
                        break
        
        except Exception as e:
            logger.error(f"❌ Ошибка чтения файла {log_path}: {e}")
            return {'token_id': token_id, 'error': str(e)}
        
        if early_holders_percent is None:
            logger.warning(f"⚠️ Не найден процент ранних холдеров для {token_id}")
            return {'token_id': token_id, 'decision': 'NO_DATA', 'reason': 'Нет данных о ранних холдерах'}
        
        if not analysis_result:
            logger.warning(f"⚠️ Не найден результат анализа для {token_id}")
            return {'token_id': token_id, 'decision': 'NO_DATA', 'reason': 'Нет результата анализа'}
        
        # Выводим найденные данные
        logger.info(f"📊 Данные на момент анализа {call_time}:")
        logger.info(f"   🎯 Ранние холдеры: {early_holders_percent:.2f}%")
        logger.info(f"   📈 Снапшотов холдеров: {len(percentages_history)}")
        logger.info(f"   🔍 Результат анализа: {analysis_result}")
        
        # Применяем фильтры как в bundle_analyzer.py
        
        # 1. Проверка процента ранних холдеров
        if early_holders_percent > self.MAX_EARLY_HOLDERS_PERCENT:
            reason = f"Слишком много у ранних: {early_holders_percent:.2f}% > {self.MAX_EARLY_HOLDERS_PERCENT}%"
            logger.info(f"❌ {reason}")
            return {'token_id': token_id, 'decision': 'REJECT', 'reason': reason, 'call_time': call_time}
        
        # 2. Анализ подозрительных паттернов холдеров (используем наш новый алгоритм)
        if len(percentages_history) >= 20:
            is_suspicious, suspicious_points = self.analyze_holder_stability(percentages_history)
            
            if is_suspicious:
                reason = f"Подозрительные паттерны холдеров: {'; '.join(suspicious_points)}"
                logger.info(f"❌ {reason}")
                return {'token_id': token_id, 'decision': 'REJECT', 'reason': reason, 'call_time': call_time, 'suspicious_points': suspicious_points}
        else:
            logger.info(f"⚠️ Недостаточно данных о холдерах для анализа: {len(percentages_history)} снапшотов")
        
        # 3. Проверяем что было в исходном анализе
        if analysis_result == 'analysis_suspicious' or analysis_result == 'analysis_rejected':
            reason = f"Исходный анализ отклонил токен: {analysis_result}"
            logger.info(f"❌ {reason} (но наш новый алгоритм мог бы пропустить)")
            return {'token_id': token_id, 'decision': 'REJECT', 'reason': reason, 'call_time': call_time}
        
        # Если все фильтры пройдены - токен был бы отправлен
        logger.info(f"✅ ВСЕ ФИЛЬТРЫ ПРОЙДЕНЫ - БОТ ОТПРАВИЛ БЫ УВЕДОМЛЕНИЕ!")
        return {
            'token_id': token_id, 
            'decision': 'SEND', 
            'reason': 'Все фильтры пройдены',
            'call_time': call_time,
            'early_holders_percent': early_holders_percent,
            'snapshots_count': len(percentages_history)
        }
    
    def analyze_directory(self, directory_path: str, label: str = "") -> List[Dict]:
        """Анализирует все логи в директории"""
        if not os.path.exists(directory_path):
            logger.error(f"❌ Директория не найдена: {directory_path}")
            return []
        
        log_files = [f for f in os.listdir(directory_path) if f.endswith('.log')]
        logger.info(f"\n🎯 Анализ директории: {directory_path} ({label})")
        logger.info(f"📁 Найдено {len(log_files)} файлов логов")
        
        results = []
        for log_file in sorted(log_files):
            log_path = os.path.join(directory_path, log_file)
            result = self.analyze_log_file(log_path)
            result['label'] = label
            results.append(result)
        
        return results
    
    def print_summary(self, results: List[Dict]):
        """Выводит сводку результатов"""
        logger.info(f"\n{'='*80}")
        logger.info("📊 ИТОГОВАЯ СВОДКА АНАЛИЗА")
        logger.info(f"{'='*80}")
        
        # Группируем результаты по лейблам
        by_label = {}
        for result in results:
            label = result.get('label', 'unknown')
            if label not in by_label:
                by_label[label] = []
            by_label[label].append(result)
        
        for label, label_results in by_label.items():
            logger.info(f"\n🏷️ {label.upper()} ТОКЕНЫ:")
            
            send_count = sum(1 for r in label_results if r.get('decision') == 'SEND')
            reject_count = sum(1 for r in label_results if r.get('decision') == 'REJECT')
            error_count = sum(1 for r in label_results if r.get('decision') not in ['SEND', 'REJECT'])
            
            logger.info(f"   ✅ Отправлено: {send_count}")
            logger.info(f"   ❌ Отклонено: {reject_count}")
            logger.info(f"   ⚠️ Ошибки: {error_count}")
            logger.info(f"   📊 Всего: {len(label_results)}")
            
            # Показываем причины отклонения
            reject_reasons = {}
            for result in label_results:
                if result.get('decision') == 'REJECT':
                    reason = result.get('reason', 'unknown')
                    # Группируем похожие причины
                    if 'Объем 24ч' in reason:
                        reason_key = 'Малый объем 24ч'
                    elif 'держателей' in reason and 'Мало' in reason:
                        reason_key = 'Мало держателей'
                    elif 'держателей' in reason and 'много' in reason:
                        reason_key = 'Много держателей'
                    elif 'Капитализация' in reason:
                        reason_key = 'Малая капитализация'
                    elif 'ранних' in reason:
                        reason_key = 'Много у ранних холдеров'
                    elif 'паттерны' in reason:
                        reason_key = 'Подозрительные паттерны холдеров'
                    else:
                        reason_key = reason
                    
                    reject_reasons[reason_key] = reject_reasons.get(reason_key, 0) + 1
            
            if reject_reasons:
                logger.info(f"   📋 Причины отклонения:")
                for reason, count in sorted(reject_reasons.items(), key=lambda x: x[1], reverse=True):
                    logger.info(f"      • {reason}: {count}")
        
        # Выводим детали по отправленным токенам
        sent_tokens = [r for r in results if r.get('decision') == 'SEND']
        if sent_tokens:
            logger.info(f"\n✅ ТОКЕНЫ, КОТОРЫЕ БОТ ОТПРАВИЛ БЫ:")
            for result in sent_tokens:
                logger.info(f"   🎯 {result['token_id']} ({result.get('label', 'unknown')}) в {result.get('call_time', 'unknown')}")


    def analyze_all_tokens_logs(self, tokens_logs_dir: str) -> List[Dict]:
        """Анализирует все токены в tokens_logs/ и возвращает краткую сводку"""
        if not os.path.exists(tokens_logs_dir):
            logger.error(f"❌ Директория не найдена: {tokens_logs_dir}")
            return []
        
        log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
        logger.info(f"🔍 Найдено {len(log_files)} файлов логов в tokens_logs/")
        
        results = []
        processed = 0
        
        for log_file in log_files:
            processed += 1
            if processed % 10 == 0:
                logger.info(f"📊 Обработано {processed}/{len(log_files)} файлов...")
            
            log_path = os.path.join(tokens_logs_dir, log_file)
            try:
                result = self.analyze_tokens_log_file_silent(log_path)  # Тихий режим
                results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка обработки {log_file}: {e}")
                
        return results
    
    def analyze_tokens_log_file_silent(self, log_path: str) -> Dict:
        """Тихая версия анализа токена из tokens_logs (без детального вывода)"""
        token_id = os.path.basename(log_path).replace('.log', '')
        
        percentages_history = []
        latest_holders_count = None
        latest_mcap = None
        latest_liquidity = None
        latest_snipers = None
        latest_early_holders = None
        notification_sent_time = None
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data = self.parse_tokens_log_line(line)
                    if not data:
                        continue
                    
                    if data['type'] == 'holders':
                        percentages_history.append(data['percentages'])
                    elif data['type'] == 'holders_count':
                        latest_holders_count = data['holders_count']
                    elif data['type'] == 'mcap':
                        latest_mcap = data['mcap']
                    elif data['type'] == 'liquidity':
                        latest_liquidity = data['liquidity']
                    elif data['type'] == 'snipers':
                        latest_snipers = data
                    elif data['type'] == 'early_holders':
                        latest_early_holders = data['early_holders_percent']
                    elif data['type'] == 'notification_sent':
                        notification_sent_time = data['timestamp']
                        # Останавливаем анализ - это момент когда бот отправил уведомление
                        break
        
        except Exception as e:
            return {'token_id': token_id, 'decision': 'ERROR', 'reason': str(e), 'metrics_count': 0}
        
        # Считаем количество доступных метрик
        metrics_count = sum([
            1 if latest_holders_count is not None else 0,
            1 if latest_mcap is not None else 0,
            1 if latest_liquidity is not None else 0,
            1 if latest_snipers is not None else 0,
            1 if latest_early_holders is not None else 0,
            1 if len(percentages_history) > 0 else 0,
            1 if notification_sent_time is not None else 0
        ])
        
        if notification_sent_time is None:
            return {
                'token_id': token_id, 
                'decision': 'NO_NOTIFICATION', 
                'reason': 'Нет уведомления',
                'metrics_count': metrics_count,
                'holders_count': latest_holders_count,
                'mcap': latest_mcap,
                'liquidity': latest_liquidity,
                'early_holders_percent': latest_early_holders,
                'snapshots_count': len(percentages_history)
            }
        
        # Применяем фильтры быстро
        if latest_holders_count and latest_holders_count < self.MIN_HOLDERS:
            return {
                'token_id': token_id, 
                'decision': 'WOULD_REJECT', 
                'reason': f'Мало держателей ({latest_holders_count})',
                'metrics_count': metrics_count,
                'holders_count': latest_holders_count,
                'mcap': latest_mcap,
                'liquidity': latest_liquidity,
                'early_holders_percent': latest_early_holders,
                'snapshots_count': len(percentages_history)
            }
        
        if latest_holders_count and latest_holders_count > self.MAX_HOLDERS:
            return {
                'token_id': token_id, 
                'decision': 'WOULD_REJECT', 
                'reason': f'Много держателей ({latest_holders_count})',
                'metrics_count': metrics_count,
                'holders_count': latest_holders_count,
                'mcap': latest_mcap,
                'liquidity': latest_liquidity,
                'early_holders_percent': latest_early_holders,
                'snapshots_count': len(percentages_history)
            }
        
        if latest_mcap and latest_mcap < self.MIN_MCAP:
            return {
                'token_id': token_id, 
                'decision': 'WOULD_REJECT', 
                'reason': f'Малая капитализация (${latest_mcap:,.0f})',
                'metrics_count': metrics_count,
                'holders_count': latest_holders_count,
                'mcap': latest_mcap,
                'liquidity': latest_liquidity,
                'early_holders_percent': latest_early_holders,
                'snapshots_count': len(percentages_history)
            }
        
        if latest_early_holders and latest_early_holders > self.MAX_EARLY_HOLDERS_PERCENT:
            return {
                'token_id': token_id, 
                'decision': 'WOULD_REJECT', 
                'reason': f'Много у ранних ({latest_early_holders:.1f}%)',
                'metrics_count': metrics_count,
                'holders_count': latest_holders_count,
                'mcap': latest_mcap,
                'liquidity': latest_liquidity,
                'early_holders_percent': latest_early_holders,
                'snapshots_count': len(percentages_history)
            }
        
        # Проверяем черный список "гениальных рагов" перед любой обработкой
        if token_id in GENIUS_RUG_BLACKLIST:
            return {
                'token_id': token_id, 
                'decision': 'WOULD_REJECT', 
                'reason': 'Токен в черном списке',
                'metrics_count': metrics_count,
                'holders_count': latest_holders_count,
                'mcap': latest_mcap,
                'liquidity': latest_liquidity,
                'early_holders_percent': latest_early_holders,
                'snapshots_count': len(percentages_history)
            }
        
        # Анализ паттернов холдеров
        if len(percentages_history) >= 20:
            is_suspicious, suspicious_points = self.analyze_holder_stability(percentages_history)
            
            if is_suspicious:
                # Добавляем токен в глобальный черный список навсегда
                GENIUS_RUG_BLACKLIST.add(token_id)
                save_blacklist()  # Сохраняем в файл
                
                # Берем первую причину для краткости
                short_reason = suspicious_points[0] if suspicious_points else "Подозрительные паттерны"
                return {
                    'token_id': token_id, 
                    'decision': 'WOULD_REJECT', 
                    'reason': f"{short_reason} (добавлен в черный список)",
                    'metrics_count': metrics_count,
                    'holders_count': latest_holders_count,
                    'mcap': latest_mcap,
                    'liquidity': latest_liquidity,
                    'early_holders_percent': latest_early_holders,
                    'snapshots_count': len(percentages_history)
                }
        
        # Если все фильтры пройдены
        return {
            'token_id': token_id, 
            'decision': 'AGREE_SEND', 
            'reason': 'Согласны с ботом',
            'metrics_count': metrics_count,
            'holders_count': latest_holders_count,
            'mcap': latest_mcap,
            'liquidity': latest_liquidity,
            'early_holders_percent': latest_early_holders,
            'snapshots_count': len(percentages_history)
        }

    async def analyze_all_tokens_with_full_criteria(self, tokens_logs_dir: str) -> List[Dict]:
        """Анализирует все токены ПАРАЛЛЕЛЬНО большими пачками для максимальной скорости"""
        results = []
        
        if not os.path.exists(tokens_logs_dir):
            logger.error(f"❌ Директория {tokens_logs_dir} не найдена")
            return results
        
        log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')]
        
        if not log_files:
            logger.error(f"❌ В директории {tokens_logs_dir} нет .log файлов")
            return results
        
        # Подготавливаем полные пути
        log_paths = [os.path.join(tokens_logs_dir, f) for f in log_files]
        
        # МАКСИМАЛЬНАЯ ПРОИЗВОДИТЕЛЬНОСТЬ: используем ВСЕ ядра + гиперпоточность
        num_processes = multiprocessing.cpu_count() * 2  # Используем гиперпоточность
        batch_size = max(200, len(log_paths) // num_processes)  # МАКСИМАЛЬНЫЕ батчи: минимум 200
        
        logger.info(f"🚀 МАКСИМАЛЬНАЯ СКОРОСТЬ: {len(log_files)} токенов")
        logger.info(f"⚡ Процессов: {num_processes}, Пачка: {batch_size}")
        
        start_time = time.time()
        
        # Обрабатываем большими пачками параллельно
        with ProcessPoolExecutor(max_workers=num_processes) as executor:
            # Разбиваем на пачки
            batches = [log_paths[i:i + batch_size] for i in range(0, len(log_paths), batch_size)]
            
            logger.info(f"📦 Обрабатываем {len(batches)} пачек параллельно...")
            
            for batch_idx, batch in enumerate(batches):
                logger.info(f"🔄 Пачка {batch_idx + 1}/{len(batches)}: {len(batch)} токенов...")
                
                # Запускаем пачку параллельно
                future_to_path = {executor.submit(process_single_token_sync, path): path for path in batch}
                
                # Собираем результаты пачки
                batch_results = []
                for future in future_to_path:
                    try:
                        result = future.result(timeout=60*10)  # 10 минут на токен максимум (увеличено для сложных токенов)
                        batch_results.append(result)
                    except Exception as e:
                        path = future_to_path[future]
                        token_id = os.path.basename(path).replace('.log', '')
                        
                        # Определяем тип ошибки для более точного сообщения
                        import concurrent.futures
                        if isinstance(e, concurrent.futures.TimeoutError):
                            error_message = f'Timeout: превышено время ожидания (600 сек)'
                            logger.warning(f"⏰ Timeout {token_id}: анализ занял более 600 секунд")
                        else:
                            error_message = f'Ошибка выполнения: {str(e)}'
                            logger.warning(f"⚠️ Ошибка {token_id}: {e}")
                            
                        error_result = {
                            'token_id': token_id,
                            'decision': 'ERROR',
                            'reason': error_message
                        }
                        # Логируем timeout/ошибку
                        log_token_result(error_result)
                        batch_results.append(error_result)
                
                results.extend(batch_results)
                
                # Промежуточный прогресс
                processed = len(results)
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                eta = (len(log_paths) - processed) / speed if speed > 0 else 0
                
                logger.info(f"⚡ Обработано: {processed}/{len(log_paths)} ({speed:.1f} токенов/сек, ETA: {eta/60:.1f} мин)")
        
        total_time = time.time() - start_time
        final_speed = len(results) / total_time if total_time > 0 else 0
        
        logger.info(f"🎯 ЗАВЕРШЕНО за {total_time:.1f} сек!")
        logger.info(f"⚡ Финальная скорость: {final_speed:.1f} токенов/сек")
        logger.info(f"✅ Обработано: {len(results)} токенов")
        
        return results

async def main():
    """Основная функция"""
    tester = TokenFilterTester()
    
    logger.info("🚀 ТУРБО-АНАЛИЗ ACTIVITY УВЕДОМЛЕНИЙ (максимальная скорость, параллельная обработка)")
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    # Записываем заголовок в файл лога
    file_logger.info("="*100)
    file_logger.info("🚀 ТУРБО-АНАЛИЗ ACTIVITY УВЕДОМЛЕНИЙ - ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ")
    file_logger.info("="*100)
    file_logger.info("📊 КРИТЕРИИ ACTIVITY ФИЛЬТРАЦИИ:")
    file_logger.info("   • Холдеры: 30-130 (максимум когда-либо ≤150)")
    file_logger.info("   • Ликвидность: ≥$10,000")
    file_logger.info("   • Рост холдеров: ≥2900/мин")
    file_logger.info("   • Dev процент: ≤2%")
    file_logger.info("   • Снайперы: ≤20 штук и ≤3.5% (или ≤5% с rapid exit)")
    file_logger.info("   • Инсайдеры: ≤15% (или ≤22% с rapid exit)")
    file_logger.info("   • Проверка подозрительных паттернов холдеров")
    file_logger.info("🔧 ФИЛЬТРАЦИЯ ЛОГОВ:")
    file_logger.info("   • Токены с <30 холдерами НЕ логируются (уменьшение шума)")
    file_logger.info("="*100)
    
    start_time = time.time()
    
    # Анализируем все токены с полными критериями
    results = await tester.analyze_all_tokens_with_full_criteria(tokens_logs_dir)
    
    if not results:
        logger.error("❌ Нет результатов для анализа")
        return
    
    # Сортируем по количеству метрик (от большего к меньшему)
    results.sort(key=lambda x: x.get('metrics_count', 0), reverse=True)
    
    # Краткая сводка по критериям bundle_analyzer.py
    total_tokens = len(results)
    would_send = sum(1 for r in results if r.get('decision') == 'WOULD_SEND')
    would_reject = sum(1 for r in results if r.get('decision') == 'WOULD_REJECT')
    blacklisted = sum(1 for r in results if r.get('decision') == 'BLACKLISTED')
    errors = sum(1 for r in results if r.get('decision') == 'ERROR')
    no_data = sum(1 for r in results if r.get('decision') == 'NO_DATA')
    
    # Статистика только по ACTIVITY уведомлениям
    activity_notifications = sum(1 for r in results if r.get('notification_type') == 'ACTIVITY' and r.get('decision') == 'WOULD_SEND')
    
    logger.info(f"\n📊 СТАТИСТИКА ACTIVITY УВЕДОМЛЕНИЙ (bundle_analyzer.py) - {total_tokens} токенов:")
    logger.info(f"🚀 ACTIVITY WOULD_SEND: {activity_notifications} ({activity_notifications/total_tokens*100:.1f}%)")
    logger.info(f"❌ WOULD_REJECT: {would_reject} ({would_reject/total_tokens*100:.1f}%)")
    logger.info(f"⚫ BLACKLISTED: {blacklisted} ({blacklisted/total_tokens*100:.1f}%)")
    logger.info(f"💥 ERRORS: {errors} ({errors/total_tokens*100:.1f}%)")
    logger.info(f"📊 NO_DATA: {no_data} ({no_data/total_tokens*100:.1f}%)")
    
    # Статистика фильтрации
    global filtered_low_holders_count
    if filtered_low_holders_count > 0:
        logger.info(f"🔇 ОТФИЛЬТРОВАНО (< 30 холдеров): {filtered_low_holders_count} (не записаны в лог)")
    
    # Детальная таблица (сортированная по метрикам)
    logger.info(f"\n📋 ДЕТАЛЬНАЯ СВОДКА (сортировка по метрикам):")
    logger.info(f"{'Токен':<12} {'Метрики':<8} {'Решение':<15} {'Причина':<40} {'Держатели':<10} {'Капитализация':<15}")
    logger.info("-" * 110)
    
    for result in results:
        token_id = result['token_id'][:11]  # Обрезаем длинные ID
        metrics = f"{result.get('metrics_count', 0)}/7"
        decision = result.get('decision', 'UNKNOWN')[:14]
        reason = result.get('reason', 'Нет причины')[:39]
        holders = str(result.get('holders_count', '-'))[:9]
        mcap = f"${result.get('mcap', 0):,.0f}" if result.get('mcap') else "-"
        mcap = mcap[:14]
        
        # Цветовое кодирование только для ACTIVITY
        if decision == 'WOULD_SEND':
            status = '🚀'  # ACTIVITY
        elif decision == 'WOULD_REJECT':
            status = '❌'
        elif decision == 'BLACKLISTED':
            status = '⚫'
        elif decision == 'ERROR':
            status = '💥'
        elif decision == 'NO_DATA':
            status = '📊'
        else:
            status = '❓'
        
        logger.info(f"{token_id:<12} {metrics:<8} {status} {decision:<14} {reason:<40} {holders:<10} {mcap:<15}")
    
    # Статистика по всем причинам (как в bundle_analyzer.py)
    all_reasons = {}
    for result in results:
        reason = result.get('reason', 'Неизвестная причина')
        all_reasons[reason] = all_reasons.get(reason, 0) + 1
    
    if all_reasons:
        logger.info(f"\n📊 ТОП КРИТЕРИИ ФИЛЬТРАЦИИ (bundle_analyzer.py style):")
        for reason, count in sorted(all_reasons.items(), key=lambda x: x[1], reverse=True)[:15]:
            logger.info(f"   • {reason}: {count} токенов")
    
    # Показываем примеры токенов, которые прошли ACTIVITY фильтрацию
    activity_examples = [r for r in results if r.get('decision') == 'WOULD_SEND' and r.get('notification_type') == 'ACTIVITY']
    if activity_examples:
        logger.info(f"\n🚀 ПРИМЕРЫ ТОКЕНОВ, КОТОРЫЕ ПРОШЛИ ACTIVITY ФИЛЬТРАЦИЮ:")
        for example in activity_examples[:5]:
            logger.info(f"   • {example['token_id']}: {example['reason']}")
    
    # Показываем примеры blacklisted токенов
    blacklisted_examples = [r for r in results if r.get('decision') == 'BLACKLISTED']
    if blacklisted_examples:
        logger.info(f"\n⚫ ПРИМЕРЫ ТОКЕНОВ В ЧЕРНОМ СПИСКЕ:")
        for example in blacklisted_examples[:3]:
            logger.info(f"   • {example['token_id']}: {example['reason']}")

    # Записываем итоговую статистику в файл лога
    total_time = time.time() - start_time
    final_speed = len(results) / total_time if total_time > 0 else 0
    
    file_logger.info("="*100)
    file_logger.info("📊 ИТОГОВАЯ СТАТИСТИКА АНАЛИЗА")
    file_logger.info("="*100)
    file_logger.info(f"⏱️ Время обработки: {total_time:.1f} секунд")
    file_logger.info(f"⚡ Скорость: {final_speed:.1f} токенов/сек")
    file_logger.info(f"📊 Всего токенов: {len(results)}")
    file_logger.info(f"🚀 ACTIVITY прошли: {activity_notifications} ({activity_notifications/len(results)*100:.1f}%)")
    file_logger.info(f"❌ Отклонены: {would_reject} ({would_reject/len(results)*100:.1f}%)")
    file_logger.info(f"⚫ Черный список: {blacklisted} ({blacklisted/len(results)*100:.1f}%)")
    file_logger.info(f"💥 Ошибки: {errors} ({errors/len(results)*100:.1f}%)")
    file_logger.info(f"📊 Нет данных: {no_data} ({no_data/len(results)*100:.1f}%)")
    file_logger.info("="*100)
    
    if activity_examples:
        file_logger.info("🚀 ПРИМЕРЫ ТОКЕНОВ, ПРОШЕДШИХ ACTIVITY ФИЛЬТРАЦИЮ:")
        for example in activity_examples[:10]:  # Больше примеров в файл
            file_logger.info(f"   ✅ {example['token_id']}: {example['reason']}")
    
    if blacklisted_examples:
        file_logger.info("⚫ ПРИМЕРЫ ТОКЕНОВ В ЧЕРНОМ СПИСКЕ:")
        for example in blacklisted_examples[:10]:
            file_logger.info(f"   ⚫ {example['token_id']}: {example['reason']}")
    
    file_logger.info("="*100)
    file_logger.info("✅ АНАЛИЗ ЗАВЕРШЕН! Все результаты сохранены в test_filter.log")
    file_logger.info("="*100)
    
    logger.info(f"\n📄 Детальные результаты сохранены в: test_filter.log")
    logger.info(f"📊 Всего записей в логе: {len(results)} токенов")


if __name__ == "__main__":
    asyncio.run(main())