from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .config import FOOTBALL_DATA_API_TOKEN
from .tv_livesoccertv import get_broadcasts
from .tv_uk import official_uk_broadcaster

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


def _apply_premier_league_rights(
    home: str,
    away: str,
    kickoff: str,
    broadcasts: dict[str, list[str]],
) -> dict[str, list[str]]:
    # Territory-wide Premier League rights.
    broadcasts["NO"] = ["Viaplay"]
    broadcasts["SE"] = ["Viaplay"]
    broadcasts["DK"] = ["Viaplay"]
    broadcasts["AU"] = ["Stan Sport"]

    # UK must ONLY use the official Premier League/Sky/TNT fixture selection.
    # If official_uk_broadcaster returns [], the match is not selected for live UK TV.
    # Do NOT fall back to LiveSoccerTV for UK, because that can pick up generic
    # Sky Go/NOW text from nearby fixtures and falsely mark 15:00 matches as Sky.
    broadcasts["UK"] = official_uk_broadcaster(home, away, kickoff)

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
            broadcasts = _apply_premier_league_rights(
                home, away, kickoff, broadcasts
            )

        rows.append({
            "competition": competition_name,
            "kickoff": kickoff,
            "home": home,
            "away": away,
            "broadcasts": broadcasts,
            "football_data_match_id": match.get("id"),
        })

        time.sleep(0.35)

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
