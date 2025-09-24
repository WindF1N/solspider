import configparser
import asyncio
import aiohttp
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from tqdm.asyncio import tqdm_asyncio
from collections import defaultdict

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'cluster_debug.log'), mode='w'),
        logging.StreamHandler()
    ]
)

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ ---
CONFIG_FILE = 'config.ini'
INPUT_DIR = 'output/classified_wallets'
OUTPUT_DIR = 'output/teams'
CACHE_FILE = 'output/launch_cache.json'
HOT_FILE = os.path.join(INPUT_DIR, 'hot_wallets.txt')
WARM_FILE = os.path.join(INPUT_DIR, 'warm_wallets.txt')

BATCH_SIZE = 25
DELAY_BETWEEN_BATCHES = 1.0

IGNORE_TOKENS = {
    'So11111111111111111111111111111111111111112', 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB', 'EKpQGSJtjMFqKZ9KQan2HdsCVcF5suca2iMPE3sUvRyt',
    'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263', 'WENWENv5M5pAc2a1DD5NaGGoSjS2goBhhc2u1T12v9s',
}

def load_config():
    config = configparser.ConfigParser()
    if not config.read(CONFIG_FILE): raise FileNotFoundError(f"Файл '{CONFIG_FILE}' не найден.")
    return {
        'api_key': config.get('API', 'helius_api_key'),
        'clustering_period_days': config.getint('AnalysisSettings', 'clustering_period_days'),
        'min_wallets_per_linking_token': config.getint('AnalysisSettings', 'min_wallets_per_linking_token'),
        'min_team_size': config.getint('AnalysisSettings', 'min_team_size')
    }

def load_active_wallets():
    wallets = set()
    for filename in [HOT_FILE, WARM_FILE]:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                for line in f: wallets.add(line.strip())
    if not wallets: raise FileNotFoundError("Не найдены файлы hot_wallets.txt или warm_wallets.txt.")
    logging.info(f"Найдено {len(wallets)} активных кошельков для анализа на предмет связей.")
    return list(wallets)

async def get_wallet_transactions(session, wallet, api_key, until_timestamp):
    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={api_key}"
    all_transactions = []
    last_signature = None
    while True:
        current_url = url
        if last_signature: current_url += f"&before={last_signature}"
        try:
            async with session.get(current_url, timeout=45) as response:
                if response.status != 200:
                    logging.warning(f"Ошибка API для кошелька {wallet}: Статус {response.status}")
                    break
                transactions = await response.json()
                if not transactions or transactions[-1]['timestamp'] < until_timestamp:
                    if transactions: all_transactions.extend(transactions)
                    break
                all_transactions.extend(transactions)
                last_signature = transactions[-1]['signature']
                await asyncio.sleep(0.1)
        except Exception as e:
            logging.error(f"Исключение при запросе для {wallet}: {e}")
            break
    logging.info(f"Для кошелька {wallet} получено {len(all_transactions)} транзакций.")
    return wallet, all_transactions

async def fetch_all_transactions_batched(wallets, api_key, period_days):
    now = datetime.now(timezone.utc)
    until_timestamp = (now - timedelta(days=period_days)).timestamp()
    wallet_histories = {}
    logging.info(f"Запрашиваю историю транзакций за {period_days} дней...")
    async with aiohttp.ClientSession() as session:
        with tqdm_asyncio(total=len(wallets), desc="Сбор транзакций") as pbar:
            for i in range(0, len(wallets), BATCH_SIZE):
                batch_wallets = wallets[i:i + BATCH_SIZE]
                tasks = [get_wallet_transactions(session, w, api_key, until_timestamp) for w in batch_wallets]
                results = await asyncio.gather(*tasks)
                for wallet, transactions in results:
                    wallet_histories[wallet] = transactions
                pbar.update(len(batch_wallets))
                if i + BATCH_SIZE < len(wallets):
                    await asyncio.sleep(DELAY_BETWEEN_BATCHES)
    return wallet_histories

