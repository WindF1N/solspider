#!/usr/bin/env python3
"""
Скрипт для анализа логов bundle_analyzer и выявления активных контрактов
"""

import re
from collections import defaultdict
import ast

def extract_contract_from_jupiter(line):
    """Извлекает адрес контракта из записи о Jupiter"""
    try:
        # Находим словарь Python в строке после 'Дата сет токена Jupiter: '
        dict_str = line.split('Дата сет токена Jupiter: ')[1].strip()
        # Используем ast.literal_eval для безопасного преобразования строки в словарь
        data = ast.literal_eval(dict_str)
        
        if data['type'] == 'new' and 'pool' in data:
            return data['pool']['baseAsset']['id']
    except Exception as e:
        print(f"Ошибка при обработке строки Jupiter: {e}")
    return None

def analyze_log(log_file):
    """
    Анализирует лог-файл и подсчитывает количество метрик для каждого контракта
    """
    # Словарь для подсчета метрик по каждому контракту
    metrics_count = defaultdict(int)
    # Словарь для хранения полных адресов контрактов из Jupiter
    jupiter_contracts = {}
    
    # Паттерн для поиска анализа метрик
    metrics_pattern = re.compile(r'📊 АНАЛИЗ МЕТРИК для ([A-Za-z0-9]{8}):')
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # Проверяем записи Jupiter
            if 'Дата сет токена Jupiter:' in line:
                contract = extract_contract_from_jupiter(line)
                if contract:
                    short_id = contract[:8]
                    jupiter_contracts[short_id] = contract  # Сохраняем полный адрес
                    print(f"Найден контракт Jupiter: {short_id} ({contract})")
            
            # Подсчитываем метрики
            match = metrics_pattern.search(line)
            if match:
                contract_id = match.group(1)
                metrics_count[contract_id] += 1
    
    # Фильтруем только контракты с достаточным количеством метрик
    active_contracts = {
        contract: {
            'count': count,
            'full_address': jupiter_contracts.get(contract)
        }
        for contract, count in metrics_count.items() 
        if count >= 100 and contract in jupiter_contracts
    }
    
    return active_contracts

def save_results(contracts, output_file):
    """Сохраняет результаты в файл"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for contract, data in sorted(contracts.items(), key=lambda x: x[1]['count'], reverse=True):
            full_address = data['full_address']
            count = data['count']
            axiom_link = f"https://axiom.trade/t/{full_address}"
            f.write(f"{contract} (метрик: {count})\n")
            f.write(f"Axiom: {axiom_link}\n\n")

def main():
    log_file = 'bundle_analyzer.log'
    output_file = 'output2.txt'
    
    print("🔍 Анализируем лог-файл...")
    active_contracts = analyze_log(log_file)
    
    print(f"✅ Найдено {len(active_contracts)} активных контрактов")
    save_results(active_contracts, output_file)
    print(f"💾 Результаты сохранены в {output_file}")
    
    # Выводим статистику
    if active_contracts:
        counts = [data['count'] for data in active_contracts.values()]
        max_metrics = max(counts)
        min_metrics = min(counts)
        avg_metrics = sum(counts) / len(counts)
        print(f"\n📊 Статистика:")
        print(f"  Максимум метрик: {max_metrics}")
        print(f"  Минимум метрик: {min_metrics}")
        print(f"  Среднее метрик: {avg_metrics:.1f}")

if __name__ == "__main__":
    main() 