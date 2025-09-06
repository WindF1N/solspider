import os
import json
import glob
import re
import time
import requests
from datetime import datetime
from collections import defaultdict
import ast  # Для безопасного eval

# Список бэкендов Padre для ротации
PADRE_BACKENDS = [
    "wss://backend1.padre.gg/_multiplex",
    "wss://backend2.padre.gg/_multiplex",
    "wss://backend3.padre.gg/_multiplex",
    "wss://backend.padre.gg/_multiplex"
]

# Счетчик для ротации бэкендов
_backend_counter = 0

def get_next_padre_backend() -> str:
    """Возвращает следующий бэкенд Padre в режиме round-robin"""
    global _backend_counter
    backend = PADRE_BACKENDS[_backend_counter % len(PADRE_BACKENDS)]
    _backend_counter += 1
    return backend

def parse_log_files(log_dirs=["tokens_logs"]):
    """
    Анализирует .log файлы и извлекает информацию о топ-10 холдерах
    Возвращает по одному результату на файл с уникальным списком всех замеченных топов
    """
    results = []

    for log_dir in log_dirs:
    
        # Ищем все .log файлы в директории
        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        
        for file_path in log_files:
            try:
                seen_holders = set()  # Для отслеживания уникальных адресов
                file_info = None

                ca = ""
                market_id = ""

                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        
                        if "📡 Top holders путь: " in line:
                            try:
                                ca = line.split("📡 Top holders путь: ")[1].split("/")[-2]
                            except:
                                continue

                        if "📡 Market путь: " in line:
                            try:
                                market_id = line.split("📡 Market путь: ")[1].split("/")[-2].split('-')[1]
                            except:
                                continue

                        # Ищем строки с JSON данными
                        if "📊 new: {" in line:
                            try:
                                # Извлекаем JSON часть строки
                                json_str = line.split("📊 new: ")[1].strip()
                                datetime_line = line.split("📊 new: ")[0]

                                # Заменяем одинарные кавычки на двойные и Python None на JSON null
                                json_str = json_str.replace("'", '"')
                                json_str = json_str.replace("None", "null")
                                json_str = json_str.replace("True", "true")
                                json_str = json_str.replace("False", "false")

                                # Пытаемся распарсить JSON
                                data = json.loads(json_str)

                                # Создаем или обновляем информацию о файле
                                if not file_info:
                                    print(ca, market_id)
                                    file_info = {
                                        'ca': ca,
                                        'market_id': market_id,
                                        'filename': os.path.basename(file_path),
                                        'timestamp': data.get('timestamp'),
                                        'datetime': datetime.fromtimestamp(data.get('timestamp')).strftime('%Y-%m-%d %H:%M:%S') if data.get('timestamp') else None,
                                        'symbol': data.get('symbol'),
                                        'name': data.get('name'),
                                        'total_holders': data.get('total_holders'),
                                        'total_supply': data.get('totalSupply'),
                                        'top10_holders': []
                                    }
                                else:
                                    if data.get('totalSupply'):
                                        file_info['total_supply'] = data.get('totalSupply')

                                # Обрабатываем топ-10 холдеров
                                top10_holders = data.get('top10holders', {})
                                for address, holder_data in top10_holders.items():
                                    if holder_data and isinstance(holder_data, dict) and address not in seen_holders:
                                        seen_holders.add(address)

                                        holder_info = {
                                            'address': address,
                                            'percentage': holder_data.get('pcnt', 0),
                                            'insider': holder_data.get('insider', False),
                                            'isBundler': holder_data.get('isBundler', False),
                                            'isPool': holder_data.get('isPool', False),
                                            'appeared_at': datetime_line.split(' - ')[0].strip(),  # Добавляем дату и время появления в формате 2025-08-28 18:26:47,141
                                        }
                                        file_info['top10_holders'].append(holder_info)
                                
                            except json.JSONDecodeError as e:
                                # print(f"Ошибка парсинга JSON в строке файла {file_path}: {e}")
                                continue
                            except Exception as e:
                                print(f"Ошибка обработки строки в {file_path}: {e}")
                                continue
                
                if file_info:
                    # Сортируем холдеров по проценту владения (по убыванию)
                    file_info['top10_holders'].sort(key=lambda x: x['percentage'], reverse=True)
                    results.append(file_info)
                    
            except Exception as e:
                print(f"Ошибка обработки {file_path}: {e}")
    
    return results

