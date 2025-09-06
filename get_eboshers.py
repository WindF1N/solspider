def find_unique_wallets(eboshers_file, losers_file, output_file):
    """
    Находит кошельки, которые есть в eboshers.txt но отсутствуют в losers.txt
    """
    try:
        # Читаем кошельки из eboshers.txt
        with open(eboshers_file, 'r', encoding='utf-8') as f:
            eboshers = set(line.strip() for line in f if line.strip())
        
        # Читаем кошельки из losers.txt
        with open(losers_file, 'r', encoding='utf-8') as f:
            losers = set(line.strip() for line in f if line.strip())
        
        # Находим уникальные кошельки (есть в eboshers, но нет в losers)
        unique_wallets = eboshers - losers
        
        # Сортируем для удобства (опционально)
        sorted_unique = sorted(unique_wallets)
        
        # Записываем результат в новый файл
        with open(output_file, 'w', encoding='utf-8') as f:
            for wallet in sorted_unique:
                f.write(wallet + '\n')
        
        # Статистика
        print(f"Обработано кошельков:")
        print(f"  В eboshers.txt: {len(eboshers)}")
        print(f"  В losers.txt: {len(losers)}")
        print(f"  Уникальных в eboshers: {len(unique_wallets)}")
        print(f"  Результат сохранен в: {output_file}")
        
        return sorted_unique
        
    except FileNotFoundError as e:
        print(f"Ошибка: Файл не найден - {e}")
    except Exception as e:
        print(f"Ошибка при обработке файлов: {e}")

# Запуск скрипта
if __name__ == "__main__":
    eboshers_file = "eboshers.txt"
    losers_file = "losers.txt"
    output_file = "eboshers_v4.txt"
    
    unique_wallets = find_unique_wallets(eboshers_file, losers_file, output_file)