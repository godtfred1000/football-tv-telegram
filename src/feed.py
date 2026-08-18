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
from .thesportsdb_cl import get_thesportsdb_cl_matches

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


def _norm_team(value: str) -> str:
    import re

    value = (value or "").lower().replace("&", " and ")
    value = re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return re.sub(r"\s+", " ", value).strip()


def _load_competition_matches(
    competition_code: str,
    competition_name: str,
    date_from: str,
    date_to: str,
) -> list[dict]:

    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
    }

    if competition_code == "PL":
        params["status"] = "SCHEDULED,TIMED"

    data = _football_data_get(
        f"/competitions/{competition_code}/matches",
        params,
    )

    rows = []

    for match in data.get("matches") or []:
        status = str(match.get("status") or "").upper()

        if status in {"CANCELLED", "POSTPONED"}:
            continue

        home = (match.get("homeTeam") or {}).get("name") or "Hjemmelag"
        away = (match.get("awayTeam") or {}).get("name") or "Bortelag"
        kickoff = match.get("utcDate")

        if not kickoff:
            continue

        broadcasts = get_broadcasts(home, away, kickoff)

        if competition_code == "PL":
            broadcasts["NO"] = ["Viaplay"]
            broadcasts["SE"] = ["Viaplay"]
            broadcasts["DK"] = ["Viaplay"]
            broadcasts["AU"] = ["Stan Sport"]
            broadcasts["UK"] = official_uk_broadcaster(
                home,
                away,
                kickoff,
            )

        rows.append({
            "competition": competition_name,
            "kickoff": kickoff,
            "home": home,
            "away": away,
            "broadcasts": broadcasts,
            "football_data_match_id": match.get("id"),
            "source": "football-data.org",
        })

        time.sleep(0.30)

    return rows


def _merge_cl_fallback(
    existing: list[dict],
    start,
    end,
) -> list[dict]:

    extra = get_thesportsdb_cl_matches(start, end)

    keys = set()

    for m in existing:
        try:
            d = datetime.fromisoformat(
                m["kickoff"].replace("Z", "+00:00")
            ).astimezone(OSLO).date().isoformat()
        except Exception:
            continue

        keys.add((
            d,
            _norm_team(m["home"]),
            _norm_team(m["away"]),
        ))

    for m in extra:
        try:
            d = datetime.fromisoformat(
                m["kickoff"].replace("Z", "+00:00")
            ).astimezone(OSLO).date().isoformat()
        except Exception:
            continue

        key = (
            d,
            _norm_team(m["home"]),
            _norm_team(m["away"]),
        )

        if key in keys:
            continue

        # Try TV data, but do not let it prevent the CL match from appearing.
        try:
            m["broadcasts"] = get_broadcasts(
                m["home"],
                m["away"],
                m["kickoff"],
            )
        except Exception as exc:
            print(
                "TV-oppslag feilet for TheSportsDB-kamp "
                f"{m['home']} – {m['away']}: {exc}"
            )

        existing.append(m)
        keys.add(key)

        time.sleep(0.20)

    return existing


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

    # TheSportsDB fills Champions League qualifying/play-off fixtures
    # that football-data.org does not return.
    matches = _merge_cl_fallback(
        matches,
        start,
        end,
    )

    matches.sort(key=lambda m: m["kickoff"])

    return {
        "matches": matches,
    }


def load_feed(
    demo: bool = False,
    days: int = 1,
) -> dict:

    if demo:
        return json.loads(
            Path("data/demo_matches.json").read_text(
                encoding="utf-8",
            )
        )

    return load_football_data_feed(days=days)
