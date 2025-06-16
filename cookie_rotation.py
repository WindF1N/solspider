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
        # Новые cookies для pump_bot от пользователя (обновлено 15.06.2025)
        self.cookies = [
            "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMTgwLCJpYXQiOjE3NDk1NjczODAsIm5iZiI6MTc0OTU2NzMyMCwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.MWX7n-_3j2AoCOgRT81RxDxHDh8nGeSyRVWDpOJTrNhN5nRkYLwGoIX7g0agIc4CKORDvVtF8G0kftQZzoTiCQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=961f682a331289503816193453b149e37456c837e1753d0fab0f583af3318a10; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5NjFmNjgyYTMzMTI4OTUwMzgxNjE5MzQ1M2IxNDllMzc0NTZjODM3ZTE3NTNkMGZhYjBmNTgzYWYzMzE4YTEwIiwiZXhwIjoxNzUwNjE2NTgwLCJpYXQiOjE3NTAwMTE3ODAsIm5iZiI6MTc1MDAxMTcyMCwibm9uY2UiOiIxNTg0NDAiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDU3YTIyOTM5ODg4ZDRhNmY0NDhhZjBjOWNiMjM5M2Q3MDczNzY4YTRlNWUzNzMyZTAwZWI1OWI1MGM3YyJ9.1oHKw6AF2QwPWmjdXtRDapL0b7MkaaLSJRNaam41OSRR1qEcpw_ChHbDBBvc5dk2WzHnrvyMprFZMSSu3rDTCg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=961f682a331289503816193453b149e37456c837e1753d0fab0f583af3318a10; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5NjFmNjgyYTMzMTI4OTUwMzgxNjE5MzQ1M2IxNDllMzc0NTZjODM3ZTE3NTNkMGZhYjBmNTgzYWYzMzE4YTEwIiwiZXhwIjoxNzUwNjE2NjMwLCJpYXQiOjE3NTAwMTE4MzAsIm5iZiI6MTc1MDAxMTc3MCwibm9uY2UiOiIxNTg0NDAiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDU3YTIyOTM5ODg4ZDRhNmY0NDhhZjBjOWNiMjM5M2Q3MDczNzY4YTRlNWUzNzMyZTAwZWI1OWI1MGM3YyJ9.9aoXYyWCmlTY8OiNTFY85c8DU5FTzzMcoJSLzUic4CvYbwpQYAMV5hxwJb9sQPDr6s1uXXlecsW-ygm9wvk8BA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=961f682a331289503816193453b149e37456c837e1753d0fab0f583af3318a10; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5NjFmNjgyYTMzMTI4OTUwMzgxNjE5MzQ1M2IxNDllMzc0NTZjODM3ZTE3NTNkMGZhYjBmNTgzYWYzMzE4YTEwIiwiZXhwIjoxNzUwNjE2Njg3LCJpYXQiOjE3NTAwMTE4ODcsIm5iZiI6MTc1MDAxMTgyNywibm9uY2UiOiIxNTg0NDAiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDU3YTIyOTM5ODg4ZDRhNmY0NDhhZjBjOWNiMjM5M2Q3MDczNzY4YTRlNWUzNzMyZTAwZWI1OWI1MGM3YyJ9.6Iq-_NvdlDMETXj0dIYbwySCR0nI4CQ2B0BAFXGYnhzRPR1ZRix_TzvfvAGugLbdFNE88wc1nmcvcPGX_iWfDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=961f682a331289503816193453b149e37456c837e1753d0fab0f583af3318a10; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5NjFmNjgyYTMzMTI4OTUwMzgxNjE5MzQ1M2IxNDllMzc0NTZjODM3ZTE3NTNkMGZhYjBmNTgzYWYzMzE4YTEwIiwiZXhwIjoxNzUwNjE2NzQxLCJpYXQiOjE3NTAwMTE5NDEsIm5iZiI6MTc1MDAxMTg4MSwibm9uY2UiOiIxNTg0NDAiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDU3YTIyOTM5ODg4ZDRhNmY0NDhhZjBjOWNiMjM5M2Q3MDczNzY4YTRlNWUzNzMyZTAwZWI1OWI1MGM3YyJ9.9R9oLSFpMOUUoTESNxTJmHoOLteYdSFFPhSdn9R-oF2c_AaGxKK4uYF4oXx_XuaW1MaWam7v7cvYL7QTyKD3BQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=961f682a331289503816193453b149e37456c837e1753d0fab0f583af3318a10; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5NjFmNjgyYTMzMTI4OTUwMzgxNjE5MzQ1M2IxNDllMzc0NTZjODM3ZTE3NTNkMGZhYjBmNTgzYWYzMzE4YTEwIiwiZXhwIjoxNzUwNjE2NzkyLCJpYXQiOjE3NTAwMTE5OTIsIm5iZiI6MTc1MDAxMTkzMiwibm9uY2UiOiIxNTg0NDAiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDU3YTIyOTM5ODg4ZDRhNmY0NDhhZjBjOWNiMjM5M2Q3MDczNzY4YTRlNWUzNzMyZTAwZWI1OWI1MGM3YyJ9.CEy4pv21fyKzV6WXmnTiJIr-s3D7tIFN2QydIFW8nwL-VTAg5JMjb_DHu4n4RZcCukysIGCgRmkStv-3L4v1Bw"
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
        # Новые cookies для background_monitor от пользователя (обновлено 15.06.2025)
        self.cookies = [
            "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTczOTM1LCJpYXQiOjE3NDk1NjkxMzUsIm5iZiI6MTc0OTU2OTA3NSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.IjRLPrd0ZqFONJKZIf9VorP0d_HiVOSfnbTXTT7ijpnCx21IE4zPaCJgxNY9VRiVrVvx64tXvpGukkQTLYQSCw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=16fda372b1b616277c793b5b7a3e08f72ddc3ed530f8fc6e194a6a66c8d76f7b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxNmZkYTM3MmIxYjYxNjI3N2M3OTNiNWI3YTNlMDhmNzJkZGMzZWQ1MzBmOGZjNmUxOTRhNmE2NmM4ZDc2ZjdiIiwiZXhwIjoxNzUwNjE1ODA4LCJpYXQiOjE3NTAwMTEwMDgsIm5iZiI6MTc1MDAxMDk0OCwibm9uY2UiOiI3ODQzOSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYjg5YmI0OTY3MzMyNWZjOGYzODdkNzQyYjk3YzA3Mzg1NWZkMzY2OTg3MDVlODAwNGQ5NGM2YTFkNjk0In0.04WnlxUqY6WfsRMLDd-4P8gQT2eac-e_ihuPndw5eSaTUWGAjVPQRhNF3-VfbIIr95AAzN7zZBCJmer71W-CDg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=16fda372b1b616277c793b5b7a3e08f72ddc3ed530f8fc6e194a6a66c8d76f7b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxNmZkYTM3MmIxYjYxNjI3N2M3OTNiNWI3YTNlMDhmNzJkZGMzZWQ1MzBmOGZjNmUxOTRhNmE2NmM4ZDc2ZjdiIiwiZXhwIjoxNzUwNjE1ODI3LCJpYXQiOjE3NTAwMTEwMjcsIm5iZiI6MTc1MDAxMDk2Nywibm9uY2UiOiI3ODQzOSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYjg5YmI0OTY3MzMyNWZjOGYzODdkNzQyYjk3YzA3Mzg1NWZkMzY2OTg3MDVlODAwNGQ5NGM2YTFkNjk0In0.vhxxUfEPWi-FaRPQ6WKACSVZ8eqnhscyI8UQNbP6B-qDLMea_pozj-gyFARml5O92gnKF7VQV8vK3b9BR5jPDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=16fda372b1b616277c793b5b7a3e08f72ddc3ed530f8fc6e194a6a66c8d76f7b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxNmZkYTM3MmIxYjYxNjI3N2M3OTNiNWI3YTNlMDhmNzJkZGMzZWQ1MzBmOGZjNmUxOTRhNmE2NmM4ZDc2ZjdiIiwiZXhwIjoxNzUwNjE1ODQwLCJpYXQiOjE3NTAwMTEwNDAsIm5iZiI6MTc1MDAxMDk4MCwibm9uY2UiOiI3ODQzOSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYjg5YmI0OTY3MzMyNWZjOGYzODdkNzQyYjk3YzA3Mzg1NWZkMzY2OTg3MDVlODAwNGQ5NGM2YTFkNjk0In0.ZWPQr3tKJawq5JZsqxtQwrZCHh8UaDQz6O8lMaVWevkOU-Y-UBLFEzIf1HUEuAJTQ6X_tYlrHemlroFxWyyuAQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=16fda372b1b616277c793b5b7a3e08f72ddc3ed530f8fc6e194a6a66c8d76f7b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxNmZkYTM3MmIxYjYxNjI3N2M3OTNiNWI3YTNlMDhmNzJkZGMzZWQ1MzBmOGZjNmUxOTRhNmE2NmM4ZDc2ZjdiIiwiZXhwIjoxNzUwNjE1ODU3LCJpYXQiOjE3NTAwMTEwNTcsIm5iZiI6MTc1MDAxMDk5Nywibm9uY2UiOiI3ODQzOSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYjg5YmI0OTY3MzMyNWZjOGYzODdkNzQyYjk3YzA3Mzg1NWZkMzY2OTg3MDVlODAwNGQ5NGM2YTFkNjk0In0.yb95x0dkJxYyZhIv7mcBI7Q-TcivFeUYM6-deBtn9tCjsay45cJ_78cRn2ANo1TBlMrbpQw0uDgbpt6aV8VUBQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=16fda372b1b616277c793b5b7a3e08f72ddc3ed530f8fc6e194a6a66c8d76f7b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxNmZkYTM3MmIxYjYxNjI3N2M3OTNiNWI3YTNlMDhmNzJkZGMzZWQ1MzBmOGZjNmUxOTRhNmE2NmM4ZDc2ZjdiIiwiZXhwIjoxNzUwNjE1OTA1LCJpYXQiOjE3NTAwMTExMDUsIm5iZiI6MTc1MDAxMTA0NSwibm9uY2UiOiI3ODQzOSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYjg5YmI0OTY3MzMyNWZjOGYzODdkNzQyYjk3YzA3Mzg1NWZkMzY2OTg3MDVlODAwNGQ5NGM2YTFkNjk0In0.L50Hp6WTAOcX6rpxW6QJ76duW7vD9BixyodPuj_9O9XLrNtQHir9xks6U1N039pJLdfFCHozgaYdYA0tRSI_Dw"
        ]
        self.current_index = 0
        self.failed_cookies = set()  # Множество для отслеживания неработающих cookies
        logger.info(f"🍪 [BACKGROUND] Инициализирован ротатор с {len(self.cookies)} cookies")
    
    def get_next_cookie(self) -> str:
        """Получает следующий cookie в ротации (исключая заблокированные)"""
        if not self.cookies:
            logger.error("❌ [BACKGROUND] НЕТ ДОСТУПНЫХ COOKIES! Все заблокированы Nitter'ом")
            return ""
            
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
        if not self.cookies:
            logger.error("❌ [BACKGROUND] НЕТ ДОСТУПНЫХ COOKIES! Все заблокированы Nitter'ом")
            return ""
            
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
        if not self.cookies:
            logger.error("❌ [BACKGROUND] НЕТ ДОСТУПНЫХ COOKIES! Нужно добавить новые рабочие cookies")
            return ""
            
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