def find_teams_and_cache_launches(wallet_histories, config):
    logging.info("Анализирую транзакции и ищу связи...")
    token_to_wallets = defaultdict(set)
    token_first_seen = defaultdict(lambda: float('inf'))
    total_tx_processed = 0
    total_swaps_found = 0

    for wallet, transactions in wallet_histories.items():
        if not transactions: continue
        total_tx_processed += len(transactions)
        for tx in transactions:
            if tx.get("type") == "SWAP" and not tx.get("transactionError"):
                total_swaps_found += 1
                for transfer in tx.get('tokenTransfers', []):
                    mint = transfer.get('mint')
                    if mint and mint not in IGNORE_TOKENS:
                        token_to_wallets[mint].add(wallet)
                        logging.info(f"Найдена связь: кошелек {wallet[:6]}... торговал токеном {mint[:6]}...")
                        if tx['timestamp'] < token_first_seen[mint]:
                            token_first_seen[mint] = tx['timestamp']
    
    logging.info(f"Всего обработано транзакций: {total_tx_processed}")
    logging.info(f"Найдено SWAP-транзакций: {total_swaps_found}")

    linking_tokens = {token for token, wals in token_to_wallets.items() if len(wals) >= config['min_wallets_per_linking_token']}
    logging.info(f"Найдено {len(linking_tokens)} 'токенов-связок', указывающих на командную работу.")
    if not linking_tokens: return [], {}

    launch_cache = {token: ts for token, ts in token_first_seen.items() if token in linking_tokens}
    wallet_to_tokens = defaultdict(set)
    for token in linking_tokens:
        for wallet in token_to_wallets[token]: wallet_to_tokens[wallet].add(token)
    teams_wallets = []
    visited = set()
    all_wallets_in_play = list(wallet_to_tokens.keys())
    for wallet in all_wallets_in_play:
        if wallet not in visited:
            team = set()
            q = [wallet]; visited.add(wallet)
            head = 0
            while head < len(q):
                current_wallet = q[head]; head += 1
                team.add(current_wallet)
                for other_wallet in all_wallets_in_play:
                    if other_wallet not in visited and wallet_to_tokens[current_wallet] & wallet_to_tokens[other_wallet]:
                        visited.add(other_wallet); q.append(other_wallet)
            if len(team) >= config['min_team_size']:
                teams_wallets.append(list(team))
    teams_with_tokens = []
    for team in teams_wallets:
        team_linking_tokens = {token for token in linking_tokens if not set(team).isdisjoint(token_to_wallets[token])}
        teams_with_tokens.append((team, list(team_linking_tokens)))
    return teams_with_tokens, launch_cache

def save_teams_and_cache(teams_data, launch_cache):
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    with open(CACHE_FILE, 'w') as f:
        json.dump(launch_cache, f, indent=4)
    logging.info(f"Кэш времени запуска для {len(launch_cache)} токенов сохранен в {CACHE_FILE}")
    logging.info(f"Кластеризация завершена! Найдено {len(teams_data)} команд.")
    for i, (team_wallets, team_tokens) in enumerate(teams_data):
        team_dir = os.path.join(OUTPUT_DIR, f'team_{i+1}')
        os.makedirs(team_dir, exist_ok=True)
        with open(os.path.join(team_dir, 'wallets.txt'), 'w') as f: f.write('\n'.join(sorted(team_wallets)))
        with open(os.path.join(team_dir, 'linking_tokens.txt'), 'w') as f: f.write('\n'.join(sorted(team_tokens)))
        logging.info(f"Команда {i+1}: {len(team_wallets)} кошельков, {len(team_tokens)} токенов-улик. Сохранено в {team_dir}")

async def main():
    config = load_config()
    active_wallets = load_active_wallets()
    wallet_histories = await fetch_all_transactions_batched(active_wallets, config['api_key'], config['clustering_period_days'])
    teams_data, launch_cache = find_teams_and_cache_launches(wallet_histories, config)
    save_teams_and_cache(teams_data, launch_cache)

if __name__ == "__main__":
    asyncio.run(main())