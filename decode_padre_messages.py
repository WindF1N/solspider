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
            "b64": "kwHaAyZleUpoYkdjaU9pSlNVekkxTmlJc0ltdHBaQ0k2SW1WbU1qUTRaalF5WmpjMFlXVXdaamswT1RJd1lXWTVZVGxoTURFek1UZGxaakprTXpWbVpURWlMQ0owZVhBaU9pSktWMVFpZlEuZXlKdVlXMWxJam9pZDI5eWEyVnlNVEF3TUhnaUxDSm9ZWFYwYUNJNmRISjFaU3dpYVhOeklqb2lhSFIwY0hNNkx5OXpaV04xY21WMGIydGxiaTVuYjI5bmJHVXVZMjl0TDNCaFpISmxMVFF4TnpBeU1DSXNJbUYxWkNJNkluQmhaSEpsTFRReE56QXlNQ0lzSW1GMWRHaGZkR2x0WlNJNk1UYzFOVFkwT0RBM09Dd2lkWE5sY2w5cFpDSTZJblJuWHpjNE9URTFNalF5TkRRaUxDSnpkV0lpT2lKMFoxODNPRGt4TlRJME1qUTBJaXdpYVdGMElqb3hOelUyTlRneU56WXlMQ0psZUhBaU9qRTNOVFkxT0RZek5qSXNJbVpwY21WaVlYTmxJanA3SW1sa1pXNTBhWFJwWlhNaU9udDlMQ0p6YVdkdVgybHVYM0J5YjNacFpHVnlJam9pWTNWemRHOXRJbjE5LkJwb2p2WDNWUkRtTkxmRzBPTHRSMTZIRGd4V1pZQTJLWUI4dXlCamtveWdQVVVrNGwyR1dUZ2RSaXc1T21JVnk4QW5mV0VndzlmLTBQNDZyTTY0Q2lWQkJ3UzVWUi1zWlJSRmp1clVPTjhrUXZMNU1sRmFnV1Y4Yzg1YWJnNmt0bUxVcVJJYzZGcndrYW1IUXVUNFZpRlFHSWxWMzJtenhTRGJHb2otOWxSemh5c0xBZFQxYms1NzZiNmdzZ1dVdlNiVGxLV3NXQkZfRmxOaDdfbGl3bXZoTHBCRVMydFYtcFJvY2tnNllkeWczSGZDQk9fNkh2ZFM0VlptMVpXdjF2ZDRnblFNc2MyUDRnaTlpS0U5UktvSVp4Nk9kWFAxaU9YbklweTV3dVNCWUNHOFU4MkFGM1NDd2dqZXFtZTUxTElvS1lPTkV0eWo5N3VkbjlLeTEtd61lMjJiZTllYS0yYTJl",
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