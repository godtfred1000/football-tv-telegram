from __future__ import annotations

import requests


class TelegramError(RuntimeError):
    pass


def send_message(token: str, channel: str, text: str) -> dict:
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN mangler.")
    if not channel:
        raise TelegramError("TELEGRAM_CHANNEL mangler.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": channel,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=25,
    )
    data = response.json()
    if not response.ok or not data.get("ok"):
        raise TelegramError(f"Telegram-feil: {data}")
    return data
