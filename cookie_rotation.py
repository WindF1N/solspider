#!/usr/bin/env python3
"""
Система ротации cookies для Nitter
"""
import logging
import random
from typing import List

logger = logging.getLogger(__name__)

class CookieRotator:
    """Класс для ротации cookies (используется в pump_bot.py)"""
    
    def __init__(self):
        self.cookies = [
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTA4ODgwLCJpYXQiOjE3NDk1MDQwODAsIm5iZiI6MTc0OTUwNDAyMCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.S3Hm59re1huDxEqjiEe2jJfgEbMaTubvgLFlsaA9w3JMNyYBK1nRqYSEw1i6NBYrqKQcC8zLXPWb2u3O8mbODg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTA5MDgxLCJpYXQiOjE3NDk1MDQyODEsIm5iZiI6MTc0OTUwNDIyMSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.lKLIjlOfiXyjZSeg00hIBsyQVg20t4sZ-qe5WaM9noh7Xx9MVkuB6EqpD6ekg7TxsoPNHh9NGMOjCVUE3VlNCA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTA5MDk3LCJpYXQiOjE3NDk1MDQyOTcsIm5iZiI6MTc0OTUwNDIzNywibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.1_7sZqzuoKHWwvF3hQXaTIfoP1CCTSVcgmCQZCWMWSMdh5t1DSPMnF5soSCOGJDrb0km_RsYsoa1KyWU_9zwDA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTA5MTEwLCJpYXQiOjE3NDk1MDQzMTAsIm5iZiI6MTc0OTUwNDI1MCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.zrV9w3UorGwSliw740EMugdQV2WP0DmbHpS4j3KX_4PKjGw3qRhVJTEoqlUN1k3kUDTier8gxSnLR8dnDjLFDA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTA5MTI5LCJpYXQiOjE3NDk1MDQzMjksIm5iZiI6MTc0OTUwNDI2OSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.vh3-cQz6cAZLspZAB2VhP4N5pggm8PJDXe7BedP6Q-752o3M7_i16cBML13IeIobB78Bqwi0Ns_dUFIWnpkRAQ",
            "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTEwNTEwLCJpYXQiOjE3NDk1MDU3MTAsIm5iZiI6MTc0OTUwNTY1MCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.nkh-GbS0dOCua9dMKbQeVR3NF8pCeYg8j3Mk2qCVip7LhsAJMpFgjVIE4909DHCXWDm_SCNDDdr34ddILetKAQ"
        ]
        self.current_index = 0
        self.failed_cookies = set()  # Множество для отслеживания неработающих cookies
        logger.info(f"🍪 [PUMP_BOT] Инициализирован ротатор с {len(self.cookies)} cookies")
    
    def get_next_cookie(self) -> str:
        """Получает следующий cookie в ротации (исключая заблокированные)"""
        attempts = 0
        max_attempts = len(self.cookies)
        
        while attempts < max_attempts:
            cookie = self.cookies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.cookies)
            
            # Если cookie не в списке заблокированных, возвращаем его
            if cookie not in self.failed_cookies:
                cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
                logger.debug(f"🍪 [PUMP_BOT] Используем cookie #{self.current_index}: {cookie_short}")
                return cookie
            
            attempts += 1
        
        # Если все cookies заблокированы, сбрасываем список и начинаем заново
        logger.warning(f"⚠️ [PUMP_BOT] Все cookies заблокированы, сбрасываем список и начинаем заново")
        self.failed_cookies.clear()
        cookie = self.cookies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.cookies)
        return cookie
    
    def mark_cookie_failed(self, cookie: str):
        """Помечает cookie как неработающий"""
        self.failed_cookies.add(cookie)
        logger.warning(f"❌ [PUMP_BOT] Cookie помечен как неработающий (всего заблокировано: {len(self.failed_cookies)}/{len(self.cookies)})")
    
    def get_random_cookie(self) -> str:
        """Получает случайный работающий cookie"""
        available_cookies = [c for c in self.cookies if c not in self.failed_cookies]
        
        if not available_cookies:
            # Если все cookies заблокированы, сбрасываем и берем случайный
            logger.warning(f"⚠️ [PUMP_BOT] Все cookies заблокированы, сбрасываем список")
            self.failed_cookies.clear()
            available_cookies = self.cookies
        
        cookie = random.choice(available_cookies)
        cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
        logger.debug(f"🎲 [PUMP_BOT] Случайный cookie: {cookie_short}")
        return cookie
    
    def reset_failed_cookies(self):
        """Сбрасывает список заблокированных cookies"""
        failed_count = len(self.failed_cookies)
        self.failed_cookies.clear()
        logger.info(f"🔄 [PUMP_BOT] Сброшен список заблокированных cookies (было: {failed_count})")
    
    def get_cycle_cookie(self) -> str:
        """Получает cookie для целого цикла работы (не меняется в рамках цикла)"""
        cookie = self.get_next_cookie()
        cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
        logger.info(f"🔄 [PUMP_BOT] Cookie для нового цикла: #{self.current_index} - {cookie_short}")
        return cookie
    
    def get_stats(self) -> dict:
        """Возвращает статистику по cookies"""
        return {
            'total_cookies': len(self.cookies),
            'failed_cookies': len(self.failed_cookies),
            'available_cookies': len(self.cookies) - len(self.failed_cookies),
            'current_index': self.current_index
        }


