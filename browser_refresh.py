#!/usr/bin/env python3
"""
Скрипт для автоматического обновления страницы браузера
Полезно для обновления IndexedDB и Local Storage
"""

import time
import subprocess
import sys
from pathlib import Path

# Константы для Windows (не используется в WSL)
CREATE_NO_WINDOW = 0x08000000

def refresh_existing_window(url="https://trade.padre.gg/trade/solana/TQnDxmfeV9G2cVPywPG5q5Ri37RNCoRyTzA7TLsvnt1"):
    """
    Обновляет существующее окно браузера вместо открытия нового
    """
    print(f"🔄 Обновляем существующее окно браузера...")

    try:
        # Получаем домен из URL для поиска
        from urllib.parse import urlparse
        domain = urlparse(url).netloc

        # Способ 1: Через PowerShell - находим окно и отправляем F5 (обновление)
        try:
            # PowerShell скрипт для поиска окна и отправки клавиши F5
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            $processes = Get-Process msedge -ErrorAction SilentlyContinue
            Write-Host "Поиск окон браузера..."
            $found = $false
            foreach ($process in $processes) {{
                $title = $process.MainWindowTitle
                Write-Host "Проверяем окно: '$title'"
                if ($title -like '*{domain}*' -or $title -like '*trade.padre.gg*' -or $title -like '*padre*') {{
                    Write-Host "Найдено подходящее окно: '$title'"
                    Write-Host "Активируем окно, открываем нужный URL и закрываем другие вкладки..."
                    # Активируем окно браузера
                    $process | Select-Object -First 1 | ForEach-Object {{
                        [Microsoft.VisualBasic.Interaction]::AppActivate($_.Id)
                    }}
                    Start-Sleep -Milliseconds 500

                    # Открываем нужный URL в новой вкладке (Ctrl+T, затем вводим URL)
                    Write-Host "Открываем новую вкладку с нужным URL..."
                    [System.Windows.Forms.SendKeys]::SendWait('^t')  # Ctrl+T для новой вкладки
                    Start-Sleep -Milliseconds 300
                    [System.Windows.Forms.SendKeys]::SendWait('{url}')  # Вводим URL
                    Start-Sleep -Milliseconds 200
                    [System.Windows.Forms.SendKeys]::SendWait('~')  # Enter
                    Start-Sleep -Milliseconds 1000  # Ждём загрузки страницы

                    # Закрываем все другие вкладки (Ctrl+W для каждой вкладки)
                    Write-Host "Закрываем все другие вкладки..."
                    # Повторяем Ctrl+W несколько раз, чтобы закрыть все вкладки кроме текущей
                    for ($i = 1; $i -le 10; $i++) {{
                        [System.Windows.Forms.SendKeys]::SendWait('^w')  # Ctrl+W закрывает вкладку
                        Start-Sleep -Milliseconds 200
                    }}
                    Start-Sleep -Milliseconds 500

                    Write-Host "Все операции выполнены для процесса: $($process.Id)"
                    $found = $true
                    exit 0
                }}
            }}
            if (-not $found) {{
                Write-Host "Подходящее окно не найдено"
            }}
            exit 1
            """

            cmd = ["powershell.exe", "-Command", ps_script]
            result = subprocess.run(cmd, capture_output=True, timeout=10, text=True, encoding='cp1251')

            if result.returncode == 0 and "Все операции выполнены" in result.stdout:
                print("✅ Окно найдено, URL открыт и другие вкладки закрыты")
                return True  # УСПЕХ! Возвращаемся сразу
            else:
                print(f"⚠️ Окно не найдено или не удалось обновить: {result.stdout.strip()}")

        except Exception as e:
            print(f"⚠️ PowerShell метод обновления не сработал: {e}")

        # Способ 2: Использование режима --app для открытия в отдельном окне
        try:
            print(f"🔄 Пробуем открыть {url} в режиме --app...")
            # Используем --app режим для открытия в отдельном окне приложения
            cmd = ["cmd.exe", "/c", f'start msedge.exe --app="{url}"']
            subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
            print("✅ URL открыт в режиме --app (отдельное окно приложения)")
            return True
        except Exception as e:
            print(f"⚠️ Режим --app не сработал: {e}")

        # Способ 3: Параметр --new-tab (может использовать существующую вкладку)
        try:
            print(f"🔄 Пробуем открыть {url} через --new-tab...")
            cmd = ["cmd.exe", "/c", f'start msedge.exe --new-tab "{url}"']
            subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
            print("✅ URL открыт через --new-tab (должен использовать существующее окно)")
            return True
        except Exception as e:
            print(f"⚠️ Параметр --new-tab не сработал: {e}")

        # Способ 4: Через PowerShell без дополнительных параметров
        try:
            ps_script2 = f"""
            try {{
                Write-Host "Запуск Edge с URL: {url}"
                Start-Process "msedge.exe" -ArgumentList "{url}"
                Write-Host "Edge запущен успешно"
                exit 0
            }} catch {{
                Write-Host "Ошибка запуска Edge"
                exit 1
            }}
            """

            cmd = ["powershell.exe", "-Command", ps_script2]
            result = subprocess.run(cmd, capture_output=True, timeout=5, text=True, encoding='cp1251')

            if result.returncode == 0:
                print("✅ Edge запущен с URL (должен использовать существующую вкладку)")
                return True
            else:
                print(f"⚠️ Не удалось запустить Edge: {result.stdout.strip()}")

        except Exception as e:
            print(f"⚠️ PowerShell метод запуска не сработал: {e}")

        # Способ 5: Через wslview (для WSL)
        try:
            subprocess.run(["wslview", url], capture_output=True, timeout=10)
            print("✅ Edge запущен через wslview (использует существующее окно/вкладку)")
            return True
        except Exception as e:
            print(f"⚠️ wslview метод не сработал: {e}")

    except Exception as e:
        print(f"⚠️ Ошибка при обновлении существующего окна: {e}")

    return False

def refresh_browser_page(url="https://trade.padre.gg/trade/solana/TQnDxmfeV9G2cVPywPG5q5Ri37RNCoRyTzA7TLsvnt1", interval_minutes=5):
    """
    Автоматически обновляет страницу браузера через заданные интервалы

    Args:
        url: URL страницы для обновления
        interval_minutes: Интервал обновления в минутах
    """
    print("🔄 Запуск автообновления страницы браузера")
    print(f"📄 URL: {url}")
    print(f"⏱️  Интервал: {interval_minutes} минут")
    print("💡 Для остановки нажмите Ctrl+C")
    print("-" * 50)

    try:
        while True:
            print(f"🔄 Обновление страницы... ({time.strftime('%H:%M:%S')})")

            # Закрываем все окна браузера перед обновлением
            print("🔒 Закрываем все окна браузера...")
            try:
                cmd = ["powershell.exe", "-Command", "Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force"]
                result = subprocess.run(cmd, capture_output=True, timeout=5, text=True, encoding='cp1251')
                if result.returncode == 0:
                    print("✅ Все окна браузера закрыты")
                else:
                    print("ℹ️ Нет открытых окон браузера для закрытия")
            except Exception as e:
                print(f"⚠️ Не удалось закрыть окна браузера: {e}")

            # Небольшая пауза после закрытия
            time.sleep(2)

            # Поскольку мы закрыли все окна, сразу открываем новое
            print(f"🔄 Открываем новое окно браузера с URL...")

            # Используем простой и надёжный способ открытия браузера
            try:
                cmd = ["powershell.exe", "-Command", f"Start-Process 'msedge.exe' -ArgumentList '{url}'"]
                result = subprocess.run(cmd, capture_output=True, timeout=10, text=True, encoding='cp1251')
                if result.returncode == 0:
                    print("✅ Новое окно браузера открыто с нужным URL")
                else:
                    print(f"⚠️ Не удалось открыть браузер: {result.stdout.strip()}")
            except Exception as e:
                print(f"⚠️ Ошибка при открытии браузера: {e}")

                # Резервный способ через cmd
                try:
                    cmd = ["cmd.exe", "/c", f"start msedge.exe {url}"]
                    subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
                    print("✅ Браузер открыт через cmd")
                except Exception as e:
                    print(f"⚠️ Резервный способ тоже не сработал: {e}")

            # Ждем заданный интервал
            print(f"⏳ Ожидание {interval_minutes} минут до следующего обновления...")
            time.sleep(interval_minutes * 60)

    except KeyboardInterrupt:
        print("\n🛑 Автообновление остановлено пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")

def refresh_page_once(url="https://trade.padre.gg/trade/solana/TQnDxmfeV9G2cVPywPG5q5Ri37RNCoRyTzA7TLsvnt1"):
    """
    Одноразовое обновление страницы
    """
    print(f"🔄 Одноразовое обновление страницы: {url}")

    # Закрываем все окна браузера перед обновлением
    print("🔒 Закрываем все окна браузера...")
    try:
        cmd = ["powershell.exe", "-Command", "Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force"]
        result = subprocess.run(cmd, capture_output=True, timeout=5, text=True, encoding='cp1251')
        if result.returncode == 0:
            print("✅ Все окна браузера закрыты")
        else:
            print("ℹ️ Нет открытых окон браузера для закрытия")
    except Exception as e:
        print(f"⚠️ Не удалось закрыть окна браузера: {e}")

    # Небольшая пауза после закрытия
    time.sleep(2)

    print(f"🔄 После закрытия окон переходим к открытию нового...")

    # Поскольку мы только что закрыли все окна, сразу открываем новое с нужным URL
    print(f"🔄 Открываем новое окно браузера с URL: {url}")

    # Используем простой и надёжный способ открытия браузера
    try:
        cmd = ["powershell.exe", "-Command", f"Start-Process 'msedge.exe' -ArgumentList '{url}'"]
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True, encoding='cp1251')
        if result.returncode == 0:
            print("✅ Новое окно браузера открыто с нужным URL")
            return True
        else:
            print(f"⚠️ Не удалось открыть браузер: {result.stdout.strip()}")
    except Exception as e:
        print(f"⚠️ Ошибка при открытии браузера: {e}")

    # Резервный способ через cmd
    try:
        cmd = ["cmd.exe", "/c", f"start msedge.exe {url}"]
        subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
        print("✅ Браузер открыт через cmd")
        return True
    except Exception as e:
        print(f"⚠️ Резервный способ тоже не сработал: {e}")

    return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Одноразовое обновление
        url = sys.argv[2] if len(sys.argv) > 2 else "https://trade.padre.gg/trade/solana/TQnDxmfeV9G2cVPywPG5q5Ri37RNCoRyTzA7TLsvnt1"
        refresh_page_once(url)
    else:
        # Автоматическое обновление
        interval = 1  # минут
        if len(sys.argv) > 1:
            try:
                interval = int(sys.argv[1])
            except ValueError:
                print("❌ Неверный формат интервала. Используйте число минут.")

        url = "https://trade.padre.gg/trade/solana/TQnDxmfeV9G2cVPywPG5q5Ri37RNCoRyTzA7TLsvnt1"
        if len(sys.argv) > 2:
            url = sys.argv[2]

        refresh_browser_page(url, interval)
