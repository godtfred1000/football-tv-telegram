from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

OSLO = ZoneInfo("Europe/Oslo")
UTC = ZoneInfo("UTC")

API_BASE = "https://www.thesportsdb.com/api/v1/json/123"
UCL_LEAGUE_ID = "4480"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


def _norm_team(value: str) -> str:
    value = (value or "").lower().replace("&", " and ")
    value = re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _api_get(path: str, params: dict) -> dict:
    try:
        r = requests.get(
            f"{API_BASE}/{path}",
            params=params,
            headers=HEADERS,
            timeout=(8, 15),
        )

        if not r.ok:
            print(f"TheSportsDB: HTTP {r.status_code} for {path}")
            return {}

        return r.json()

    except requests.Timeout:
        print(f"TheSportsDB: timeout for {path}")
        return {}

    except (requests.RequestException, ValueError) as exc:
        print(f"TheSportsDB: feil for {path}: {exc}")
        return {}


def _event_to_match(event: dict) -> dict | None:
    home = (event.get("strHomeTeam") or "").strip()
    away = (event.get("strAwayTeam") or "").strip()

    if not home or not away:
        return None

    league_id = str(event.get("idLeague") or "")
    league_name = str(event.get("strLeague") or "").lower()

    if league_id and league_id != UCL_LEAGUE_ID:
        return None

    if league_name and "champions league" not in league_name:
        return None

    kickoff = None

    timestamp = event.get("strTimestamp")
    if timestamp:
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            kickoff = dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
        except Exception:
            kickoff = None

    if not kickoff:
        date_value = event.get("dateEvent") or event.get("dateEventLocal")
        time_value = event.get("strTime") or event.get("strTimeLocal") or "20:00:00"

        if not date_value:
            return None

        try:
            hhmm = str(time_value)[:5] if time_value else "20:00"
            dt = datetime.fromisoformat(f"{date_value}T{hhmm}:00").replace(tzinfo=UTC)
            kickoff = dt.isoformat().replace("+00:00", "Z")
        except Exception:
            return None

    return {
        "competition": "UEFA Champions League",
        "kickoff": kickoff,
        "home": home,
        "away": away,
        "broadcasts": {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []},
        "source": "TheSportsDB",
        "thesportsdb_event_id": event.get("idEvent"),
    }


def get_thesportsdb_cl_matches(date_from: date, date_to: date) -> list[dict]:
    matches = []
    day = date_from

    while day <= date_to:
        data = _api_get(
            "eventsday.php",
            {
                "d": day.isoformat(),
                "l": UCL_LEAGUE_ID,
            },
        )

        for event in data.get("events") or []:
            match = _event_to_match(event)
            if match:
                matches.append(match)

        day += timedelta(days=1)

    seen = set()
    result = []

    for m in matches:
        try:
            local_day = datetime.fromisoformat(
                m["kickoff"].replace("Z", "+00:00")
            ).astimezone(OSLO).date().isoformat()
        except Exception:
            local_day = m["kickoff"][:10]

        key = (
            local_day,
            _norm_team(m["home"]),
            _norm_team(m["away"]),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(m)

    result.sort(key=lambda m: m["kickoff"])

    print(
        f"TheSportsDB fallback: fant {len(result)} "
        "Champions League-kamp(er) i perioden."
    )

    return result
