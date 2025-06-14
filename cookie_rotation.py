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
        # Новые cookies для pump_bot от пользователя (база a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49)
        self.cookies = [
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc1ODY2LCJpYXQiOjE3NDk1NzEwNjYsIm5iZiI6MTc0OTU3MTAwNiwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.JBGVExmG0n4nRtiAJeDkXX9IZnkISQFUa_uJhie9xtQGrc_3JIVHuWYWr8ToGGVrzf_HS4yNyIJCl4IhArU7Bw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc1OTUyLCJpYXQiOjE3NDk1NzExNTIsIm5iZiI6MTc0OTU3MTA5Miwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.zJ_BWEsshpC3Fnsl36I6t9FXnZb3lU4HuAOfMWOptrDrvBs3K4wYRoG7BehusaMwMZsFMl91FiUNMmtfpPFFDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc1OTczLCJpYXQiOjE3NDk1NzExNzMsIm5iZiI6MTc0OTU3MTExMywibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.X0ucX1ZsqHtAIbXwKxOhxAB2fr70HHNsgTMIv6x6yPf3-B6kYDwMvXzguJUUU9riZ_ta2cTSdTf87f91LK5wCA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MDA0LCJpYXQiOjE3NDk1NzEyMDQsIm5iZiI6MTc0OTU3MTE0NCwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.feug_zRgouYAg0zaL2AoHeaJkx3XRq6X5ZaL3-dCgVN6xLIQAYcvcCW--63UT14h_N-1Utpr0QFQUT-7hZITCQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MDE4LCJpYXQiOjE3NDk1NzEyMTgsIm5iZiI6MTc0OTU3MTE1OCwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.JjNPBsfqDYurbpK_0XWc4E4GUlZZJGQc0Y4zqqFvsCcNQRoSVBQU6H1qVPgJURYblCqzfMJGq1fi6V3lxjJoDQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MDczLCJpYXQiOjE3NDk1NzEyNzMsIm5iZiI6MTc0OTU3MTIxMywibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.EjETCR8ZxEz1Lppwm4v933rgRJ3FQ-GwQQbl-dQY6dUKcMsK--8Tpssc5-7SHY4bogSatjldal-E3iwPK9Y3Bw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MDkwLCJpYXQiOjE3NDk1NzEyOTAsIm5iZiI6MTc0OTU3MTIzMCwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.PrlEoe3FwE1H9BToJtaHp7l2PpPzqfe3cuZKw4yq-CgP8Cori1JiLcdWpLEWKK2X0XRPuWS_44Af2MxIvmXrBw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MTE0LCJpYXQiOjE3NDk1NzEzMTQsIm5iZiI6MTc0OTU3MTI1NCwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.YBeaiexW3yJYaL9ExuJh8e37JIeP0oqlcZwGj8hA_063wBRTqVzhKIdF420TCOA6rCEqc91M9oUWWwtyjtZeCw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MTI5LCJpYXQiOjE3NDk1NzEzMjksIm5iZiI6MTc0OTU3MTI2OSwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.GnTrjosD8uQO-pq2hmv5G2Ki_gYX3LdvslREdEEVBxdJfnkboQOzUhpml6VpSrr9d6N6ZH5Wr_2OcHkOakkdDA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MTQ1LCJpYXQiOjE3NDk1NzEzNDUsIm5iZiI6MTc0OTU3MTI4NSwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.Qc_7HaUWIXIEbNSJF60Sc7ucLmuusXsrYjMabIdYg23WP_6Yk38e_lQjf1D5zpKojjfzLY07uVTJ0k-JzzQzAQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MTU3LCJpYXQiOjE3NDk1NzEzNTcsIm5iZiI6MTc0OTU3MTI5Nywibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.0E5aiciRRwr9ytOSECNoS8KMDhj9uTNJQezCSThCdShdpVZYr_Nwoh0U9RSTjIW8lqtYS2vHZYzMvqS8XHmuBQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MTc3LCJpYXQiOjE3NDk1NzEzNzcsIm5iZiI6MTc0OTU3MTMxNywibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.eh7IYEm6JzYJYqAFofpf1jAjJcXB8816prqFnbeRI0OZQF5ugAKMlLPyfE3ky9meon5Q9kSPy7YYZ5t_agOHAA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a481f367aa11eec3e352881c914ffe2e4e819f820a13d45f46692553287c0e49; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNDgxZjM2N2FhMTFlZWMzZTM1Mjg4MWM5MTRmZmUyZTRlODE5ZjgyMGExM2Q0NWY0NjY5MjU1MzI4N2MwZTQ5IiwiZXhwIjoxNzUwMTc2MjQxLCJpYXQiOjE3NDk1NzE0NDEsIm5iZiI6MTc0OTU3MTM4MSwibm9uY2UiOiI0MzgyIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1YjJkOTFmZjZjODcyMzUzOTdhNzU2NmI2MDdlMjIxZWI5NTE1NzE1OGM3NWFjZTVkYjhmNzhiMTdiZTIifQ.m3YaW8U2hXWevtrHwj-PuMWAfH9gcpP3iW-Kjvka2rRhLE4zY0FtSIjckqU35udN3oUTudgBWcqytIck5BFZCA"
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
        # Новые cookies для background_monitor от пользователя
        self.cookies = [
            "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiMGEyOWM0YzcwZGM0YzYxMjE2NTNkMzQwYTU0YTNmNTFmZmJlNDIwOGM4MWZkZmUxNDA4MTY2MGNmMDc3ZGY2IiwiZXhwIjoxNzQ5NjAyOTA3LCJpYXQiOjE3NDg5OTgxMDcsIm5iZiI6MTc0ODk5ODA0Nywibm9uY2UiOiIxMzI4MSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYWEwZjdmMjBjNGQ0MGU5ODIzMWI4MDNmNWZiMGJlMGZjZmZiOGRhOTIzNDUyNDdhZjU1Yjk1MDJlZWE2In0.615N6HT0huTaYXHffqbBWqlpbpUgb7uVCh__TCoIuZLtGzBkdS3K8fGOPkFxHrbIo2OY3bw0igmtgDZKFesjAg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxNjA3LCJpYXQiOjE3NDk1NjY4MDcsIm5iZiI6MTc0OTU2Njc0Nywibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.JxfrDbGynNqeGJX8ml0IgLesYARdqXhaPx6NO6d-6jYawwxu4Ly9ExDReofDV5QIOa2eqvcp8FumWixE_-eVDA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxNjQyLCJpYXQiOjE3NDk1NjY4NDIsIm5iZiI6MTc0OTU2Njc4Miwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.THmfiDD3YM6joEFcOr0IQwTAv0m0mFjKy66kEqOtabUccedOvMJs2ZmFXH_hFtC08u3eBYq_EO7Lhohhi6dnDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxNzEzLCJpYXQiOjE3NDk1NjY5MTMsIm5iZiI6MTc0OTU2Njg1Mywibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.TCGCxBFt_EYVMr21JW_PX8T6NiQIzP1cQYGFXBTxr8PcYyYB4qQOd69gpmoF4-ys4GXQKjzRI4I7CnKHw0aODw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxNzM4LCJpYXQiOjE3NDk1NjY5MzgsIm5iZiI6MTc0OTU2Njg3OCwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.rr_T_bVa6UxX3WQYt-S8QC7hMCFHPIoxXaynVEql2bqxEIalMTiay8-x87CVfruBunQYQ3_n2EjZKXzIY7JiAw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxNzYxLCJpYXQiOjE3NDk1NjY5NjEsIm5iZiI6MTc0OTU2NjkwMSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.Z3tCI_59CYK10_oJKLz7uOIy_fBPaYG11T2R4itwmyBK6ZJacB8EMUBOTOeGGdDWkD6AUxuHa0G4kn1v4zItAg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxODA5LCJpYXQiOjE3NDk1NjcwMDksIm5iZiI6MTc0OTU2Njk0OSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.huLiJPLsDHBIF7KlI_yPgCPVFkKd-Z9KJxM_bRPK9lijD6AsRF2fXY7FtUabzD1MQXzyfiMsUkx7wJC-SiHyBg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxOTQwLCJpYXQiOjE3NDk1NjcxNDAsIm5iZiI6MTc0OTU2NzA4MCwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.vk68Bwbj6WBkd5MtTGEQWF5bi39bCPb0vPc7q4TnRAL1IlfnDUxjARF_L9ZBPQ1-g4o-FVWPLUvC4gXSLIdhBQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcxOTY5LCJpYXQiOjE3NDk1NjcxNjksIm5iZiI6MTc0OTU2NzEwOSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.udRngon8c1ZB4Pcmr_rUlNBNrx96c_zF55yZXu_oFTC8X4UenB-MSbmyorsCL4-z1aNeFOr8cmYY5_4lwQq3Cg",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMDAyLCJpYXQiOjE3NDk1NjcyMDIsIm5iZiI6MTc0OTU2NzE0Miwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.Uy3O3_pIuEdInryqnYfYyJRXveizPdoVq3Z0AXshDX-aYjqP_xRWFOjvvLkO81nCpzDqscPMe9w2bXJAKdssAA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMDI5LCJpYXQiOjE3NDk1NjcyMjksIm5iZiI6MTc0OTU2NzE2OSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.JQ7Na5X9MT7dZpMMggU18jyFpys-rU_HPcrU2rPP_QQ5zLgv5EOgXWQbYyhbD1S5pcfhVRJsDscFMbmiVabRBQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMDgyLCJpYXQiOjE3NDk1NjcyODIsIm5iZiI6MTc0OTU2NzIyMiwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.Zy5L98b1NS5iOApG1XgZFnbebme2skLI2vwT4zuvjoFPpX67M5wVTfKjFEoDmO2S6mE4wJf85IdDgJJ6uWYZCQ",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMTA5LCJpYXQiOjE3NDk1NjczMDksIm5iZiI6MTc0OTU2NzI0OSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.CVNE7hFmmmRIVDviCTalvEmuF4xv1utA5v3f4YMqdUTVzkQBKuaEbf7y3SyCm35nq88ViQgWOHSNJ-Tjmx_ZDw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMTMxLCJpYXQiOjE3NDk1NjczMzEsIm5iZiI6MTc0OTU2NzI3MSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.dtsJfhQFlba7bnaSxknQNRxjHovOmQKZQquiXtQAFhPrwRIYa-Afrczcn99pu811-h5cH7Ma7xH8RuVMitQzCA",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMTU1LCJpYXQiOjE3NDk1NjczNTUsIm5iZiI6MTc0OTU2NzI5NSwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.8gzckFHJAjW3vyuzlttR_sIntJgT8ltPs3erVjHde4j_zKiXtMEM8iAIAHEnB39YcvWlooFlWux9OvJ8L0vgBw",
            "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=f5e4f074ce9769d472de00a5a8ab207cbd62f5324a20c534170bf878b83195fd; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmNWU0ZjA3NGNlOTc2OWQ0NzJkZTAwYTVhOGFiMjA3Y2JkNjJmNTMyNGEyMGM1MzQxNzBiZjg3OGI4MzE5NWZkIiwiZXhwIjoxNzUwMTcyMTgwLCJpYXQiOjE3NDk1NjczODAsIm5iZiI6MTc0OTU2NzMyMCwibm9uY2UiOiIxNTU3NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZGZmMjg1MDEyNmMxODdjM2E4YTMwZGQ2MzIxZTFmYzlkMjRkOGVlYWMyYTRkYWEzNmY4NTljY2VlN2ZmIn0.MWX7n-_3j2AoCOgRT81RxDxHDh8nGeSyRVWDpOJTrNhN5nRkYLwGoIX7g0agIc4CKORDvVtF8G0kftQZzoTiCQ"
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