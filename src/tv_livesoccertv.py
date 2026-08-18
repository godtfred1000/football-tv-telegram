from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")

# LiveSoccerTV lists legal broadcasters/streaming services. We only extract
# broadcaster names; we do not use or redistribute streams.
BASE = "https://www.livesoccertv.com"

COUNTRY_RULES = {
    "NO": [
        r"\bviaplay norway\b", r"\bviaplay norge\b", r"\btv ?2 play\b",
        r"\btv ?2 sport\b", r"\bv sport\b", r"\bvsport\b",
    ],
    "SE": [
        r"\bviaplay sweden\b", r"\bviaplay sverige\b",
        r"\bv sport\b", r"\bvsport\b",
    ],
    "DK": [
        r"\bviaplay denmark\b", r"\bviaplay danmark\b",
        r"\btv3\+?\b", r"\btv ?3 sport\b",
    ],
    "AU": [
        r"\bstan sport\b", r"\bstan\b", r"\boptus sport\b",
    ],
    "UK": [
        r"\bsky sports\b", r"\bsky go\b", r"\bsky go uk\b",
        r"\bsky go extra\b", r"\bnow\b", r"\btnt sports\b",
        r"\bamzn prime\b", r"\bamazon prime\b", r"\bbbc\b",
        r"\bitv\b", r"\bitvx\b",
    ],
}

GENERIC_SPLIT = re.compile(r"\s{2,}|\s*[|•]\s*")


def _norm_team(name: str) -> str:
    value = (name or "").lower()
    for token in [" football club", " fc", " afc", " cf"]:
        value = value.replace(token, "")
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _same_match(text: str, home: str, away: str) -> bool:
    t = _norm_team(text)
    h = _norm_team(home)
    a = _norm_team(away)
    return h in t and a in t


def _candidate_row_texts(html: str, home: str, away: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # Look through compact containers first; this tends to pick a single match row.
    for tag in soup.find_all(["tr", "li", "div", "article"]):
        text = tag.get_text(" ", strip=True)
        if len(text) > 900:
            continue
        if _same_match(text, home, away):
            candidates.append(text)

    # Fallback: page text around the match.
    if not candidates:
        text = soup.get_text(" ", strip=True)
        h = _norm_team(home)
        a = _norm_team(away)
        normalized = _norm_team(text)
        if h in normalized and a in normalized:
            candidates.append(text)

    # Shortest text is usually the most precise match row.
    return sorted(set(candidates), key=len)


def _extract_channels(row_text: str, home: str, away: str) -> dict[str, list[str]]:
    result = {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []}

    # Known broadcaster names are matched directly from the row text.
    known = [
        "Viaplay Norway", "Viaplay Norge", "TV 2 Play", "TV2 Play",
        "TV 2 Sport", "V Sport", "Viaplay Sweden", "Viaplay Sverige",
        "Viaplay Denmark", "Viaplay Danmark", "TV3+", "TV3 Sport",
        "Stan Sport", "Stan", "Optus Sport",
        "Sky Sports Premier League", "Sky Sports Main Event",
        "Sky Sports Football", "Sky Go UK", "Sky Go", "SKY GO Extra",
        "NOW", "TNT Sports 1", "TNT Sports 2", "TNT Sports",
        "Amazon Prime Video", "Prime Video", "BBC One", "BBC Two",
        "BBC iPlayer", "ITV 1 UK", "ITVX",
    ]

    lower = row_text.lower()
    found = []
    for name in known:
        if name.lower() in lower and name not in found:
            found.append(name)

    # Also catch explicit country-labelled Viaplay variants not in list.
    for match in re.findall(
        r"(Viaplay\s+(?:Norway|Norge|Sweden|Sverige|Denmark|Danmark))",
        row_text,
        flags=re.IGNORECASE,
    ):
        pretty = match.strip()
        if pretty not in found:
            found.append(pretty)

    for channel in found:
        cl = channel.lower()
        for code, patterns in COUNTRY_RULES.items():
            if any(re.search(p, cl, flags=re.IGNORECASE) for p in patterns):
                # Avoid assigning generic V Sport to all Nordics unless country is explicit.
                if cl in {"v sport", "vsport"} and code in {"NO", "SE"}:
                    continue
                if channel not in result[code]:
                    result[code].append(channel)

    return result


def get_broadcasts(home: str, away: str, kickoff_iso: str) -> dict[str, list[str]]:
    empty = {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []}

    try:
        dt = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).astimezone(OSLO)
    except Exception:
        return empty

    date_iso = dt.date().isoformat()
    url = f"{BASE}/schedules/{date_iso}/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; FootballTVGuideBot/1.0; "
            "+https://github.com/godtfred1000/football-tv-telegram)"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        if not r.ok:
            print(f"LiveSoccerTV: HTTP {r.status_code} for {date_iso}")
            return empty

        candidates = _candidate_row_texts(r.text, home, away)
        if not candidates:
            print(f"LiveSoccerTV: fant ikke {home} – {away} på {date_iso}")
            return empty

        # Try the smallest few candidate containers and merge broadcaster results.
        merged = empty
        for text in candidates[:5]:
            current = _extract_channels(text, home, away)
            for code in merged:
                for channel in current[code]:
                    if channel not in merged[code]:
                        merged[code].append(channel)

        return merged

    except requests.RequestException as exc:
        print(f"LiveSoccerTV-feil: {exc}")
        return empty
