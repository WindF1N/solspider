import os
import glob
import re
from collections import defaultdict

def analyze_top10_changes_before_telegram(log_dir="tokens_logs_0"):
    """
    Анализирует ИЗМЕНЕНИЯ ТОП-10 сливов только ДО отправки в Telegram
    Уменьшения = продажи, Увеличения = покупки
    Считает покупки только после первой продажи
    """
    results = []
    
    # Ищем все .log файлы в директории
    log_files = glob.glob(os.path.join(log_dir, "*.log"))
    
    for file_path in log_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Находим позицию отправки в Telegram
            telegram_line_index = None
            for i, line in enumerate(lines):
                if '📤 Отправляем в Telegram:' in line:
                    telegram_line_index = i
                    break

            if telegram_line_index == None:
                # Создаем папку no_sent если ее нет
                no_sent_dir = os.path.join(log_dir, "no_sent")
                os.makedirs(no_sent_dir, exist_ok=True)
                
                # Перемещаем файл в no_sent
                new_path = os.path.join(no_sent_dir, os.path.basename(file_path))
                os.rename(file_path, new_path)
                print(f"Файл {os.path.basename(file_path)} перемещен в no_sent")
                continue
            
            # Собираем все записи ТОП-10 ДО отправки в Telegram
            top10_records = []
            first_sale_found = False
            first_sale_line_index = None
            
            for i, line in enumerate(lines):
                # Если достигли отправки в Telegram, останавливаемся
                if telegram_line_index is not None and i >= telegram_line_index:
                    break
                
                # Ищем записи ТОП-10
                top10_match = re.search(r'🏆 ТОП-10: ([\d\.]+)%', line)
                if top10_match:
                    top10_value = float(top10_match.group(1))
                    top10_records.append({
                        'line_index': i,
                        'value': top10_value,
                        'is_sale': False,
                        'is_purchase': False,
                        'is_after_first_sale': False
                    })
            
            # Анализируем изменения ТОП-10
            changes = []
            purchases_after_first_sale = 0
            purchases_after_sale_list = []
            
            if len(top10_records) >= 2:
                is_sold = False
                # Находим все изменения
                for i in range(1, len(top10_records)):
                    prev_value = top10_records[i-1]['value']
                    curr_value = top10_records[i]['value']
                    
                    if curr_value < prev_value:
                        # УМЕНЬШЕНИЕ - продажа
                        change_amount = prev_value - curr_value
                        change = {
                            'line_index': top10_records[i]['line_index'],
                            'from': prev_value,
                            'to': curr_value,
                            'amount': change_amount,
                            'type': 'sale',
                            'is_after_first_sale': False
                        }
                        changes.append(change)
                        top10_records[i]['is_sale'] = True
                        is_sold = True

                    elif curr_value > prev_value and is_sold:
                        # УВЕЛИЧЕНИЕ - покупка
                        change_amount = curr_value - prev_value
                        change = {
                            'line_index': top10_records[i]['line_index'],
                            'from': prev_value,
                            'to': curr_value,
                            'amount': change_amount,
                            'type': 'purchase',
                            'is_after_first_sale': False
                        }
                        changes.append(change)
                        top10_records[i]['is_purchase'] = True
            
            # Находим первую продажу
            first_sale_change = None
            for change in changes:
                if change['type'] == 'sale':
                    first_sale_change = change
                    break
            
            # Помечаем покупки после первой продажи
            if first_sale_change:
                first_sale_line_index = first_sale_change['line_index']
                for change in changes:
                    if (change['type'] == 'purchase' and 
                        change['line_index'] > first_sale_line_index):
                        change['is_after_first_sale'] = True
                        purchases_after_first_sale += 1
                        purchases_after_sale_list.append(change)
            
            # Разделяем изменения
            decreases = [c for c in changes if c['type'] == 'sale']
            increases = [c for c in changes if c['type'] == 'purchase']
            
            # Форматируем для вывода
            decrease_values = [f"{c['from']}%→{c['to']}% (Δ-{c['amount']:.1f}%)" for c in decreases]
            increase_values = [f"{c['from']}%→{c['to']}% (Δ+{c['amount']:.1f}%)" for c in increases]
            purchases_after_sale_values = [f"{c['from']}%→{c['to']}% (Δ+{c['amount']:.1f}%)" for c in purchases_after_sale_list]
            
            # Формируем результат
            result = {
                'file': os.path.basename(file_path),
                'total_top10_records': len(top10_records),
                'total_changes': len(changes),
                'decreases_count': len(decreases),
                'increases_count': len(increases),
                'decreases_list': ', '.join(decrease_values),
                'increases_list': ', '.join(increase_values),
                'purchases_after_sale_list': ', '.join(purchases_after_sale_values),
                'first_value': top10_records[0]['value'] if top10_records else 0,
                'last_value': top10_records[-1]['value'] if top10_records else 0,
                'max_value': max(r['value'] for r in top10_records) if top10_records else 0,
                'min_value': min(r['value'] for r in top10_records) if top10_records else 0,
                'total_decrease_amount': sum(c['amount'] for c in decreases),
                'total_increase_amount': sum(c['amount'] for c in increases),
                'has_telegram_send': telegram_line_index is not None,
                'has_sales': len(decreases) > 0,
                'first_sale_line_index': first_sale_line_index,
                'purchases_after_first_sale': purchases_after_first_sale,
                'total_purchases': len(increases)
            }
            
            results.append(result)
                
        except Exception as e:
            print(f"Ошибка обработки {file_path}: {e}")
    
    return results

