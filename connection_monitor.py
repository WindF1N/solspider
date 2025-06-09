import asyncio
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ConnectionStats:
    """Статистика соединения"""
    connected_at: datetime
    total_messages: int = 0
    last_message_at: Optional[datetime] = None
    disconnections: int = 0
    reconnections: int = 0
    ping_failures: int = 0
    last_ping_time: Optional[float] = None
    avg_ping_time: float = 0.0
    
    def update_message_received(self):
        """Обновляет статистику при получении сообщения"""
        self.total_messages += 1
        self.last_message_at = datetime.now()
    
    def update_ping(self, ping_time: float):
        """Обновляет статистику ping"""
        self.last_ping_time = ping_time
        if self.avg_ping_time == 0:
            self.avg_ping_time = ping_time
        else:
            # Скользящее среднее
            self.avg_ping_time = (self.avg_ping_time * 0.9) + (ping_time * 0.1)
    
    def get_uptime(self) -> timedelta:
        """Возвращает время работы соединения"""
        return datetime.now() - self.connected_at
    
    def get_messages_per_minute(self) -> float:
        """Возвращает среднее количество сообщений в минуту"""
        uptime_minutes = self.get_uptime().total_seconds() / 60
        if uptime_minutes > 0:
            return self.total_messages / uptime_minutes
        return 0.0

class ConnectionMonitor:
    """Монитор состояния WebSocket соединения"""
    
    def __init__(self):
        self.stats = None
        self.connection_quality = "unknown"
        self.quality_history = []
        
    def connection_established(self):
        """Вызывается при установке соединения"""
        self.stats = ConnectionStats(connected_at=datetime.now())
        logger.info("📊 Мониторинг соединения запущен")
    
    def connection_lost(self):
        """Вызывается при потере соединения"""
        if self.stats:
            self.stats.disconnections += 1
            uptime = self.stats.get_uptime()
            logger.info(f"📊 Соединение потеряно после {uptime}")
    
    def message_received(self):
        """Вызывается при получении сообщения"""
        if self.stats:
            self.stats.update_message_received()
    
    async def ping_test(self, websocket) -> float:
        """Выполняет ping тест и возвращает время ответа"""
        try:
            start_time = time.time()
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=10)
            ping_time = (time.time() - start_time) * 1000  # в миллисекундах
            
            if self.stats:
                self.stats.update_ping(ping_time)
            
            return ping_time
            
        except Exception as e:
            if self.stats:
                self.stats.ping_failures += 1
            logger.warning(f"❌ Ping тест неудачен: {e}")
            return -1
    
    def assess_connection_quality(self) -> str:
        """Оценивает качество соединения"""
        if not self.stats:
            return "unknown"
        
        # Критерии оценки качества
        issues = []
        
        # Проверяем время последнего сообщения
        if self.stats.last_message_at:
            time_since_message = (datetime.now() - self.stats.last_message_at).total_seconds()
            if time_since_message > 300:  # 5 минут
                issues.append("no_messages")
        
        # Проверяем ping
        if self.stats.last_ping_time:
            if self.stats.last_ping_time > 1000:  # >1 секунды
                issues.append("high_latency")
            if self.stats.avg_ping_time > 500:  # >500ms среднее
                issues.append("avg_high_latency")
        
        # Проверяем количество неудачных ping'ов
        if self.stats.ping_failures > 3:
            issues.append("ping_failures")
        
        # Проверяем частоту сообщений
        msg_per_min = self.stats.get_messages_per_minute()
        if msg_per_min < 0.1:  # Меньше 1 сообщения в 10 минут
            issues.append("low_activity")
        
        # Определяем общее качество
        if len(issues) == 0:
            quality = "excellent"
        elif len(issues) <= 1:
            quality = "good"
        elif len(issues) <= 2:
            quality = "fair"
        else:
            quality = "poor"
        
        self.connection_quality = quality
        self.quality_history.append({
            'time': datetime.now(),
            'quality': quality,
            'issues': issues.copy()
        })
        
        # Ограничиваем историю
        if len(self.quality_history) > 100:
            self.quality_history = self.quality_history[-50:]
        
        return quality
    
    def get_stats_summary(self) -> dict:
        """Возвращает сводку статистики"""
        if not self.stats:
            return {"status": "disconnected"}
        
        uptime = self.stats.get_uptime()
        quality = self.assess_connection_quality()
        
        return {
            "status": "connected",
            "uptime_seconds": uptime.total_seconds(),
            "uptime_formatted": str(uptime).split('.')[0],  # Без микросекунд
            "total_messages": self.stats.total_messages,
            "messages_per_minute": round(self.stats.get_messages_per_minute(), 2),
            "disconnections": self.stats.disconnections,
            "ping_failures": self.stats.ping_failures,
            "last_ping_ms": self.stats.last_ping_time,
            "avg_ping_ms": round(self.stats.avg_ping_time, 1),
            "connection_quality": quality,
            "last_message_ago": (
                (datetime.now() - self.stats.last_message_at).total_seconds()
                if self.stats.last_message_at else None
            )
        }
    
    def format_stats_message(self) -> str:
        """Форматирует статистику для отправки в Telegram"""
        stats = self.get_stats_summary()
        
        if stats["status"] == "disconnected":
            return "❌ <b>Соединение отсутствует</b>"
        
        quality_emoji = {
            "excellent": "🟢",
            "good": "🟡", 
            "fair": "🟠",
            "poor": "🔴"
        }
        
        emoji = quality_emoji.get(stats["connection_quality"], "⚪")
        
        # Безопасное форматирование значений
        ping_str = f"{stats['last_ping_ms']:.0f}ms" if stats['last_ping_ms'] is not None else "не измерен"
        avg_ping_str = f"{stats['avg_ping_ms']:.0f}ms" if stats['avg_ping_ms'] > 0 else "не измерен"
        
        message = (
            f"{emoji} <b>Статистика соединения</b>\n\n"
            f"⏱️ <b>Время работы:</b> {stats['uptime_formatted']}\n"
            f"📨 <b>Сообщений:</b> {stats['total_messages']:,}\n"
            f"📊 <b>Частота:</b> {stats['messages_per_minute']} сообщ/мин\n"
            f"🏓 <b>Ping:</b> {ping_str} "
            f"(среднее: {avg_ping_str})\n"
            f"🔄 <b>Переподключений:</b> {stats['disconnections']}\n"
            f"❌ <b>Ошибок ping:</b> {stats['ping_failures']}\n"
            f"🎯 <b>Качество:</b> {stats['connection_quality']}"
        )
        
        if stats["last_message_ago"]:
            message += f"\n📥 <b>Последнее сообщение:</b> {stats['last_message_ago']:.0f}с назад"
        
        return message

# Глобальный экземпляр монитора
connection_monitor = ConnectionMonitor() 