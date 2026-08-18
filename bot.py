from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import BOT_TOKEN, CHANNEL
from src.feed import load_feed
from src.formatter import build_message
from src.telegram import send_message

OSLO = ZoneInfo("Europe/Oslo")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--days", type=int, default=1)
    return parser.parse_args()


def main():
    args = parse_args()

    if args.scheduled and datetime.now(OSLO).hour != 9:
        print("Ikke 09:xx i Europe/Oslo – hopper over denne cron-kjøringen.")
        return

    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN mangler.")
    if not CHANNEL:
        raise RuntimeError("TELEGRAM_CHANNEL mangler.")

    feed = load_feed(demo=args.demo, days=args.days)
    matches = feed.get("matches") or []

    if not matches:
        if args.days > 1:
            print(f"Ingen Champions League- eller Premier League-kamper de neste {args.days} dagene.")
        else:
            print("Ingen Champions League- eller Premier League-kamper i dag.")
        return

    message = build_message(feed, demo=args.demo)
    send_message(BOT_TOKEN, CHANNEL, message)
    print(f"Sendte {len(matches)} kamp(er) til Telegram.")


if __name__ == "__main__":
    main()
