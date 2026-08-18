from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

PL_FIXTURES_URL = "https://www.premierleague.com/en/news/4675097"


def _clean(name: str) -> str:
    value = (name or "").lower().replace("&", " and ")

    for token in ("football club", "fc", "afc", "cf"):
        value = re.sub(rf"\b{token}\b", " ", value)

    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    aliases = {
        "bournemouth": {"bournemouth", "afc bournemouth"},
        "brighton and hove albion": {"brighton", "brighton and hove albion"},
        "manchester city": {"man city", "manchester city"},
        "manchester united": {"man utd", "manchester united"},
        "nottingham forest": {"nottm forest", "nottingham forest"},
        "tottenham hotspur": {"tottenham", "spurs", "tottenham hotspur"},
        "newcastle united": {"newcastle", "newcastle united"},
        "ipswich town": {"ipswich", "ipswich town"},
        "hull city": {"hull", "hull city"},
        "coventry city": {"coventry", "coventry city"},
    }

    return value


def _variants(name: str) -> set[str]:
    base = _clean(name)

    mapping = {
        "bournemouth": {"bournemouth", "afc bournemouth"},
        "brighton and hove albion": {"brighton", "brighton and hove albion"},
        "manchester city": {"man city", "manchester city"},
        "manchester united": {"man utd", "manchester united"},
        "nottingham forest": {"nottm forest", "nottingham forest"},
        "tottenham hotspur": {"tottenham", "spurs", "tottenham hotspur"},
        "newcastle united": {"newcastle", "newcastle united"},
        "ipswich town": {"ipswich", "ipswich town"},
        "hull city": {"hull", "hull city"},
        "coventry city": {"coventry", "coventry city"},
    }

    return mapping.get(base, {base})


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

        return [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if line.strip()
        ]

    except requests.RequestException as exc:
        print(f"PremierLeague UK TV-feil: {exc}")
        return []


def _fixture_is_on_line(line: str, home: str, away: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", line.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    home_ok = any(v in normalized for v in _variants(home))
    away_ok = any(v in normalized for v in _variants(away))

    return home_ok and away_ok


def official_uk_broadcaster(home: str, away: str, kickoff_iso: str) -> list[str]:
    """
    UK broadcaster must be printed on the SAME Premier League fixture line.

    Example:
      12:30 Hull City v Manchester United (TNT Sports)
      Nottingham Forest v Leeds United
      17:30 Brentford v Tottenham Hotspur (Sky Sports)

    This deliberately never looks at the previous/next fixture line, preventing
    Sky/TNT labels from leaking onto ordinary Saturday 15:00 matches.
    """
    for line in _fetch_lines():
        if not _fixture_is_on_line(line, home, away):
            continue

        low = line.lower()

        if "tnt sports" in low:
            return ["TNT Sports"]

        if "sky sports" in low:
            return ["Sky Sports"]

        return []

    return []
