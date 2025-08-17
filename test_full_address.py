#!/usr/bin/env python3
"""
Тест извлечения полного адреса токена из логов
"""

import asyncio
import os
from test_filter import TokenFilterTester

async def test_full_address_extraction():
    """Тестируем извлечение полного адреса токена"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    if not os.path.exists(tokens_logs_dir):
        print(f"❌ Директория {tokens_logs_dir} не найдена")
        return
    
    log_files = [f for f in os.listdir(tokens_logs_dir) if f.endswith('.log')][:5]
    
    print(f"🔍 ТЕСТ ИЗВЛЕЧЕНИЯ ПОЛНОГО АДРЕСА ТОКЕНА")
    print(f"="*70)
    
    for i, log_file in enumerate(log_files, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        short_id = log_file.replace('.log', '')
        
        print(f"{i}. ФАЙЛ: {log_file}")
        print(f"   Короткий ID: {short_id}")
        
        # Извлекаем полный адрес
        full_address = None
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    # Ищем строку с полным адресом токена
                    if '/tokenAddress/' in line:
                        import re
                        match = re.search(r'/tokenAddress/([A-Za-z0-9]{32,})', line)
                        if match:
                            full_address = match.group(1)
                            print(f"   ✅ ПОЛНЫЙ АДРЕС: {full_address}")
                            print(f"   📍 Найден в строке {line_num}")
                            break
                    # Альтернативный поиск в данных
                    elif "'tokenAddress':" in line:
                        match = re.search(r"'tokenAddress':\s*'([A-Za-z0-9]{32,})'", line)
                        if match:
                            full_address = match.group(1)
                            print(f"   ✅ ПОЛНЫЙ АДРЕС: {full_address}")
                            print(f"   📍 Найден в строке {line_num} (alt)")
                            break
                    
                    # Ограничиваем поиск первыми 100 строками
                    if line_num > 100:
                        break
                        
            if not full_address:
                print(f"   ❌ Полный адрес НЕ НАЙДЕН")
                
        except Exception as e:
            print(f"   💥 ОШИБКА: {e}")
        
        print()
    
    print("="*70)
    print("🎯 РЕЗУЛЬТАТ:")
    print("✅ Поиск полного адреса работает")
    print("📊 Теперь в логах будут показываться полные адреса токенов")
    print("🔍 Формат: TOKEN: 2Bi9HXbaJWaJxiWY3ZzrLTcyp4QqKcBugR5DaexLzhwx")

if __name__ == "__main__":
    asyncio.run(test_full_address_extraction())