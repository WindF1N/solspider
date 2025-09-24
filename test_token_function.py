#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функции получения токена
"""

import os
import sys
import subprocess
from typing import Optional

def _sync_get_token_from_script() -> Optional[str]:
    """Синхронный вызов скрипта padre_get_access_token.py"""
    try:
        # Запускаем скрипт padre_get_access_token.py
        script_path = os.path.join(os.path.dirname(__file__), "padre_get_access_token.py")
        result = subprocess.run(
            ["python", script_path],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__)
        )

        if result.returncode == 0:
            print("✅ Скрипт padre_get_access_token.py выполнен успешно")

            # Читаем токен из файла token.txt
            token_file = os.path.join(os.path.dirname(__file__), "token.txt")
            if os.path.exists(token_file):
                with open(token_file, 'r') as f:
                    token = f.read().strip()

                if token and token.startswith('eyJ'):
                    return token
                else:
                    print("❌ Токен в файле имеет неправильный формат")
                    return None
            else:
                print("❌ Файл token.txt не найден")
                return None
        else:
            print(f"❌ Ошибка выполнения скрипта: {result.stderr}")
            return None

    except Exception as e:
        print(f"❌ Ошибка при вызове скрипта: {e}")
        return None

if __name__ == "__main__":
    print("🔄 Тестируем функцию получения токена...")
    token = _sync_get_token_from_script()

    if token:
        print("✅ Токен получен успешно!")
        print(f"📏 Длина токена: {len(token)} символов")
        print(f"🔑 Начало токена: {token[:50]}...")
    else:
        print("❌ Не удалось получить токен")
