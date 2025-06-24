#!/usr/bin/env python3
"""
🌟 VIP TWITTER CONFIG 🌟
Конфигурация VIP Twitter аккаунтов для независимого мониторинга
"""

# VIP TWITTER АККАУНТЫ - основная конфигурация
VIP_TWITTER_ACCOUNTS = {
    'MoriCoinCrypto': {
        'enabled': True,  # Активирован для мониторинга
        'description': 'Mori Coin Crypto - ведущий сигнальный аккаунт',
        'priority': 'VIP',  # VIP приоритет с максимальным газом
        'auto_buy': True,  # 🚀 АВТОМАТИЧЕСКАЯ ПОКУПКА ВКЛЮЧЕНА!
        'buy_amount_sol': 6.4,  # VIP автопокупка: 6.4 SOL (~$896 при $140/SOL)
        'check_interval': 0.1,  # Мгновенная обработка без задержек
        'notify_unknown_contracts': True,  # Уведомлять даже о неизвестных контрактах
        'bypass_filters': True  # Обходить все фильтры - VIP статус
    },
    
    'elonmusk': {
        'enabled': False,  # Отключен (тестовый)
        'description': 'Илон Маск - глобальные сигналы',
        'priority': 'ULTRA',
        'auto_buy': False,
        'buy_amount_sol': 3.57,  # ~$500 при курсе $140/SOL
        'check_interval': 60,
        'notify_unknown_contracts': True,
        'bypass_filters': True
    },
    
    'VitalikButerin': {
        'enabled': False,  # Отключен (тестовый)
        'description': 'Виталик Бутерин - экспертные сигналы',
        'priority': 'ULTRA',
        'auto_buy': False,
        'buy_amount_sol': 7.14,  # ~$1000 при курсе $140/SOL
        'check_interval': 60,
        'notify_unknown_contracts': True,
        'bypass_filters': True
    },
    
    'cz_binance': {
        'enabled': False,  # Отключен (тестовый)
        'description': 'CZ Binance - биржевые сигналы',
        'priority': 'HIGH',
        'auto_buy': False,
        'buy_amount_sol': 5.36,  # ~$750 при курсе $140/SOL
        'check_interval': 45,
        'notify_unknown_contracts': True,
        'bypass_filters': True
    }
}

# НАСТРОЙКИ VIP МОНИТОРИНГА
VIP_MONITOR_SETTINGS = {
    'default_check_interval': 0.1,  # Базовый интервал проверки (секунды) - без задержек
    'max_retries': 3,  # Максимум попыток при ошибках
    'cache_cleanup_threshold': 1000,  # Очистка кэша при превышении
    'request_timeout': 15,  # Таймаут запросов к Nitter
    'log_level': 'INFO',  # Уровень логирования
    'enable_detailed_logging': True,  # Детальное логирование
    'send_startup_notification': True,  # Уведомление о запуске
    'send_error_notifications': True  # Уведомления об ошибках
}

# TELEGRAM VIP BOT НАСТРОЙКИ
VIP_TELEGRAM_CONFIG = {
    'bot_token': "8001870018:AAGwL4GiMC9TTKRMKfqghE6FAP4uBgGHXLU",
    'chat_id_env_var': 'VIP_CHAT_ID',  # Переменная окружения для VIP chat ID
    'parse_mode': 'HTML',
    'disable_web_page_preview': False,
    'timeout': 10,
    'retry_attempts': 3
}

