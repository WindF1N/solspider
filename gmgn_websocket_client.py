import asyncio
import websockets
import json
import logging
import ssl

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GmgnWebSocketClient:
    def __init__(self):
        self.websocket = None
        self.running = False
        self.logger = logger

        # Request URL components
        base_url = "wss://gmgn.ai/ws"
        device_id = "eeb8dafa-3383-469c-9eff-0d8e7f91772b"
        fp_did = "d77855ac6b24fee27da1ac79e7aaf072"
        client_id = "gmgn_web_20250922-4296-2d47d6d"
        from_app = "gmgn"
        app_ver = "20250922-4296-2d47d6d"
        tz_name = "Europe%2FMoscow"
        tz_offset = "10800"
        app_lang = "ru"
        os_type = "web"
        uuid = "18b45ab50dac1aa9"

        # Construct the full WebSocket URL
        self.url = (
            f"{base_url}?"
            f"device_id={device_id}&"
            f"fp_did={fp_did}&"
            f"client_id={client_id}&"
            f"from_app={from_app}&"
            f"app_ver={app_ver}&"
            f"tz_name={tz_name}&"
            f"tz_offset={tz_offset}&"
            f"app_lang={app_lang}&"
            f"os={os_type}&"
            f"uuid={uuid}"
        )

        self.headers = {
            "cookie": "_ga=GA1.1.1563693264.1757841681; sid=gmgn%7Ca483520275744a1651a6156b423b3a8c; _ga_UGLVBMV4Z0=GS1.2.1758563209334888.df49406be1f500d04ba8d86c6c3a94c4.LY9q%2BaKKBZzMxzZDQKV4Qg%3D%3D.n9w6FXI6l%2Fv0A70B0ZQx7g%3D%3D.CmILlhy0y8htfp5ReVzjOw%3D%3D.tUoQYdjhd%2BSC1jPI6%2BtjHw%3D%3D; __cf_bm=FAf1S8Hc0qkE1Q_PrVJ1_UNh2P8a1v03DgjEdBr8K0M-1758563214-1.0.1.1-I8w0PxhNy7xqNz2C6G_ISS30zvryL7HD3sKTva4wWBwZE_NhU4ef.esxByogWm3jpAgEcPKB3PzZp3gRYfXfyFCoGOT1ajfwuTg.EqtsU38; cf_clearance=bsn098MgFPdifHQXSW9gJJkpDFJuLzY951AkCdTGGpM-1758563504-1.2.1.1-GlUZIHcyPpZ9VdU_bRdKubLUGmlO_nfXav74JYSdZp1s7lJ4DHFvXdVZLtGxLnzxySiaeEAA_oa2WC2UdIMbg30Iy4L7C7LodcCmz_0dfgl263VDu0gUUHbaZ2gvHybCr3J4eGufDxu6jAJcUts1Vb2oVU3jND.hYb7YVL_xYnHYu8ZCfQTXcmdYNIzdXieQ8oyQ7b_at6w1LqTkKY_2e5lYaN5OlmFSD3If99q5OnU; _ga_0XM0LYXGC8=GS2.1.s1758539747$o69$g1$t1758563603$j60$l0$h0",
            "host": "gmgn.ai",
            "origin": "https://gmgn.ai",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 OPR/122.0.0.0 (Edition Yx 08)"
        }

    async def connect(self):
        """Подключение к WebSocket"""
        try:
            self.logger.info(f"🔗 Подключаемся к: {self.url}")

            # Добавляем обработку ошибок SSL
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            self.websocket = await websockets.connect(
                self.url,
                extra_headers=self.headers,
                ping_interval=None,
                ping_timeout=None,
                ssl=ssl_context
            )
            self.logger.info("✅ WebSocket соединение установлено")
            self.running = True
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к WebSocket: {e}")
            return False

    async def listen_for_messages(self):
        """Слушаем входящие сообщения"""
        while self.running:
            try:
                message = await self.websocket.recv()
                await self.process_message(message)
            except websockets.exceptions.ConnectionClosedOK:
                self.logger.info("🔌 WebSocket соединение закрыто (нормально)")
                self.running = False
            except Exception as e:
                self.logger.error(f"❌ Ошибка при прослушивании сообщения: {e}")
                self.running = False # Останавливаем, чтобы попробовать переподключиться в main

    async def process_message(self, message):
        """Обрабатываем входящее сообщение"""
        try:
            if isinstance(message, str):
                self.logger.info(f"📨 Получено текстовое сообщение: {message}")
                # Дополнительная логика обработки текстовых сообщений
                # Например, если сообщения в JSON формате:
                # data = json.loads(message)
                # print(f"Parsed JSON: {data}")
            elif isinstance(message, bytes):
                self.logger.info(f"📨 Получено бинарное сообщение: {len(message)} байт")
                # Дополнительная логика обработки бинарных сообщений
                # Например, если используется msgpack:
                # import msgpack
                # data = msgpack.unpackb(message, raw=False)
                # print(f"Parsed MessagePack: {data}")
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки сообщения: {e}")

async def main():
    """Главная функция для запуска клиента"""
    client = GmgnWebSocketClient()
    if await client.connect():
        await client.listen_for_messages()
    else:
        logger.error("Не удалось подключиться к WebSocket.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем (Ctrl+C).")
