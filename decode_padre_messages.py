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
            "b64": "kwUPhKpfY3JlYXRlZEF0zmiHsH6vc29sU2F2ZWRGaWx0ZXJzkKpzb2xGaWx0ZXJzg6NORVfeABawRVhDTFVERSBLRVlXT1JEU5ClU0VMTFOCpGZyb23AonRvwKRCVVlTgqJ0b8CkZnJvbcC1Qk9UIFVTRVIgVFJBTlNBQ1RJT05TgqJ0b8CkZnJvbcCzREVYU0NSRUVORVIgQk9PU1RFRMK4VE9QIElOU0lERVIgSE9MRElORyBQQ05UgqJ0b8CkZnJvbcCtSE9MREVSUyBDT1VOVIKkZnJvbcCidG/AtFRPS0VOIEFHRSBJTiBTRUNPTkRTgqJ0b8CkZnJvbcCmVk9MVU1FgqJ0b8CkZnJvbcC2UEVSQ0VOVEFHRSBERVYgSE9MRElOR4KidG/ApGZyb23AqkRFViBCT05ERUSConRvwKRmcm9twKpMQVVOQ0hQQURTwKtERVYgSE9MRElOR8KrSEFTIFNPQ0lBTFPCs0hBUyBPUklHSU5BTCBBVkFUQVLCskJVWSBUSVBTIElOIE5BVElWRYKkZnJvbcCidG/Ap1RJQ0tFUlOQs1RPUCAxMCBIT0xERVJTIFBDTlSCpGZyb23AonRvwLRCVU5ETEVTIEhPTERJTkcgUENOVIKkZnJvbcCidG/AsE5PIFNPQ0lBTFMgUkVVU0XCrkNVUlZFX1BST0dSRVNTgqJ0b8CkZnJvbcCqTUFSS0VUIENBUIKkZnJvbcCidG/ArUFMTU9TVF9CT05ERUTeABarREVWIEhPTERJTkfCpVNFTExTgqJ0b8CkZnJvbcCzSEFTIE9SSUdJTkFMIEFWQVRBUsK0VE9LRU4gQUdFIElOIFNFQ09ORFOCpGZyb23AonRvwKdUSUNLRVJTkK5DVVJWRV9QUk9HUkVTU4KidG/ApGZyb23AskJVWSBUSVBTIElOIE5BVElWRYKidG/ApGZyb23AtEJVTkRMRVMgSE9MRElORyBQQ05UgqJ0b8CkZnJvbcC4VE9QIElOU0lERVIgSE9MRElORyBQQ05UgqJ0b8CkZnJvbcCrSEFTIFNPQ0lBTFPCs0RFWFNDUkVFTkVSIEJPT1NURUTCqk1BUktFVCBDQVCCpGZyb23AonRvwLBOTyBTT0NJQUxTIFJFVVNFwqpERVYgQk9OREVEgqRmcm9twKJ0b8CmVk9MVU1FgqJ0b8CkZnJvbcCqTEFVTkNIUEFEU8CwRVhDTFVERSBLRVlXT1JEU5C2UEVSQ0VOVEFHRSBERVYgSE9MRElOR4KkZnJvbcCidG/AtUJPVCBVU0VSIFRSQU5TQUNUSU9OU4KidG/ApGZyb23ArUhPTERFUlMgQ09VTlSConRvwKRmcm9twKRCVVlTgqJ0b8CkZnJvbcCzVE9QIDEwIEhPTERFUlMgUENOVIKkZnJvbcCidG/Ar1JFQ0VOVExZX0JPTkRFRN4AFrNUT1AgMTAgSE9MREVSUyBQQ05UgqRmcm9twKJ0b8CzREVYU0NSRUVORVIgQk9PU1RFRMK2UEVSQ0VOVEFHRSBERVYgSE9MRElOR4KidG/ApGZyb23ArUhPTERFUlMgQ09VTlSConRvwKRmcm9twLJCVVkgVElQUyBJTiBOQVRJVkWConRvwKRmcm9twLNIQVMgT1JJR0lOQUwgQVZBVEFSwqVTRUxMU4KidG/ApGZyb23AsE5PIFNPQ0lBTFMgUkVVU0XCplZPTFVNRYKidG/ApGZyb23Aqk1BUktFVCBDQVCCpGZyb23AonRvwLhUT1AgSU5TSURFUiBIT0xESU5HIFBDTlSConRvwKRmcm9twKtIQVMgU09DSUFMU8KqTEFVTkNIUEFEU8C0QlVORExFUyBIT0xESU5HIFBDTlSCpGZyb23AonRvwKdUSUNLRVJTkKRCVVlTgqRmcm9twKJ0b8CwRVhDTFVERSBLRVlXT1JEU5CuQ1VSVkVfUFJPR1JFU1OConRvwKRmcm9twLRUT0tFTiBBR0UgSU4gU0VDT05EU4KkZnJvbcCidG/Aq0RFViBIT0xESU5HwqpERVYgQk9OREVEgqRmcm9twKJ0b8C1Qk9UIFVTRVIgVFJBTlNBQ1RJT05TgqRmcm9twKJ0b8CjdWlkrXRnXzc4OTE1MjQyNDQ=",
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