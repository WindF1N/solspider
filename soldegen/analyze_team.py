import pandas as pd
import numpy as np
import os
import asyncio
from collections import defaultdict
import configparser
import json
from tqdm import tqdm
import bullx_client # bullx_client.py НЕ МЕНЯЕМ, он уже готов

CONFIG_FILE = 'config.ini'
TEAMS_DIR = 'output/teams'
CACHE_FILE = 'output/launch_cache.json' # <<< ПУТЬ К НАШЕМУ КЭШУ
TARGET_TEAM = 'team_1'

def load_config():
    config = configparser.ConfigParser()
    if not config.read(CONFIG_FILE): raise FileNotFoundError(f"Файл '{CONFIG_FILE}' не найден.")
    return { 'entry_signal_wallets': config.getint('TeamAnalysisSettings', 'entry_signal_wallets'), 'safe_entry_window_minutes': config.getint('TeamAnalysisSettings', 'safe_entry_window_minutes'), }

def load_team_data(team_name):
    team_dir = os.path.join(TEAMS_DIR, team_name);
    if not os.path.exists(team_dir): raise FileNotFoundError(f"Папка для команды {team_name} не найдена.")
    with open(os.path.join(team_dir, 'wallets.txt'), 'r') as f: wallets = {line.strip() for line in f if line.strip()}
    with open(os.path.join(team_dir, 'linking_tokens.txt'), 'r') as f: tokens = {line.strip() for line in f if line.strip()}
    print(f"🔬 Анализирую команду '{team_name}': {len(wallets)} кошельков, {len(tokens)} токенов-улик.")
    return wallets, list(tokens)

def load_launch_cache(tokens_to_find):
    if not os.path.exists(CACHE_FILE): raise FileNotFoundError(f"Файл кэша {CACHE_FILE} не найден. Сначала запустите cluster.py")
    with open(CACHE_FILE, 'r') as f:
        full_cache = json.load(f)
    
    # Возвращаем только нужные нам timestamp'ы
    return {token: ts for token, ts in full_cache.items() if token in tokens_to_find}

def analyze_token_performance(price_df, t0_timestamp, config):
    if price_df.empty: return {}
    
    t0 = pd.to_datetime(t0_timestamp, unit='s', utc=True)
    
    # ЗАГЛУШКА ДЛЯ АГРЕССИВНОГО ВХОДА. Нам все еще нужны транзакции для этого.
    # Пока что мы можем посчитать только "терпеливый" хитрейт.
    aggressive_entry_price = np.nan 

    safe_window_start = t0 + pd.Timedelta(minutes=config['safe_entry_window_minutes'])
    safe_window_end = safe_window_start + pd.Timedelta(minutes=8)
    safe_window_prices = price_df[(price_df.index >= safe_window_start) & (price_df.index <= safe_window_end)]
    patient_entry_price = safe_window_prices['price'].median() if not safe_window_prices.empty else np.nan
    
    results = {}
    if not pd.isna(patient_entry_price):
        peak_price_after = price_df[price_df.index >= safe_window_start]['price'].max()
        multiplier = peak_price_after / patient_entry_price if patient_entry_price > 0 else 0
        results['pat_x2_hit'] = multiplier >= 2; results['pat_peak'] = multiplier
    return results

async def main():
    config = load_config()
    team_wallets, tokens = load_team_data(TARGET_TEAM)

    # --- Шаг 1: Загружаем время старта из кэша ---
    tokens_with_start_time = load_launch_cache(tokens)
    print(f"🕒 Из кэша загружено время запуска для {len(tokens_with_start_time)} токенов.")
    if not tokens_with_start_time: return

    # --- Шаг 2: Запрашиваем точные графики в BullX ---
    price_fetcher = bullx_client.PriceHistoryFetcher()
    price_histories = await price_fetcher.fetch_all_precise(tokens_with_start_time)
    await price_fetcher.close()
    if not price_histories: print("\n❌ Не удалось загрузить ни одного детального графика."); return

    performance_results = []
    print("\n" + "="*50)
    for token, price_df in tqdm(price_histories.items(), desc="Анализ токенов"):
        # Передаем timestamp из кэша
        result = analyze_token_performance(price_df, tokens_with_start_time[token], config)
        performance_results.append(result)

    total_tokens = len(performance_results)
    if total_tokens == 0: print("\nНе удалось проанализировать ни одного токена."); return
    
    pat_x2 = sum(1 for r in performance_results if r.get('pat_x2_hit'))
    avg_pat_peak = np.mean([r.get('pat_peak', 0) for r in performance_results if 'pat_peak' in r])
    
    team_dir = os.path.join(TEAMS_DIR, TARGET_TEAM)
    report_lines = [
        f"--- Аналитический отчет по Команде: {TARGET_TEAM} ---",
        f"\n[Анализ эффективности на {total_tokens} токенах]",
        f"\n--- 🧘 ТЕРПЕЛИВАЯ СТРАТЕГИЯ (вход после {config['safe_entry_window_minutes']} мин хаоса) ---",
        f"Хитрейт x2: {pat_x2}/{total_tokens} ({pat_x2/total_tokens:.1% if total_tokens > 0 else 0})",
        f"Средний пиковый множитель: x{avg_pat_peak:.2f}",
        "\n[Анализ ролей и агрессивной стратегии будет добавлен в след. модуле]",
    ]
    report_path = os.path.join(team_dir, 'analysis_report.txt')
    with open(report_path, 'w') as f: f.write('\n'.join(report_lines))
    print("\n" + "\n".join(report_lines))
    print(f"\n✅ Отчет сохранен в: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())