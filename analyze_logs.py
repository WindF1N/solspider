#!/usr/bin/env python3
"""
Скрипт для анализа логов из папки tokens_logs и выявления активных контрактов
"""

import re
import os
from collections import defaultdict
import ast

def extract_contract_from_jupiter(line):
    """Извлекает адрес контракта из записи о Jupiter"""
    try:
        
        return line.split('/')[-2].strip()
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
            if '📡 Top holders путь: /holders/chains/SOLANA/tokenAddress/' in line:
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

def process_logs_directory():
    """Обрабатывает все лог-файлы в директории tokens_logs"""
    logs_dir = 'tokens_logs'
    combined_contracts = {}
    
    # Проверяем существование директории
    if not os.path.exists(logs_dir):
        print(f"❌ Директория {logs_dir} не найдена")
        return
    
    # Получаем список всех файлов .log в директории
    log_files = [f for f in os.listdir(logs_dir) if f.endswith('.log')]
    
    if not log_files:
        print(f"❌ Лог-файлы не найдены в директории {logs_dir}")
        return
    
    print(f"🔍 Найдено {len(log_files)} лог-файлов для анализа")
    
    # Обрабатываем каждый файл
    for log_file in log_files:
        full_path = os.path.join(logs_dir, log_file)
        print(f"\nАнализируем файл: {log_file}")
        
        file_contracts = analyze_log(full_path)
        
        # Объединяем результаты
        for contract, data in file_contracts.items():
            if contract not in combined_contracts:
                combined_contracts[contract] = data
            else:
                # Если контракт уже существует, суммируем количество метрик
                combined_contracts[contract]['count'] += data['count']
    
    return combined_contracts

def main():
    output_file = 'output2.txt'
    
    print("🔍 Начинаем анализ лог-файлов...")
    active_contracts = process_logs_directory()
    
    if not active_contracts:
        print("❌ Нет данных для сохранения")
        return
    
    print(f"✅ Найдено {len(active_contracts)} активных контрактов")
    save_results(active_contracts, output_file)
    print(f"💾 Результаты сохранены в {output_file}")
    
    # Выводим статистику
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