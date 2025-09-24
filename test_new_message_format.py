#!/usr/bin/env python3
"""
Тестовый скрипт для демонстрации нового формата сообщений
"""

from datetime import datetime

def generate_test_message(token_name="TestCoin", token_address="ABC123...XYZ789", wallet_count=30, total_volume=2500):
    """Генерирует тестовое сообщение в новом формате"""

    message = (
        f"<b>памп монеты от топов</b>\n\n"
        f"<b>{token_name}</b>\n"
        f"<code>{token_address}</code>\n\n"
        f"топ трейдеров зашло: {wallet_count}\n"
        f"топы вложили: ${total_volume:,.0f} баксов\n\n"
        f"<i><a href='https://axiom.trade/t/{token_address}'>axiom</a></i> | "
        f"<i><a href='https://dexscreener.com/solana/{token_address}'>dexscreener</a></i>\n\n"
        f"<i>🚀 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')} © <b>by Wormster</b></i>"
    )

    return message

if __name__ == "__main__":
    print("🎯 ПРИМЕР НОВОГО ФОРМАТА СООБЩЕНИЙ:")
    print("=" * 60)

    test_message = generate_test_message()
    print(test_message)

    print("\n" + "=" * 60)
    print("✅ Это будет отправлено в Telegram при обнаружении скопления!")