def generate_report(results, output_file="top10_holders_report.txt"):
    """
    Генерирует отчет по топ-10 холдерам
    """

    JWT_TOKEN = None
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Отчет по топ-10 холдерам токенов\n")
        f.write("=" * 80 + "\n\n")

        count_rockets_of_address = {}
        all_rockets = []
        
        for result in results:
            # Находим самого раннего холдера (не инсайдера, не пула, не бандлера)
            earliest_holder = None
            for holder in result['top10_holders']:
                if not holder['insider'] and not holder['isPool'] and not holder['isBundler']:
                    if earliest_holder is None or holder['appeared_at'] < earliest_holder['appeared_at']:
                        earliest_holder = holder

            is_rocket = False
            first_market_cap = None
            max_market_cap = None
            min_marketcap = None

            if earliest_holder:
                # Делаем один запрос для всего файла
                appeared_at_str = earliest_holder['appeared_at'].split(',')[0]  # Убираем миллисекунды
                from_time = int(datetime.strptime(appeared_at_str, '%Y-%m-%d %H:%M:%S').timestamp())
                backend = get_next_padre_backend().replace('wss://', 'https://').replace('/_multiplex', '')
                current_time = from_time + 60 * 60 * 4
                
                url = (
                    f"{backend}/candles/history?"
                    f"symbol=solana-{result['market_id']}&"
                    f"from={from_time}&"
                    f"to={current_time}&"
                    f"resolution=1S&"
                    f"countback={current_time - from_time}"
                )

                if JWT_TOKEN == None:
                    JWT_TOKEN = input("Введите JWT токен: ").strip()

                headers = {
                    "Authorization": f"Bearer {JWT_TOKEN}",
                    "Origin": "https://trade.padre.gg",
                    "Referer": "https://trade.padre.gg/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
                }

                print(f"🕯️ Запрашиваем историю свечей для {result['ca']} с {backend}...")
                print(f"📡 URL запроса: {url}")

                candles_data = None

                try:
                    response = requests.get(url, headers=headers)
                    if response.status_code == 200:
                        try:
                            response_text = response.text
                            data = json.loads(response_text)
                            candles_data = data
                        except json.JSONDecodeError as e:
                            print(f"❌ Ошибка преобразования ответа в JSON: {str(e)}")
                            print(f"Полученный текст ответа: {response_text[:200]}...")
                    elif response.status_code == 401:
                        print(f"❌ Ошибка авторизации: {response.status_code}")
                        print(f"Ответ сервера: {response.text[:200]}...")
                        JWT_TOKEN = input("Введите JWT токен: ").strip()
                        continue
                    else:
                        print(f"❌ Ошибка запроса свечей ({response.status_code}): {url}")
                        print(f"Ответ сервера: {response.text[:200]}...")
                except Exception as e:
                    print(f"❌ Ошибка при запросе свечей: {str(e)}")

                if candles_data and candles_data.get('s') == 'ok':
                    closes = candles_data['c']
                    times = candles_data['t']
                    
                    if len(closes) > 0:
                        # Рассчитываем маркеткап первой свечи
                        first_price = closes[0] or 0
                        first_market_cap = (int(result.get('total_supply', 1000000000000000) or 1000000000000000) / (10 ** 9)) * first_price * 1000
                        
                        # Находим максимальный маркеткап на всем графике
                        max_price = max(closes) or 0
                        max_market_cap = (int(result.get('total_supply', 1000000000000000) or 1000000000000000) / (10 ** 9)) * max_price * 1000

                        if max_market_cap >= 50000:
                            is_rocket = True

                        min_marketcap = (int(result.get('total_supply', 1000000000000000) or 1000000000000000) / (10 ** 9)) * min(closes) or 0 * 1000

                    else:
                        print("❌ Нет данных о свечах")

            if not first_market_cap and not max_market_cap and not min_marketcap:
                print("❌ Нет данных от свечей")

            first_market_cap = first_market_cap or 0
            max_market_cap = max_market_cap or 0
            min_marketcap = min_marketcap or 0

            if is_rocket:
                all_rockets.append(result['ca'])

            f.write(f"Файл: {result['filename']}\n")
            f.write(f"CA: {result['ca']}\n")
            f.write(f"Rocket: {'Да' if is_rocket else 'Нет'}\n")
            f.write(f"Дата/время: {result['datetime']}\n")
            f.write(f"Всего холдеров: {result['total_holders']}\n")
            f.write(f"📊 Маркеткап первой свечи: {first_market_cap:,.2f}$\n")
            f.write(f"📈 Максимальный маркеткап: {max_market_cap:,.2f}$\n")
            f.write(f"📉 Минимальный маркеткап: {min_marketcap:,.2f}$\n\n")
            f.write(f"Топ-10 холдеров:\n")

            for i, holder in enumerate(result['top10_holders'], 1):
                if not holder['insider'] and not holder['isPool'] and not holder['isBundler']:
                    f.write(f"  {i}. {holder['address']} {holder['percentage']:.6f}% | {holder['appeared_at']}\n")
                    # f.write(f"     Доля: {holder['percentage']:.6f}%\n")
                    # f.write(f"     Инсайдер: {'Да' if holder['insider'] else 'Нет'}\n")
                    # f.write(f"     Бандлер: {'Да' if holder['isBundler'] else 'Нет'}\n")
                    # f.write(f"     Пул: {'Да' if holder['isPool'] else 'Нет'}\n")
                    # f.write(f"     Встречается: {address_counter[holder['address']]} раз(а)\n")
                    if is_rocket:
                        count_rockets_of_address[holder['address']] = count_rockets_of_address.get(holder['address'], 0) + 1
            
            f.write("-" * 80 + "\n\n")

        # Собираем статистику по частоте встречаемости адресов (не инсайдеры, не пулы, не бандлеры)
        address_counter = {}
        for result in results:
            # if result['ca'] not in all_rockets:
            #     continue
            for holder in result['top10_holders']:
                if not holder['insider'] and not holder['isPool'] and not holder['isBundler']:
                    address = holder['address']
                    if address in address_counter:
                        new_count = address_counter[address].get('count', 0) + 1
                        rockets = count_rockets_of_address.get(address, 0)
                        address_counter[address].update({
                            'count': new_count,
                            'rockets': rockets,
                            'winrate': (rockets / new_count * 100) if new_count > 0 else 0
                        })
                    else:
                        rockets = count_rockets_of_address.get(address, 0)
                        address_counter[address] = {
                            'count': 1,
                            'rockets': rockets,
                            'winrate': (rockets / 1 * 100) if 1 > 0 else 0
                        }
        
        # Сортируем по winrate (по убыванию), затем по count (по убыванию)
        top_addresses = sorted(address_counter.items(), key=lambda x: (x[1]['winrate'], x[1]['count']), reverse=True)

        # Выводим топ часто встречающихся адресов
        if top_addresses:
            f.write("Топ часто встречающихся адресов (не инсайдеры, не пулы, не бандлеры):\n")
            for i, (address, value) in enumerate(top_addresses, 1):
                if value['count'] <= 1:
                    continue
                f.write(f"  {i}. {address} - {value['count']} раз(а) | rockets: {value['rockets']} | wr: {round(value['winrate'], 2)}%\n")
            f.write("\n" + "=" * 80 + "\n\n")

            f.write("Топ часто встречающихся адресов (не инсайдеры, не пулы, не бандлеры) чистый список:\n")
            for i, (address, count) in enumerate(top_addresses, 1):
                if value['count'] <= 1:
                    continue
                f.write(f"{address}\n")
            f.write("\n" + "=" * 80 + "\n\n")

