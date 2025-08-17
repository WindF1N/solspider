#!/usr/bin/env python3
"""
Тест для отлова конкретной ошибки slice
"""

import asyncio
import os
import logging
from test_filter import TokenFilterTester

# Включаем подробное логирование
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_slice_error():
    """Тестируем конкретные токены которые вызывают ошибку slice"""
    tester = TokenFilterTester()
    
    tokens_logs_dir = '/home/creatxr/solspider/tokens_logs'
    
    # Токены которые вызывали ошибку
    error_tokens = [
        '2u1AMFNttZggLy1mHDAofoNQA8nC56dqnQg5JkaKhgiN.log',
        'EsYns2NH9r5U7VTp2uCkV7TVkmwsu4o1j1gdtbSSmytn.log'
    ]
    
    print(f"🔍 ТЕСТ ОШИБКИ SLICE")
    print(f"="*60)
    print(f"📊 Тестируем токены которые вызывали ошибку")
    print()
    
    for i, log_file in enumerate(error_tokens, 1):
        log_path = os.path.join(tokens_logs_dir, log_file)
        
        if not os.path.exists(log_path):
            print(f"{i}. ❌ ФАЙЛ НЕ НАЙДЕН: {log_file}")
            continue
            
        token_id = log_file.replace('.log', '')
        
        print(f"{i}. 🔍 ТЕСТ: {token_id}")
        print(f"   Файл: {log_path}")
        
        try:
            print(f"   📊 Начинаем анализ...")
            result = await tester.analyze_token_with_full_criteria(log_path)
            
            decision = result.get('decision', 'UNKNOWN')
            reason = result.get('reason', 'Нет причины')
            
            print(f"   ✅ УСПЕХ: {decision}")
            print(f"   💡 Причина: {reason[:100]}")
            
        except Exception as e:
            print(f"   💥 ОШИБКА: {e}")
            
            if "slice" in str(e):
                print(f"   🚨 ОШИБКА SLICE НАЙДЕНА!")
                
                # Выводим полный traceback
                import traceback
                print(f"   📊 Полный traceback:")
                traceback.print_exc()
            else:
                print(f"   📊 Другая ошибка (не slice)")
        
        print()
        
        # Тестируем только первый для начала
        if i == 1:
            break
    
    print("="*60)
    print("🎯 ЦЕЛЬ:")
    print("✅ Найти точное место где происходит ошибка slice")
    print("✅ Исправить все проблемные места")

if __name__ == "__main__":
    asyncio.run(test_slice_error())