
import httpx
import json

def get_contract_transactions(contract_address):
    url = f"https://gmgn.ai/vas/api/v1/token_trades/sol/{contract_address}"

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "priority": "u=1, i",
        "referer": f"https://gmgn.ai/sol/token/{contract_address}",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Opera";v="122"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 OPR/122.0.0.0 (Edition Yx 08)"
    }

    params = {
        "device_id": "eeb8dafa-3383-469c-9eff-0d8e7f91772b",
        "fp_did": "d77855ac6b24fee27da1ac79e7aaf072",
        "client_id": "gmgn_web_20250915-3852-aaf4123",
        "from_app": "gmgn",
        "app_ver": "20250915-3852-aaf4123",
        "tz_name": "Europe/Moscow",
        "tz_offset": "10800",
        "app_lang": "ru",
        "os": "web",
        "limit": "50",
        "maker": ""
    }

    try:
        response = httpx.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except httpx.RequestError as e:
        print(f"Error fetching data: {e}")
        return None

if __name__ == "__main__":
    contract_address = "7dSBYv1kXuB1h25crC69BviHVVqjBXw8gRnLnCM9pump"  # Replace with the actual contract address
    transactions = get_contract_transactions(contract_address)

    if transactions:
        print(json.dumps(transactions, indent=4))
