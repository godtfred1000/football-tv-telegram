from __future__ import annotations

import requests


class TelegramError(RuntimeError):
    pass


def send_message(bot_token: str, channel: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": channel,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok or not data.get("ok"):
        description = data.get("description") or response.text[:300]
        raise TelegramError(
            f"Telegram-feil {response.status_code}: {description}"
        )