class BackgroundCookieRotator:
    """Класс для ротации cookies для фонового мониторинга (используется в background_monitor.py)"""
    
    def __init__(self):
        self.cookies = [
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NDIwLCJpYXQiOjE3NDk1MDk2MjAsIm5iZiI6MTc0OTUwOTU2MCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.2QfRn5J3JnOv1Ked6IHA32vpGPuElJk64Z4ioihxUD16DkY5BBQCYCVbnzTXOSy3mzQGcfvgeAghL8NEGMsADA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NDQ1LCJpYXQiOjE3NDk1MDk2NDUsIm5iZiI6MTc0OTUwOTU4NSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.1U7gpZFKXCffJix2VWUGvPadeh4gtdoCUq8aHJOD1_S_-P7ei3PFYOzge0I0k3MAWHc-WPBPE8JFqQyZo6_jDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NDYxLCJpYXQiOjE3NDk1MDk2NjEsIm5iZiI6MTc0OTUwOTYwMSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.cEPa0bO_0RLDNOCNBMHhk9kQrw8-zZv8Wj8vUTR7YOAxkAb64mIr4wHaM1nfufuU18t6s3McNyM6Q7qruPiQAA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NDc4LCJpYXQiOjE3NDk1MDk2NzgsIm5iZiI6MTc0OTUwOTYxOCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.nQGLtA9LVzRcWUxHD36HMZ3TmjZswCFfXBW08DDZ2CeUibFNE2zFWO8FadiOjuupvdHmE-3yBB5j7kMVwkUyDQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NDk0LCJpYXQiOjE3NDk1MDk2OTQsIm5iZiI6MTc0OTUwOTYzNCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.XPUMbJSqYuwFjL9sqH9Zzy7_gHnjJS6JWAWFEOKCK4K2TDuGtdPrJ1am-UZGaKdDw7hhHyQevSq9Z0UBIdmxDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NTA1LCJpYXQiOjE3NDk1MDk3MDUsIm5iZiI6MTc0OTUwOTY0NSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.YtD4PrquA7N85S0Sk0zDqJqKJ24FJctlHvl28Eu2pRNLoC9UneiQDDvS88PWdjG61ikZ65rXX34c4N-VMXe7AA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NTIyLCJpYXQiOjE3NDk1MDk3MjIsIm5iZiI6MTc0OTUwOTY2Miwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.POGReTMFSdJLa-NW8WVjgZ75Ny7kCzLhA131DDzX3jz-eILG7q7BA1ToxZURsan7fWZRwKZBH5W6gjw85ta4CA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTE0NTM5LCJpYXQiOjE3NDk1MDk3MzksIm5iZiI6MTc0OTUwOTY3OSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.q042TlGg5zPxcOObxNyGFawEfOaeOqrc_HVpZdCrwuCOwmHAckNm76ohSF_H2PXqi4tXu32Gup_JHK4ei10GAQ"
        ]
        self.current_index = 0
        self.failed_cookies = set()  # Множество для отслеживания неработающих cookies
        logger.info(f"🍪 [BACKGROUND] Инициализирован ротатор с {len(self.cookies)} cookies")
    
    def get_next_cookie(self) -> str:
        """Получает следующий cookie в ротации (исключая заблокированные)"""
        attempts = 0
        max_attempts = len(self.cookies)
        
        while attempts < max_attempts:
            cookie = self.cookies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.cookies)
            
            # Если cookie не в списке заблокированных, возвращаем его
            if cookie not in self.failed_cookies:
                cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
                logger.debug(f"🍪 [BACKGROUND] Используем cookie #{self.current_index}: {cookie_short}")
                return cookie
            
            attempts += 1
        
        # Если все cookies заблокированы, сбрасываем список и начинаем заново
        logger.warning(f"⚠️ [BACKGROUND] Все cookies заблокированы, сбрасываем список и начинаем заново")
        self.failed_cookies.clear()
        cookie = self.cookies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.cookies)
        return cookie
    
    def mark_cookie_failed(self, cookie: str):
        """Помечает cookie как неработающий"""
        self.failed_cookies.add(cookie)
        logger.warning(f"❌ [BACKGROUND] Cookie помечен как неработающий (всего заблокировано: {len(self.failed_cookies)}/{len(self.cookies)})")
    
    def get_random_cookie(self) -> str:
        """Получает случайный работающий cookie"""
        available_cookies = [c for c in self.cookies if c not in self.failed_cookies]
        
        if not available_cookies:
            # Если все cookies заблокированы, сбрасываем и берем случайный
            logger.warning(f"⚠️ [BACKGROUND] Все cookies заблокированы, сбрасываем список")
            self.failed_cookies.clear()
            available_cookies = self.cookies
        
        cookie = random.choice(available_cookies)
        cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
        logger.debug(f"🎲 [BACKGROUND] Случайный cookie: {cookie_short}")
        return cookie
    
    def reset_failed_cookies(self):
        """Сбрасывает список заблокированных cookies"""
        failed_count = len(self.failed_cookies)
        self.failed_cookies.clear()
        logger.info(f"🔄 [BACKGROUND] Сброшен список заблокированных cookies (было: {failed_count})")
    
    def get_cycle_cookie(self) -> str:
        """Получает cookie для целого цикла работы (не меняется в рамках цикла)"""
        cookie = self.get_next_cookie()
        cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
        logger.info(f"🔄 Cookie для нового цикла: #{self.current_index} - {cookie_short}")
        return cookie
    
    def get_stats(self) -> dict:
        """Возвращает статистику по cookies"""
        return {
            'total_cookies': len(self.cookies),
            'failed_cookies': len(self.failed_cookies),
            'available_cookies': len(self.cookies) - len(self.failed_cookies),
            'current_index': self.current_index
        }


# Глобальные экземпляры ротаторов
cookie_rotator = CookieRotator()  # Для pump_bot.py
background_cookie_rotator = BackgroundCookieRotator()  # Для background_monitor.py 