from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import BOT_TOKEN, CHANNEL
from src.feed import load_feed
from src.formatter import format_daily_message, matches_for_day
from src.telegram_client import send_message

OSLO = ZoneInfo("Europe/Oslo")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Bruk demo-kamper")
    parser.add_argument("--print-only", action="store_true", help="Skriv meldingen uten å sende")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Kjør bare når klokken er 09 i Europe/Oslo (brukes av GitHub Actions)",
    )
    args = parser.parse_args()

    now = datetime.now(OSLO)
    if args.scheduled and now.hour != 9:
        print(f"Ikke 09:xx i Norge ({now:%H:%M}). Hopper over.")
        return

    feed = load_feed(demo=args.demo)
    matches = matches_for_day(feed)
    text = format_daily_message(matches, demo=args.demo)

    if not text:
        print("Ingen Champions League- eller Premier League-kamper i dag.")
        return

    if args.print_only:
        print(text)
        return

    send_message(BOT_TOKEN, CHANNEL, text)
    print(f"Sendt {len(matches)} kamp(er) til {CHANNEL}.")


if __name__ == "__main__":
    main()
