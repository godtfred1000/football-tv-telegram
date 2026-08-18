from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .config import FOOTBALL_DATA_API_TOKEN, THESPORTSDB_API_KEY

OSLO = ZoneInfo("Europe/Oslo")

FD_BASE = "https://api.football-data.org/v4"
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json"

COMPETITIONS = {
    "PL": "Premier League",
    "CL": "UEFA Champions League",
}

COUNTRY_MAP = {
    "norway": "NO",
    "norge": "NO",
    "sweden": "SE",
    "sverige": "SE",
    "denmark": "DK",
    "danmark": "DK",
    "australia": "AU",
    "united kingdom": "UK",
    "uk": "UK",
    "england": "UK",
    "great britain": "UK",
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

    if r.status_code == 401:
        raise FeedError("football-data.org avviste API-tokenet (401).")
    if r.status_code == 403:
        raise FeedError("football-data.org ga 403. Sjekk at Free-planen har tilgang til konkurransen.")
    if r.status_code == 429:
        raise FeedError("football-data.org rate limit er nådd (429).")

    try:
        data = r.json()
    except ValueError:
        data = {}

    if not r.ok:
        raise FeedError(
            f"football-data.org-feil {r.status_code}: "
            f"{data.get('message') or r.text[:300]}"
        )

    return data


def _tsdb_get(endpoint: str, params: dict | None = None) -> dict:
    r = requests.get(
        f"{TSDB_BASE}/{THESPORTSDB_API_KEY}/{endpoint}",
        params=params or {},
        timeout=25,
    )
    if not r.ok:
        raise FeedError(f"TheSportsDB-feil {r.status_code}: {r.text[:250]}")
    try:
        return r.json()
    except ValueError:
        return {}


def _clean_team_name(name: str) -> str:
    value = (name or "").strip()

    replacements = [
        (r"\bFC\b", ""),
        (r"\bAFC\b", ""),
        (r"\bCF\b", ""),
        (r"\bAC\b", ""),
        (r"\bSC\b", ""),
        (r"\bFK\b", ""),
    ]
    for pattern, repl in replacements:
        value = re.sub(pattern, repl, value, flags=re.IGNORECASE)

    value = re.sub(r"\s+", " ", value).strip()
    return value


def _slug(value: str) -> str:
    value = _clean_team_name(value)
    value = value.replace("&", "and")
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s-]+", "_", value).strip("_")
    return value


def _norm(value: str) -> str:
    value = _clean_team_name(value).lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def _event_matches_teams(event: dict, home: str, away: str) -> bool:
    event_name = event.get("strEvent") or ""
    if "_vs_" in event_name:
        left, right = event_name.split("_vs_", 1)
    elif " vs " in event_name.lower():
        parts = re.split(r"\s+vs\s+", event_name, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            return False
        left, right = parts
    else:
        left = event.get("strHomeTeam") or ""
        right = event.get("strAwayTeam") or ""

    h = _norm(home)
    a = _norm(away)
    l = _norm(left)
    r = _norm(right)

    return (h == l and a == r) or (h == r and a == l)


def _find_tsdb_event_id(home: str, away: str, date_iso: str) -> str | None:
    query = f"{_slug(home)}_vs_{_slug(away)}"
    data = _tsdb_get(
        "searchevents.php",
        {"e": query, "d": date_iso},
    )
    events = data.get("event") or data.get("events") or []

    for event in events:
        if _event_matches_teams(event, home, away):
            return str(event.get("idEvent") or "") or None

    # Noen kilder bruker motsatt rekkefølge i eventnavnet.
    query = f"{_slug(away)}_vs_{_slug(home)}"
    data = _tsdb_get(
        "searchevents.php",
        {"e": query, "d": date_iso},
    )
    events = data.get("event") or data.get("events") or []

    for event in events:
        if _event_matches_teams(event, home, away):
            return str(event.get("idEvent") or "") or None

    return None


def _broadcasts_from_tsdb(event_id: str | None) -> dict[str, list[str]]:
    result = {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []}

    if not event_id:
        return result

    data = _tsdb_get("lookuptv.php", {"id": event_id})
    rows = data.get("tvevent") or []

    for row in rows:
        country = str(row.get("strCountry") or "").strip().lower()
        channel = str(row.get("strChannel") or "").strip()

        code = COUNTRY_MAP.get(country)
        if not code or not channel:
            continue

        if channel not in result[code]:
            result[code].append(channel)

    return result


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

        oslo_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).astimezone(OSLO)
        date_iso = oslo_dt.date().isoformat()

        event_id = _find_tsdb_event_id(home, away, date_iso)
        broadcasts = _broadcasts_from_tsdb(event_id)

        rows.append(
            {
                "competition": competition_name,
                "kickoff": kickoff,
                "home": home,
                "away": away,
                "broadcasts": broadcasts,
                "football_data_match_id": match.get("id"),
                "thesportsdb_event_id": event_id,
            }
        )

        # Hold oss godt under gratisgrensene.
        time.sleep(0.15)

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
