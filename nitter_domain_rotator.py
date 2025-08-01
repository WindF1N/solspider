#!/usr/bin/env python3
"""
🔄 Система ротации доменов Nitter

Автоматически переключается между доменами при 429 ошибках
и распределяет нагрузку равномерно между всеми доступными доменами.
"""

import asyncio
import time
import random
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class DomainStats:
    """Статистика по домену"""
    domain: str
    total_requests: int = 0
    successful_requests: int = 0
    rate_limit_errors: int = 0  # 429 ошибки
    timeout_errors: int = 0  # timeout/connection ошибки
    last_rate_limit: Optional[datetime] = None
    last_timeout: Optional[datetime] = None
    consecutive_429s: int = 0
    consecutive_timeouts: int = 0
    avg_response_time: float = 0.0
    is_available: bool = True
    cooldown_until: Optional[datetime] = None

class NitterDomainRotator:
    """Ротатор доменов Nitter с умным переключением"""
    
    def __init__(self):
        # Протестированные рабочие домены (в порядке по скорости)
        self.domains = [
            "nitter.tiekoetter.com",        # Самый быстрый (0.29s) с Anubis
            "89.252.140.174"                # Прямой IP nitter.space (1.14s) без Anubis
        ]
        
        # Статистика по доменам
        self.domain_stats: Dict[str, DomainStats] = {}
        for domain in self.domains:
            self.domain_stats[domain] = DomainStats(domain=domain)
        
        # ИСПРАВЛЕНИЕ: Начинаем с случайного индекса чтобы избежать всегда одного домена после перезапуска
        self.current_index = random.randint(0, len(self.domains) - 1)
        
        # Настройки cooldown для 429 ошибок
        self.rate_limit_cooldown = 30  # секунд cooldown после 429
        self.max_consecutive_429s = 3  # максимум подряд 429 до долгого cooldown
        self.long_cooldown = 300  # 5 минут долгого cooldown
        
        # Настройки cooldown для timeout ошибок
        self.timeout_cooldown = 60  # секунд cooldown после timeout
        self.max_consecutive_timeouts = 3  # максимум подряд timeout до долгого cooldown
        self.timeout_long_cooldown = 180  # 3 минуты долгого cooldown
        
        # Настройки балансировки
        self.response_time_weight = 0.3  # вес времени ответа при выборе домена
        self.success_rate_weight = 0.7   # вес процента успеха
        
        logger.info(f"🔄 Инициализирован ротатор доменов: {', '.join(self.domains)}")
        logger.info(f"🎲 Начальный индекс: {self.current_index} (домен: {self.domains[self.current_index]})")
    
    def get_next_domain(self) -> str:
        """Получает следующий домен для использования (простая круговая ротация)"""
        
        # УПРОЩЕННАЯ ЛОГИКА: Просто поочередно используем домены
        domain = self.domains[self.current_index % len(self.domains)]
        selected_index = self.current_index % len(self.domains)
        self.current_index = (self.current_index + 1) % len(self.domains)
        
        logger.debug(f"🎯 Выбран домен: {domain} (индекс: {selected_index})")
        return domain
    
    def _select_best_domain(self, available_domains: List[str]) -> str:
        """Выбирает лучший домен из доступных"""
        
        if len(available_domains) == 1:
            return available_domains[0]
        
        # Простая ротация если статистики еще мало
        total_requests = sum(self.domain_stats[d].total_requests for d in available_domains)
        if total_requests < 10:
            # ИСПРАВЛЕНИЕ: Используем случайный выбор вместо круговой ротации
            # чтобы избежать всегда одного и того же домена после перезапусков
            domain = random.choice(available_domains)
            logger.debug(f"🎲 Случайный выбор домена (статистики мало): {domain}")
            return domain
        
        # Умный выбор на основе статистики
        best_domain = None
        best_score = -1
        best_domains = []  # Список доменов с лучшим score
        
        for domain in available_domains:
            stats = self.domain_stats[domain]
            score = self._calculate_domain_score(stats)
            
            logger.debug(f"📊 {domain}: score={score:.3f}")
            
            if score > best_score:
                best_score = score
                best_domain = domain
                best_domains = [domain]  # Новый лучший score
            elif score == best_score:
                best_domains.append(domain)  # Такой же score
        
        # Если несколько доменов имеют одинаковый лучший score, выбираем случайно
        if len(best_domains) > 1:
            selected = random.choice(best_domains)
            logger.debug(f"🎲 Случайный выбор из {len(best_domains)} доменов с одинаковым score: {selected}")
            return selected
        
        return best_domain or available_domains[0]
    
    def _calculate_domain_score(self, stats: DomainStats) -> float:
        """Вычисляет оценку домена для выбора"""
        
        if stats.total_requests == 0:
            return 1.0  # Новый домен получает высокий приоритет
        
        # Процент успеха (без учета 429 ошибок)
        non_rate_limit_requests = stats.total_requests - stats.rate_limit_errors
        if non_rate_limit_requests > 0:
            success_rate = stats.successful_requests / non_rate_limit_requests
        else:
            success_rate = 0.0
        
        # Штраф за недавние 429 ошибки
        rate_limit_penalty = 0.0
        if stats.last_rate_limit:
            minutes_since_429 = (datetime.now() - stats.last_rate_limit).total_seconds() / 60
            if minutes_since_429 < 5:  # Штраф в течение 5 минут
                rate_limit_penalty = 0.5 * (5 - minutes_since_429) / 5
        
        # Штраф за медленный ответ
        response_time_penalty = 0.0
        if stats.avg_response_time > 1.0:  # Если медленнее 1 секунды
            response_time_penalty = min(0.3, (stats.avg_response_time - 1.0) * 0.1)
        
        # Итоговая оценка
        score = success_rate - rate_limit_penalty - response_time_penalty
        
        # Бонус за стабильность (мало 429 ошибок)
        if stats.total_requests > 10:
            rate_limit_ratio = stats.rate_limit_errors / stats.total_requests
            if rate_limit_ratio < 0.1:  # Меньше 10% rate limit ошибок
                score += 0.2
        
        return max(0.0, score)
    
    def record_request_result(self, domain: str, success: bool, response_time: float, 
                            status_code: Optional[int] = None) -> None:
        """Записывает результат запроса для статистики"""
        
        if domain not in self.domain_stats:
            logger.warning(f"⚠️ Неизвестный домен: {domain}")
            return
        
        stats = self.domain_stats[domain]
        stats.total_requests += 1
        
        # Обновляем среднее время ответа
        if stats.total_requests == 1:
            stats.avg_response_time = response_time
        else:
            stats.avg_response_time = (stats.avg_response_time * (stats.total_requests - 1) + response_time) / stats.total_requests
        
        if success:
            stats.successful_requests += 1
            # Сбрасываем счетчики подряд идущих ошибок при успехе
            stats.consecutive_429s = 0
            stats.consecutive_timeouts = 0
            
        elif status_code == 429:
            stats.rate_limit_errors += 1
            stats.last_rate_limit = datetime.now()
            stats.consecutive_429s += 1
            
            # Только логируем ошибки, НЕ устанавливаем cooldown
            if stats.consecutive_429s >= self.max_consecutive_429s:
                logger.warning(f"🚫 {domain}: {stats.consecutive_429s} подряд 429 ошибок! (БЕЗ блокировки)")
            else:
                logger.warning(f"⏸️ {domain}: 429 ошибка! (БЕЗ блокировки)")
            
            # НЕ устанавливаем cooldown и НЕ блокируем домен
            # stats.cooldown_until = datetime.now() + timedelta(seconds=cooldown_duration)
            # stats.is_available = False
        
        elif status_code is None or status_code == 502:  # Timeout/Connection/502 ошибки
            stats.timeout_errors += 1
            stats.last_timeout = datetime.now()
            stats.consecutive_timeouts += 1
            
            # Только логируем ошибки, НЕ устанавливаем cooldown
            if stats.consecutive_timeouts >= self.max_consecutive_timeouts:
                logger.warning(f"⏰ {domain}: {stats.consecutive_timeouts} подряд timeout ошибок! (БЕЗ блокировки)")
            else:
                logger.warning(f"⏰ {domain}: timeout ошибка! (БЕЗ блокировки)")
            
            # НЕ устанавливаем cooldown и НЕ блокируем домен
            # stats.cooldown_until = datetime.now() + timedelta(seconds=cooldown_duration)
            # stats.is_available = False
        
        logger.debug(f"📈 {domain}: {stats.successful_requests}/{stats.total_requests} успех, "
                    f"429: {stats.rate_limit_errors}, timeout: {stats.timeout_errors}, время: {stats.avg_response_time:.2f}с")
    
    def get_domain_statistics(self) -> Dict[str, Dict]:
        """Возвращает статистику по всем доменам"""
        
        result = {}
        now = datetime.now()
        
        for domain, stats in self.domain_stats.items():
            success_rate = (stats.successful_requests / max(stats.total_requests, 1)) * 100
            
            cooldown_remaining = 0
            if stats.cooldown_until and now < stats.cooldown_until:
                cooldown_remaining = (stats.cooldown_until - now).total_seconds()
            
            result[domain] = {
                'total_requests': stats.total_requests,
                'successful_requests': stats.successful_requests,
                'success_rate': f"{success_rate:.1f}%",
                'rate_limit_errors': stats.rate_limit_errors,
                'timeout_errors': stats.timeout_errors,
                'consecutive_429s': stats.consecutive_429s,
                'consecutive_timeouts': stats.consecutive_timeouts,
                'avg_response_time': f"{stats.avg_response_time:.2f}s",
                'is_available': stats.is_available,
                'cooldown_remaining': f"{cooldown_remaining:.1f}s" if cooldown_remaining > 0 else "none",
                'score': f"{self._calculate_domain_score(stats):.3f}"
            }
        
        return result
    
    def reset_domain_stats(self, domain: Optional[str] = None) -> None:
        """Сбрасывает статистику домена или всех доменов"""
        
        if domain:
            if domain in self.domain_stats:
                self.domain_stats[domain] = DomainStats(domain=domain)
                logger.info(f"🔄 Статистика {domain} сброшена")
        else:
            for d in self.domains:
                self.domain_stats[d] = DomainStats(domain=d)
            logger.info("🔄 Статистика всех доменов сброшена")
    
    def force_enable_domain(self, domain: str) -> bool:
        """Принудительно включает домен (убирает cooldown)"""
        
        if domain not in self.domain_stats:
            return False
        
        stats = self.domain_stats[domain]
        stats.cooldown_until = None
        stats.consecutive_429s = 0
        stats.consecutive_timeouts = 0
        stats.is_available = True
        
        logger.info(f"🔓 Домен {domain} принудительно включен")
        return True

