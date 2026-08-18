from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")

SKY_URL = "https://www.skysports.com/watch/football-on-sky/competitions/premier-league"
TNT_URL = (
    "https://www.tntsports.co.uk/football/premier-league/2026-2027/"
    "hbo-max-schedule-how-watch-tv-live-stream-which-matches_sto23282553/story.shtml"
)


def _norm_team(name: str) -> str:
    value = (name or "").lower()
    value = value.replace("&", " and ")
    aliases = {
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
    for token in [" football club", " fc", " afc", " cf"]:
        value = re.sub(rf"\b{re.escape(token.strip())}\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return aliases.get(value, value)


def _match_in_text(text: str, home: str, away: str, day: datetime) -> bool:
    t = text.lower()
    h = _norm_team(home)
    a = _norm_team(away)

    variants = {
        h,
        h.replace("man utd", "manchester united"),
        h.replace("man city", "manchester city"),
        h.replace("nottm forest", "nottingham forest"),
        a,
        a.replace("man utd", "manchester united"),
        a.replace("man city", "manchester city"),
        a.replace("nottm forest", "nottingham forest"),
    }

    # Require both teams somewhere in the candidate block.
    home_ok = any(v and v in t for v in list(variants)[:3])
    away_ok = any(v and v in t for v in list(variants)[3:])
    if not (home_ok and away_ok):
        return False

    # Date is a useful extra guard when present.
    date_variants = {
        day.strftime("%d/%m/%Y").lstrip("0"),
        day.strftime("%d/%m/%Y"),
        day.strftime("%d %B").lower().lstrip("0"),
        day.strftime("%A, %B %d").lower(),
        day.strftime("%A %d %B").lower().lstrip("0"),
    }
    return any(d in t for d in date_variants) or True


def _get(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.ok:
            return r.text
        print(f"UK TV: HTTP {r.status_code} for {url}")
    except requests.RequestException as exc:
        print(f"UK TV-feil: {exc}")
    return ""


def _sky_match(home: str, away: str, kickoff_iso: str) -> bool:
    html = _get(SKY_URL)
    if not html:
        return False

    soup = BeautifulSoup(html, "html.parser")
    day = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).astimezone(OSLO)

    # Search compact containers first.
    for tag in soup.find_all(["li", "div", "article", "tr", "section"]):
        text = tag.get_text(" ", strip=True)
        if len(text) > 1200:
            continue
        if _match_in_text(text, home, away, day) and "sky sports" in text.lower():
            return True

    # Fallback: whole page around both team names.
    text = soup.get_text(" ", strip=True).lower()
    h = _norm_team(home)
    a = _norm_team(away)
    hi = text.find(h)
    ai = text.find(a)
    if hi >= 0 and ai >= 0 and abs(hi - ai) < 700:
        start = max(0, min(hi, ai) - 300)
        end = min(len(text), max(hi, ai) + 700)
        return "sky sports" in text[start:end]

    return False


def _tnt_match(home: str, away: str, kickoff_iso: str) -> bool:
    html = _get(TNT_URL)
    if not html:
        return False

    soup = BeautifulSoup(html, "html.parser")
    day = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).astimezone(OSLO)

    for tag in soup.find_all(["tr", "li", "div", "article", "p"]):
        text = tag.get_text(" ", strip=True)
        if len(text) > 1400:
            continue
        if _match_in_text(text, home, away, day):
            # The dedicated TNT schedule article is itself authoritative.
            return True

    text = soup.get_text(" ", strip=True).lower()
    h = _norm_team(home)
    a = _norm_team(away)
    hi = text.find(h)
    ai = text.find(a)
    return hi >= 0 and ai >= 0 and abs(hi - ai) < 600


def official_uk_broadcaster(home: str, away: str, kickoff_iso: str) -> list[str]:
    # TNT first because a generic Sky page may mention teams elsewhere on-page.
    if _tnt_match(home, away, kickoff_iso):
        return ["TNT Sports"]

    if _sky_match(home, away, kickoff_iso):
        return ["Sky Sports"]

    return []
