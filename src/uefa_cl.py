from __future__ import annotations

import json
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")
PARIS = ZoneInfo("Europe/Paris")

FIXTURES_URL = "https://www.uefa.com/uefachampionsleague/fixtures-results/"
QUALIFYING_URL = "https://www.uefa.com/uefachampionsleague/accesslist/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


def _get(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=35)
        if r.ok:
            return r.text
        print(f"UEFA: HTTP {r.status_code} for {url}")
    except requests.RequestException as exc:
        print(f"UEFA-feil: {exc}")
    return ""


def _norm_team(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _pick_team(obj) -> str | None:
    if isinstance(obj, str):
        return obj.strip() or None
    if not isinstance(obj, dict):
        return None
    for key in ("internationalName", "name", "displayName", "clubName", "teamName"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _parse_dt(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()

    # ISO datetime.
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=PARIS)
        return dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    except Exception:
        pass

    return None


def _match_from_dict(d: dict) -> dict | None:
    home = None
    away = None

    for key in ("homeTeam", "home", "team1", "homeClub"):
        if key in d:
            home = _pick_team(d.get(key))
            if home:
                break

    for key in ("awayTeam", "away", "team2", "awayClub"):
        if key in d:
            away = _pick_team(d.get(key))
            if away:
                break

    if not home or not away:
        return None

    kickoff = None
    for key in (
        "kickOffTime", "kickoffTime", "kickoff", "dateTime",
        "matchDate", "scheduledAt", "utcDate"
    ):
        kickoff = _parse_dt(d.get(key))
        if kickoff:
            break

    if not kickoff:
        # Sometimes date + time are separate.
        date_value = d.get("date") or d.get("matchDay")
        time_value = d.get("time") or d.get("kickOff")
        if isinstance(date_value, str) and isinstance(time_value, str):
            try:
                dt = datetime.fromisoformat(
                    f"{date_value[:10]}T{time_value[:5]}:00"
                ).replace(tzinfo=PARIS)
                kickoff = dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
            except Exception:
                pass

    if not kickoff:
        return None

    # Keep only Champions League records if competition info exists.
    blob = json.dumps(d, ensure_ascii=False).lower()
    if any(x in blob for x in ("europa league", "conference league", "women")):
        return None

    return {
        "competition": "UEFA Champions League",
        "kickoff": kickoff,
        "home": home,
        "away": away,
        "broadcasts": {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []},
        "source": "UEFA",
    }


def _walk_json(obj, out: list[dict]) -> None:
    if isinstance(obj, dict):
        m = _match_from_dict(obj)
        if m:
            out.append(m)
        for v in obj.values():
            _walk_json(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_json(v, out)


def _from_embedded_json(html: str) -> list[dict]:
    out = []
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script"):
        text = script.string or script.get_text("", strip=True)
        if not text:
            continue

        candidates = []
        stype = (script.get("type") or "").lower()

        if "json" in stype:
            candidates.append(text)
        else:
            # Common embedded JSON assignments.
            for marker in ("__NEXT_DATA__", "__APOLLO_STATE__", "__INITIAL_STATE__"):
                if marker in text:
                    start = text.find("{")
                    end = text.rfind("}")
                    if start >= 0 and end > start:
                        candidates.append(text[start:end + 1])

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except Exception:
                continue
            _walk_json(data, out)

    return out


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _from_visible_qualifying_text(html: str) -> list[dict]:
    """
    Fallback for UEFA's qualifying article. It handles blocks like:
      Tuesday 18 August
      Team A vs Team B (20:00)
    UEFA says qualifying kick-off times are CET/central European time;
    Europe/Paris handles the August daylight-saving offset correctly.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]

    out = []
    current_date = None
    in_playoff = False

    date_re = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
        r"(\d{1,2})\s+([A-Za-z]+)$",
        re.I,
    )
    match_re = re.compile(
        r"^(.+?)\s+(?:vs|v)\s+(.+?)\s+\((\d{1,2}):(\d{2})\)\s*$",
        re.I,
    )

    for line in lines:
        low = line.lower()

        if "play-off round" in low or "playoff round" in low:
            in_playoff = True
            continue

        # Do not wander into league-phase text after the qualifying section.
        if in_playoff and "league phase draw" in low:
            break

        dm = date_re.match(line)
        if dm:
            day = int(dm.group(2))
            month = MONTHS.get(dm.group(3).lower())
            if month:
                current_date = date(2026, month, day)
            continue

        if not current_date:
            continue

        mm = match_re.match(line)
        if not mm:
            continue

        home, away = mm.group(1).strip(), mm.group(2).strip()
        hour, minute = int(mm.group(3)), int(mm.group(4))
        dt = datetime(
            current_date.year, current_date.month, current_date.day,
            hour, minute, tzinfo=PARIS
        )
        out.append({
            "competition": "UEFA Champions League",
            "kickoff": dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
            "home": home,
            "away": away,
            "broadcasts": {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []},
            "source": "UEFA",
        })

    return out


def get_uefa_matches(date_from: date, date_to: date) -> list[dict]:
    matches = []

    html = _get(FIXTURES_URL)
    if html:
        matches.extend(_from_embedded_json(html))

    qhtml = _get(QUALIFYING_URL)
    if qhtml:
        matches.extend(_from_embedded_json(qhtml))
        matches.extend(_from_visible_qualifying_text(qhtml))

    seen = set()
    result = []

    for m in matches:
        try:
            dt = datetime.fromisoformat(
                m["kickoff"].replace("Z", "+00:00")
            ).astimezone(OSLO)
        except Exception:
            continue

        if not (date_from <= dt.date() <= date_to):
            continue

        key = (
            dt.date().isoformat(),
            _norm_team(m["home"]),
            _norm_team(m["away"]),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(m)

    result.sort(key=lambda x: x["kickoff"])
    print(f"UEFA fallback: fant {len(result)} CL-kamp(er) i perioden.")
    return result
