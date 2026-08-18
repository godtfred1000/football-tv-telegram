from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")
BASE = "https://www.livesoccertv.com"

TEAM_SLUGS = {
    "arsenal": "arsenal",
    "aston villa": "aston-villa",
    "bournemouth": "bournemouth",
    "afc bournemouth": "bournemouth",
    "brentford": "brentford",
    "brighton hove albion": "brighton-hove-albion",
    "brighton and hove albion": "brighton-hove-albion",
    "burnley": "burnley",
    "chelsea": "chelsea",
    "coventry city": "coventry-city",
    "crystal palace": "crystal-palace",
    "everton": "everton",
    "fulham": "fulham",
    "hull city": "hull-city",
    "ipswich town": "ipswich-town",
    "leeds united": "leeds-united",
    "liverpool": "liverpool",
    "manchester city": "manchester-city",
    "manchester united": "manchester-united",
    "newcastle united": "newcastle-united",
    "nottingham forest": "nottingham-forest",
    "sunderland": "sunderland",
    "tottenham hotspur": "tottenham-hotspur",
    "west ham united": "west-ham-united",
    "wolverhampton wanderers": "wolverhampton-wanderers",
}

KNOWN_CHANNELS = [
    # Nordics
    "Viaplay Norway", "Viaplay Norge", "Viaplay Sweden", "Viaplay Sverige",
    "Viaplay Denmark", "Viaplay Danmark", "TV 2 Play", "TV2 Play",
    "TV 2 Sport", "TV2 Sport", "V Sport", "V Sport 1", "V Sport 2",
    "V Sport Premium", "TV3+", "TV3 Sport",
    # Australia
    "Stan Sport", "Stan", "Optus Sport",
    # UK
    "Sky Sports Premier League", "Sky Sports Main Event", "Sky Sports Football",
    "Sky Sports Action", "Sky Go UK", "Sky Go", "SKY GO Extra", "NOW",
    "TNT Sports 1", "TNT Sports 2", "TNT Sports", "TNT Sports Ultimate",
    "Amazon Prime Video", "Prime Video", "BBC One", "BBC Two", "BBC iPlayer",
    "ITV 1 UK", "ITVX",
]

def _clean_team(name: str) -> str:
    value = (name or "").lower()
    value = value.replace("&", " and ")
    for token in [" football club", " fc", " afc", " cf"]:
        value = re.sub(rf"\b{re.escape(token.strip())}\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _slug_for_team(name: str) -> str:
    clean = _clean_team(name)
    if clean in TEAM_SLUGS:
        return TEAM_SLUGS[clean]
    return clean.replace(" ", "-")

def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean_team(value))

def _same_match(text: str, home: str, away: str) -> bool:
    n = _norm(text)
    return _norm(home) in n and _norm(away) in n

def _request(url: str) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        if r.ok and len(r.text) > 1000:
            return r.text
        print(f"LiveSoccerTV: HTTP {r.status_code} for {url}")
    except requests.RequestException as exc:
        print(f"LiveSoccerTV-feil: {exc}")
    return None

def _candidate_texts(html: str, home: str, away: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    result = []

    for tag in soup.find_all(["tr", "li", "div", "article", "section"]):
        text = tag.get_text(" ", strip=True)
        if 20 <= len(text) <= 1400 and _same_match(text, home, away):
            result.append(text)

    # Also grab a text window around the match from the whole page.
    full = soup.get_text(" ", strip=True)
    low = full.lower()
    home_key = _clean_team(home)
    away_key = _clean_team(away)
    for key in (home_key, away_key):
        idx = low.find(key.lower())
        if idx >= 0:
            start = max(0, idx - 250)
            end = min(len(full), idx + 1100)
            window = full[start:end]
            if _same_match(window, home, away):
                result.append(window)

    return sorted(set(result), key=len)

def _classify_channel(name: str) -> set[str]:
    n = name.lower()
    result = set()

    if any(x in n for x in ["norway", "norge"]):
        result.add("NO")
    if any(x in n for x in ["sweden", "sverige"]):
        result.add("SE")
    if any(x in n for x in ["denmark", "danmark"]):
        result.add("DK")
    if any(x in n for x in ["stan sport", "optus sport"]):
        result.add("AU")
    if any(x in n for x in [
        "sky sports", "sky go", "sky go uk", "now",
        "tnt sports", "bbc", "itv", "prime video", "amazon prime"
    ]):
        result.add("UK")

    return result

def _extract(texts: list[str]) -> dict[str, list[str]]:
    out = {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []}

    for text in texts:
        low = text.lower()
        for channel in KNOWN_CHANNELS:
            if channel.lower() not in low:
                continue
            for code in _classify_channel(channel):
                if channel not in out[code]:
                    out[code].append(channel)

        # Catch country-labelled Viaplay names even if spelling varies.
        for m in re.findall(
            r"Viaplay\s+(Norway|Norge|Sweden|Sverige|Denmark|Danmark)",
            text,
            flags=re.IGNORECASE,
        ):
            channel = f"Viaplay {m}"
            for code in _classify_channel(channel):
                if channel not in out[code]:
                    out[code].append(channel)

    return out

def _merge(a: dict[str, list[str]], b: dict[str, list[str]]) -> dict[str, list[str]]:
    for code in a:
        for item in b.get(code, []):
            if item not in a[code]:
                a[code].append(item)
    return a

def get_broadcasts(home: str, away: str, kickoff_iso: str) -> dict[str, list[str]]:
    empty = {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []}

    try:
        dt = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).astimezone(OSLO)
    except Exception:
        return empty

    date_iso = dt.date().isoformat()
    merged = {k: [] for k in empty}

    # 1) Daily schedules page.
    for url in [
        f"{BASE}/schedules/{date_iso}/",
        f"{BASE}/es/schedules/{date_iso}/",
    ]:
        html = _request(url)
        if html:
            merged = _merge(merged, _extract(_candidate_texts(html, home, away)))

    # 2) Home team page.
    home_slug = _slug_for_team(home)
    html = _request(f"{BASE}/teams/england/{home_slug}/")
    if html:
        merged = _merge(merged, _extract(_candidate_texts(html, home, away)))

    # 3) Away team page if still incomplete.
    if not all(merged.values()):
        away_slug = _slug_for_team(away)
        html = _request(f"{BASE}/teams/england/{away_slug}/")
        if html:
            merged = _merge(merged, _extract(_candidate_texts(html, home, away)))

    found = sum(len(v) for v in merged.values())
    if found:
        print(
            f"LiveSoccerTV: {home} – {away}: "
            + ", ".join(f"{k}={len(v)}" for k, v in merged.items())
        )
    else:
        print(f"LiveSoccerTV: ingen TV-data funnet for {home} – {away} på {date_iso}")

    return merged