# VIP NITTER COOKIES для ротации - используем те же что в основной системе
VIP_NITTER_COOKIES = [
    # Cookie 1 (без прокси)
    "techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4OTVlZGU2NDY2MGUzNzJmNWE2MDExYjQwMmU5ZmM1YTZmMzAxMWVkZjAxNWYxZjI5ZDdkYTlhNjE5YzJjZTMxIiwiZXhwIjoxNzUwODU5OTA0LCJpYXQiOjE3NTAyNTUxMDQsIm5iZiI6MTc1MDI1NTA0NCwibm9uY2UiOiIxNDg4OTciLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDNmNjI5ZGQ5ZjhjMDkyZGQ0ZDJmM2E3MDIyY2QwMzFmM2Y3ZmMyZjQ0MWIxZDE3YTgyYzE0MGQ1M2NiMSJ9.O1XvQu_1HCgDFU8ILIC-WlFoqen4d12nr-QvtrYsGJImvbEMRA9aZgVrjK1rrC9G10MAjeUOVq0bG5TcfER5BA",
    
    # Cookie 2 (с прокси 37.221.80.162)
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=a607cd2f9fc888da55745df416ca0ddce579222a010c9020a772768f2fa1ff55; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhNjA3Y2QyZjlmYzg4OGRhNTU3NDVkZjQxNmNhMGRkY2U1NzkyMjJhMDEwYzkwMjBhNzcyNzY4ZjJmYTFmZjU1IiwiZXhwIjoxNzUxMjI3MzY1LCJpYXQiOjE3NTA2MjI1NjUsIm5iZiI6MTc1MDYyMjUwNSwibm9uY2UiOiIxMTI1NTUiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDZhM2ViZTQwZDg2NWM1Njk2YjAyZGQ4MmZlZWI3ZmMzNzg1ZGE3NWFkMDJmODA2YzljMzBlYTU3MmNlZCJ9.AHEIImU75BSJKphf-XHOuneiSdmRFRyoXgUesDJnWu-ADJfPwQqTPYbmSqPDm97948-2agXl0tWN2mXpUL6eBQ",
    
    # Cookie 3 (с прокси 46.149.174.203)
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=550be1f6767b67c39b7b9581b96136a13993bff4c9962a80e48ef1ac521bb1de; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI1NTBiZTFmNjc2N2I2N2MzOWI3Yjk1ODFiOTYxMzZhMTM5OTNiZmY0Yzk5NjJhODBlNDhlZjFhYzUyMWJiMWRlIiwiZXhwIjoxNzUxMjI3NjE2LCJpYXQiOjE3NTA2MjI4MTYsIm5iZiI6MTc1MDYyMjc1Niwibm9uY2UiOiIxMjI4OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwM2FlMDhiMzJlM2YwZDJhNmY5NTIxNjMzYThkZWMyZDJmZmFkZTZmYWY5NzdmNDNmNTBiZjMwNzY1NDBlIn0.deJLruyJ4XwbClVRoiNM8ys6mYjz_a_WbI6eJJnzEFnqBaC-k_5NJWVsC8tL8bzo23optfIqdg6cZbPzZggYBQ",
    
    # Cookie 4-18 - все остальные из основной системы
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=9da6e511c844ee7b8931b1c65a96577ede92b24efb4591166a6fc0a5746f22d4; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI5ZGE2ZTUxMWM4NDRlZTdiODkzMWIxYzY1YTk2NTc3ZWRlOTJiMjRlZmI0NTkxMTY2YTZmYzBhNTc0NmYyMmQ0IiwiZXhwIjoxNzUxMjI3OTkyLCJpYXQiOjE3NTA2MjMxOTIsIm5iZiI6MTc1MDYyMzEzMiwibm9uY2UiOiI2ODA4IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBhOWI3NzY0YWUxNzRlZTg5Yzc3NjBhODYwNjg5OGE3NjhmZDI0ZWRiZGVhMWEwNTVlZjFmZmVmNjBjOWEifQ.LpKsMJLtHdfs3pWilQJ66ztfx9Np7Dh94A0zUF72YFX0IEauizIMmigLL5cHPLeMpYEQo6XL5JJxiJelEKEFDQ",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=b82012dc7e93544fd02ac4bf4e7f22041df4e6bd4e658f92b804722bd2c5003c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJiODIwMTJkYzdlOTM1NDRmZDAyYWM0YmY0ZTdmMjIwNDFkZjRlNmJkNGU2NThmOTJiODA0NzIyYmQyYzUwMDNjIiwiZXhwIjoxNzUxMjI4NDM5LCJpYXQiOjE3NTA2MjM2MzksIm5iZiI6MTc1MDYyMzU3OSwibm9uY2UiOiIxMzU2MzUiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDVmYzljNDZlYWNiOTZmNzYzNWViNTY4MmQxYzk1ZWQ3MWE4MTk5YzQ5NDhkYTIzZGNkMTRmNTM4NzkxZSJ9.NJKwLI30zkSPJLNdcHaryml3VkLs7tv8_JMEB52wKbWFrgKa6kywwUBPrS87L03YiKLlHW1kQA6Ak8X3rm1tBw",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=ad4a9c3d675eceb6bce30f69b40057337f27e5fee32fc5cf7f7ff49d4c944200; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJhZDRhOWMzZDY3NWVjZWI2YmNlMzBmNjliNDAwNTczMzdmMjdlNWZlZTMyZmM1Y2Y3ZjdmZjQ5ZDRjOTQ0MjAwIiwiZXhwIjoxNzUxMjI4NDk4LCJpYXQiOjE3NTA2MjM2OTgsIm5iZiI6MTc1MDYyMzYzOCwibm9uY2UiOiI5ODUzIiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDAzMjcxMzlhNDljMmI4MDJiODU3M2Q1YmVkM2M1YzNmNjAyNDI0NzI0OGIxMmFjNmUxNzJmNDFlMWQxNzAifQ.A2XmCo9hmrkwl34gMkX1uJpY-2-6V7l8A34V5pEiUm9As9D9K2-Q51IUULDaUfTXsqE6WBHuAAnxpwBgljFoDQ",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=d39f01fcd3c4d84fd21298c8c6b05d70db7d42dd91204c9278aa6c669ef09e9f; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJkMzlmMDFmY2QzYzRkODRmZDIxMjk4YzhjNmIwNWQ3MGRiN2Q0MmRkOTEyMDRjOTI3OGFhNmM2NjllZjA5ZTlmIiwiZXhwIjoxNzUxMjI4NTU4LCJpYXQiOjE3NTA2MjM3NTgsIm5iZiI6MTc1MDYyMzY5OCwibm9uY2UiOiI2ODU5IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDBmODYzNzI2ZGNhN2EwMWJiYzIyZTU0YzRhMWJmMmMwZDNiMTA5MWEzYzAxMDUxYWZiMzk1MzZiOWZjYWYifQ.vmz5F63IDpQgkhpP9XNdIbBEKGPUSsAltapMVxd1CZI_HRJsmy0lgG5FPZMSW1lo_5u35gs133fa4tD9GeSmBg",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=312c430e3cd6662928d09a1d5e613357e2b37dcc69a4b242bd705ca7cc38906c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIzMTJjNDMwZTNjZDY2NjI5MjhkMDlhMWQ1ZTYxMzM1N2UyYjM3ZGNjNjlhNGIyNDJiZDcwNWNhN2NjMzg5MDZjIiwiZXhwIjoxNzUxMjI4NzQzLCJpYXQiOjE3NTA2MjM5NDMsIm5iZiI6MTc1MDYyMzg4Mywibm9uY2UiOiIxMDI5NjUiLCJwb2xpY3lSdWxlIjoiZWQ1NWU4YTBiZGY3MDRjODUxZGNkYzI0NzlmZjEyZTIzNWM2NWNkNDYzMGRmMDE4MDRjOGU4MjM2YzM1NTcxNiIsInJlc3BvbnNlIjoiMDAwMDliOThiMjY4MzI5ODQyMmQxNTIxYmI4YmQxMDZjOWM4YTkxY2U2ODhjZjA1MDUxNGRjYzViMDVhYTI5MiJ9.DQMvFyweJzaK02R_kwYfIj7_n5y7BL-zsP5uPJ-e72cLiur1NgGIZF9zE8SdVxQ-zm9dz-_e0jngRnNe1jK_BA",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=e125fb2da4fa8402aad8fce0456a4511a34499b598fac18abc01b085b8b776e7; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJlMTI1ZmIyZGE0ZmE4NDAyYWFkOGZjZTA0NTZhNDUxMWEzNDQ5OWI1OThmYWMxOGFiYzAxYjA4NWI4Yjc3NmU3IiwiZXhwIjoxNzUxMjI4NzgzLCJpYXQiOjE3NTA2MjM5ODMsIm5iZiI6MTc1MDYyMzkyMywibm9uY2UiOiI2NjQyMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNmYzMWUxYTFjMDJhNDVmMDc5ZjMzYjc3ZmFhZThmOTRlZGQ3MWQ2YmNkN2IwYWMzMDBkOTNkYzNhNTQxIn0.6NKLCqazQD3d1kPKzH8KcfC2FWjluRsuykUpk53fQUMxuZ5h9_42WnaPmXyenLcM9PJaKdY6jPQKFBuMLupWAA",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=5c4df9306977eec418ce0482d07263f966e2937825f29321d00a6397b2b41dac; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI1YzRkZjkzMDY5NzdlZWM0MThjZTA0ODJkMDcyNjNmOTY2ZTI5Mzc4MjVmMjkzMjFkMDBhNjM5N2IyYjQxZGFjIiwiZXhwIjoxNzUxMjI4ODc0LCJpYXQiOjE3NTA2MjQwNzQsIm5iZiI6MTc1MDYyNDAxNCwibm9uY2UiOiI2MTg4MiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwMDc2NWIwYzVlOTNiM2QwZjQ5ZTljMzczOWIxMjAyMTM0YzI4ZWQwMTA3NTEzNzA3ZWIxZTA1Yzg1Yzk4In0.QfW5KzEUUVOsA9u_djQ7KV6TxrcGmm3yErxJQu8zcHP3acci4JQZow2KNYD75wuVxC7Nh9xLVqotssZC5A70BQ",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=1e698693eec2819b87e8e8035f1975270a89664b99272250c7ef4e58d2f62390; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxZTY5ODY5M2VlYzI4MTliODdlOGU4MDM1ZjE5NzUyNzBhODk2NjRiOTkyNzIyNTBjN2VmNGU1OGQyZjYyMzkwIiwiZXhwIjoxNzUxMjI4OTI0LCJpYXQiOjE3NTA2MjQxMjQsIm5iZiI6MTc1MDYyNDA2NCwibm9uY2UiOiI1ODA3IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDAwMTQxODE1NzlhZTNmYWUzNTU0ZDRhZDIzODFhNmQ0MWNhMDhkZDQ2MWU3ZTQzOGJlMTkwYTVhNWFhMTgifQ.mIfg66_9lnde6OUhBQyexszm-kCA9bzCLhuRc32ozqnBx116ItLZqo_ApgEUPrjkgKiJP_rBGvmEcuqF2XoCCA",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=8caba8f4a08b37dc0d81c16456fd2297d57f0f65abba25bfa75857afc6a33632; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4Y2FiYThmNGEwOGIzN2RjMGQ4MWMxNjQ1NmZkMjI5N2Q1N2YwZjY1YWJiYTI1YmZhNzU4NTdhZmM2YTMzNjMyIiwiZXhwIjoxNzUxMjMwMjc1LCJpYXQiOjE3NTA2MjU0NzUsIm5iZiI6MTc1MDYyNTQxNSwibm9uY2UiOiIxMDU1NCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYWZmMzM5OThlNDQ5ZmI2N2E2ZTZiMDIxNDdmYzUyZjc4YjA0NjI3NGI5YTlhMTU5OTExYjBjMWRlNzMxIn0.PD0aMKkIQjvIVr31i3LHrKoj9ZhvQZhLijE9UYJ8OYrVjc1didSrogTzD6r6m9FXN4PV0pnrRg4nYDjsIAiAAg",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=790091eb589bcaa95765ac08312aa4fcb08076bf7f908b4e133d95781d605ee4; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI3OTAwOTFlYjU4OWJjYWE5NTc2NWFjMDgzMTJhYTRmY2IwODA3NmJmN2Y5MDhiNGUxMzNkOTU3ODFkNjA1ZWU0IiwiZXhwIjoxNzUxMjMwMzM2LCJpYXQiOjE3NTA2MjU1MzYsIm5iZiI6MTc1MDYyNTQ3Niwibm9uY2UiOiI1ODk5IiwicG9saWN5UnVsZSI6ImVkNTVlOGEwYmRmNzA0Yzg1MWRjZGMyNDc5ZmYxMmUyMzVjNjVjZDQ2MzBkZjAxODA0YzhlODIzNmMzNTU3MTYiLCJyZXNwb25zZSI6IjAwMDA1ZTk0Yzg5YmRlYmZhMGI0NjdhMDBlMTlhYmM1ZjA0ODIwYjM2NDgyMTA3ZjYxZGVlY2Q4ODM5NWExMjQifQ.Hlkz9FruO0vwuqndxHa2drZiWN1KAtbKK1yAjn7mtZ24jJziJEE3ka81VFciW7uEcoE_qXqfw1vLNWIFwZU-BA",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=8020fcf0b1a215c39300529b857c6edb1c228b1a4e4a437032b419c77822043c; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI4MDIwZmNmMGIxYTIxNWMzOTMwMDUyOWI4NTdjNmVkYjFjMjI4YjFhNGU0YTQzNzAzMmI0MTljNzc4MjIwNDNjIiwiZXhwIjoxNzUxMjMwMzk0LCJpYXQiOjE3NTA2MjU1OTQsIm5iZiI6MTc1MDYyNTUzNCwibm9uY2UiOiIzMTk4OCIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNWY2MGQyZWY2OTVjNGFlZTMwMjVhZjNlNmQ2MWEzNWRmZTVlYmMzZGJkYmYyMjU2MzdmNzhjOWVmMDc5In0.6EmW6xK0gT-I9O9bhHtEOBw6jVpiWabdUHiN2FTqn-d6gnUAKJXjOtTXNnDA7KrJzEp9SkFjv3_DExVoCoAbDQ",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=40d28cf964d9c90b62d472174f87c482331adb84b5c4fc4b26bee3d603f66a33; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiI0MGQyOGNmOTY0ZDljOTBiNjJkNDcyMTc0Zjg3YzQ4MjMzMWFkYjg0YjVjNGZjNGIyNmJlZTNkNjAzZjY2YTMzIiwiZXhwIjoxNzUxMjMwNDQxLCJpYXQiOjE3NTA2MjU2NDEsIm5iZiI6MTc1MDYyNTU4MSwibm9uY2UiOiI3OTY1NyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZTFlZmVlYjA1YTI5NjgxMGI1NDRiMmQ2YWQ2ZTMyNGI3YzY5ZjhkMjk2NWM3MGI3ZDk1OWNiYWM0ZGI1In0.P4vpWS7TPGXw4XgZ2lK2excSkWgh7RfpwMJdgJb0FWam81VMBAdhpBR9b1N92GE-U6NN25giZQQFi0nBlEjmDw",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=fc43083e591f95d07276242097c007719467997f6bff8b1c55c2b35c77b37e3b; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiJmYzQzMDgzZTU5MWY5NWQwNzI3NjI0MjA5N2MwMDc3MTk0Njc5OTdmNmJmZjhiMWM1NWMyYjM1Yzc3YjM3ZTNiIiwiZXhwIjoxNzUxMjMwNDg3LCJpYXQiOjE3NTA2MjU2ODcsIm5iZiI6MTc1MDYyNTYyNywibm9uY2UiOiI4OTMwMiIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwZmM3ZjIwZjE3ZDgxMjk5MmI4Y2E5YjBmYTc4NTAxYmRlYjA5MGViYmNhYzQ3OGNlODhjYjZjNGYzYWJjIn0.YDD8dTw_KPuQzvegSCBid3HgI0oNTtilzMIx8-Ruy5zCDv3tvUyWR34IXBP6GLgo2yPeg1uR2xolNqVzBXUYAQ",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=1de7ef7f870cabbb4233de8d5edc9db65e3d2ab7a6728b9e79cc5edf714e5526; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIxZGU3ZWY3Zjg3MGNhYmJiNDIzM2RlOGQ1ZWRjOWRiNjVlM2QyYWI3YTY3MjhiOWU3OWNjNWVkZjcxNGU1NTI2IiwiZXhwIjoxNzUxMjMwNTI4LCJpYXQiOjE3NTA2MjU3MjgsIm5iZiI6MTc1MDYyNTY2OCwibm9uY2UiOiIyMTE0NyIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwYTg0MjMwMDkxNWE4MDE4MzA0NjE5ZDJlZTJkNGE2ZWU2MTdkY2Q5ZWJiOTIzYzI3NGNiNWFjYTk1YjhhIn0.ZRYfUUNHuuEwZ3YCooNjELtDw6mLQHyCmL0-WeiVTxgdo6qKRquAcl5oF0vrgzpxOdLtQMjeW5mq8JLSnLTsBQ",
    "techaro.lol-anubis-cookie-test-if-you-block-this-anubis-wont-work=2e5d2cfe52c1b4c969b6f3aaea069a6cd14c7e3cd0b93fb8a3b80915a3a12cbe; techaro.lol-anubis-auth-for-nitter.tiekoetter.com=eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhY3Rpb24iOiJDSEFMTEVOR0UiLCJjaGFsbGVuZ2UiOiIyZTVkMmNmZTUyYzFiNGM5NjliNmYzYWFlYTA2OWE2Y2QxNGM3ZTNjZDBiOTNmYjhhM2I4MDkxNWEzYTEyY2JlIiwiZXhwIjoxNzUxMjMwNTY5LCJpYXQiOjE3NTA2MjU3NjksIm5iZiI6MTc1MDYyNTcwOSwibm9uY2UiOiI4MTQ4NSIsInBvbGljeVJ1bGUiOiJlZDU1ZThhMGJkZjcwNGM4NTFkY2RjMjQ3OWZmMTJlMjM1YzY1Y2Q0NjMwZGYwMTgwNGM4ZTgyMzZjMzU1NzE2IiwicmVzcG9uc2UiOiIwMDAwNmZhNWI5MTE3YjE1ZDI2OGEzMzE5ZGEwNGFkM2QzMTBhODc4YzNmNzE1ZTNhNGQzZDJmMzUyMGVjNDRjIn0.KfNDo_g7hWGnxh4vR1J7dWlnWJYJpj4C26tR8XINc5V3_UOzKC_lTM-14I0yx4sOPVGwT2mJIFb4PjS24S3GAQ"
]

