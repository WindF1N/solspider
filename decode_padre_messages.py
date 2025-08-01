#!/usr/bin/env python3
"""
Скрипт для декодирования base64 сообщений от trade.padre.gg
"""

import base64
import json

def decode_message(b64_message, description=""):
    """Декодирует base64 сообщение"""
    try:
        decoded = base64.b64decode(b64_message)
        decoded_str = decoded.decode('utf-8', errors='ignore')
        
        print(f"\n{'='*60}")
        print(f"📨 {description}")
        print(f"{'='*60}")
        print(f"🔤 Base64: {b64_message[:50]}...")
        print(f"📝 Decoded: {decoded_str}")
        
        # Попытаемся найти структуру сообщения
        if decoded_str.startswith('/'):
            print(f"🌐 Тип: WebSocket путь/подписка")
        elif '{' in decoded_str:
            print(f"📋 Тип: JSON данные")
        else:
            print(f"📄 Тип: Текстовое сообщение")
            
        return decoded_str
        
    except Exception as e:
        print(f"❌ Ошибка декодирования: {e}")
        return None

def main():
    print("🔍 Анализ сообщений trade.padre.gg")
    print("="*60)
    
    # Сообщения для анализа
    messages = [
        {
            "b64": "kwHaBLFleUpoYkdjaU9pSlNVekkxTmlJc0ltdHBaQ0k2SW1FNFpHWTJNbVF6WVRCaE5EUmxNMlJtWTJSallXWmpObVJoTVRNNE16YzNORFU1WmpsaU1ERWlMQ0owZVhBaU9pSktWMVFpZlEuZXlKdVlXMWxJam9pMEpyUXNOR0MwWThnMEpqUXN0Q3cwTDNRdnRDeTBMQWlMQ0p3YVdOMGRYSmxJam9pYUhSMGNITTZMeTlzYURNdVoyOXZaMnhsZFhObGNtTnZiblJsYm5RdVkyOXRMMkV2UVVObk9HOWpTVVJZUmtoWVVsaFpSa3h3WVhjMGJFMU5ZbHBuUzNoTFNFUkJUR2xvWVRkRGFYcHRibFprZGpFeGJXNUJNMlJyY3oxek9UWXRZeUlzSW1oaGRYUm9JanAwY25WbExDSnBjM01pT2lKb2RIUndjem92TDNObFkzVnlaWFJ2YTJWdUxtZHZiMmRzWlM1amIyMHZjR0ZrY21VdE5ERTNNREl3SWl3aVlYVmtJam9pY0dGa2NtVXROREUzTURJd0lpd2lZWFYwYUY5MGFXMWxJam94TnpRNU5qWXpOekkzTENKMWMyVnlYMmxrSWpvaWFEbFBlRkYxVm5FNVNWa3lWSFp5TkdNMGFVRnJaSEUyZW5OeU1TSXNJbk4xWWlJNkltZzVUM2hSZFZaeE9VbFpNbFIyY2pSak5HbEJhMlJ4Tm5wemNqRWlMQ0pwWVhRaU9qRTNOVE14TVRnNE5USXNJbVY0Y0NJNk1UYzFNekV5TWpRMU1pd2laVzFoYVd3aU9pSmhaMkZtYjI1dmRpNWxaMjl5ZFhOb2EyRkFaMjFoYVd3dVkyOXRJaXdpWlcxaGFXeGZkbVZ5YVdacFpXUWlPblJ5ZFdVc0ltWnBjbVZpWVhObElqcDdJbWxrWlc1MGFYUnBaWE1pT25zaVoyOXZaMnhsTG1OdmJTSTZXeUl4TURrM01qYzNOell3TVRreU5EWTNOelEyTXpFaVhTd2laVzFoYVd3aU9sc2lZV2RoWm05dWIzWXVaV2R2Y25WemFHdGhRR2R0WVdsc0xtTnZiU0pkZlN3aWMybG5ibDlwYmw5d2NtOTJhV1JsY2lJNkltZHZiMmRzWlM1amIyMGlmWDAuUjBhMHRHaUl5TzJOM2tVdVJONTVZb2Q4NmlPSk0xRFhHOFNDcFJQSzdkMmlxLXVOMllMN0pmZlk0X1VfWmpPQW9FemFSeWhzTDZQeDhYOWswR01kZ1VDQWtaTUd2LWd3THpWMlZ4SXF3dTRUQzdIemFFYTN1bGNuMEJGMkRrZUVRR19CcEE5OWUzUnNkUzVSVFRqeVhEMTZPM2laNGYwSFZRSVYyby1KZ1E0RHN1N0FnNk44eENNZ2FHbVhnNmNobFB3TjVZd3ZLb0tpRVRSWVJfYnJ5a1d1UDJPUGpHMWtFLXk4dEo3RXNfd0JpMTgybGlJeUd4VTZIVUR0RGU3RmhCcl9OT0l0ZjF0dTdBY1gtcndhc0p2cDNqUllGS1hNTXFDYUdQaWxJRVVmd0JoWkc2N0EzaXFwdzdoUU9PWWdzWFM5ZVdIeGlOQU1TZE5wOXlCT2RRrTczNTQ1ODNhLTdkM2E=",
            "desc": "Сообщение 1 - Возможно цены/маркет данные"
        },
    ]
    
    # Декодируем все сообщения
    for i, msg in enumerate(messages, 1):
        decode_message(msg["b64"], msg["desc"])
    
    print(f"\n🎯 АНАЛИЗ РЕЗУЛЬТАТОВ:")
    print("="*60)
    print("1. Первое сообщение - запрос маркет данных для конкретного токена")
    print("2. Второе сообщение - ПОДПИСКА НА FAST-STATS для МНОЖЕСТВА токенов!")
    print("3. Третье сообщение - подписка на trailing prices для одного токена")
    print("4. Четвертое сообщение - получение персональных заметок")
    print()
    print("🔥 ВТОРОЕ СООБЩЕНИЕ выглядит как то что нам нужно!")
    print("   Оно подписывается на 'fast-stats' для encoded-tokens")
    print("   Это может содержать данные о бандлерах!")

if __name__ == "__main__":
    main() 