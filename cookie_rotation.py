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
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=aec8b163d7e642042ac7b7e2842f11ee29dc919511a91ad33f4843c55464472c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhZWM4YjE2M2Q3ZTY0MjA0MmFjN2I3ZTI4NDJmMTFlZTI5ZGM5MTk1MTFhOTFhZDMzZjQ4NDNjNTU0NjQ0NzJjIiwiZXhwIjoxNzUxNDY2MDkzLCJpYXQiOjE3NTA4NjEyOTMsIm5iZiI6MTc1MDg2MTIzMywibm9uY2UiOiIxNDg1OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMDdjZGI4N2Y1MGNjZWY5ZDdjYzA1MjIxN2M4OTY2NDgyZmNlM2Y1NDBkNzNiYzMwYmUxMWQyMTQ0OTM4In0.0dXy-1gIINqEdAnmvbVERMhg7DvXvDU2NwnLfl_W9W1BLk46onCz0W6YzDCdhkg_i7do9y7Y2JmhygwuUMfZBQ"
            },
            # С прокси
            {
                "proxy": "http://user132581:schrvd@37.221.80.162:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=c0fefc0551e48af61c97aaa40b3c1a922f156fe13e1b0d8ffbadf59112527a7b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJjMGZlZmMwNTUxZTQ4YWY2MWM5N2FhYTQwYjNjMWE5MjJmMTU2ZmUxM2UxYjBkOGZmYmFkZjU5MTEyNTI3YTdiIiwiZXhwIjoxNzUxNDY2Njk5LCJpYXQiOjE3NTA4NjE4OTksIm5iZiI6MTc1MDg2MTgzOSwibm9uY2UiOiIyNTMyMSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNjY3ODRiZDAxYmE1OTE2MDU4Zjk4NmM1ZTc5ZGI1YmUzODI3YmRmMjcxMDU2MWRiODdhYWUyNGYzNmEyIn0.poVfPwB7eFJ3FGu-wo3H0RrtZh7No7kqIqHLf9kLWMIJagsJe2AH1ZJxaFJ-aqwWVmXciMVTXG6zO5MizxDpAA"
            },
            {
                "proxy": "http://user132581:schrvd@46.149.174.203:3542", 
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=7b0434f62b73985292af5b187b0e450cc9495130a36376706c91ff47ceb0bcc5; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI3YjA0MzRmNjJiNzM5ODUyOTJhZjViMTg3YjBlNDUwY2M5NDk1MTMwYTM2Mzc2NzA2YzkxZmY0N2NlYjBiY2M1IiwiZXhwIjoxNzUxNDY2Nzk0LCJpYXQiOjE3NTA4NjE5OTQsIm5iZiI6MTc1MDg2MTkzNCwibm9uY2UiOiIyNzE4NyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwOTg1NTdiNzk4NjJmN2JkOWMyNGVjYTkxZjFjYzE5OTRhNWI0MWY1YjFiOGZjYWU0NmYxYjhmYWJjOWEzIn0.QjUKm5gU7yVfz3Uuhtzo36eHeEov3Tpfc8k6oh0FXfq1n_EqExq8snHtH30hkc6ItcoMRHJev3Guodp7xJPFDA"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.181:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=424a46497ff2add4bf0a47b78ff61c721be81a3335f8edf02967860e409d8001; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI0MjRhNDY0OTdmZjJhZGQ0YmYwYTQ3Yjc4ZmY2MWM3MjFiZTgxYTMzMzVmOGVkZjAyOTY3ODYwZTQwOWQ4MDAxIiwiZXhwIjoxNzUxNDY2OTA2LCJpYXQiOjE3NTA4NjIxMDYsIm5iZiI6MTc1MDg2MjA0Niwibm9uY2UiOiIxNDYzNyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYzIxZDk5NzdhODc4ODE3MjBhYThjNGI0MGJjYTg2MjA0OTlmZjE0YWY4MDcwYTY4M2JjZWRiNzA5MDI4In0.LYyUC1ihHZMThwhdv24P2gpkxJn_72YoFq8W17-xlgae8zmnmWxun5Hw5NcQNaMRPwHoro7hkTkN2WVtyjiXAw"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.125:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=c0e3d84cf7142b5af83161aa287d44bdda5f5346da759b738c589c5d3f31b7e2; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJjMGUzZDg0Y2Y3MTQyYjVhZjgzMTYxYWEyODdkNDRiZGRhNWY1MzQ2ZGE3NTliNzM4YzU4OWM1ZDNmMzFiN2UyIiwiZXhwIjoxNzUxNDY3MTAyLCJpYXQiOjE3NTA4NjIzMDIsIm5iZiI6MTc1MDg2MjI0Miwibm9uY2UiOiI2NzMyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA2MWRiY2U5NzU2ODEzOGQ0Y2MxMWJhMmE5MjBlNDJiYzk4MjNjYTViOGI2ODM0ZmNlNWU4OTNlNTZlNDgifQ.sYjM4_xbxAzRlISqtrUyMhV3FuNMgUVzWqcRygUyZZOFQs7TozVsyTJQsoOv8uI-XGzwxpyXM7FIPpwZX4MoDA"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.5:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=d6b2905b9ea152f65812cf6ea00b37f395869e4c197888be96678e80c1d7f551; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJkNmIyOTA1YjllYTE1MmY2NTgxMmNmNmVhMDBiMzdmMzk1ODY5ZTRjMTk3ODg4YmU5NjY3OGU4MGMxZDdmNTUxIiwiZXhwIjoxNzUxNDY3MTc1LCJpYXQiOjE3NTA4NjIzNzUsIm5iZiI6MTc1MDg2MjMxNSwibm9uY2UiOiIzNjIwMyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwOTk5NzY1Yzg3ZGU1ZWZiNjRhN2FhM2Y3YTQxNWNlMTdlMjFlNjEyMTc4MWU4MjY2NzcxYjZhZTFlM2Q0In0.uSbVPjNnoEfk9gdP91mG8mI25bk0-SVajiRXXvnt8Cz7K7Ajqmfrc3CjzodueqSnvAsluwIgi1DT70kReAXNCQ"
            },
            {
                "proxy": "http://user132581:schrvd@213.139.231.127:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=769c9b702f74e4091a8039ea933fa104685fa5fa31cb49a2e9fa002ba9d1bf85; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI3NjljOWI3MDJmNzRlNDA5MWE4MDM5ZWE5MzNmYTEwNDY4NWZhNWZhMzFjYjQ5YTJlOWZhMDAyYmE5ZDFiZjg1IiwiZXhwIjoxNzUxNDY3MjU2LCJpYXQiOjE3NTA4NjI0NTYsIm5iZiI6MTc1MDg2MjM5Niwibm9uY2UiOiI5MDU1IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBmN2JhZGQxMDk5YjU5YzhhNjU0ZmNjYzg4YjgwZGU0ODMyMDU4MTgyZGYxYzY3OTk1ZDJlNDBmMWVlNjQifQ.43EjYyn13RylT0YwKRzkRX_XvsBnh_kQHNO1qFk__uTqzFvLV1qMxt6uXHihFnI-xJHut99bJMdPTyxd2PleDw"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.23:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=9576c635a287f72f00eaf9950fc12a57eb016218130889e662782006652ddff5; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5NTc2YzYzNWEyODdmNzJmMDBlYWY5OTUwZmMxMmE1N2ViMDE2MjE4MTMwODg5ZTY2Mjc4MjAwNjY1MmRkZmY1IiwiZXhwIjoxNzUxNDg5NjUyLCJpYXQiOjE3NTA4ODQ4NTIsIm5iZiI6MTc1MDg4NDc5Miwibm9uY2UiOiI4MzM3MyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwM2Y2NzJlYjZiNjBmZTU2ZWYzMjNiZjJiMDAzNzg0MjAzYjFjYTRmYzU5MTFmNTU3ZDJiYTA3YzZkNWVhIn0.xqNAJeDZjsIXm_2px1O55jbwquGxFfYb8bLep3D-DDyQOm0y4XroYFos990Kv0S_Kq1U-31Wm00ONgsIHbeGDg"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.188:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=91863dcd5a8dc8a43e1d8ed5d9b212bf3bdd51836de621367e604d0e2fa6b97b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5MTg2M2RjZDVhOGRjOGE0M2UxZDhlZDVkOWIyMTJiZjNiZGQ1MTgzNmRlNjIxMzY3ZTYwNGQwZTJmYTZiOTdiIiwiZXhwIjoxNzUxNDg5ODczLCJpYXQiOjE3NTA4ODUwNzMsIm5iZiI6MTc1MDg4NTAxMywibm9uY2UiOiI5MTU2NyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMTJiZDM4MThmOGUxNjI3NGU5YTMzZTk2MjY3ZDBmM2Q2YjFjYzExMjI5MTgzMmI1MzJmOWQyNmY5MWI2In0.HI7rcOwvH-oJd6kVSoUAyHOhx8Chb1CNxoCu1_YiDQ7YUzvaShwONpzZBKoVpOBes_8p-27FYxeQv8II6KB_DQ"
            },
            {
                "proxy": "http://user132581:schrvd@45.91.160.28:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=875162d594d0996fc23cbb2420c949b5d3769377905807cab345b25555ef8d5c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4NzUxNjJkNTk0ZDA5OTZmYzIzY2JiMjQyMGM5NDliNWQzNzY5Mzc3OTA1ODA3Y2FiMzQ1YjI1NTU1ZWY4ZDVjIiwiZXhwIjoxNzUxNDkwMDI1LCJpYXQiOjE3NTA4ODUyMjUsIm5iZiI6MTc1MDg4NTE2NSwibm9uY2UiOiIxMjkxNzYiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDNiNzQ0ZDkyZmU2OTkwZDJkNWU4M2IwNGIzNmY3ZTA0OTJkYTE1ZjJlYWNmNjRkMjhiYzhiNmJkNDkxZSJ9.8oeANM2Mbh4DxxSOh9wWJ6ij2tTEnz3npgfWB49E8Z87sjnQTLzILylUIPfGcsPZmCvRd7Gf6IiDHX3VAB4zBg"
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
            # С прокси user132581:schrvd@194.34.250.178:3542
            {
                "proxy": "http://user132581:schrvd@194.34.250.178:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=1e698693eec2819b87e8e8035f1975270a89664b99272250c7ef4e58d2f62390; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxZTY5ODY5M2VlYzI4MTliODdlOGU4MDM1ZjE5NzUyNzBhODk2NjRiOTkyNzIyNTBjN2VmNGU1OGQyZjYyMzkwIiwiZXhwIjoxNzUxMjI4OTI0LCJpYXQiOjE3NTA2MjQxMjQsIm5iZiI6MTc1MDYyNDA2NCwibm9uY2UiOiI1ODA3IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDAwMTQxODE1NzlhZTNmYWUzNTU0ZDRhZDIzODFhNmQ0MWNhMDhkZDQ2MWU3ZTQzOGJlMTkwYTVhNWFhMTgifQ.mIfg66_9lnde6OUhBQyexszm-kCA9bzCLhuRc32ozqnBx116ItLZqo_ApgEUPrjkgKiJP_rBGvmEcuqF2XoCCA"
            },
            # С прокси user132581:schrvd@149.126.199.210:3542
            {
                "proxy": "http://user132581:schrvd@149.126.199.210:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=8caba8f4a08b37dc0d81c16456fd2297d57f0f65abba25bfa75857afc6a33632; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4Y2FiYThmNGEwOGIzN2RjMGQ4MWMxNjQ1NmZkMjI5N2Q1N2YwZjY1YWJiYTI1YmZhNzU4NTdhZmM2YTMzNjMyIiwiZXhwIjoxNzUxMjMwMjc1LCJpYXQiOjE3NTA2MjU0NzUsIm5iZiI6MTc1MDYyNTQxNSwibm9uY2UiOiIxMDU1NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYWZmMzM5OThlNDQ5ZmI2N2E2ZTZiMDIxNDdmYzUyZjc4YjA0NjI3NGI5YTlhMTU5OTExYjBjMWRlNzMxIn0.PD0aMKkIQjvIVr31i3LHrKoj9ZhvQZhLijE9UYJ8OYrVjc1didSrogTzD6r6m9FXN4PV0pnrRg4nYDjsIAiAAg"
            },
            # С прокси user132581:schrvd@149.126.199.53:3542
            {
                "proxy": "http://user132581:schrvd@149.126.199.53:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=790091eb589bcaa95765ac08312aa4fcb08076bf7f908b4e133d95781d605ee4; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI3OTAwOTFlYjU4OWJjYWE5NTc2NWFjMDgzMTJhYTRmY2IwODA3NmJmN2Y5MDhiNGUxMzNkOTU3ODFkNjA1ZWU0IiwiZXhwIjoxNzUxMjMwMzM2LCJpYXQiOjE3NTA2MjU1MzYsIm5iZiI6MTc1MDYyNTQ3Niwibm9uY2UiOiI1ODk5IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1ZTk0Yzg5YmRlYmZhMGI0NjdhMDBlMTlhYmM1ZjA0ODIwYjM2NDgyMTA3ZjYxZGVlY2Q4ODM5NWExMjQifQ.Hlkz9FruO0vwuqndxHa2drZiWN1KAtbKK1yAjn7mtZ24jJziJEE3ka81VFciW7uEcoE_qXqfw1vLNWIFwZU-BA"
            },
            # С прокси user132581:schrvd@149.126.211.4:3542
            {
                "proxy": "http://user132581:schrvd@149.126.211.4:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=8020fcf0b1a215c39300529b857c6edb1c228b1a4e4a437032b419c77822043c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4MDIwZmNmMGIxYTIxNWMzOTMwMDUyOWI4NTdjNmVkYjFjMjI4YjFhNGU0YTQzNzAzMmI0MTljNzc4MjIwNDNjIiwiZXhwIjoxNzUxMjMwMzk0LCJpYXQiOjE3NTA2MjU1OTQsIm5iZiI6MTc1MDYyNTUzNCwibm9uY2UiOiIzMTk4OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNWY2MGQyZWY2OTVjNGFlZTMwMjVhZjNlNmQ2MWEzNWRmZTVlYmMzZGJkYmYyMjU2MzdmNzhjOWVmMDc5In0.6EmW6xK0gT-I9O9bhHtEOBw6jVpiWabdUHiN2FTqn-d6gnUAKJXjOtTXNnDA7KrJzEp9SkFjv3_DExVoCoAbDQ"
            },
            # С прокси user132581:schrvd@149.126.211.208:3542
            {
                "proxy": "http://user132581:schrvd@149.126.211.208:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=40d28cf964d9c90b62d472174f87c482331adb84b5c4fc4b26bee3d603f66a33; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI0MGQyOGNmOTY0ZDljOTBiNjJkNDcyMTc0Zjg3YzQ4MjMzMWFkYjg0YjVjNGZjNGIyNmJlZTNkNjAzZjY2YTMzIiwiZXhwIjoxNzUxMjMwNDQxLCJpYXQiOjE3NTA2MjU2NDEsIm5iZiI6MTc1MDYyNTU4MSwibm9uY2UiOiI3OTY1NyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZTFlZmVlYjA1YTI5NjgxMGI1NDRiMmQ2YWQ2ZTMyNGI3YzY5ZjhkMjk2NWM3MGI3ZDk1OWNiYWM0ZGI1In0.P4vpWS7TPGXw4XgZ2lK2excSkWgh7RfpwMJdgJb0FWam81VMBAdhpBR9b1N92GE-U6NN25giZQQFi0nBlEjmDw"
            },
            # С прокси user132581:schrvd@149.126.212.129:3542
            {
                "proxy": "http://user132581:schrvd@149.126.212.129:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=fc43083e591f95d07276242097c007719467997f6bff8b1c55c2b35c77b37e3b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmYzQzMDgzZTU5MWY5NWQwNzI3NjI0MjA5N2MwMDc3MTk0Njc5OTdmNmJmZjhiMWM1NWMyYjM1Yzc3YjM3ZTNiIiwiZXhwIjoxNzUxMjMwNDg3LCJpYXQiOjE3NTA2MjU2ODcsIm5iZiI6MTc1MDYyNTYyNywibm9uY2UiOiI4OTMwMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZmM3ZjIwZjE3ZDgxMjk5MmI4Y2E5YjBmYTc4NTAxYmRlYjA5MGViYmNhYzQ3OGNlODhjYjZjNGYzYWJjIn0.YDD8dTw_KPuQzvegSCBid3HgI0oNTtilzMIx8-Ruy5zCDv3tvUyWR34IXBP6GLgo2yPeg1uR2xolNqVzBXUYAQ"
            },
            # С прокси user132581:schrvd@149.126.240.124:3542
            {
                "proxy": "http://user132581:schrvd@149.126.240.124:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=1de7ef7f870cabbb4233de8d5edc9db65e3d2ab7a6728b9e79cc5edf714e5526; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxZGU3ZWY3Zjg3MGNhYmJiNDIzM2RlOGQ1ZWRjOWRiNjVlM2QyYWI3YTY3MjhiOWU3OWNjNWVkZjcxNGU1NTI2IiwiZXhwIjoxNzUxMjMwNTI4LCJpYXQiOjE3NTA2MjU3MjgsIm5iZiI6MTc1MDYyNTY2OCwibm9uY2UiOiIyMTE0NyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYTg0MjMwMDkxNWE4MDE4MzA0NjE5ZDJlZTJkNGE2ZWU2MTdkY2Q5ZWJiOTIzYzI3NGNiNWFjYTk1YjhhIn0.ZRYfUUNHuuEwZ3YCooNjELtDw6mLQHyCmL0-WeiVTxgdo6qKRquAcl5oF0vrgzpxOdLtQMjeW5mq8JLSnLTsBQ"
            },
            # С прокси user132581:schrvd@149.126.227.154:3542
            {
                "proxy": "http://user132581:schrvd@149.126.227.154:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=7bb8291529f130a5a1f3089e2251d578e374a2aa9079b350ba15fb1c73ee3f65; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI3YmI4MjkxNTI5ZjEzMGE1YTFmMzA4OWUyMjUxZDU3OGUzNzRhMmFhOTA3OWIzNTBiYTE1ZmIxYzczZWUzZjY1IiwiZXhwIjoxNzUxMjMwNTc4LCJpYXQiOjE3NTA2MjU3NzgsIm5iZiI6MTc1MDYyNTcxOCwibm9uY2UiOiIyNDQzMjIiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDdlYzg0YzgwZDhiNDhkMTVjYTk2MDM2M2M1MmI0MGNmNWIwOTAwYjk3YjM3ZDcwZDE2MDJiNWRjYWEwZiJ9.q5Db9Ph6qci2m3MJ3UAyysaUZWH6rTtHpSPtDbcRIyItfpPuGltohpRkLovPGvhkzRYDEft0-tByVqPP_Y4JCw"
            },
            # С прокси user132581:schrvd@149.126.209.117:3542
            {
                "proxy": "http://user132581:schrvd@149.126.209.117:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=888620729b8e7d12b5e14e7da229c41da955672a032c7465c0bb247d0dd8a3fc; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4ODg2MjA3MjliOGU3ZDEyYjVlMTRlN2RhMjI5YzQxZGE5NTU2NzJhMDMyYzc0NjVjMGJiMjQ3ZDBkZDhhM2ZjIiwiZXhwIjoxNzUxMjMwNjIyLCJpYXQiOjE3NTA2MjU4MjIsIm5iZiI6MTc1MDYyNTc2Miwibm9uY2UiOiIyNzAyMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNTg3ODMzMDhkYjFlZTg1ZDgxODkyZmFmMzAxNzZjNzY3NzVkZmFjNWRjYWZkNTZhMmRjMGRiYjk1MTdkIn0.j8AbX9tYleQF35bkcDjQ7AQNAp__Ir6ClX3wrJFxRp8MV1fPhbm_B3L0iDIHzeiLudKBSRL0b8HiR8taRweJDQ"
            },
            # С прокси user132581:schrvd@149.126.211.192:3542
            {
                "proxy": "http://user132581:schrvd@149.126.211.192:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=455c56e245bb1d882cf4f884023eb9f0165131304ab91822f69da00c3ee70b9c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI0NTVjNTZlMjQ1YmIxZDg4MmNmNGY4ODQwMjNlYjlmMDE2NTEzMTMwNGFiOTE4MjJmNjlkYTAwYzNlZTcwYjljIiwiZXhwIjoxNzUxMjMwNjY4LCJpYXQiOjE3NTA2MjU4NjgsIm5iZiI6MTc1MDYyNTgwOCwibm9uY2UiOiI0NjI3OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwOGE0MzNmYTM4NDc3YTkwMGYyMDFjYTQwMzNkMDQ2ZjYwMzVjMmU0OTM0ZDcxYjRmOTgyMmE3OWIwNmNkIn0.I2BRc0JCWs6DXPiUvLTKqua2-xpFQWwdB3gUnvyQi2TJyAw8PTBvPys4uQ9rrfQFsCWUv7rlknCXXAFD1BUqCA"
            },
            # С прокси user132581:schrvd@149.126.209.127:3542
            {
                "proxy": "http://user132581:schrvd@149.126.209.127:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=90e5a2c21f173d140c4e6414aef0ff5d9937dbc018a8c3dbd1212e74adeb4ba2; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5MGU1YTJjMjFmMTczZDE0MGM0ZTY0MTRhZWYwZmY1ZDk5MzdkYmMwMThhOGMzZGJkMTIxMmU3NGFkZWI0YmEyIiwiZXhwIjoxNzUxMjMwNzgxLCJpYXQiOjE3NTA2MjU5ODEsIm5iZiI6MTc1MDYyNTkyMSwibm9uY2UiOiI2NzgzIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBkYjMyNTIzYWJkODA1NDc1MGU1YTdiZjNiZjk3ZDc0YTVjY2E1Y2RhY2ZiNmFmNjk2ZWU1M2FjMTgwMTQifQ.3Tp50k0o7SkhS12YkE7msodiXX2076iO7lNNYsmmQtjwURo2HYWUfhvIg7-i5MJu-Q4sNHoaoL-4oeq0wm17DA"
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