# Глобальный экземпляр ротатора
domain_rotator = NitterDomainRotator()

def reload_domain_rotator():
    """Перезагружает глобальный экземпляр ротатора с новыми доменами"""
    global domain_rotator
    domain_rotator = NitterDomainRotator()
    logger.info("🔄 Ротатор доменов перезагружен с новыми доменами")

def get_next_nitter_domain() -> str:
    """Получает следующий домен Nitter для использования"""
    return domain_rotator.get_next_domain()

def record_nitter_request_result(domain: str, success: bool, response_time: float, 
                                status_code: Optional[int] = None) -> None:
    """Записывает результат запроса к Nitter домену"""
    domain_rotator.record_request_result(domain, success, response_time, status_code)

def get_nitter_domain_stats() -> Dict[str, Dict]:
    """Возвращает статистику по доменам Nitter"""
    return domain_rotator.get_domain_statistics()

def reset_nitter_domain_stats(domain: Optional[str] = None) -> None:
    """Сбрасывает статистику доменов Nitter"""
    domain_rotator.reset_domain_stats(domain)

def force_enable_nitter_domain(domain: str) -> bool:
    """Принудительно включает домен Nitter"""
    return domain_rotator.force_enable_domain(domain)

def get_all_nitter_domains() -> List[str]:
    """Возвращает список всех доменов Nitter"""
    return domain_rotator.domains.copy()

