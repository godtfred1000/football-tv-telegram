from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .config import FEED_URL, SPORTMONKS_API_TOKEN

OSLO = ZoneInfo("Europe/Oslo")
UTC = ZoneInfo("UTC")
BASE = "https://api.sportmonks.com/v3/football"

ALIASES = {
    "NO": {"NO", "NOR", "NORWAY", "NORG"},
    "SE": {"SE", "SWE", "SWEDEN", "SVERIGE"},
    "DK": {"DK", "DNK", "DENMARK", "DANMARK"},
    "AU": {"AU", "AUS", "AUSTRALIA"},
    "UK": {
        "GB", "GBR", "UK", "UNITED KINGDOM", "GREAT BRITAIN",
        "ENGLAND", "SCOTLAND", "WALES", "NORTHERN IRELAND"
    },
}


class SportMonksError(RuntimeError):
    pass


def _get(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=30)

    try:
        data = r.json()
    except ValueError:
        data = {}

    if r.status_code == 401:
        raise SportMonksError("SportMonks avviste API-tokenet (401).")
    if r.status_code == 403:
        raise SportMonksError(
            "SportMonks ga 403. Planen din har trolig ikke tilgang til "
            "denne ligaen eller TV-dataene."
        )
    if r.status_code == 429:
        raise SportMonksError("SportMonks rate limit er nådd (429).")

    if not r.ok:
        raise SportMonksError(
            f"SportMonks-feil {r.status_code}: "
            f"{data.get('message') or r.text[:300]}"
        )

    return data


def _all_pages(url: str, params: dict) -> list[dict]:
    rows = []
    page = 1

    while True:
        p = dict(params)
        p["page"] = page
        data = _get(url, p)
        rows.extend(data.get("data") or [])

        pagination = data.get("pagination") or {}
        if not pagination.get("has_more"):
            break

        page += 1
        if page > 10:
            break

    return rows


def _competition(name: str) -> str | None:
    n = (name or "").lower().strip()

    if "champions league" in n and "women" not in n and "youth" not in n:
        return "UEFA Champions League"

    if "premier league" in n and "women" not in n:
        return "Premier League"

    return None


def _teams(fixture: dict) -> tuple[str, str]:
    participants = fixture.get("participants") or []

    home = None
    away = None
    unknown = []

    for team in participants:
        name = team.get("name") or "Ukjent lag"
        meta = team.get("meta") or {}
        side = str(meta.get("location") or meta.get("position") or "").lower()

        if side in {"home", "local"}:
            home = name
        elif side in {"away", "visitor"}:
            away = name
        else:
            unknown.append(name)

    if home is None and unknown:
        home = unknown.pop(0)

    if away is None and unknown:
        away = unknown.pop(0)

    if home and away:
        return home, away

    fixture_name = fixture.get("name") or ""
    if " vs " in fixture_name:
        left, right = fixture_name.split(" vs ", 1)
        return left.strip(), right.strip()

    return home or "Hjemmelag", away or "Bortelag"


def _kickoff(fixture: dict) -> str:
    raw = str(fixture.get("starting_at") or "").replace("Z", "+00:00")

    if not raw:
        raise SportMonksError("En kamp mangler starting_at.")

    dt = datetime.fromisoformat(raw)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(UTC).isoformat()


def _country_tokens(country: dict) -> set[str]:
    out = set()

    for key in ("name", "iso2", "iso3", "iso_code", "code"):
        value = country.get(key)
        if value:
            out.add(str(value).upper().strip())

    return out


def _station_country_codes(station: dict) -> set[str]:
    countries = station.get("countries") or []

    if isinstance(countries, dict):
        countries = countries.get("data") or []

    tokens = set()

    for country in countries:
        if isinstance(country, dict):
            tokens |= _country_tokens(country)

    result = set()

    for code, aliases in ALIASES.items():
        if tokens & aliases:
            result.add(code)

    return result


def _tv_stations_for_fixture(fixture_id: int) -> list[dict]:
    url = f"{BASE}/tv-stations/fixtures/{fixture_id}"

    return _all_pages(
        url,
        {
            "api_token": SPORTMONKS_API_TOKEN,
            "include": "countries",
            "per_page": 100,
        },
    )


def _broadcasts_for_fixture(fixture_id: int) -> dict[str, list[str]]:
    result = {
        "NO": [],
        "SE": [],
        "DK": [],
        "AU": [],
        "UK": [],
    }

    stations = _tv_stations_for_fixture(fixture_id)

    for station in stations:
        if not isinstance(station, dict):
            continue

        name = station.get("name")
        if not name:
            continue

        for code in _station_country_codes(station):
            if name not in result[code]:
                result[code].append(name)

    return result


def load_sportmonks_feed() -> dict:
    if not SPORTMONKS_API_TOKEN:
        raise SportMonksError(
            "SPORTMONKS_API_TOKEN mangler i GitHub Secrets."
        )

    today = datetime.now(OSLO).date().isoformat()

    fixtures = _all_pages(
        f"{BASE}/fixtures/date/{today}",
        {
            "api_token": SPORTMONKS_API_TOKEN,
            "include": "participants;league",
            "per_page": 50,
            "order": "asc",
        },
    )

    matches = []

    for fixture in fixtures:
        league_name = (fixture.get("league") or {}).get("name") or ""
        competition = _competition(league_name)

        if not competition:
            continue

        fixture_id = fixture.get("id")
        if not fixture_id:
            continue

        home, away = _teams(fixture)

        matches.append({
            "competition": competition,
            "kickoff": _kickoff(fixture),
            "home": home,
            "away": away,
            "broadcasts": _broadcasts_for_fixture(fixture_id),
            "sportmonks_fixture_id": fixture_id,
        })

    return {"matches": matches}


def load_feed(demo: bool = False) -> dict:
    if demo:
        return json.loads(
            Path("data/demo_matches.json").read_text(encoding="utf-8")
        )

    if FEED_URL:
        r = requests.get(FEED_URL, timeout=25)
        r.raise_for_status()
        return r.json()

    return load_sportmonks_feed()