# VIP ПРОКСИ для ротации - используем те же что в основной системе
VIP_PROXIES = [
    # Прокси pump_bot.py
    None,  # Без прокси
    "http://user132581:schrvd@37.221.80.162:3542",
    "http://user132581:schrvd@46.149.174.203:3542",
    "http://user132581:schrvd@37.221.80.181:3542",
    "http://user132581:schrvd@37.221.80.125:3542",
    "http://user132581:schrvd@37.221.80.5:3542",
    "http://user132581:schrvd@213.139.231.127:3542",
    "http://user132581:schrvd@37.221.80.23:3542",
    "http://user132581:schrvd@37.221.80.188:3542",
    "http://user132581:schrvd@45.91.160.28:3542",
    
    # Прокси background_monitor.py
    "http://user132581:schrvd@194.34.250.178:3542",
    "http://user132581:schrvd@149.126.199.210:3542",
    "http://user132581:schrvd@149.126.199.53:3542",
    "http://user132581:schrvd@149.126.211.4:3542",
    "http://user132581:schrvd@149.126.211.208:3542",
    "http://user132581:schrvd@149.126.212.129:3542",
    "http://user132581:schrvd@149.126.240.124:3542",
    "http://user132581:schrvd@149.126.227.154:3542"
]

# РАСШИРЕННЫЕ НАСТРОЙКИ ГАЗА для максимально быстрого подтверждения
GAS_CONFIG = {
    # 🔥 VIP сигналы - высокий приоритет (0.19 SOL)
    'vip_signals': {
        'priority_fee_sol': 0.19,  # 0.19 SOL (~$26.6 при $140/SOL)
        'description': 'Высокий газ для VIP сигналов - быстрое подтверждение'
    },
    
    # 📱 Twitter токены - средний приоритет
    'twitter_tokens': {
        'priority_fee_sol': 0.002,   # ~$0.28
        'description': 'Средний газ для Twitter токенов'
    },
    
    # 🆕 Новые токены - обычный приоритет
    'new_tokens': {
        'priority_fee_sol': 0.001,   # ~$0.14
        'description': 'Обычный газ для новых токенов'
    },
    
    # 🚀 ULTRA VIP - для экстремально важных сигналов ($5)
    'ultra_vip': {
        'priority_fee_sol': 0.0357,  # ~$5.00
        'description': 'Экстремальный газ для критически важных сигналов'
    }
}

