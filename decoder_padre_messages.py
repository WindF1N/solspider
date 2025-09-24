import base64
import msgpack

encoded_str = "kwQl2U0vdHJhZGVzL3JlY2VudC9zb2xhbmEtSExLelhkc2czcTJXd2dKSGlVVUNYZ29ubnZYcnZ2UFNxa3Bucmp1OTR5alIvc21hcnQtZmVlZA=="

try:
    decoded_bytes = base64.b64decode(encoded_str)
    decoded_data = msgpack.unpackb(decoded_bytes)
    print("Декодированные данные:")
    print(decoded_data)
    print(f"\nТип: {type(decoded_data)}")
    print(f"Длина: {len(decoded_data) if hasattr(decoded_data, '__len__') else 'N/A'}")
except Exception as e:
    print(f"Ошибка декодирования: {e}")