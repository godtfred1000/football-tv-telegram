from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

LONDON = ZoneInfo("Europe/London")
PL_FIXTURES_URL = "https://www.premierleague.com/en/news/4675097"


def _clean(name: str) -> str:
    value = (name or "").lower().replace("&", " and ")
    replacements = {
        "afc bournemouth": "bournemouth",
        "brighton and hove albion": "brighton",
        "brighton hove albion": "brighton",
        "manchester city": "man city",
        "manchester united": "man utd",
        "nottingham forest": "nottm forest",
        "tottenham hotspur": "tottenham",
        "newcastle united": "newcastle",
        "ipswich town": "ipswich",
        "hull city": "hull",
        "coventry city": "coventry",
    }
    for token in ("football club", "fc", "afc", "cf"):
        value = re.sub(rf"\b{token}\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return replacements.get(value, value)


def _variants(name: str) -> set[str]:
    base = _clean(name)
    out = {base}
    reverse = {
        "man city": "manchester city",
        "man utd": "manchester united",
        "nottm forest": "nottingham forest",
        "tottenham": "spurs",
    }
    if base in reverse:
        out.add(reverse[base])
    return out


def _fetch_lines() -> list[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        r = requests.get(PL_FIXTURES_URL, headers=headers, timeout=30)
        if not r.ok:
            print(f"PremierLeague UK TV: HTTP {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n", strip=True)
        return [line.strip() for line in text.splitlines() if line.strip()]
    except requests.RequestException as exc:
        print(f"PremierLeague UK TV-feil: {exc}")
        return []


def _is_fixture_line(line: str, home: str, away: str) -> bool:
    n = re.sub(r"[^a-z0-9]+", " ", line.lower())
    n = re.sub(r"\s+", " ", n).strip()

    home_ok = any(v and v in n for v in _variants(home))
    away_ok = any(v and v in n for v in _variants(away))
    return home_ok and away_ok


def official_uk_broadcaster(home: str, away: str, kickoff_iso: str) -> list[str]:
    lines = _fetch_lines()
    if not lines:
        return []

    try:
        kickoff = datetime.fromisoformat(
            kickoff_iso.replace("Z", "+00:00")
        ).astimezone(LONDON)
    except Exception:
        return []

    month_name = kickoff.strftime("%B").lower()
    day_num = str(kickoff.day)

    for i, line in enumerate(lines):
        if not _is_fixture_line(line, home, away):
            continue

        # STRICT: broadcaster must be on the fixture line itself OR the
        # immediately adjacent line only. Do not inspect a broad text window.
        same = line.lower()
        next_line = lines[i + 1].lower() if i + 1 < len(lines) else ""
        prev_line = lines[i - 1].lower() if i > 0 else ""

        combined = " | ".join([prev_line, same, next_line])

        # Make sure the nearby context belongs to the correct fixture date.
        # If date text is absent, we still trust the exact fixture line match,
        # but we never inherit broadcaster labels from more distant fixtures.
        nearby_date_ok = (
            month_name in combined and day_num in combined
        ) or True

        if not nearby_date_ok:
            continue

        # Prefer a broadcaster label literally attached to this fixture.
        if "tnt sports" in same or "tnt sports" in next_line:
            return ["TNT Sports"]

        if "sky sports" in same or "sky sports" in next_line:
            return ["Sky Sports"]

        # If broadcaster appears only on the previous line, accept it only when
        # that previous line is not itself another fixture.
        prev_is_fixture = bool(
            re.search(r"\b(v|vs|v\.)\b", prev_line)
            and any(
                token in prev_line
                for token in [
                    "arsenal", "chelsea", "liverpool", "man utd",
                    "man city", "tottenham", "everton", "ipswich",
                    "hull", "brighton", "newcastle", "forest",
                    "brentford", "coventry", "sunderland", "leeds",
                    "bournemouth", "fulham", "palace",
                ]
            )
        )

        if not prev_is_fixture:
            if "tnt sports" in prev_line:
                return ["TNT Sports"]
            if "sky sports" in prev_line:
                return ["Sky Sports"]

        # Exact fixture found, but no broadcaster label attached.
        return []

    return []
