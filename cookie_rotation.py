#!/usr/bin/env python3
"""
Система ротации cookies и прокси для Nitter
"""
import logging
import random
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class ProxyCookieRotator:
    """Класс для ротации связок прокси+cookies (используется в pump_bot.py)"""
    
    def __init__(self):
        # Обновленные связки прокси+cookies от пользователя (17.06.2025)
        self.proxy_cookie_pairs = [
            # Без прокси
            {
                "proxy": None,
                "cookie": "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4Mjc3YWEzYjA5Y2FlM2U1YzMzMDU3MWY4YWFlMjc2ZjRjM2QyNmZhMjRiYzExYjBiNzVlNjA4ODBmNDJhNzQwIiwiZXhwIjoxNzUwNjE3NTc3LCJpYXQiOjE3NTAwMTI3NzcsIm5iZiI6MTc1MDAxMjcxNywibm9uY2UiOiI2MzU4IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBjMWNiYWQzOTZhNDZiMjRmNTMwZmRlNzY0MTljYjY2NDQyOTQyMTI5MmEyYzdjMzQzN2U3ZDFjMjUwZjgifQ.sMThBhNTakbILW9NwtJPBo0t9Piai9GE6Hnrg89bLErsawZE77mkEeZ-KDyvJEM8gYug7r9zM5x0EYm8XpodBA"
            },
            # С прокси user291921:9ikrxg@45.12.115.17:1367
            {
                "proxy": "http://user291921:9ikrxg@45.12.115.17:1367",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=8acecc56026667b601911fe3c8cc05c35a0c3f112f8cebe2c50e694af54ce68c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4YWNlY2M1NjAyNjY2N2I2MDE5MTFmZTNjOGNjMDVjMzVhMGMzZjExMmY4Y2ViZTJjNTBlNjk0YWY1NGNlNjhjIiwiZXhwIjoxNzUwNzk4ODk4LCJpYXQiOjE3NTAxOTQwOTgsIm5iZiI6MTc1MDE5NDAzOCwibm9uY2UiOiIxMTQ4ODQiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDE1NDZmMDFmZWY5NTRlMGY3OTMzZTM3YjE1YWE4NGQxNzIwMGEwODI2MmNkNWMyYzEwMzNlM2E1MmRhOSJ9.r25UvTP41abhmSxFyrXsnuxd8AYIi2atQvCH5LCTjqHSembltEiej4gp_SeHcKWBnvSvO6FZrkEqO5rAwrN5Cw"
            },
            # С прокси user291921:9ikrxg@45.8.156.99:1416
            {
                "proxy": "http://user291921:9ikrxg@45.8.156.99:1416",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=0a08c72769aaf09a93283b61ebc69e4762106fb6f85cfca73e94f1c06f574b40; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIwYTA4YzcyNzY5YWFmMDlhOTMyODNiNjFlYmM2OWU0NzYyMTA2ZmI2Zjg1Y2ZjYTczZTk0ZjFjMDZmNTc0YjQwIiwiZXhwIjoxNzUwNzk5MDQ3LCJpYXQiOjE3NTAxOTQyNDcsIm5iZiI6MTc1MDE5NDE4Nywibm9uY2UiOiI0MjEyMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYTkxM2VhZjMxY2U0MTAyMGJlZmNjYTZhMWRlZDA5ZjQxMGI0MjI3ODc2ZDVjYWI2OTUwOTJmYjA4MGFmIn0.6DDwQFmhwTAfyjbAr1czHszYBlZf60_-U3yR1xtJxCx6KMLN3m3utUSQqVq3PDE7dwWLOw_UaoSgoeSg5q6CAw"
            },
            # С прокси user291921:9ikrxg@37.221.80.235:1416
            {
                "proxy": "http://user291921:9ikrxg@37.221.80.235:1416",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f6b8341a5676cb9d04f5e7327b542770131f8cce7fd873ff2410c252771b6195; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNmI4MzQxYTU2NzZjYjlkMDRmNWU3MzI3YjU0Mjc3MDEzMWY4Y2NlN2ZkODczZmYyNDEwYzI1Mjc3MWI2MTk1IiwiZXhwIjoxNzUwNzk5MTg5LCJpYXQiOjE3NTAxOTQzODksIm5iZiI6MTc1MDE5NDMyOSwibm9uY2UiOiI1OTk3IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDAxZTAzNDQyZDc0MTdiMjU1OTE4OGI2MzQzZDBkNDllMGVjMzRlMDQ0OTZlOGJmNDFhMjQ3MzMxNzNhNjAifQ.vkqDpDAtnXqdgYpVYzOSckAaeMDfqs1oFm59noe3axwcQ1ZUqTI0IzxmMsEpCFHnKr3kT3DF6QveZpuc3aOyCg"
            },
            # С прокси user291921:9ikrxg@149.126.240.31:1416
            {
                "proxy": "http://user291921:9ikrxg@149.126.240.31:1416",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f142216877a946d6bcb3b746b3b22f86a2e51da316d7222bc78a7ce6c6499234; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmMTQyMjE2ODc3YTk0NmQ2YmNiM2I3NDZiM2IyMmY4NmEyZTUxZGEzMTZkNzIyMmJjNzhhN2NlNmM2NDk5MjM0IiwiZXhwIjoxNzUwNzk5Mjg2LCJpYXQiOjE3NTAxOTQ0ODYsIm5iZiI6MTc1MDE5NDQyNiwibm9uY2UiOiI4MjA2IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA5NWZlYTFmNDYzNzY3YmI1NmQ4M2Q0Yzc2ZjVhMmJjOGFjZGM3NjFkOGQzZTYwOTI0YTNlZTVhMTVhZWEifQ.gbCe5V2xs5bXnJWS2lgpfaOkuaetKI5tL1HLLS6Ilg5KyznFkqSwm5SF_kV6S0B1hKq-OQvMVCGAfveToKcUCg"
            },
            # С прокси user291921:9ikrxg@194.32.124.66:2514
            {
                "proxy": "http://user291921:9ikrxg@194.32.124.66:2514",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=b3c7b9c45350e0a8349506d6c3ee7067dde25271b3fbe829b1d6bebed2181cd8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiM2M3YjljNDUzNTBlMGE4MzQ5NTA2ZDZjM2VlNzA2N2RkZTI1MjcxYjNmYmU4MjliMWQ2YmViZWQyMTgxY2Q4IiwiZXhwIjoxNzUwNzk5MzU2LCJpYXQiOjE3NTAxOTQ1NTYsIm5iZiI6MTc1MDE5NDQ5Niwibm9uY2UiOiIyMTkwMzQiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDYzMTQ5OTk3N2JhMjdkMWU4M2I1ZTdiNjkwNTIzM2VmOGNlZDFmZGE0ZTAyNGY4YmE1N2ZlNDMyNzdkYSJ9.JK-BCyjxAd2L5-_VkGM_0aA1gmb3UDUE7DbwUD4UztcZpJp0NTEVdabKYIpsDGac7kdobidM_KpICt-sf6HUCg"
            },
            # С прокси user291921:9ikrxg@213.166.92.96:2514
            {
                "proxy": "http://user291921:9ikrxg@213.166.92.96:2514",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=ce242ad2c8779dc1d83e59db4dc6847cbffeed6ed72679d2589d2de59ca80a9d; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJjZTI0MmFkMmM4Nzc5ZGMxZDgzZTU5ZGI0ZGM2ODQ3Y2JmZmVlZDZlZDcyNjc5ZDI1ODlkMmRlNTljYTgwYTlkIiwiZXhwIjoxNzUwNzk5NDA2LCJpYXQiOjE3NTAxOTQ2MDYsIm5iZiI6MTc1MDE5NDU0Niwibm9uY2UiOiI2NzE2OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMWRlM2NjYmFhMGY0OTRmMjA0YzAxMmIxOTQ2MTkzMGZmYmExMjQ4NjMwM2MyOGJmYzQ4NzIxNjNjYmUwIn0.LN75eORPbBA80BV16hPg1JJBzwrT9ClbXBdO2Zyd0mgvW7FWUHNmpUpflJZ7XJtfP8yuWDm3DeWf1UT8hiQGDA"
            },
            # С прокси user291921:9ikrxg@149.126.227.4:2514
            {
                "proxy": "http://user291921:9ikrxg@149.126.227.4:2514",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=06bf91ac4e14207e08e33fc4d1fe198ef1371b50136b7a412811182cadcb77a2; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIwNmJmOTFhYzRlMTQyMDdlMDhlMzNmYzRkMWZlMTk4ZWYxMzcxYjUwMTM2YjdhNDEyODExMTgyY2FkY2I3N2EyIiwiZXhwIjoxNzUwNzk5NDgwLCJpYXQiOjE3NTAxOTQ2ODAsIm5iZiI6MTc1MDE5NDYyMCwibm9uY2UiOiIxMjU0NjgiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDdjMWE3YWJiYTIyYjMzMjI2NjU2YTA2M2MyNWMwMzI5Mjg4OTk5OTNhYWJlNjViOWJmOWU5YWI2NmE3NiJ9.ShZXfE7FoM2KjhYhbF5jE8dbUASw80I6_be4Caw5_E6IGSSL0Fy7HhsymawMo79qjENklXDx_-IBQpJ-lN42DQ"
            }
        ]
        self.current_index = 0
        self.failed_pairs = set()  # Множество для отслеживания неработающих связок
        logger.info(f"🍪🌐 [PUMP_BOT] Инициализирован ротатор с {len(self.proxy_cookie_pairs)} прокси+cookie связками")
    
    def get_next_proxy_cookie(self) -> Tuple[Optional[str], str]:
        """Получает следующую связку прокси+cookie в ротации (исключая заблокированные)"""
        attempts = 0
        max_attempts = len(self.proxy_cookie_pairs)
        
        while attempts < max_attempts:
            pair = self.proxy_cookie_pairs[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxy_cookie_pairs)
            
            # Создаем идентификатор связки для проверки
            pair_id = f"{pair['proxy']}|{pair['cookie'][:50]}"
            
            # Если связка не в списке заблокированных, возвращаем её
            if pair_id not in self.failed_pairs:
                proxy_info = f"NO_PROXY" if pair['proxy'] is None else pair['proxy'].split('@')[1]
                cookie_short = pair['cookie'][:50] + "..." if len(pair['cookie']) > 50 else pair['cookie']
                logger.debug(f"🍪🌐 [PUMP_BOT] Используем связку #{self.current_index}: {proxy_info} + {cookie_short}")
                return pair['proxy'], pair['cookie']
            
            attempts += 1
        
        # Если все связки заблокированы, сбрасываем список и начинаем заново
        logger.warning(f"⚠️ [PUMP_BOT] Все прокси+cookie связки заблокированы, сбрасываем список")
        self.failed_pairs.clear()
        pair = self.proxy_cookie_pairs[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxy_cookie_pairs)
        return pair['proxy'], pair['cookie']
    
    def mark_pair_failed(self, proxy: Optional[str], cookie: str):
        """Помечает связку прокси+cookie как неработающую"""
        pair_id = f"{proxy}|{cookie[:50]}"
        self.failed_pairs.add(pair_id)
        proxy_info = f"NO_PROXY" if proxy is None else proxy.split('@')[1]
        logger.warning(f"❌ [PUMP_BOT] Связка помечена как неработающая: {proxy_info} (всего заблокировано: {len(self.failed_pairs)}/{len(self.proxy_cookie_pairs)})")
    
    def get_random_proxy_cookie(self) -> Tuple[Optional[str], str]:
        """Получает случайную работающую связку прокси+cookie"""
        available_pairs = []
        for pair in self.proxy_cookie_pairs:
            pair_id = f"{pair['proxy']}|{pair['cookie'][:50]}"
            if pair_id not in self.failed_pairs:
                available_pairs.append(pair)
        
        if not available_pairs:
            # Если все связки заблокированы, сбрасываем и берем случайную
            logger.warning(f"⚠️ [PUMP_BOT] Все прокси+cookie связки заблокированы, сбрасываем список")
            self.failed_pairs.clear()
            available_pairs = self.proxy_cookie_pairs
        
        pair = random.choice(available_pairs)
        proxy_info = f"NO_PROXY" if pair['proxy'] is None else pair['proxy'].split('@')[1]
        cookie_short = pair['cookie'][:50] + "..." if len(pair['cookie']) > 50 else pair['cookie']
        logger.debug(f"🎲 [PUMP_BOT] Случайная связка: {proxy_info} + {cookie_short}")
        return pair['proxy'], pair['cookie']
    
    def reset_failed_pairs(self):
        """Сбрасывает список заблокированных связок"""
        failed_count = len(self.failed_pairs)
        self.failed_pairs.clear()
        logger.info(f"🔄 [PUMP_BOT] Сброшен список заблокированных связок (было: {failed_count})")
    
    def get_cycle_proxy_cookie(self) -> Tuple[Optional[str], str]:
        """Получает связку прокси+cookie для целого цикла работы (не меняется в рамках цикла)"""
        proxy, cookie = self.get_next_proxy_cookie()
        proxy_info = f"NO_PROXY" if proxy is None else proxy.split('@')[1]
        cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
        logger.info(f"🔄 [PUMP_BOT] Связка для нового цикла: #{self.current_index} - {proxy_info} + {cookie_short}")
        return proxy, cookie
    
    def get_stats(self) -> dict:
        """Возвращает статистику по связкам"""
        return {
            'total_pairs': len(self.proxy_cookie_pairs),
            'failed_pairs': len(self.failed_pairs),
            'available_pairs': len(self.proxy_cookie_pairs) - len(self.failed_pairs),
            'current_index': self.current_index
        }
        
    # Обратная совместимость для старого API
    def get_next_cookie(self) -> str:
        """Устаревший метод - получает только cookie без прокси"""
        _, cookie = self.get_next_proxy_cookie()
        return cookie
    
    def mark_cookie_failed(self, cookie: str):
        """Устаревший метод - помечает cookie как неработающий"""
        # Находим соответствующую связку и помечаем её как неработающую
        for pair in self.proxy_cookie_pairs:
            if pair['cookie'] == cookie:
                self.mark_pair_failed(pair['proxy'], cookie)
                break


