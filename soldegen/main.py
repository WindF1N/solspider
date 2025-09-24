import configparser
import asyncio
import aiohttp
import os
import glob
from datetime import datetime, timedelta, timezone
from tqdm import tqdm

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ ---
CONFIG_FILE = 'config.ini'
INPUT_DIR = 'input_wallets'
OUTPUT_DIR = 'output/classified_wallets'
HOT_FILE = os.path.join(OUTPUT_DIR, 'hot_wallets.txt')
WARM_FILE = os.path.join(OUTPUT_DIR, 'warm_wallets.txt')
COLD_FILE = os.path.join(OUTPUT_DIR, 'cold_wallets.txt')

# --- НАСТРОЙКИ ГИБРИДНОГО РЕЖИМА ---
BATCH_SIZE = 25             # Размер пачки для асинхронных запросов
INITIAL_DELAY = 0.5         # Пауза между пачками при первой быстрой прогонке
RETRY_DELAY = 1.5           # Увеличенная пауза для повторных попыток
MAX_RETRIES = 3             # Макс. количество повторных прогонов для неудавшихся кошельков

def load_config():
    # ... (код этой функции не меняется)
    if not os.path.exists(CONFIG_FILE): raise FileNotFoundError(f"Файл '{CONFIG_FILE}' не найден.")
    config = configparser.ConfigParser(); config.read(CONFIG_FILE)
    settings = {'api_key': config.get('API', 'helius_api_key', fallback=None), 'hot_hours': config.getint('TriageSettings', 'hot_hours', fallback=24), 'warm_days': config.getint('TriageSettings', 'warm_days', fallback=7)}
    if not settings['api_key'] or 'ВАШ_КЛЮЧ' in settings['api_key']: raise ValueError("API ключ Helius не указан в config.ini")
    return settings

def load_wallets_from_input_dir():
    # ... (код этой функции не меняется)
    if not os.path.exists(INPUT_DIR): os.makedirs(INPUT_DIR); print(f"📁 Создана папка '{INPUT_DIR}'."); return []
    file_list = glob.glob(os.path.join(INPUT_DIR, '*.txt'))
    if not file_list: print(f"⚠️  В '{INPUT_DIR}' не найдено .txt файлов."); return []
    print(f"📂 Сканирую файлы: {', '.join([os.path.basename(f) for f in file_list])}")
    unique_wallets = set()
    for filename in file_list:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    wallet = line.strip()
                    if wallet and 32 <= len(wallet) <= 44: unique_wallets.add(wallet)
        except Exception as e: print(f"Ошибка чтения {filename}: {e}")
    if not unique_wallets: raise ValueError("Не удалось найти кошельки.")
    print(f"🔍 Найдено {len(unique_wallets)} уникальных кошельков для анализа.")
    return list(unique_wallets)

async def get_last_transaction_timestamp_async(session, wallet, api_key):
    # ... (код этой функции не меняется)
    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={api_key}&limit=1"
    try:
        async with session.get(url, timeout=20) as response:
            if response.status == 200:
                data = await response.json()
                if data: return wallet, data[0].get('timestamp')
                else: return wallet, None
            else: return wallet, 'api_error'
    except Exception: return wallet, "network_error"

def classify_wallets(results, settings):
    # ... (код этой функции не меняется)
    hot_wallets, warm_wallets, cold_wallets = [], [], []
    now = datetime.now(timezone.utc); hot_threshold = timedelta(hours=settings['hot_hours']); warm_threshold = timedelta(days=settings['warm_days'])
    print("\n🗂️  Классификация кошельков...")
    error_count = 0
    for wallet, timestamp in results:
        if timestamp is None or isinstance(timestamp, str):
            cold_wallets.append(wallet)
            if isinstance(timestamp, str): error_count += 1
            continue
        try:
            tx_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            delta = now - tx_time
            if delta <= hot_threshold: hot_wallets.append(wallet)
            elif delta <= warm_threshold: warm_wallets.append(wallet)
            else: cold_wallets.append(wallet)
        except Exception: cold_wallets.append(wallet); error_count += 1
    if error_count > 0: print(f"⚠️  {error_count} кошельков не удалось обработать после всех попыток. Они помещены в 'холодные'.")
    return hot_wallets, warm_wallets, cold_wallets