def is_rag_file(analysis_result):
    """
    Улучшенное определение рагов
    """
    # 1. Сильное падение от максимума к концу (>30% от пика)
    if analysis_result['last_value'] < analysis_result['max_value'] * 0.7:
        return True
    
    # 2. Очень много мелких продаж (>30)
    if analysis_result['decreases_count'] > 30:
        return True
    
    # 3. Средний размер продажи > среднего размера покупки
    avg_sale = analysis_result['total_decrease_amount'] / analysis_result['decreases_count']
    avg_purchase = analysis_result['total_increase_amount'] / analysis_result['increases_count']
    if avg_sale > avg_purchase * 1.2:
        return True
    
    # 4. Низкое конечное значение относительно максимума
    if analysis_result['last_value'] < 25 and analysis_result['max_value'] > 35:
        return True
    
    return False

def save_analysis_to_file(results, output_file="result_analysis_before_telegram.txt"):
    """
    Сохраняет информацию об изменениях ТОП-10 ДО отправки в Telegram
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Анализ ИЗМЕНЕНИЙ ТОП-10 сливов ДО отправки в Telegram\n")
        f.write("Уменьшения = продажи, Увеличения = покупки\n")
        f.write("Покупки считаются только после первой продажи\n")
        f.write("=" * 100 + "\n\n")
        
        for result in results:
            f.write(f"Файл: {result['file']}\n")
            f.write(f"Запись отправки в Telegram: {'Да' if result['has_telegram_send'] else 'Нет'}\n")
            f.write(f"Продажи обнаружены: {'Да' if result['has_sales'] else 'Нет'}\n")
            f.write(f"Номер строки первой продажи: {result['first_sale_line_index'] if result['first_sale_line_index'] is not None else 'Нет продаж'}\n")
            f.write(f"Всего записей ТОП-10: {result['total_top10_records']}\n")
            f.write(f"Всего изменений ТОП-10: {result['total_changes']}\n")
            f.write(f"Количество продаж (уменьшений): {result['decreases_count']}\n")
            f.write(f"Количество покупок (увеличений): {result['increases_count']}\n")
            f.write(f"Покупок после первой продажи: {result['purchases_after_first_sale']}\n")
            f.write(f"Общая сумма продаж: {result['total_decrease_amount']:.2f}%\n")
            f.write(f"Общая сумма покупок: {result['total_increase_amount']:.2f}%\n")
            f.write(f"Начальное значение: {result['first_value']}%\n")
            f.write(f"Последнее значение до отправки: {result['last_value']}%\n")
            f.write(f"Максимальное значение: {result['max_value']}%\n")
            f.write(f"Минимальное значение: {result['min_value']}%\n")
            
            if result['decreases_count'] > 0:
                f.write(f"Продажи (уменьшения) ДО отправки в Telegram:\n")
                decreases = result['decreases_list'].split(', ')
                for decrease in decreases:
                    f.write(f"  • {decrease}\n")
            else:
                f.write("Продаж ДО отправки в Telegram не обнаружено\n")
            
            if result['purchases_after_first_sale'] > 0:
                f.write(f"Покупки ПОСЛЕ первой продажи:\n")
                purchases = result['purchases_after_sale_list'].split(', ')
                for purchase in purchases:
                    f.write(f"  • {purchase}\n")
            elif result['has_sales']:
                f.write("Покупок после первой продажи не обнаружено\n")

            # f.write(f"RAG: {is_rag_file(result)}\n")
                
            f.write("-" * 100 + "\n\n")

# Основной код
if __name__ == "__main__":
    print("Анализируем ИЗМЕНЕНИЯ ТОП-10 сливов ДО отправки в Telegram...")
    print("Уменьшения = продажи, Увеличения = покупки")
    print("Покупки считаются только после первой продажи")
    
    results = analyze_top10_changes_before_telegram()
    
    # Сортируем по количеству покупок после первой продажи (по убыванию)
    results.sort(key=lambda x: x['purchases_after_first_sale'], reverse=True)
    
    save_analysis_to_file(results)
    
    # Статистика
    files_with_telegram = sum(1 for r in results if r['has_telegram_send'])
    files_with_sales = sum(1 for r in results if r['has_sales'])
    total_sales = sum(r['decreases_count'] for r in results)
    total_purchases = sum(r['increases_count'] for r in results)
    total_purchases_after_sale = sum(r['purchases_after_first_sale'] for r in results)
    total_sale_amount = sum(r['total_decrease_amount'] for r in results)
    total_purchase_amount = sum(r['total_increase_amount'] for r in results)
    
    print(f"Анализ завершен! Результаты сохранены в result_analysis_before_telegram.txt")
    print(f"Обработано файлов: {len(results)}")
    print(f"Файлов с отправкой в Telegram: {files_with_telegram}")
    print(f"Файлов с продажами: {files_with_sales}")
    print(f"Общее количество продаж: {total_sales}")
    print(f"Общее количество покупок: {total_purchases}")
    print(f"Общее количество покупок после первой продажи: {total_purchases_after_sale}")
    print(f"Общая сумма продаж: {total_sale_amount:.2f}%")
    print(f"Общая сумма покупок: {total_purchase_amount:.2f}%")

    # Дополнительная статистика
    if files_with_sales > 0:
        avg_purchases_after_sale = total_purchases_after_sale / files_with_sales
        print(f"Среднее количество покупок после продажи на файл: {avg_purchases_after_sale:.2f}")
    
    if total_sales > 0:
        sale_to_purchase_ratio = total_purchases_after_sale / total_sales
        print(f"Соотношение покупок после продажи к общему количеству продаж: {sale_to_purchase_ratio:.2f}")