def get_gas_fee(signal_type='new_tokens', sol_price_usd=140):
    """
    Возвращает оптимальную комиссию газа для типа сигнала
    
    Args:
        signal_type: тип сигнала ('vip_signals', 'twitter_tokens', 'new_tokens', 'ultra_vip')
        sol_price_usd: текущий курс SOL в USD для динамического расчета
    """
    config = GAS_CONFIG.get(signal_type, GAS_CONFIG['new_tokens'])
    
    # Можно добавить динамический пересчет на основе курса
    # Пока возвращаем фиксированное значение
    return config['priority_fee_sol']

def get_gas_description(signal_type='new_tokens'):
    """Возвращает описание настроек газа"""
    config = GAS_CONFIG.get(signal_type, GAS_CONFIG['new_tokens'])
    return config['description']

# НАСТРОЙКИ АВТОМАТИЧЕСКОЙ ПОКУПКИ
AUTO_BUY_CONFIG = {
    'enabled_accounts': ['MoriCoinCrypto'],  # Аккаунты с автопокупкой
    'default_amount_sol': 6.4,  # VIP автопокупка: 6.4 SOL (~$896 при $140/SOL)
    'max_amount_sol': 14.29,  # Максимальная сумма в SOL (~$2000)
    'execution_timeout': 30,  # Таймаут выполнения покупки
    'retry_attempts': 2,  # Попытки при ошибках
    'simulate_only': False,  # 🚀 РЕАЛЬНАЯ АВТОПОКУПКА ВКЛЮЧЕНА!
    'trading_platform': 'axiom',  # Используемая платформа (axiom/jupiter)
    'slippage_percent': 15,  # Проскальзывание %
    'priority_fee': 0.19  # 🔥 VIP ПРИОРИТЕТНАЯ КОМИССИЯ 0.19 SOL (~$26.6 при $140/SOL)
}