def write_results(hot, warm, cold, settings):
    # ... (код этой функции не меняется)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(HOT_FILE, 'w') as f: f.write('\n'.join(hot))
    with open(WARM_FILE, 'w') as f: f.write('\n'.join(warm))
    with open(COLD_FILE, 'w') as f: f.write('\n'.join(cold))
    print("\n" + "="*50)
    print("✅ Анализ завершен! Результаты сохранены.")
    print(f"🔥 Горячие (< {settings['hot_hours']} ч.):\t{len(hot)} кошельков -> {HOT_FILE}")
    print(f"🟠 Теплые (< {settings['warm_days']} д.):\t{len(warm)} кошельков -> {WARM_FILE}")
    print(f"🧊 Холодные (> {settings['warm_days']} д.):\t{len(cold)} кошельков -> {COLD_FILE}")
    print("="*50)

async def process_wallets_in_batches(session, wallets, api_key, delay, pbar):
    """Ключевая функция: обрабатывает список кошельков пачками."""
    all_results_for_pass = []
    for i in range(0, len(wallets), BATCH_SIZE):
        batch = wallets[i:i + BATCH_SIZE]
        tasks = [get_last_transaction_timestamp_async(session, wallet, api_key) for wallet in batch]
        
        batch_results = await asyncio.gather(*tasks)
        all_results_for_pass.extend(batch_results)
        
        pbar.update(len(batch) - pbar.n if pbar.n < pbar.total else len(batch)) # Корректируем прогресс бар

        if i + BATCH_SIZE < len(wallets):
            await asyncio.sleep(delay)
    return all_results_for_pass

async def main():
    """Основная функция с гибридной логикой."""
    config = load_config()
    wallets_to_process = load_wallets_from_input_dir()
    if not wallets_to_process: return

    successful_results = []
    
    print(f"🚀 Запускаю гибридный анализ для {len(wallets_to_process)} кошельков...")
    
    with tqdm(total=len(wallets_to_process), desc="Анализ активности") as pbar:
        async with aiohttp.ClientSession() as session:
            
            # --- Основная быстрая прогонка ---
            pbar.set_postfix_str("Быстрая прогонка")
            initial_results = await process_wallets_in_batches(session, wallets_to_process, config['api_key'], INITIAL_DELAY, pbar)
            
            failed_wallets = []
            for wallet, timestamp in initial_results:
                if timestamp is None or not isinstance(timestamp, str):
                    successful_results.append((wallet, timestamp))
                else:
                    failed_wallets.append(wallet)
            
            pbar.n = len(successful_results) # Обновляем прогресс бар на кол-во успешных
            pbar.refresh()

            # --- Цикл повторных попыток для неудавшихся ---
            for i in range(MAX_RETRIES):
                if not failed_wallets: break # Если все получилось, выходим
                
                pbar.set_postfix_str(f"Повтор {i+1}/{MAX_RETRIES} для {len(failed_wallets)} кошельков")
                await asyncio.sleep(RETRY_DELAY) # Доп. пауза перед циклом повторов

                retry_results = await process_wallets_in_batches(session, failed_wallets, config['api_key'], RETRY_DELAY, pbar)
                
                newly_failed_wallets = []
                for wallet, timestamp in retry_results:
                    if timestamp is None or not isinstance(timestamp, str):
                        if wallet in failed_wallets: # Убеждаемся, что это тот, кого мы искали
                           successful_results.append((wallet, timestamp))
                    else:
                        newly_failed_wallets.append(wallet)

                failed_wallets = newly_failed_wallets # Список на следующий повтор
                pbar.n = len(successful_results) # Снова обновляем прогресс
                pbar.refresh()

    # Добавляем в финальный список тех, кто так и не ответил
    for wallet in failed_wallets:
        successful_results.append((wallet, 'final_error'))

    hot, warm, cold = classify_wallets(successful_results, config)
    write_results(hot, warm, cold, config)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (FileNotFoundError, ValueError) as e: print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
    except KeyboardInterrupt: print("\n🚫 Процесс прерван пользователем.")