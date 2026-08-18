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
    "NO": {"NO","NOR","NORWAY","NORG"},
    "SE": {"SE","SWE","SWEDEN","SVERIGE"},
    "DK": {"DK","DNK","DENMARK","DANMARK"},
    "AU": {"AU","AUS","AUSTRALIA"},
    "UK": {"GB","GBR","UK","UNITED KINGDOM","GREAT BRITAIN","ENGLAND","SCOTLAND","WALES","NORTHERN IRELAND"},
}

class SportMonksError(RuntimeError):
    pass

def _get(url, params):
    r = requests.get(url, params=params, timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code == 401:
        raise SportMonksError("SportMonks avviste API-tokenet (401).")
    if r.status_code == 403:
        raise SportMonksError("SportMonks ga 403. Planen din har trolig ikke tilgang til ligaen eller TV-dataene.")
    if r.status_code == 429:
        raise SportMonksError("SportMonks rate limit er nådd (429).")
    if not r.ok:
        raise SportMonksError(f"SportMonks-feil {r.status_code}: {data.get('message') or r.text[:300]}")
    return data

def _all_pages(url, params):
    rows, page = [], 1
    while True:
        p = dict(params)
        p["page"] = page
        data = _get(url, p)
        rows.extend(data.get("data") or [])
        if not (data.get("pagination") or {}).get("has_more"):
            break
        page += 1
        if page > 10:
            break
    return rows

def _competition(name):
    n = (name or "").lower()
    if "champions league" in n and "women" not in n and "youth" not in n:
        return "UEFA Champions League"
    if "premier league" in n and "women" not in n:
        return "Premier League"
    return None

def _teams(f):
    parts = f.get("participants") or []
    home = away = None
    rest = []
    for t in parts:
        name = t.get("name") or "Ukjent lag"
        meta = t.get("meta") or {}
        side = str(meta.get("location") or meta.get("position") or "").lower()
        if side in {"home","local"}:
            home = name
        elif side in {"away","visitor"}:
            away = name
        else:
            rest.append(name)
    if home is None and rest: home = rest.pop(0)
    if away is None and rest: away = rest.pop(0)
    if home and away:
        return home, away
    name = f.get("name") or ""
    if " vs " in name:
        a,b = name.split(" vs ",1)
        return a.strip(), b.strip()
    return home or "Hjemmelag", away or "Bortelag"

def _kickoff(f):
    raw = str(f.get("starting_at") or "").replace("Z","+00:00")
    if not raw:
        raise SportMonksError("En kamp mangler starting_at.")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()

def _country_tokens(c):
    out = set()
    for k in ("name","iso2","iso3","iso_code","code"):
        if c.get(k):
            out.add(str(c[k]).upper().strip())
    return out

def _station_codes(station):
    countries = station.get("countries") or []
    if isinstance(countries, dict):
        countries = countries.get("data") or []
    tokens = set()
    for c in countries:
        if isinstance(c, dict):
            tokens |= _country_tokens(c)
    result = set()
    for code, aliases in ALIASES.items():
        if tokens & aliases:
            result.add(code)
    return result

def _broadcasts(f):
    result = {"NO":[],"SE":[],"DK":[],"AU":[],"UK":[]}
    stations = f.get("tv_stations") or f.get("tvStations") or []
    if isinstance(stations, dict):
        stations = stations.get("data") or []
    for s in stations:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        for code in _station_codes(s):
            if s["name"] not in result[code]:
                result[code].append(s["name"])
    return result

def load_sportmonks_feed():
    if not SPORTMONKS_API_TOKEN:
        raise SportMonksError("SPORTMONKS_API_TOKEN mangler i GitHub Secrets.")

    today = datetime.now(OSLO).date().isoformat()
    fixtures = _all_pages(
        f"{BASE}/fixtures/date/{today}",
        {
            "api_token": SPORTMONKS_API_TOKEN,
            "include": "participants;league;tvStations.countries",
            "per_page": 50,
            "order": "asc",
        },
    )

    matches = []
    for f in fixtures:
        league = (f.get("league") or {}).get("name") or ""
        comp = _competition(league)
        if not comp:
            continue
        home, away = _teams(f)
        matches.append({
            "competition": comp,
            "kickoff": _kickoff(f),
            "home": home,
            "away": away,
            "broadcasts": _broadcasts(f),
            "sportmonks_fixture_id": f.get("id"),
        })
    return {"matches": matches}

def load_feed(demo=False):
    if demo:
        return json.loads(Path("data/demo_matches.json").read_text(encoding="utf-8"))
    if FEED_URL:
        r = requests.get(FEED_URL, timeout=25)
        r.raise_for_status()
        return r.json()
    return load_sportmonks_feed()