# КНОПКИ ДЛЯ VIP УВЕДОМЛЕНИЙ
VIP_KEYBOARD_BUTTONS = {
    'buy_axiom': {"text": "💎 Купить на Axiom", "url_template": "https://axiom.trade/t/{contract}"},
    'quick_buy': {"text": "⚡ QUICK BUY", "url_template": "https://t.me/alpha_web3_bot?start=call-dex_men-SO-{contract}"},
    'dexscreener': {"text": "📊 DexScreener", "url_template": "https://dexscreener.com/solana/{contract}"},
    'pump_fun': {"text": "🚀 Pump.fun", "url_template": "https://pump.fun/{contract}"}
}

# ШАБЛОНЫ СООБЩЕНИЙ
VIP_MESSAGE_TEMPLATES = {
    'contract_found': """🌟 <b>VIP TWITTER СИГНАЛ!</b> 🌟

🔥 <b>{description}</b>
👤 <b>От:</b> @{username}

📍 <b>Контракт:</b> <code>{contract}</code>
📱 <b>Твит:</b>
<blockquote>{tweet_text}</blockquote>

⚡ <b>МГНОВЕННЫЙ VIP СИГНАЛ!</b>
🎯 <b>Приоритет:</b> {priority}
🚀 <b>Время действовать СЕЙЧАС!</b>
<b>🕐 Время:</b> {timestamp}""",

    'auto_buy_success': """

💰 <b>АВТОМАТИЧЕСКАЯ ПОКУПКА ВЫПОЛНЕНА!</b>
✅ <b>Статус:</b> {status}
⚡ <b>Сумма:</b> {sol_amount:.6f} SOL
⏱️ <b>Время:</b> {execution_time:.2f}с
🔗 <b>TX:</b> <code>{tx_hash}</code>""",

    'auto_buy_error': """

❌ <b>ОШИБКА АВТОМАТИЧЕСКОЙ ПОКУПКИ</b>
⚠️ <b>Ошибка:</b> {error}""",

    'auto_buy_enabled': """

🤖 <b>Автоматическая покупка активирована!</b>""",

    'startup': """🌟 <b>VIP TWITTER MONITOR ЗАПУЩЕН!</b>

📊 <b>Активных аккаунтов:</b> {active_accounts}
⚡ <b>Режим мониторинга:</b> НЕПРЕРЫВНЫЙ (без задержек)
🤖 <b>Автопокупка активна для:</b> {auto_buy_accounts}

✅ <b>Система готова к работе!</b>
🕐 <b>Время запуска:</b> {timestamp}""",

    'error_notification': """❌ <b>ОШИБКА VIP МОНИТОРИНГА</b>

🚫 <b>Проблема:</b> {error_type}
📝 <b>Описание:</b> {error_message}
👤 <b>Аккаунт:</b> @{username}
🕐 <b>Время:</b> {timestamp}

⚠️ <b>Мониторинг продолжается...</b>"""
}

