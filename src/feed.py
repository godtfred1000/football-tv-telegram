from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .config import FOOTBALL_DATA_API_TOKEN
from .tv_livesoccertv import get_broadcasts

OSLO = ZoneInfo("Europe/Oslo")
FD_BASE = "https://api.football-data.org/v4"

COMPETITIONS = {
    "PL": "Premier League",
    "CL": "UEFA Champions League",
}


class FeedError(RuntimeError):
    pass


def _football_data_get(path: str, params: dict | None = None) -> dict:
    if not FOOTBALL_DATA_API_TOKEN:
        raise FeedError("FOOTBALL_DATA_API_TOKEN mangler i GitHub Secrets.")

    r = requests.get(
        f"{FD_BASE}{path}",
        headers={"X-Auth-Token": FOOTBALL_DATA_API_TOKEN},
        params=params or {},
        timeout=30,
    )

    try:
        data = r.json()
    except ValueError:
        data = {}

    if r.status_code == 401:
        raise FeedError("football-data.org avviste API-tokenet (401).")
    if r.status_code == 403:
        raise FeedError("football-data.org ga 403.")
    if r.status_code == 429:
        raise FeedError("football-data.org rate limit er nådd (429).")
    if not r.ok:
        raise FeedError(
            f"football-data.org-feil {r.status_code}: "
            f"{data.get('message') or r.text[:300]}"
        )

    return data


def _clean_uk_channels(channels: list[str]) -> list[str]:
    normalized = []

    # If any Sky access product appears, show the main brand only.
    if any(
        any(token in ch.lower() for token in ["sky sports", "sky go", "now"])
        for ch in channels
    ):
        normalized.append("Sky Sports")

    # Keep TNT Sports as broadcaster brand.
    if any("tnt sports" in ch.lower() for ch in channels):
        normalized.append("TNT Sports")

    # Prime Video is its own broadcaster/platform.
    if any(
        any(token in ch.lower() for token in ["prime video", "amazon prime"])
        for ch in channels
    ):
        normalized.append("Prime Video")

    # BBC / ITV can appear for specific cup or free-to-air coverage.
    if any("bbc" in ch.lower() for ch in channels):
        normalized.append("BBC")
    if any("itv" in ch.lower() for ch in channels):
        normalized.append("ITV")

    return normalized


def _apply_premier_league_rights(broadcasts: dict[str, list[str]]) -> dict[str, list[str]]:
    # Official Premier League territory rights for 2025/26-2027/28.
    # Viaplay holds Norway, Sweden and Denmark; Stan Sport holds Australia.
    broadcasts["NO"] = ["Viaplay"]
    broadcasts["SE"] = ["Viaplay"]
    broadcasts["DK"] = ["Viaplay"]
    broadcasts["AU"] = ["Stan Sport"]

    # UK is still match-by-match, so only clean whatever LiveSoccerTV found.
    broadcasts["UK"] = _clean_uk_channels(broadcasts.get("UK") or [])

    return broadcasts


def _load_competition_matches(
    competition_code: str,
    competition_name: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    data = _football_data_get(
        f"/competitions/{competition_code}/matches",
        {
            "dateFrom": date_from,
            "dateTo": date_to,
            "status": "SCHEDULED,TIMED",
        },
    )

    rows = []
    for match in data.get("matches") or []:
        home = (match.get("homeTeam") or {}).get("name") or "Hjemmelag"
        away = (match.get("awayTeam") or {}).get("name") or "Bortelag"
        kickoff = match.get("utcDate")
        if not kickoff:
            continue

        broadcasts = get_broadcasts(home, away, kickoff)

        if competition_code == "PL":
            broadcasts = _apply_premier_league_rights(broadcasts)

        rows.append({
            "competition": competition_name,
            "kickoff": kickoff,
            "home": home,
            "away": away,
            "broadcasts": broadcasts,
            "football_data_match_id": match.get("id"),
        })

        time.sleep(0.4)

    return rows


def load_football_data_feed(days: int = 1) -> dict:
    start = datetime.now(OSLO).date()
    end = start + timedelta(days=max(days, 1) - 1)

    matches = []
    for code, name in COMPETITIONS.items():
        matches.extend(
            _load_competition_matches(
                code,
                name,
                start.isoformat(),
                end.isoformat(),
            )
        )

    matches.sort(key=lambda m: m["kickoff"])
    return {"matches": matches}


def load_feed(demo: bool = False, days: int = 1) -> dict:
    if demo:
        return json.loads(
            Path("data/demo_matches.json").read_text(encoding="utf-8")
        )
    return load_football_data_feed(days=days)