def export_to_csv(results, output_file="top10_holders.csv"):
    """
    Экспортирует данные в CSV
    """
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Filename', 'DateTime', 'Symbol', 'Name', 'TotalHolders', 
                        'Rank', 'Address', 'Percentage', 'Insider', 'Bundler', 'IsPool'])
        
        for result in results:
            for i, holder in enumerate(result['top10_holders'], 1):
                writer.writerow([
                    result['filename'],
                    result['datetime'],
                    result['symbol'],
                    result['name'],
                    result['total_holders'],
                    i,
                    holder['address'],
                    holder['percentage'],
                    holder['insider'],
                    holder['isBundler'],
                    holder['isPool']
                ])

# Альтернативная функция для сложных случаев
def parse_with_regex(content):
    """
    Парсит данные с помощью регулярных выражений для сложных случаев
    """
    # Ищем top10holders данные
    top10_pattern = r"'top10holders':\s*\{([^}]+)\}"
    top10_match = re.search(top10_pattern, content)
    
    if top10_match:
        top10_data = {}
        # Ищем все адреса и их данные
        address_pattern = r"'([A-Za-z0-9]+)':\s*\{([^}]+)\}"
        addresses = re.findall(address_pattern, top10_match.group(1))
        
        for address, data_str in addresses:
            holder_data = {}
            # Извлекаем данные каждого холдера
            pcnt_match = re.search(r"'pcnt':\s*([0-9.]+)", data_str)
            insider_match = re.search(r"'insider':\s*(True|False)", data_str)
            bundler_match = re.search(r"'isBundler':\s*(True|False)", data_str)
            pool_match = re.search(r"'isPool':\s*(True|False)", data_str)
            
            if pcnt_match:
                holder_data['pcnt'] = float(pcnt_match.group(1))
            if insider_match:
                holder_data['insider'] = insider_match.group(1) == 'True'
            if bundler_match:
                holder_data['isBundler'] = bundler_match.group(1) == 'True'
            if pool_match:
                holder_data['isPool'] = pool_match.group(1) == 'True'
            
            top10_data[address] = holder_data
        
        return top10_data
    
    return {}

# Основной код
if __name__ == "__main__":
    print("Анализируем .log файлы...")
    
    results = parse_log_files(log_dirs=["tokens_logs", "tokens_logs_0", "tokens_logs_1", "tokens_logs_2", "tokens_logs_3", "tokens_logs_4", "tokens_logs_6",
                                        "tokens_logs_7", "tokens_logs_8", "tokens_logs_9", "tokens_logs_10", "tokens_logs_11", "tokens_logs_12", "tokens_logs_13",
                                        "tokens_logs_14", "tokens_logs_15", "tokens_logs_16"])
    
    # Сортируем по дате
    results.sort(key=lambda x: x['timestamp'] if x['timestamp'] else 0)
    
    generate_report(results)
    export_to_csv(results)
    
    print(f"Анализ завершен! Обработано файлов: {len(results)}")
    print("Отчет сохранен в top10_holders_report.txt")
    print("CSV данные сохранены в top10_holders.csv")