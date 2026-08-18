from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

VIAPLAY_PL_URL = "https://viaplay.no/sport/fotball/premier-league"


def _norm(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    for token in [" football club", " fc", " afc", " cf"]:
        value = re.sub(rf"\b{re.escape(token.strip())}\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def premier_league_on_viaplay(home: str, away: str) -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
    }

    try:
        r = requests.get(VIAPLAY_PL_URL, headers=headers, timeout=30)
        if not r.ok:
            print(f"Viaplay Norge: HTTP {r.status_code}")
            return False

        soup = BeautifulSoup(r.text, "html.parser")
        text = _norm(soup.get_text(" ", strip=True))

        h = _norm(home)
        a = _norm(away)

        # The official Viaplay Premier League page exposes upcoming event names
        # in the page text. Require both teams to avoid false positives.
        return h in text and a in text

    except requests.RequestException as exc:
        print(f"Viaplay Norge-feil: {exc}")
        return False