def get_active_accounts():
    """Возвращает список активных VIP аккаунтов"""
    return {username: config for username, config in VIP_TWITTER_ACCOUNTS.items() 
            if config.get('enabled', False)}

def get_auto_buy_accounts():
    """Возвращает список аккаунтов с автопокупкой"""
    return {username: config for username, config in VIP_TWITTER_ACCOUNTS.items() 
            if config.get('enabled', False) and config.get('auto_buy', False)}

def get_account_config(username):
    """Получает конфигурацию конкретного аккаунта"""
    return VIP_TWITTER_ACCOUNTS.get(username, {})

def is_account_enabled(username):
    """Проверяет включен ли аккаунт"""
    return VIP_TWITTER_ACCOUNTS.get(username, {}).get('enabled', False)

def get_check_interval(username):
    """Получает интервал проверки для аккаунта"""
    account_config = VIP_TWITTER_ACCOUNTS.get(username, {})
    return account_config.get('check_interval', VIP_MONITOR_SETTINGS['default_check_interval'])

def format_vip_message(template_name, **kwargs):
    """Форматирует VIP сообщение по шаблону"""
    template = VIP_MESSAGE_TEMPLATES.get(template_name, "")
    try:
        return template.format(**kwargs)
    except KeyError as e:
        return f"❌ Ошибка форматирования сообщения: отсутствует параметр {e}"

