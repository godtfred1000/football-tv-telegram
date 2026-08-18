from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

LONDON = ZoneInfo("Europe/London")

# Official Premier League fixture article. TV-selected matches are shown with
# "(Sky Sports)" or "(TNT Sports)" beside the fixture.
PL_FIXTURES_URL = "https://www.premierleague.com/en/news/4675097"


def _norm_team(name: str) -> str:
    value = (name or "").lower().replace("&", " and ")

    aliases = {
        "afc bournemouth": "bournemouth",
        "brighton and hove albion": "brighton",
        "brighton hove albion": "brighton",
        "manchester city": "manchester city",
        "manchester united": "manchester united",
        "nottingham forest": "nottingham forest",
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
    return aliases.get(value, value)


def _fetch_text() -> str:
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
            return ""

        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text("\n", strip=True)

    except requests.RequestException as exc:
        print(f"PremierLeague UK TV-feil: {exc}")
        return ""


def _line_has_teams(line: str, home: str, away: str) -> bool:
    n = re.sub(r"[^a-z0-9]+", " ", line.lower())
    n = re.sub(r"\s+", " ", n).strip()

    h = _norm_team(home)
    a = _norm_team(away)

    home_variants = {h}
    away_variants = {a}

    # Common shortened names used by the Premier League.
    short = {
        "manchester city": "man city",
        "manchester united": "man utd",
        "nottingham forest": "nottm forest",
        "tottenham": "spurs",
    }
    if h in short:
        home_variants.add(short[h])
    if a in short:
        away_variants.add(short[a])

    return (
        any(v in n for v in home_variants if v)
        and any(v in n for v in away_variants if v)
    )


def official_uk_broadcaster(home: str, away: str, kickoff_iso: str) -> list[str]:
    text = _fetch_text()
    if not text:
        return []

    try:
        kickoff = datetime.fromisoformat(
            kickoff_iso.replace("Z", "+00:00")
        ).astimezone(LONDON)
    except Exception:
        return []

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Find an exact fixture line/window. We deliberately require broadcaster
    # text in the same small window so a TNT mention elsewhere on the page
    # cannot incorrectly mark every match as TNT/Sky.
    for i, line in enumerate(lines):
        if not _line_has_teams(line, home, away):
            continue

        window = " ".join(lines[max(0, i - 2): min(len(lines), i + 3)])
        wl = window.lower()

        # Guard against matching the wrong round/date if the same teams are
        # mentioned elsewhere in the article.
        day_tokens = {
            str(kickoff.day),
            kickoff.strftime("%d").lstrip("0"),
            kickoff.strftime("%B").lower(),
        }
        date_ok = (
            kickoff.strftime("%B").lower() in wl
            or kickoff.strftime("%d/%m/%Y").lower() in wl
            or kickoff.strftime("%Y").lower() in wl
        )

        if not date_ok:
            # The page often puts the date heading one or two lines above.
            wider = " ".join(lines[max(0, i - 5): min(len(lines), i + 3)]).lower()
            date_ok = (
                kickoff.strftime("%B").lower() in wider
                and str(kickoff.day) in wider
            )

        if not date_ok:
            continue

        if "tnt sports" in wl:
            return ["TNT Sports"]

        if "sky sports" in wl:
            return ["Sky Sports"]

        # No broadcaster label beside the fixture = not selected for live UK TV.
        return []

    return []
