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
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4MzYwLCJpYXQiOjE3NDk1NjM1NjAsIm5iZiI6MTc0OTU2MzUwMCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.crxJEq7qXZQ1w_8exz7mrbZQh1L1MocYUz08X4q6XFFxtjiYmWYQ7P6Ba7SEG8OazxGOjuOJ_clFM6xWbHIIAw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDA2LCJpYXQiOjE3NDk1NjM2MDYsIm5iZiI6MTc0OTU2MzU0Niwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.WNF7BxglR4P-AmRVsF6uFVXDP0vcNqkepU2bRIG6Ci03Yo1mzXw9z-DZ1ctMwLq3Wrrnfm61p8gAjwPJsskRAA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDE4LCJpYXQiOjE3NDk1NjM2MTgsIm5iZiI6MTc0OTU2MzU1OCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.9bHIbLAZsVaQpMoCxUqN2mUU5HoLmx5ljvX3TxTA-c55I6lWLBqmrk79cxb7xoA2B9ttXcojJDAwn61jvEyhAg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDMyLCJpYXQiOjE3NDk1NjM2MzIsIm5iZiI6MTc0OTU2MzU3Miwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.R52aFYTmzyyOsXY21iRtlHuFLLFixpvtXYtD6Ta1RfSJqBVkTJ-S963i1ImUTgmQAyicTlS6B47mL2nDj6WlAw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDUwLCJpYXQiOjE3NDk1NjM2NTAsIm5iZiI6MTc0OTU2MzU5MCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.zhOFgUXPLkNzGTwi9LeTcGVfjWqSw5Q9Y7ug2eNLtVCBOtCi-MT5fVDf8GEq3RkSoBSgyLVKvm5eAQO_SqoVBw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDY5LCJpYXQiOjE3NDk1NjM2NjksIm5iZiI6MTc0OTU2MzYwOSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.JQ2rGsiJoQeyqQhCq5QGWcHxOzOpAThtSL_nHEO2p5BzVSY3fekgM-RGoxh3E_WghwKfk0UGe0M7JDm3g_4PAg"
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
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDg0LCJpYXQiOjE3NDk1NjM2ODQsIm5iZiI6MTc0OTU2MzYyNCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.Rs0ylL48P2Koc_Ig4B3V6BLB9RDoYhstBSc5IwYQwbBRKsRKme3cnKinSmVnEews27bM9ZOqVR1jEHvBt4FxDQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NDk4LCJpYXQiOjE3NDk1NjM2OTgsIm5iZiI6MTc0OTU2MzYzOCwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.83-tKXobFmdVlGrAoHQC7G5EkFnqCEuxV6swM8xHnwUWLVzQkiVzJ5s23lKWNh3rXA_6pyRdlBYrJW0z2puABQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NTEyLCJpYXQiOjE3NDk1NjM3MTIsIm5iZiI6MTc0OTU2MzY1Miwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OWVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.EepOW5UG1c_AxwGURTGBqkY0JMbVKxKibydA2B6zJSmRV8eAMhU8LHd_63ejN94gytHDmjO_d54sZ_aYEUYVDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NTI2LCJpYXQiOjE3NDk1NjM3MjYsIm5iZiI6MTc0OTU2MzY2Niwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.GDmHT1lzDhayg3aDF3dOJBG3dtKbge2T35ERvDjPC9C6bIdq95jQHyAlqAj0asYfxqbcz7zJeksfNiAfoO6nCg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NTM3LCJpYXQiOjE3NDk1NjM3MzcsIm5iZiI6MTc0OTU2MzY3Nywibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.O0RXZ0GTnkM8xW5xy2gXoV6Bw_-4UTgEnd2b8J5TYampKNt9MLc-Macz1UYOIWfoOCUcYttDiH0_MJlF_nbWBw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NTU2LCJpYXQiOjE3NDk1NjM3NTYsIm5iZiI6MTc0OTU2MzY5Niwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.MDZMBDOacCJZPKMYQ0ffWNod6X-DAivi6-xBHmFIuGXTE79UzHv2gP3_lIi5NIZ6D1TM756X8etFbexe6pTbBQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NTgzLCJpYXQiOjE3NDk1NjM3ODMsIm5iZiI6MTc0OTU2MzcyMywibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.OIawVCcQAcfw5vr4TRJQr3iJ9Mf726_perjvXv12GHjk0T5WQ110ddcs-W4gweD8jfYHBV69-WJm0qcltvH-Cw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NTk5LCJpYXQiOjE3NDk1NjM3OTksIm5iZiI6MTc0OTU2MzczOSwibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OGVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.8SdAs1_3u0-9BC3e4uoWwycGLmBgVnusUYoUjtAjtsQImKvFFHreJI7Kn4W0GRIrAvVEnR1PMrRztBof9U-zDA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=182c6afe4a7b50575ee9f8e9028ccb210ddaf0792c8ff05237f756d196ccc1e8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxODJjNmFmZTRhN2I1MDU3NWVlOWY4ZTkwMjhjY2IyMTBkZGFmMDc5MmM4ZmYwNTIzN2Y3NTZkMTk2Y2NjMWU4IiwiZXhwIjoxNzUwMTY4NjEzLCJpYXQiOjE3NDk1NjM4MTMsIm5iZiI6MTc0OTU2Mzc1Mywibm9uY2UiOiI3OTc5OSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMzlhZGZjMjM4YTdjY2Y1OWVhMzc3NmM0MThkODE1YjllNDZjMzgxOGVhMzhmZjcyYTE1YTViNDg3ZmI5In0.zo-qzxZDcvP_t9e7G_JP8jjT7nrA_nvow4li7FnPLimpwbnrLZwZwL3EHfiXwy2Nsh1RwSAbEtHwUdT19kn3Ag"
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