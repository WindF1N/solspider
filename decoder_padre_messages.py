import base64
import msgpack

encoded_str = "kwQ12d8vdHJhY2tlZC10cmFkZXMvd2FsbGV0LWdyb3Vwcy85YzU2NWFlZC0zMTU2LTQ3MTEtYjFhZi0wZTJkOWVmZjE1YTQvc3Vic2NyaWJlP2VuY29kZWRGaWx0ZXI9JTdCJTIydHJhZGVUeXBlJTIyJTNBJTVCMCUyQzElMkMzJTJDMiU1RCUyQyUyMmFtb3VudEluVXNkJTIyJTNBJTdCJTdEJTJDJTIybWNhcEluVXNkJTIyJTNBJTdCJTdEJTJDJTIydG9rZW5BZ2VTZWNvbmRzJTIyJTNBJTdCJTdEJTdE"

try:
    decoded_bytes = base64.b64decode(encoded_str)
    decoded_data = msgpack.unpackb(decoded_bytes)
    print("Декодированные данные:")
    print(decoded_data)
    print(f"\nТип: {type(decoded_data)}")
    print(f"Длина: {len(decoded_data) if hasattr(decoded_data, '__len__') else 'N/A'}")
except Exception as e:
    print(f"Ошибка декодирования: {e}")