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
                "cookie": "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4OTVlZGU2NDY2MGUzNzJmNWE2MDExYjQwMmU5ZmM1YTZmMzAxMWVkZjAxNWYxZjI5ZDdkYTlhNjE5YzJjZTMxIiwiZXhwIjoxNzUwODU5OTA0LCJpYXQiOjE3NTAyNTUxMDQsIm5iZiI6MTc1MDI1NTA0NCwibm9uY2UiOiIxNDg4OTciLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDNmNjI5ZGQ5ZjhjMDkyZGQ0ZDJmM2E3MDIyY2QwMzFmM2Y3ZmMyZjQ0MWIxZDE3YTgyYzE0MGQ1M2NiMSJ9.O1XvQu_1HCgDFU8ILIC-WlFoqen4d12nr-QvtrYsGJImvbEMRA9aZgVrjK1rrC9G10MAjeUOVq0bG5TcfER5BA"
            },
            # С прокси
            {
                "proxy": "http://user132581:schrvd@37.221.80.162:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a607cd2f9fc888da55745df416ca0ddce579222a010c9020a772768f2fa1ff55; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNjA3Y2QyZjlmYzg4OGRhNTU3NDVkZjQxNmNhMGRkY2U1NzkyMjJhMDEwYzkwMjBhNzcyNzY4ZjJmYTFmZjU1IiwiZXhwIjoxNzUxMjI3MzY1LCJpYXQiOjE3NTA2MjI1NjUsIm5iZiI6MTc1MDYyMjUwNSwibm9uY2UiOiIxMTI1NTUiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDZhM2ViZTQwZDg2NWM1Njk2YjAyZGQ4MmZlZWI3ZmMzNzg1ZGE3NWFkMDJmODA2YzljMzBlYTU3MmNlZCJ9.AHEIImU75BSJKphf-XHOuneiSdmRFRyoXgUesDJnWu-ADJfPwQqTPYbmSqPDm97948-2agXl0tWN2mXpUL6eBQ"
            },
            {
                "proxy": "http://user132581:schrvd@46.149.174.203:3542", 
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=550be1f6767b67c39b7b9581b96136a13993bff4c9962a80e48ef1ac521bb1de; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI1NTBiZTFmNjc2N2I2N2MzOWI3Yjk1ODFiOTYxMzZhMTM5OTNiZmY0Yzk5NjJhODBlNDhlZjFhYzUyMWJiMWRlIiwiZXhwIjoxNzUxMjI3NjE2LCJpYXQiOjE3NTA2MjI4MTYsIm5iZiI6MTc1MDYyMjc1Niwibm9uY2UiOiIxMjI4OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwM2FlMDhiMzJlM2YwZDJhNmY5NTIxNjMzYThkZWMyZDJmZmFkZTZmYWY5NzdmNDNmNTBiZjMwNzY1NDBlIn0.deJLruyJ4XwbClVRoiNM8ys6mYjz_a_WbI6eJJnzEFnqBaC-k_5NJWVsC8tL8bzo23optfIqdg6cZbPzZggYBQ"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.181:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=9da6e511c844ee7b8931b1c65a96577ede92b24efb4591166a6fc0a5746f22d4; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5ZGE2ZTUxMWM4NDRlZTdiODkzMWIxYzY1YTk2NTc3ZWRlOTJiMjRlZmI0NTkxMTY2YTZmYzBhNTc0NmYyMmQ0IiwiZXhwIjoxNzUxMjI3OTkyLCJpYXQiOjE3NTA2MjMxOTIsIm5iZiI6MTc1MDYyMzEzMiwibm9uY2UiOiI2ODA4IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBhOWI3NzY0YWUxNzRlZTg5Yzc3NjBhODYwNjg5OGE3NjhmZDI0ZWRiZGVhMWEwNTVlZjFmZmVmNjBjOWEifQ.LpKsMJLtHdfs3pWilQJ66ztfx9Np7Dh94A0zUF72YFX0IEauizIMmigLL5cHPLeMpYEQo6XL5JJxiJelEKEFDQ"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.125:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=b82012dc7e93544fd02ac4bf4e7f22041df4e6bd4e658f92b804722bd2c5003c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiODIwMTJkYzdlOTM1NDRmZDAyYWM0YmY0ZTdmMjIwNDFkZjRlNmJkNGU2NThmOTJiODA0NzIyYmQyYzUwMDNjIiwiZXhwIjoxNzUxMjI4NDM5LCJpYXQiOjE3NTA2MjM2MzksIm5iZiI6MTc1MDYyMzU3OSwibm9uY2UiOiIxMzU2MzUiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDVmYzljNDZlYWNiOTZmNzYzNWViNTY4MmQxYzk1ZWQ3MWE4MTk5YzQ5NDhkYTIzZGNkMTRmNTM4NzkxZSJ9.NJKwLI30zkSPJLNdcHaryml3VkLs7tv8_JMEB52wKbWFrgKa6kywwUBPrS87L03YiKLlHW1kQA6Ak8X3rm1tBw"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.5:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=ad4a9c3d675eceb6bce30f69b40057337f27e5fee32fc5cf7f7ff49d4c944200; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhZDRhOWMzZDY3NWVjZWI2YmNlMzBmNjliNDAwNTczMzdmMjdlNWZlZTMyZmM1Y2Y3ZjdmZjQ5ZDRjOTQ0MjAwIiwiZXhwIjoxNzUxMjI4NDk4LCJpYXQiOjE3NTA2MjM2OTgsIm5iZiI6MTc1MDYyMzYzOCwibm9uY2UiOiI5ODUzIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDAzMjcxMzlhNDljMmI4MDJiODU3M2Q1YmVkM2M1YzNmNjAyNDI0NzI0OGIxMmFjNmUxNzJmNDFlMWQxNzAifQ.A2XmCo9hmrkwl34gMkX1uJpY-2-6V7l8A34V5pEiUm9As9D9K2-Q51IUULDaUfTXsqE6WBHuAAnxpwBgljFoDQ"
            },
            {
                "proxy": "http://user132581:schrvd@213.139.231.127:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=d39f01fcd3c4d84fd21298c8c6b05d70db7d42dd91204c9278aa6c669ef09e9f; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJkMzlmMDFmY2QzYzRkODRmZDIxMjk4YzhjNmIwNWQ3MGRiN2Q0MmRkOTEyMDRjOTI3OGFhNmM2NjllZjA5ZTlmIiwiZXhwIjoxNzUxMjI4NTU4LCJpYXQiOjE3NTA2MjM3NTgsIm5iZiI6MTc1MDYyMzY5OCwibm9uY2UiOiI2ODU5IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBmODYzNzI2ZGNhN2EwMWJiYzIyZTU0YzRhMWJmMmMwZDNiMTA5MWEzYzAxMDUxYWZiMzk1MzZiOWZjYWYifQ.vmz5F63IDpQgkhpP9XNdIbBEKGPUSsAltapMVxd1CZI_HRJsmy0lgG5FPZMSW1lo_5u35gs133fa4tD9GeSmBg"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.23:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=312c430e3cd6662928d09a1d5e613357e2b37dcc69a4b242bd705ca7cc38906c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIzMTJjNDMwZTNjZDY2NjI5MjhkMDlhMWQ1ZTYxMzM1N2UyYjM3ZGNjNjlhNGIyNDJiZDcwNWNhN2NjMzg5MDZjIiwiZXhwIjoxNzUxMjI4NzQzLCJpYXQiOjE3NTA2MjM5NDMsIm5iZiI6MTc1MDYyMzg4Mywibm9uY2UiOiIxMDI5NjUiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDliOThiMjY4MzI5ODQyMmQxNTIxYmI4YmQxMDZjOWM4YTkxY2U2ODhjZjA1MDUxNGRjYzViMDVhYTI5MiJ9.DQMvFyweJzaK02R_kwYfIj7_n5y7BL-zsP5uPJ-e72cLiur1NgGIZF9zE8SdVxQ-zm9dz-_e0jngRnNe1jK_BA"
            },
            {
                "proxy": "http://user132581:schrvd@37.221.80.188:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=e125fb2da4fa8402aad8fce0456a4511a34499b598fac18abc01b085b8b776e7; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJlMTI1ZmIyZGE0ZmE4NDAyYWFkOGZjZTA0NTZhNDUxMWEzNDQ5OWI1OThmYWMxOGFiYzAxYjA4NWI4Yjc3NmU3IiwiZXhwIjoxNzUxMjI4NzgzLCJpYXQiOjE3NTA2MjM5ODMsIm5iZiI6MTc1MDYyMzkyMywibm9uY2UiOiI2NjQyMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNmYzMWUxYTFjMDJhNDVmMDc5ZjMzYjc3ZmFhZThmOTRlZGQ3MWQ2YmNkN2IwYWMzMDBkOTNkYzNhNTQxIn0.6NKLCqazQD3d1kPKzH8KcfC2FWjluRsuykUpk53fQUMxuZ5h9_42WnaPmXyenLcM9PJaKdY6jPQKFBuMLupWAA"
            },
            {
                "proxy": "http://user132581:schrvd@45.91.160.28:3542",
                "cookie": "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=5c4df9306977eec418ce0482d07263f966e2937825f29321d00a6397b2b41dac; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI1YzRkZjkzMDY5NzdlZWM0MThjZTA0ODJkMDcyNjNmOTY2ZTI5Mzc4MjVmMjkzMjFkMDBhNjM5N2IyYjQxZGFjIiwiZXhwIjoxNzUxMjI4ODc0LCJpYXQiOjE3NTA2MjQwNzQsIm5iZiI6MTc1MDYyNDAxNCwibm9uY2UiOiI2MTg4MiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMDc2NWIwYzVlOTNiM2QwZjQ5ZTljMzczOWIxMjAyMTM0YzI4ZWQwMTA3NTEzNzA3ZWIxZTA1Yzg1Yzk4In0.QfW5KzEUUVOsA9u_djQ7KV6TxrcGmm3yErxJQu8zcHP3acci4JQZow2KNYD75wuVxC7Nh9xLVqotssZC5A70BQ"
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