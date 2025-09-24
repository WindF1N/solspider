#!/usr/bin/env python3

import os
import sys

EBOSHERS_LOGS_DIR = "eboshers_logs"

def generate_output_filename(wallet_addresses: list[str]) -> str:
    """Генерирует имя файла для сохранения результатов на основе адресов кошельков."""
    # Берем первые 8 символов каждого кошелька и объединяем их через '+'
    short_wallet_names = [addr[:8] for addr in wallet_addresses]
    filename_prefix = "+".join(short_wallet_names)
    return f"contracts_{filename_prefix}.txt"


def search_wallets_in_logs(wallet_addresses: list[str]):
    """Ищет указанные адреса кошельков во всех лог-файлах в папке EBOSHERS_LOGS_DIR."""
    if not wallet_addresses:
        print("❌ Необходимо указать хотя бы один адрес кошелька.")
        return

    print(f"🔍 Ищем контракты, содержащие все кошельки: {', '.join(wallet_addresses)}...")
    found_contracts = set()

    if not os.path.exists(EBOSHERS_LOGS_DIR):
        print(f"❌ Папка {EBOSHERS_LOGS_DIR} не найдена.")
        return

    for filename in os.listdir(EBOSHERS_LOGS_DIR):
        if filename.endswith('.log'):
            contract_address = filename.replace('.log', '')
            filepath = os.path.join(EBOSHERS_LOGS_DIR, filename)

            try:
                # Отслеживаем, какие кошельки найдены в текущем файле
                wallets_found_in_file = {addr: False for addr in wallet_addresses}
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        for wallet_addr in wallet_addresses:
                            if wallet_addr in line:
                                wallets_found_in_file[wallet_addr] = True
                        
                        # Если все кошельки найдены в этом файле, прерываем чтение файла
                        if all(wallets_found_in_file.values()):
                            found_contracts.add(contract_address)
                            print(f"✅ Все кошельки найдены в контракте: {contract_address}")
                            break  # Найдены все, переходим к следующему файлу
            except Exception as e:
                print(f"❌ Ошибка чтения файла {filepath}: {e}")

    if not found_contracts:
        print(f"🤷‍♂️ Все кошельки ({', '.join(wallet_addresses)}) не найдены вместе ни в одном контракте.")
    else:
        print(f"\n--- Все контракты ({len(found_contracts)}), содержащие все указанные кошельки --- ")
        for contract in sorted(list(found_contracts)):
            print(contract)

        # Сохранение результата в файл
        output_filename = generate_output_filename(wallet_addresses)
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(f"Контракты, содержащие кошельки: {', '.join(wallet_addresses)}\n")
                f.write(f"Всего найдено контрактов: {len(found_contracts)}\n\n")
                f.write("--- Список контрактов ---\n")
                for contract in sorted(list(found_contracts)):
                    f.write(f"{contract}\n")
            print(f"💾 Результат сохранен в файл: {output_filename}")
        except Exception as e:
            print(f"❌ Ошибка сохранения результата в файл {output_filename}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python search_wallet_in_logs.py <wallet_address_1> [<wallet_address_2> ...]")
        sys.exit(1)

    wallets_to_search = sys.argv[1:]
    search_wallets_in_logs(wallets_to_search)
