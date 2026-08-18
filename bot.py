from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.config import BOT_TOKEN, CHANNEL
from src.feed import load_feed
from src.formatter import format_daily_message, matches_for_day
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

    start_day = datetime.now(OSLO).date()
    sent_days = 0
    sent_matches = 0

    for offset in range(max(args.days, 1)):
        day = start_day + timedelta(days=offset)
        matches = matches_for_day(feed, day=day)

        if not matches:
            continue

        message = format_daily_message(matches, demo=args.demo)
        if not message:
            continue

        send_message(BOT_TOKEN, CHANNEL, message)
        sent_days += 1
        sent_matches += len(matches)

    if sent_matches == 0:
        if args.days > 1:
            print(
                f"Ingen Champions League- eller Premier League-kamper "
                f"de neste {args.days} dagene."
            )
        else:
            print("Ingen Champions League- eller Premier League-kamper i dag.")
        return

    print(
        f"Sendte {sent_matches} kamp(er) fordelt på "
        f"{sent_days} dag(er) til Telegram."
    )


if __name__ == "__main__":
    main()
