#!/usr/bin/env python3

import os
import sys
import re
from collections import defaultdict

EBOSHERS_LOGS_DIR = "eboshers_logs"

def generate_output_filename(target_wallet_address: str) -> str:
    """Генерирует имя файла для сохранения результатов на основе целевого адреса кошелька."""
    # Берем первые 8 символов целевого кошелька
    filename_prefix = target_wallet_address[:8]
    return f"exclusive_wallets_{filename_prefix}.txt"

def find_exclusive_wallets_for_target_contract(target_wallet_address: str):
    """Выявляет кошельки, которые работают ТОЛЬКО с контрактами, где есть target_wallet_address."""
    print(f"🔍 Ищем кошельки, работающие исключительно с {target_wallet_address}...")

    if not os.path.exists(EBOSHERS_LOGS_DIR):
        print(f"❌ Папка {EBOSHERS_LOGS_DIR} не найдена.")
        return

    # Словарь: wallet_address -> set(contract_addresses, где найден этот wallet)
    wallet_to_contracts_map = defaultdict(set)

    # Адрес для извлечения кошелька из строки лога: [YYYY-MM-DD HH:MM:SS] [WALLET_ADDRESS] ...
    wallet_pattern = re.compile(r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s\[([a-zA-Z0-9]{30,})\]')

    # Первый проход: собираем данные о том, какие кошельки в каких контрактах встречаются
    for filename in os.listdir(EBOSHERS_LOGS_DIR):
        if filename.endswith('.log'):
            contract_address = filename.replace('.log', '')
            filepath = os.path.join(EBOSHERS_LOGS_DIR, filename)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        match = wallet_pattern.match(line)
                        if match:
                            current_wallet = match.group(1)
                            wallet_to_contracts_map[current_wallet].add(contract_address)
            except Exception as e:
                print(f"❌ Ошибка чтения файла {filepath}: {e}")

    # Определяем контракты, в которых присутствует target_wallet_address
    target_wallet_contracts = wallet_to_contracts_map.get(target_wallet_address, set())

    if not target_wallet_contracts:
        print(f"🤷‍♂️ Целевой кошелек {target_wallet_address} не найден ни в одном контракте.")
        return

    exclusive_wallets_data = []

    # Второй проход: анализируем собранные данные
    for wallet, contracts_set in wallet_to_contracts_map.items():
        # Исключаем сам целевой кошелек из результатов
        if wallet == target_wallet_address:
            continue

        # Проверяем два условия:
        # 1. Кошелек присутствует хотя бы в одном контракте вместе с целевым кошельком
        # 2. Все контракты, в которых присутствует этот кошелек, также содержат целевой кошелек
        #    (т.е. contracts_set является подмножеством target_wallet_contracts)
        
        # intersection_contracts = contracts_set.intersection(target_wallet_contracts)
        # if intersection_contracts and contracts_set.issubset(target_wallet_contracts):
        #     exclusive_wallets_data.append({'wallet': wallet, 'shared_contracts': sorted(list(intersection_contracts))})

        # Исправленная логика: все контракты, с которыми работает данный кошелек, должны быть среди контрактов целевого кошелька
        # И при этом должна быть хотя бы одна общая транзакция с целевым кошельком
        if contracts_set.issubset(target_wallet_contracts) and not contracts_set.isdisjoint(target_wallet_contracts):
            # Дополнительная проверка: убедиться, что они действительно взаимодействуют в этих контрактах
            # Это уже подразумевается, если contracts_set.issubset(target_wallet_contracts)
            # и contracts_set не пуст (что следует из not contracts_set.isdisjoint(target_wallet_contracts))
            
            exclusive_wallets_data.append({
                'wallet': wallet,
                'shared_contracts': sorted(list(contracts_set))
            })

    if not exclusive_wallets_data:
        print(f"🤷‍♂️ Не найдено кошельков, работающих исключительно с {target_wallet_address}.")
        return # Выходим, если нет эксклюзивных кошельков

    # Шаг 3: Подсчитываем плотность эксклюзивных кошельков в контрактах
    contract_density = defaultdict(int)
    for entry in exclusive_wallets_data:
        for contract in entry['shared_contracts']:
            contract_density[contract] += 1

    # Сортируем контракты по плотности в убывающем порядке
    sorted_contract_density = sorted(contract_density.items(), key=lambda item: item[1], reverse=True)

    output_filename = generate_output_filename(target_wallet_address)
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(f"Кошельки, работающие ТОЛЬКО с контрактами, содержащими {target_wallet_address}:\n")
        f.write(f"Всего найдено эксклюзивных кошельков: {len(exclusive_wallets_data)}\n\n")
        
        for entry in exclusive_wallets_data:
            wallet = entry['wallet']
            shared_contracts = entry['shared_contracts']
            
            print(f"Кошелек: {wallet}")
            f.write(f"Кошелек: {wallet}\n")
            print("  Контракты:")
            f.write("  Контракты:\n")
            for contract in shared_contracts:
                print(f"    - {contract}")
                f.write(f"    - {contract}\n")
            print("\n")
            f.write("\n")

        # Вывод и сохранение топа контрактов по плотности
        if sorted_contract_density:
            f.write(f"\n--- Топ контрактов по плотности эксклюзивных кошельков (найдено {len(sorted_contract_density)}) ---\n")
            print(f"\n--- Топ контрактов по плотности эксклюзивных кошельков (найдено {len(sorted_contract_density)}) ---")
            for i, (contract, count) in enumerate(sorted_contract_density[:10]): # Выводим топ 10 по умолчанию
                print(f"  {i+1}. {contract} (Эксклюзивных кошельков: {count})")
                f.write(f"  {i+1}. {contract} (Эксклюзивных кошельков: {count})\n")
        else:
            f.write("\n🤷‍♂️ Не найдено контрактов с эксклюзивными кошельками.\n")
            print("\n🤷‍♂️ Не найдено контрактов с эксклюзивными кошельками.\n")

        print(f"💾 Результат сохранен в файл: {output_filename}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python find_exclusive_wallets.py <target_wallet_address>")
        print("Пример: python find_exclusive_wallets.py niggerd597QYedtvjQDVHZTCCGyJrwHNm2i49dkm5zS")
        sys.exit(1)

    target_wallet = sys.argv[1]
    find_exclusive_wallets_for_target_contract(target_wallet)
