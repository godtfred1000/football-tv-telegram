from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")
PARIS = ZoneInfo("Europe/Paris")

# UEFA qualifying/play-off article. This page lists the play-off fixtures
# by date and states that kick-off times are 21:00 CET unless otherwise shown.
QUALIFYING_URL = "https://www.uefa.com/uefachampionsleague/accesslist/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

DATE_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})\s+([A-Za-z]+)$",
    re.I,
)

# Handles:
#   Levski Sofia vs AEK Athens
#   Sabah vs Hapoel Beer-Sheva (18:45)
MATCH_RE = re.compile(
    r"^(.+?)\s+(?:vs|v)\s+(.+?)(?:\s+\((\d{1,2}):(\d{2})\))?$",
    re.I,
)


def _get_lines() -> list[str]:
    try:
        r = requests.get(QUALIFYING_URL, headers=HEADERS, timeout=35)
        if not r.ok:
            print(f"UEFA: HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n", strip=True)

        return [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if line.strip()
        ]

    except requests.RequestException as exc:
        print(f"UEFA-feil: {exc}")
        return []


def _norm_team(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _make_match(
    day: date,
    home: str,
    away: str,
    hour: int = 21,
    minute: int = 0,
) -> dict:
    # UEFA's article says 21:00 CET unless otherwise stated.
    # Using Europe/Paris correctly handles the actual local offset in August.
    local_dt = datetime(
        day.year,
        day.month,
        day.day,
        hour,
        minute,
        tzinfo=PARIS,
    )

    kickoff_utc = (
        local_dt.astimezone(ZoneInfo("UTC"))
        .isoformat()
        .replace("+00:00", "Z")
    )

    return {
        "competition": "UEFA Champions League",
        "kickoff": kickoff_utc,
        "home": home.strip(),
        "away": away.strip(),
        "broadcasts": {
            "NO": [],
            "SE": [],
            "DK": [],
            "AU": [],
            "UK": [],
        },
        "source": "UEFA",
    }


def get_uefa_matches(date_from: date, date_to: date) -> list[dict]:
    lines = _get_lines()
    if not lines:
        return []

    matches: list[dict] = []
    current_date: date | None = None

    # We only parse the explicit "Play-off fixtures" block.
    in_fixtures = False

    for line in lines:
        low = line.lower()

        if low == "play-off fixtures" or low == "playoff fixtures":
            in_fixtures = True
            continue

        if not in_fixtures:
            continue

        # Stop once the article leaves the fixture listing.
        if low.startswith("qualifying: fixtures") or low.startswith(
            "how does the play-off round work"
        ):
            break

        dm = DATE_RE.match(line)
        if dm:
            day_num = int(dm.group(2))
            month_num = MONTHS.get(dm.group(3).lower())
            if month_num:
                current_date = date(2026, month_num, day_num)
            continue

        if current_date is None:
            continue

        mm = MATCH_RE.match(line)
        if not mm:
            continue

        home = mm.group(1).strip()
        away = mm.group(2).strip()

        # Reject headings/paragraphs that happen to contain "vs".
        if len(home) > 60 or len(away) > 60:
            continue

        hour = int(mm.group(3)) if mm.group(3) else 21
        minute = int(mm.group(4)) if mm.group(4) else 0

        match = _make_match(
            current_date,
            home,
            away,
            hour,
            minute,
        )

        oslo_day = (
            datetime.fromisoformat(
                match["kickoff"].replace("Z", "+00:00")
            )
            .astimezone(OSLO)
            .date()
        )

        if date_from <= oslo_day <= date_to:
            matches.append(match)

    # De-duplicate.
    seen = set()
    result = []

    for m in matches:
        key = (
            m["kickoff"][:10],
            _norm_team(m["home"]),
            _norm_team(m["away"]),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(m)

    result.sort(key=lambda x: x["kickoff"])

    print(
        "UEFA fallback: "
        f"fant {len(result)} Champions League play-off-kamp(er)."
    )

    return result
