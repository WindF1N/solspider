#!/usr/bin/env python3
"""
Анализ оригинального сообщения подписки на fast-stats
"""

import base64
import msgpack

def analyze_original_message():
    # Оригинальное base64 сообщение из браузера
    original_b64 = "kwQB2gI1L2Zhc3Qtc3RhdHMvZW5jb2RlZC10b2tlbnMvc29sYW5hLTI2S0hFazZZMUYzdFkyTHVtNGZDaVRpSEMxQXRRNkNuZWc1eVA0VExib25rX3NvbGFuYS0zTGk4YUFnRGJhRjJpV2FGdGViR3FLQU03dEdzaDl4WTZ2bWhLdlNrcHVtcF9zb2xhbmEtM3hMdXVHaEY4OFlvUjcxNEZvZkU1TmFBYllxYlZHdEJENWQ1dDZteXB1bXBfc29sYW5hLTdGZG9UZWNBWncyc0NaQ0xwNmdrWTM0WG5LeE4yNlZCaU5qWkVjN3BwdW1wX3NvbGFuYS03U0ZtZThoZ1R4VGl4R0w4WWRNem5ua0FqUzJOS1BLVHltNEdyOEc1cHVtcF9zb2xhbmEtQWlyd1F1QW53V0JLbzRuNWJLaFkxM04zY1ZvMXRCVVF6QjRyYjJ4UnB1bXBfc29sYW5hLUVoTGJ3bmpnM2dFeWs4d01XQjZCWGd2cVVwc1hOVWdUcDRucUQ2S3pib25rX3NvbGFuYS1IYUx5WFZqUlFmWjMyWktudDk4S3FjMTNFS0tvM2lyWkYxeUd0VlRnQkFHU19zb2xhbmEtWDY5R0tCMmZMTjh0U1V4TlRNbmVHQVF3NzlxRHc5S2NQUXAzUm9BazljZl9zb2xhbmEtcXFndjFpUDk0U1NHZlN6bTFwQWJFYVZGSDVBQm9WTXRaS1FYclBocnU4QS9vbi1mYXN0LXN0YXRzLXVwZGF0ZQ=="
    
    print("🔍 Анализ оригинального сообщения подписки")
    print("="*60)
    
    # Декодируем base64
    decoded_bytes = base64.b64decode(original_b64)
    print(f"📦 Размер декодированного сообщения: {len(decoded_bytes)} байт")
    print(f"🔤 Первые 20 байт в hex: {decoded_bytes[:20].hex()}")
    print(f"🔤 Последние 20 байт в hex: {decoded_bytes[-20:].hex()}")
    
    # Анализируем структуру
    print(f"\n📋 Анализ структуры:")
    
    # Пытаемся понять MessagePack структуру
    try:
        # MessagePack может быть в начале
        for i in range(0, min(10, len(decoded_bytes))):
            try:
                header = decoded_bytes[:i]
                payload = decoded_bytes[i:]
                text_payload = payload.decode('utf-8', errors='ignore')
                
                if '/fast-stats' in text_payload:
                    print(f"✅ Найден заголовок длиной {i} байт: {header.hex()}")
                    print(f"📝 Payload: {text_payload[:100]}...")
                    
                    # Пытаемся декодировать заголовок как MessagePack
                    try:
                        if len(header) > 0:
                            mp_data = msgpack.unpackb(header, raw=False)
                            print(f"🎯 MessagePack заголовок: {mp_data}")
                    except:
                        pass
                    
                    break
            except:
                continue
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}")
    
    # Попробуем альтернативные подходы
    print(f"\n🔬 Альтернативные подходы:")
    
    # Вариант 1: Весь массив как MessagePack
    try:
        mp_full = msgpack.unpackb(decoded_bytes, raw=False)
        print(f"🎯 Полный MessagePack: {mp_full}")
    except Exception as e:
        print(f"❌ Не полный MessagePack: {e}")
    
    # Вариант 2: Поиск текстовой части
    try:
        text_part = decoded_bytes.decode('utf-8', errors='ignore')
        fast_stats_pos = text_part.find('/fast-stats')
        if fast_stats_pos > 0:
            binary_prefix = decoded_bytes[:fast_stats_pos]
            print(f"🔧 Бинарный префикс: {binary_prefix.hex()}")
            print(f"📝 Текстовая часть: {text_part[fast_stats_pos:fast_stats_pos+50]}...")
    except:
        pass

def create_correct_subscription(tokens):
    """Создаём правильное сообщение подписки"""
    print(f"\n🔧 Создание правильного сообщения подписки для {len(tokens)} токенов")
    print("="*60)
    
    # Формируем путь как в браузере
    tokens_part = "_".join([f"solana-{token}" for token in tokens])
    path = f"/fast-stats/encoded-tokens/{tokens_part}/on-fast-stats-update"
    
    print(f"📡 Путь: {path[:100]}...")
    
    # Пробуем различные префиксы
    prefixes_to_try = [
        b'\x93\x04\x01\xda\x02\x35',  # Наша текущая догадка
        b'\x93\x04\x01',             # Упрощённый вариант
        b'\x93\x04',                 # Ещё проще
        b'\x94\x04\x01\xda\x02\x35', # Альтернатива
        b'',                         # Без префикса
    ]
    
    for i, prefix in enumerate(prefixes_to_try, 1):
        try:
            message_bytes = prefix + path.encode('utf-8')
            message_b64 = base64.b64encode(message_bytes).decode('utf-8')
            
            print(f"\n🧪 Вариант {i}:")
            print(f"   Prefix: {prefix.hex() if prefix else 'None'}")
            print(f"   Size: {len(message_bytes)} bytes")
            print(f"   Base64: {message_b64[:50]}...")
            
        except Exception as e:
            print(f"❌ Ошибка варианта {i}: {e}")

if __name__ == "__main__":
    analyze_original_message()
    
    # Пример создания сообщения для нескольких токенов
    test_tokens = [
        "6C2dwLGLf9yHdSiiaie9PsHsF23WJx3pSinEPLybonk",
        "4bGgiWAaThSceVAbFc5JTrLv7yVYcWvtwBm2C527pump"
    ]
    create_correct_subscription(test_tokens) 