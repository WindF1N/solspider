
def extract_firebase_token():
    """
    Извлечение Firebase access token из IndexedDB .ldb файлов, Local Storage и logs
    """
    print("🔍 Ищем Firebase токен в IndexedDB .ldb файлах...")

    try:
        # Сначала пытаемся найти в IndexedDB .ldb файлах (основной метод)
        token = search_token_in_indexeddb_ldb()
        if token:
            print("✅ Access Token найден в IndexedDB .ldb файлах!")
            print(f"Token: {token[:50]}...")
            return token

        # # Если в IndexedDB не нашли, пробуем Local Storage
        # print("🔄 Токен не найден в IndexedDB .ldb, проверяем Local Storage...")
        # token = search_token_in_local_storage()
        # if token:
        #     print("✅ Access Token найден в Local Storage!")
        #     print(f"Token: {token[:50]}...")
        #     return token

        # Если и в Local Storage не нашли, пробуем IndexedDB logs
        print("🔄 Токен не найден в Local Storage, проверяем IndexedDB logs...")
        token = search_token_in_log_files()
        if token:
            print("✅ Access Token найден в IndexedDB logs!")
            print(f"Token: {token[:50]}...")
            return token

        print("❌ Firebase токен не найден ни в одном источнике")
        return None

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        return None


def search_token_in_local_storage():
    """
    Поиск токена в Local Storage браузера (Firebase tokens)
    """
    import glob

    # Ищем в Local Storage браузера
    storage_path = "/mnt/c/Users/agafo/AppData/Local/Microsoft/Edge/User Data/Default/Local Storage/leveldb"
    db_files = glob.glob(f"{storage_path}/*.ldb") + glob.glob(f"{storage_path}/*.log")

    all_tokens = []

    for db_file in db_files:
        try:
            with open(db_file, 'rb') as f:
                content = f.read()

                # Ищем Firebase токены в localStorage
                if b'firebase' in content.lower() or b'accessToken' in content:
                    # Ищем паттерн токена Firebase
                    import re
                    content_str = content.decode('utf-8', errors='ignore')
                    token_pattern = r'eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'
                    matches = re.findall(token_pattern, content_str)

                    if matches:
                        for match in matches:
                            if len(match) > 200:  # Firebase токены обычно длинные
                                all_tokens.append(match)
                                print(f"🎯 Найден токен в {db_file}")

        except Exception as e:
            continue

    # Возвращаем последний найденный токен
    if all_tokens:
        print(f"📊 Найдено {len(all_tokens)} токенов в Local Storage, выбираем последний")
        return all_tokens[-1]

    return None

def search_token_in_indexeddb_ldb():
    """
    Поиск токена в .ldb файлах IndexedDB (основной метод)
    """
    import glob

    # Основная директория IndexedDB с .ldb файлами
    db_path = "/mnt/c/Users/agafo/AppData/Local/Microsoft/Edge/User Data/Default/IndexedDB/https_trade.padre.gg_0.indexeddb.leveldb"
    ldb_files = glob.glob(f"{db_path}/*.ldb")

    all_tokens = []

    print(f"🔍 Ищем в IndexedDB .ldb файлах: найдено {len(ldb_files)} файлов")

    for ldb_file in ldb_files:
        try:
            print(f"📄 Проверяем файл: {ldb_file.split('/')[-1]}")
            with open(ldb_file, 'rb') as f:
                content = f.read()

                # Ищем Firebase токены в бинарных данных
                if b'firebase' in content.lower() or b'accessToken' in content or b'eyJ' in content:
                    print(f"🎯 Найдены потенциальные данные в {ldb_file.split('/')[-1]}")

                    # Ищем паттерн токена Firebase
                    import re
                    content_str = content.decode('utf-8', errors='ignore')
                    token_pattern = r'eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'
                    matches = re.findall(token_pattern, content_str)

                    if matches:
                        print(f"📊 Найдено {len(matches)} токенов в файле {ldb_file.split('/')[-1]}")
                        for match in matches:
                            if len(match) > 200:  # Firebase токены обычно длинные
                                all_tokens.append(match)
                                print(f"✅ Добыт токен длиной {len(match)} символов")

        except Exception as e:
            print(f"❌ Ошибка чтения файла {ldb_file.split('/')[-1]}: {e}")
            continue

    # Возвращаем последний найденный токен
    if all_tokens:
        print(f"🎉 Всего найдено {len(all_tokens)} подходящих токенов, выбираем последний")
        return all_tokens[-1]

    print("❌ Токены не найдены в .ldb файлах IndexedDB")
    return None

def search_token_in_log_files():
    """
    Поиск токена в log файлах IndexedDB (резервный метод)
    """
    import glob

    # Ищем все .log файлы в директории базы данных
    db_path = "/mnt/c/Users/agafo/AppData/Local/Microsoft/Edge/User Data/Default/IndexedDB/https_trade.padre.gg_0.indexeddb.leveldb"
    log_files = glob.glob(f"{db_path}/*.log")

    all_tokens = []

    for log_file in log_files:
        try:
            with open(log_file, 'rb') as f:
                content = f.read()

                # Ищем accessToken в бинарных данных
                if b'accessToken' in content:
                    # Ищем паттерн токена Firebase
                    import re
                    content_str = content.decode('utf-8', errors='ignore')
                    token_pattern = r'eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+'
                    matches = re.findall(token_pattern, content_str)

                    if matches:
                        for match in matches:
                            if len(match) > 200:  # Firebase токены обычно длинные
                                all_tokens.append(match)

        except Exception as e:
            continue

    # Возвращаем последний найденный токен
    if all_tokens:
        print(f"📊 Найдено {len(all_tokens)} токенов в IndexedDB logs, выбираем последний")
        return all_tokens[-1]

    return None


def save_token_to_file(token, filename="token.txt"):
    """
    Сохранение токена в файл (перезапись)
    """
    with open(filename, 'w') as f:
        f.write(token)
    print(f"✅ Токен сохранен в файл: {filename}")


if __name__ == "__main__":
    # Извлекаем токен из log файлов
    access_token = extract_firebase_token()

    if access_token:
        # Сохраняем в файл
        save_token_to_file(access_token)

        # Также можно скопировать в буфер обмена (опционально)
        try:
            import pyperclip
            pyperclip.copy(access_token)
            print("📋 Токен скопирован в буфер обмена")
        except ImportError:
            print("Установите pyperclip для копирования в буфер: pip install pyperclip")
    else:
        print("❌ Токен не найден в log файлах")