def create_keyboard(contract):
    """Создает клавиатуру для VIP уведомления"""
    keyboard = []
    
    # Первая строка кнопок
    row1 = []
    for button_key in ['buy_axiom', 'quick_buy']:
        if button_key in VIP_KEYBOARD_BUTTONS:
            button = VIP_KEYBOARD_BUTTONS[button_key].copy()
            button['url'] = button['url_template'].format(contract=contract)
            del button['url_template']
            row1.append(button)
    
    if row1:
        keyboard.append(row1)
    
    # Вторая строка кнопок
    row2 = []
    for button_key in ['dexscreener']:
        if button_key in VIP_KEYBOARD_BUTTONS:
            button = VIP_KEYBOARD_BUTTONS[button_key].copy()
            button['url'] = button['url_template'].format(contract=contract)
            del button['url_template']
            row2.append(button)
    
    if row2:
        keyboard.append(row2)
    
    return keyboard

# Экспортируемые конфигурации
__all__ = [
    'VIP_TWITTER_ACCOUNTS',
    'VIP_MONITOR_SETTINGS', 
    'VIP_TELEGRAM_CONFIG',
    'VIP_NITTER_COOKIES',
    'VIP_PROXIES',
    'AUTO_BUY_CONFIG',
    'VIP_KEYBOARD_BUTTONS',
    'VIP_MESSAGE_TEMPLATES',
    'get_active_accounts',
    'get_auto_buy_accounts',
    'get_account_config',
    'is_account_enabled',
    'get_check_interval',
    'format_vip_message',
    'create_keyboard'
] 