class BackgroundProxyCookieRotator:
    """Класс для ротации связок прокси+cookies для фонового мониторинга (используется в background_monitor.py)"""
    
    def __init__(self):
        # Используем те же связки что и в основном боте (17.06.2025)
        self.proxy_cookie_pairs = [
            # Без прокси
            {
                "proxy": None,
                "cookie": "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4Mjc3YWEzYjA5Y2FlM2U1YzMzMDU3MWY4YWFlMjc2ZjRjM2QyNmZhMjRiYzExYjBiNzVlNjA4ODBmNDJhNzQwIiwiZXhwIjoxNzUwNjE3NTc3LCJpYXQiOjE3NTAwMTI3NzcsIm5iZiI6MTc1MDAxMjcxNywibm9uY2UiOiI2MzU4IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBjMWNiYWQzOTZhNDZiMjRmNTMwZmRlNzY0MTljYjY2NDQyOTQyMTI5MmEyYzdjMzQzN2U3ZDFjMjUwZjgifQ.sMThBhNTakbILW9NwtJPBo0t9Piai9GE6Hnrg89bLErsawZE77mkEeZ-KDyvJEM8gYug7r9zM5x0EYm8XpodBA"
            },
            # С прокси user291921:9ikrxg@45.12.115.17:1367
            {
                "proxy": "http://user291921:9ikrxg@45.12.115.17:1367",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=8acecc56026667b601911fe3c8cc05c35a0c3f112f8cebe2c50e694af54ce68c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4YWNlY2M1NjAyNjY2N2I2MDE5MTFmZTNjOGNjMDVjMzVhMGMzZjExMmY4Y2ViZTJjNTBlNjk0YWY1NGNlNjhjIiwiZXhwIjoxNzUwNzk4ODk4LCJpYXQiOjE3NTAxOTQwOTgsIm5iZiI6MTc1MDE5NDAzOCwibm9uY2UiOiIxMTQ4ODQiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDE1NDZmMDFmZWY5NTRlMGY3OTMzZTM3YjE1YWE4NGQxNzIwMGEwODI2MmNkNWMyYzEwMzNlM2E1MmRhOSJ9.r25UvTP41abhmSxFyrXsnuxd8AYIi2atQvCH5LCTjqHSembltEiej4gp_SeHcKWBnvSvO6FZrkEqO5rAwrN5Cw"
            },
            # С прокси user291921:9ikrxg@45.8.156.99:1416
            {
                "proxy": "http://user291921:9ikrxg@45.8.156.99:1416",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=0a08c72769aaf09a93283b61ebc69e4762106fb6f85cfca73e94f1c06f574b40; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIwYTA4YzcyNzY5YWFmMDlhOTMyODNiNjFlYmM2OWU0NzYyMTA2ZmI2Zjg1Y2ZjYTczZTk0ZjFjMDZmNTc0YjQwIiwiZXhwIjoxNzUwNzk5MDQ3LCJpYXQiOjE3NTAxOTQyNDcsIm5iZiI6MTc1MDE5NDE4Nywibm9uY2UiOiI0MjEyMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYTkxM2VhZjMxY2U0MTAyMGJlZmNjYTZhMWRlZDA5ZjQxMGI0MjI3ODc2ZDVjYWI2OTUwOTJmYjA4MGFmIn0.6DDwQFmhwTAfyjbAr1czHszYBlZf60_-U3yR1xtJxCx6KMLN3m3utUSQqVq3PDE7dwWLOw_UaoSgoeSg5q6CAw"
            },
            # С прокси user291921:9ikrxg@37.221.80.235:1416
            {
                "proxy": "http://user291921:9ikrxg@37.221.80.235:1416",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f6b8341a5676cb9d04f5e7327b542770131f8cce7fd873ff2410c252771b6195; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNmI4MzQxYTU2NzZjYjlkMDRmNWU3MzI3YjU0Mjc3MDEzMWY4Y2NlN2ZkODczZmYyNDEwYzI1Mjc3MWI2MTk1IiwiZXhwIjoxNzUwNzk5MTg5LCJpYXQiOjE3NTAxOTQzODksIm5iZiI6MTc1MDE5NDMyOSwibm9uY2UiOiI1OTk3IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDAxZTAzNDQyZDc0MTdiMjU1OTE4OGI2MzQzZDBkNDllMGVjMzRlMDQ0OTZlOGJmNDFhMjQ3MzMxNzNhNjAifQ.vkqDpDAtnXqdgYpVYzOSckAaeMDfqs1oFm59noe3axwcQ1ZUqTI0IzxmMsEpCFHnKr3kT3DF6QveZpuc3aOyCg"
            },
            # С прокси user291921:9ikrxg@149.126.240.31:1416
            {
                "proxy": "http://user291921:9ikrxg@149.126.240.31:1416",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f142216877a946d6bcb3b746b3b22f86a2e51da316d7222bc78a7ce6c6499234; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmMTQyMjE2ODc3YTk0NmQ2YmNiM2I3NDZiM2IyMmY4NmEyZTUxZGEzMTZkNzIyMmJjNzhhN2NlNmM2NDk5MjM0IiwiZXhwIjoxNzUwNzk5Mjg2LCJpYXQiOjE3NTAxOTQ0ODYsIm5iZiI6MTc1MDE5NDQyNiwibm9uY2UiOiI4MjA2IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA5NWZlYTFmNDYzNzY3YmI1NmQ4M2Q0Yzc2ZjVhMmJjOGFjZGM3NjFkOGQzZTYwOTI0YTNlZTVhMTVhZWEifQ.gbCe5V2xs5bXnJWS2lgpfaOkuaetKI5tL1HLLS6Ilg5KyznFkqSwm5SF_kV6S0B1hKq-OQvMVCGAfveToKcUCg"
            },
            # С прокси user291921:9ikrxg@194.32.124.66:2514
            {
                "proxy": "http://user291921:9ikrxg@194.32.124.66:2514",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=b3c7b9c45350e0a8349506d6c3ee7067dde25271b3fbe829b1d6bebed2181cd8; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiM2M3YjljNDUzNTBlMGE4MzQ5NTA2ZDZjM2VlNzA2N2RkZTI1MjcxYjNmYmU4MjliMWQ2YmViZWQyMTgxY2Q4IiwiZXhwIjoxNzUwNzk5MzU2LCJpYXQiOjE3NTAxOTQ1NTYsIm5iZiI6MTc1MDE5NDQ5Niwibm9uY2UiOiIyMTkwMzQiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDYzMTQ5OTk3N2JhMjdkMWU4M2I1ZTdiNjkwNTIzM2VmOGNlZDFmZGE0ZTAyNGY4YmE1N2ZlNDMyNzdkYSJ9.JK-BCyjxAd2L5-_VkGM_0aA1gmb3UDUE7DbwUD4UztcZpJp0NTEVdabKYIpsDGac7kdobidM_KpICt-sf6HUCg"
            },
            # С прокси user291921:9ikrxg@213.166.92.96:2514
            {
                "proxy": "http://user291921:9ikrxg@213.166.92.96:2514",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=ce242ad2c8779dc1d83e59db4dc6847cbffeed6ed72679d2589d2de59ca80a9d; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJjZTI0MmFkMmM4Nzc5ZGMxZDgzZTU5ZGI0ZGM2ODQ3Y2JmZmVlZDZlZDcyNjc5ZDI1ODlkMmRlNTljYTgwYTlkIiwiZXhwIjoxNzUwNzk5NDA2LCJpYXQiOjE3NTAxOTQ2MDYsIm5iZiI6MTc1MDE5NDU0Niwibm9uY2UiOiI2NzE2OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMWRlM2NjYmFhMGY0OTRmMjA0YzAxMmIxOTQ2MTkzMGZmYmExMjQ4NjMwM2MyOGJmYzQ4NzIxNjNjYmUwIn0.LN75eORPbBA80BV16hPg1JJBzwrT9ClbXBdO2Zyd0mgvW7FWUHNmpUpflJZ7XJtfP8yuWDm3DeWf1UT8hiQGDA"
            },
            # С прокси user291921:9ikrxg@149.126.227.4:2514
            {
                "proxy": "http://user291921:9ikrxg@149.126.227.4:2514",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=06bf91ac4e14207e08e33fc4d1fe198ef1371b50136b7a412811182cadcb77a2; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIwNmJmOTFhYzRlMTQyMDdlMDhlMzNmYzRkMWZlMTk4ZWYxMzcxYjUwMTM2YjdhNDEyODExMTgyY2FkY2I3N2EyIiwiZXhwIjoxNzUwNzk5NDgwLCJpYXQiOjE3NTAxOTQ2ODAsIm5iZiI6MTc1MDE5NDYyMCwibm9uY2UiOiIxMjU0NjgiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDdjMWE3YWJiYTIyYjMzMjI2NjU2YTA2M2MyNWMwMzI5Mjg4OTk5OTNhYWJlNjViOWJmOWU5YWI2NmE3NiJ9.ShZXfE7FoM2KjhYhbF5jE8dbUASw80I6_be4Caw5_E6IGSSL0Fy7HhsymawMo79qjENklXDx_-IBQpJ-lN42DQ"
            }
        ]
        self.current_index = 0
        self.failed_pairs = set()  # Множество для отслеживания неработающих связок
        logger.info(f"🍪🌐 [BACKGROUND] Инициализирован ротатор с {len(self.proxy_cookie_pairs)} прокси+cookie связками")
    
    def get_next_proxy_cookie(self) -> Tuple[Optional[str], str]:
        """Получает следующую связку прокси+cookie в ротации (исключая заблокированные)"""
        attempts = 0
        max_attempts = len(self.proxy_cookie_pairs)
        
        while attempts < max_attempts:
            pair = self.proxy_cookie_pairs[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxy_cookie_pairs)
            
            # Создаем идентификатор связки для проверки
            pair_id = f"{pair['proxy']}|{pair['cookie'][:50]}"
            
            # Если связка не в списке заблокированных, возвращаем её
            if pair_id not in self.failed_pairs:
                proxy_info = f"NO_PROXY" if pair['proxy'] is None else pair['proxy'].split('@')[1]
                cookie_short = pair['cookie'][:50] + "..." if len(pair['cookie']) > 50 else pair['cookie']
                logger.debug(f"🍪🌐 [BACKGROUND] Используем связку #{self.current_index}: {proxy_info} + {cookie_short}")
                return pair['proxy'], pair['cookie']
            
            attempts += 1
        
        # Если все связки заблокированы, сбрасываем список и начинаем заново
        logger.warning(f"⚠️ [BACKGROUND] Все прокси+cookie связки заблокированы, сбрасываем список")
        self.failed_pairs.clear()
        pair = self.proxy_cookie_pairs[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxy_cookie_pairs)
        return pair['proxy'], pair['cookie']
    
    def mark_pair_failed(self, proxy: Optional[str], cookie: str):
        """Помечает связку прокси+cookie как неработающую"""
        pair_id = f"{proxy}|{cookie[:50]}"
        self.failed_pairs.add(pair_id)
        proxy_info = f"NO_PROXY" if proxy is None else proxy.split('@')[1]
        logger.warning(f"❌ [BACKGROUND] Связка помечена как неработающая: {proxy_info} (всего заблокировано: {len(self.failed_pairs)}/{len(self.proxy_cookie_pairs)})")
    
    def get_random_proxy_cookie(self) -> Tuple[Optional[str], str]:
        """Получает случайную работающую связку прокси+cookie"""
        available_pairs = []
        for pair in self.proxy_cookie_pairs:
            pair_id = f"{pair['proxy']}|{pair['cookie'][:50]}"
            if pair_id not in self.failed_pairs:
                available_pairs.append(pair)
        
        if not available_pairs:
            # Если все связки заблокированы, сбрасываем и берем случайную
            logger.warning(f"⚠️ [BACKGROUND] Все прокси+cookie связки заблокированы, сбрасываем список")
            self.failed_pairs.clear()
            available_pairs = self.proxy_cookie_pairs
        
        pair = random.choice(available_pairs)
        proxy_info = f"NO_PROXY" if pair['proxy'] is None else pair['proxy'].split('@')[1]
        cookie_short = pair['cookie'][:50] + "..." if len(pair['cookie']) > 50 else pair['cookie']
        logger.debug(f"🎲 [BACKGROUND] Случайная связка: {proxy_info} + {cookie_short}")
        return pair['proxy'], pair['cookie']
    
    def reset_failed_pairs(self):
        """Сбрасывает список заблокированных связок"""
        failed_count = len(self.failed_pairs)
        self.failed_pairs.clear()
        logger.info(f"🔄 [BACKGROUND] Сброшен список заблокированных связок (было: {failed_count})")
    
    def get_cycle_proxy_cookie(self) -> Tuple[Optional[str], str]:
        """Получает связку прокси+cookie для целого цикла работы (не меняется в рамках цикла)"""
        proxy, cookie = self.get_next_proxy_cookie()
        proxy_info = f"NO_PROXY" if proxy is None else proxy.split('@')[1]
        cookie_short = cookie[:50] + "..." if len(cookie) > 50 else cookie
        logger.info(f"🔄 [BACKGROUND] Связка для нового цикла: #{self.current_index} - {proxy_info} + {cookie_short}")
        return proxy, cookie
    
    def get_stats(self) -> dict:
        """Возвращает статистику по связкам"""
        return {
            'total_pairs': len(self.proxy_cookie_pairs),
            'failed_pairs': len(self.failed_pairs),
            'available_pairs': len(self.proxy_cookie_pairs) - len(self.failed_pairs),
            'current_index': self.current_index
        }
        
    # Обратная совместимость для старого API
    def get_next_cookie(self) -> str:
        """Устаревший метод - получает только cookie без прокси"""
        _, cookie = self.get_next_proxy_cookie()
        return cookie
    
    def mark_cookie_failed(self, cookie: str):
        """Устаревший метод - помечает cookie как неработающий"""
        # Находим соответствующую связку и помечаем её как неработающую
        for pair in self.proxy_cookie_pairs:
            if pair['cookie'] == cookie:
                self.mark_pair_failed(pair['proxy'], cookie)
                break


# Глобальные экземпляры ротаторов
proxy_cookie_rotator = ProxyCookieRotator()  # Для pump_bot.py
background_proxy_cookie_rotator = BackgroundProxyCookieRotator()  # Для background_monitor.py

# Обратная совместимость (устаревшие имена)
cookie_rotator = proxy_cookie_rotator  # Старое имя для pump_bot.py
background_cookie_rotator = background_proxy_cookie_rotator  # Старое имя для background_monitor.py 