def get_best_nitter_domains(limit: int = 5) -> List[str]:
    """Возвращает список лучших доменов Nitter по статистике"""
    stats = domain_rotator.get_domain_statistics()
    
    # Сортируем домены по качеству (успешность + скорость)
    sorted_domains = []
    for domain, domain_stats in stats.items():
        # Убираем проверку is_available - используем все домены
        # if not domain_stats.get('is_available', True):
        #     continue
            
        total_requests = domain_stats.get('total_requests', 0)
        successful_requests = domain_stats.get('successful_requests', 0)
        avg_response_time = domain_stats.get('avg_response_time', 999.0)
        consecutive_429s = domain_stats.get('consecutive_429s', 0)
        consecutive_timeouts = domain_stats.get('consecutive_timeouts', 0)
        
        # Рассчитываем score (чем выше, тем лучше)
        if total_requests == 0:
            # Новые домены получают средний приоритет
            score = 50.0
        else:
            success_rate = successful_requests / total_requests
            # Штрафуем за медленную работу и частые ошибки
            speed_penalty = min(avg_response_time / 10.0, 50.0)  # Максимум 50 очков штрафа
            error_penalty = (consecutive_429s + consecutive_timeouts) * 5
            
            score = (success_rate * 100) - speed_penalty - error_penalty
        
        sorted_domains.append((domain, score))
    
    # Сортируем по score (лучшие первыми)
    sorted_domains.sort(key=lambda x: x[1], reverse=True)
    
    # Возвращаем только домены, ограничивая количество
    return [domain for domain, score in sorted_domains[:limit]]

def get_domain_count() -> int:
    """Возвращает общее количество доменов Nitter"""
    return len(domain_rotator.domains) 