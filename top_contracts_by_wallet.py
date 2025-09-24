#!/usr/bin/env python3

import os
import sys
from collections import defaultdict

EBOSHERS_LOGS_DIR = "eboshers_logs"

def get_top_contracts_with_wallet_by_total_lines(wallet_address: str, top_n: int = 1000):
    """Ищет топ контрактов, содержащих указанный кошелек, по общему количеству строк в лог-файле."""
    print(f"🔍 Ищем топ контрактов, содержащих кошелек {wallet_address}, по общему количеству строк...")
    contract_total_lines = defaultdict(int)

    if not os.path.exists(EBOSHERS_LOGS_DIR):
        print(f"❌ Папка {EBOSHERS_LOGS_DIR} не найдена.")
        return []

    for filename in os.listdir(EBOSHERS_LOGS_DIR):
        if filename.endswith('.log'):
            contract_address = filename.replace('.log', '')
            filepath = os.path.join(EBOSHERS_LOGS_DIR, filename)

            try:
                # Шаг 1: Проверяем, есть ли указанный кошелек в этом лог-файле
                wallet_found_in_file = False
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        if wallet_address in line:
                            wallet_found_in_file = True
                            break
                
                # Шаг 2: Если кошелек найден, подсчитываем общее количество строк
                if wallet_found_in_file:
                    contract_total_lines[contract_address] = len(lines)

            except Exception as e:
                print(f"❌ Ошибка чтения файла {filepath}: {e}")

    if not contract_total_lines:
        print(f"🤷‍♂️ Кошелек {wallet_address} не найден ни в одном контракте или нет транзакций.")
        return []

    # Сортируем контракты по общему количеству строк в убывающем порядке
    sorted_contracts = sorted(contract_total_lines.items(), key=lambda item: item[1], reverse=True)

    print(f"\n--- Топ {top_n} контрактов для кошелька {wallet_address} по общему количеству строк ---")
    results = []
    for i, (contract, count) in enumerate(sorted_contracts[:top_n]):
        print(f"{i+1}. {contract} (Всего строк: {count})")
        results.append((contract, count))

    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python top_contracts_with_wallet_by_total_lines.py <wallet_address> [top_N]")
        print("Пример: python top_contracts_with_wallet_by_total_lines.py niggerd597QYedtvjQDVHZTCCGyJrwHNm2i49dkm5zS 5")
        sys.exit(1)

    wallet_to_search = sys.argv[1]
    top_n_contracts = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    
    get_top_contracts_with_wallet_by_total_lines(wallet_to_search, top_n_contracts)
