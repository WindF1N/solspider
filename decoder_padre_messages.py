import base64
import msgpack

encoded_str = "kQM="

try:
    decoded_bytes = base64.b64decode(encoded_str)
    decoded_data = msgpack.unpackb(decoded_bytes)
    print("Декодированные данные:")
    print(decoded_data)
    print(f"\nТип: {type(decoded_data)}")
    print(f"Длина: {len(decoded_data) if hasattr(decoded_data, '__len__') else 'N/A'}")
except Exception as e:
    print(f"Ошибка декодирования: {e}")