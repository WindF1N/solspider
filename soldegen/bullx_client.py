import asyncio
import httpx
import pandas as pd
from tqdm.asyncio import tqdm_asyncio

# Данные для аутентификации на BullX.
HEADERS = { 'accept': 'application/json, text/plain, */*', 'content-type': 'application/json', 'origin': 'https://neo.bullx.io', 'referer': 'https://neo.bullx.io/' }
COOKIES = { 'bullx-session-token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiIweDg1NmUzMTUyZjZiNDIxM2UxYTYyMGRiMmY4MjEyODg0OGNkOWUzOWMiLCJpczJGQVZhbGlkYXRlZCI6dHJ1ZSwic2Vzc2lvbklkIjoiSlBpbmk5Z2R0MmtQVmRpN0lmZndlIiwic3Vic2NyaXB0aW9uUGxhbiI6IkJBU0lDIiwiaGFzaCI6ImU0Y2E2YzJjMTk2MGE1ODIxMDY0YzU2YzBkYmEwMjYzZmZhODM4ZDRjZWZkMGJkYWY3ZGNhOGVmZTQ0NzIzMTMiLCJoYXNoMiI6WyJlNGNhNmMyYzE5NjBhNTgyMTA2NGM1NmMwZGJhMDI2M2ZmYTgzOGQ0Y2VmZDBiZGFmN2RjYThlZmU0NDcyMzEzIl0sImlhdCI6MTc1Mzc4ODEzNiwiZXhwIjoxMDM0ODEyNzUyNzZ9.X1V4fS_mgUi0UEoFDqvk8KWGFCu0IYD5IcIyaRb1MtU', }
CHART_URL = "https://api-neo.bullx.io/v2/chartV3"
TOKEN_INFO_URL = "https://api-neo.bullx.io/v2/token/sol/{}"

class PriceHistoryFetcher:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0, limits=httpx.Limits(max_connections=20))

    async def _discover_one_launch(self, contract: str):
        try:
            response = await self.client.get(TOKEN_INFO_URL.format(contract), headers=HEADERS, cookies=COOKIES)
            if response.status_code == 200:
                data = response.json()
                if data and 'createTimestamp' in data:
                    return contract, data['createTimestamp']
        except Exception:
            return contract, None
        return contract, None

    async def discover_launch_times(self, tokens: list):
        tasks = [self._discover_one_launch(token) for token in tokens]
        results = await tqdm_asyncio.gather(*tasks, desc="Определение времени запуска токенов")
        return {contract: ts for contract, ts in results if ts is not None}

    async def _fetch_one_precise(self, contract: str, start_timestamp: int):
        from_ts = int(start_timestamp)
        to_ts = from_ts + (12 * 3600)
        payload = {"name": "chart", "data": {"chainId": 1399811149, "base": contract, "quote": "So11111111111111111111111111111111111111112", "from": from_ts, "to": to_ts, "intervalSecs": 1}}
        try:
            response = await self.client.post(CHART_URL, json=payload, headers=HEADERS, cookies=COOKIES)
            response.raise_for_status()
            raw_data = response.json()
            if not raw_data or 't' not in raw_data or not raw_data['t']: return contract, None
            df = pd.DataFrame({'timestamp': pd.to_datetime(raw_data['t'], unit='ms', utc=True), 'price': raw_data['h']}).drop_duplicates('timestamp').set_index('timestamp')
            return contract, df[df.index >= pd.to_datetime(start_timestamp, unit='s', utc=True)]
        except Exception:
            return contract, None

    async def fetch_all_precise(self, tokens_with_start_time: dict):
        tasks = [self._fetch_one_precise(token, start_ts) for token, start_ts in tokens_with_start_time.items()]
        results = await tqdm_asyncio.gather(*tasks, desc="Загрузка точных графиков с BullX")
        return {contract: data for contract, data in results if data is not None and not data.empty}

    async def close(self):
        await self.client.aclose()