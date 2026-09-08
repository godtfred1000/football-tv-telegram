from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")
BASE = "https://www.livesoccertv.com"

# Common name variants between football-data.org / TheSportsDB / LiveSoccerTV.
TEAM_ALIASES = {
    "club brugge": ["club brugge", "brugge"],
    "aston villa": ["aston villa"],
    "pae aek": ["aek athens", "aek"],
    "aek": ["aek athens", "aek"],
    "lask linz": ["lask linz", "lask"],
    "real madrid": ["real madrid"],
    "internazionale milano": ["inter milan", "internazionale", "inter"],
    "internazionale": ["inter milan", "internazionale", "inter"],
    "borussia dortmund": ["borussia dortmund", "dortmund"],
    "villarreal": ["villarreal"],
    "lille osc": ["lille", "lille osc"],
    "lille": ["lille", "lille osc"],
    "real betis balompie": ["real betis", "betis"],
    "real betis": ["real betis", "betis"],
    "porto": ["porto", "fc porto"],
    "manchester city": ["manchester city", "man city"],
}

KNOWN_CHANNELS = [
    # Nordics
    "Viaplay Norway", "Viaplay Norge", "Viaplay Sweden", "Viaplay Sverige",
    "Viaplay Denmark", "Viaplay Danmark", "TV 2 Play", "TV2 Play",
    "TV 2 Sport", "TV2 Sport", "V Sport Extra", "V Sport Ultra HD",
    "V Sport", "V Sport 1", "V Sport 2", "V Sport Premium",
    "Viaplay Sport News", "TV3+", "TV3 Sport",
    # Australia
    "Stan Sport", "Stan", "Optus Sport",
    # UK
    "Sky Sports Premier League", "Sky Sports Main Event", "Sky Sports Football",
    "Sky Sports Action", "Sky Go UK", "Sky Go", "SKY GO Extra", "NOW",
    "TNT Sports 1", "TNT Sports 2", "TNT Sports", "TNT Sports Ultimate",
    "Amazon Prime Video", "Prime Video", "HBO Max", "BBC One", "BBC Two",
    "BBC iPlayer", "ITV 1 UK", "ITVX",
]


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _clean_team(name: str) -> str:
    value = _ascii(name).lower().replace("&", " and ")
    value = re.sub(r"\b(football club|fc|afc|cf|fk|sk|sc|kv)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _aliases(name: str) -> list[str]:
    clean = _clean_team(name)
    result = [clean]
    for alias in TEAM_ALIASES.get(clean, []):
        alias_clean = _clean_team(alias)
        if alias_clean and alias_clean not in result:
            result.append(alias_clean)
    # Useful shorter fallback for names with 2+ meaningful words.
    words = [w for w in clean.split() if len(w) > 2]
    if len(words) >= 2:
        short = " ".join(words[-2:])
        if short not in result:
            result.append(short)
    return result


def _contains_alias(text: str, team: str) -> bool:
    hay = f" {_clean_team(text)} "
    for alias in _aliases(team):
        if len(alias) < 3:
            continue
        if f" {alias} " in hay or alias.replace(" ", "") in hay.replace(" ", ""):
            return True
    return False


def _same_match(text: str, home: str, away: str) -> bool:
    return _contains_alias(text, home) and _contains_alias(text, away)


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
    result: list[str] = []

    # Match containers from the daily schedule page.
    for tag in soup.find_all(["tr", "li", "div", "article", "section"]):
        text = tag.get_text(" ", strip=True)
        if 20 <= len(text) <= 2200 and _same_match(text, home, away):
            result.append(text)

    # Also search the full page around every known alias. This catches layouts
    # where teams and broadcasters are split across neighbouring elements.
    full = soup.get_text(" ", strip=True)
    full_clean = _clean_team(full)
    for team in (home, away):
        for alias in _aliases(team):
            idx = full_clean.find(alias)
            if idx < 0:
                continue
            # Indices in cleaned/full text are not identical, so use a generous
            # full-page window by locating the raw alias where possible.
            raw_idx = _ascii(full).lower().find(alias)
            if raw_idx < 0:
                raw_idx = max(0, min(len(full) - 1, idx))
            start = max(0, raw_idx - 600)
            end = min(len(full), raw_idx + 2200)
            window = full[start:end]
            if _same_match(window, home, away):
                result.append(window)

    return sorted(set(result), key=len)


def _classify_channel(name: str, text: str = "") -> set[str]:
    n = name.lower()
    context = text.lower()
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
        "sky sports", "sky go", "now", "tnt sports", "bbc", "itv",
        "prime video", "amazon prime", "hbo max"
    ]):
        result.add("UK")

    # Some Nordic channels are shown without the country in the channel name.
    # Use nearby country labels from the schedule text when available.
    if not result and ("v sport" in n or "viaplay sport" in n or "tv3" in n):
        if "sweden" in context or "sverige" in context:
            result.add("SE")
        if "denmark" in context or "danmark" in context:
            result.add("DK")
        if "norway" in context or "norge" in context:
            result.add("NO")

    return result


def _extract(texts: list[str]) -> dict[str, list[str]]:
    out = {"NO": [], "SE": [], "DK": [], "AU": [], "UK": []}

    for text in texts:
        low = text.lower()
        for channel in KNOWN_CHANNELS:
            if channel.lower() not in low:
                continue
            for code in _classify_channel(channel, text):
                if channel not in out[code]:
                    out[code].append(channel)

        for m in re.findall(
            r"Viaplay\s+(Norway|Norge|Sweden|Sverige|Denmark|Danmark)",
            text,
            flags=re.IGNORECASE,
        ):
            channel = f"Viaplay {m}"
            for code in _classify_channel(channel, text):
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

    # Daily schedule pages are country-independent and work for Champions League
    # clubs from any nation. Avoid /teams/england/... URLs for non-English clubs.
    for url in [
        f"{BASE}/schedules/{date_iso}/",
        f"{BASE}/es/schedules/{date_iso}/",
    ]:
        html = _request(url)
        if html:
            candidates = _candidate_texts(html, home, away)
            if candidates:
                merged = _merge(merged, _extract(candidates))

    found = sum(len(v) for v in merged.values())
    if found:
        print(
            f"LiveSoccerTV: {home} – {away}: "
            + ", ".join(f"{k}={len(v)}" for k, v in merged.items())
        )
    else:
        print(f"LiveSoccerTV: ingen TV-data funnet for {home} – {away} på {date_iso}")

    return merged
