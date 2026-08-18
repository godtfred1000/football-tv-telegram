from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OSLO = ZoneInfo("Europe/Oslo")
PARIS = ZoneInfo("Europe/Paris")

URL = "https://www.uefa.com/uefachampionsleague/accesslist/"

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

MATCH_RE = re.compile(
    r"^(.+?)\s+(?:vs|v)\s+(.+?)\s+"
    r"\((\d{1,2}):(\d{2})(?:\s+or\s+\d{1,2}:\d{2})?\)$",
    re.I,
)


def _lines() -> list[str]:
    try:
        # Shorter timeouts so UEFA can never hold the whole workflow for long.
        r = requests.get(
            URL,
            headers=HEADERS,
            timeout=(8, 12),
        )

        if not r.ok:
            print(f"UEFA fallback: HTTP {r.status_code} – hopper over UEFA.")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        return [
            re.sub(r"\s+", " ", x).strip()
            for x in soup.get_text("\n", strip=True).splitlines()
            if x.strip()
        ]

    except requests.Timeout:
        print("UEFA fallback: timeout – hopper over UEFA denne kjøringen.")
        return []

    except requests.RequestException as exc:
        print(f"UEFA fallback: nettverksfeil ({exc}) – hopper over UEFA.")
        return []

    except Exception as exc:
        # UEFA must never be allowed to crash the complete Telegram workflow.
        print(f"UEFA fallback: uventet feil ({exc}) – hopper over UEFA.")
        return []


def _norm(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def get_uefa_matches(date_from: date, date_to: date) -> list[dict]:
    try:
        lines = _lines()
        if not lines:
            return []

        current = None
        in_playoff = False
        out = []

        for line in lines:
            low = line.lower()

            if low in {"play-off round", "playoff round"}:
                in_playoff = True
                continue

            if not in_playoff:
                continue

            if low.startswith("league phase draw"):
                break

            dm = DATE_RE.match(line)
            if dm:
                month = MONTHS.get(dm.group(3).lower())
                if month:
                    current = date(2026, month, int(dm.group(2)))
                continue

            if current is None:
                continue

            mm = MATCH_RE.match(line)
            if not mm:
                continue

            home = mm.group(1).strip()
            away = mm.group(2).strip()
            hour = int(mm.group(3))
            minute = int(mm.group(4))

            local = datetime(
                current.year,
                current.month,
                current.day,
                hour,
                minute,
                tzinfo=PARIS,
            )

            kickoff = (
                local.astimezone(ZoneInfo("UTC"))
                .isoformat()
                .replace("+00:00", "Z")
            )

            oslo_day = (
                datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                .astimezone(OSLO)
                .date()
            )

            if date_from <= oslo_day <= date_to:
                out.append({
                    "competition": "UEFA Champions League",
                    "kickoff": kickoff,
                    "home": home,
                    "away": away,
                    "broadcasts": {
                        "NO": [],
                        "SE": [],
                        "DK": [],
                        "AU": [],
                        "UK": [],
                    },
                    "source": "UEFA",
                })

        seen = set()
        result = []

        for m in out:
            key = (
                m["kickoff"][:10],
                _norm(m["home"]),
                _norm(m["away"]),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(m)

        result.sort(key=lambda x: x["kickoff"])
        print(f"UEFA fallback: fant {len(result)} CL play-off-kamp(er).")
        return result

    except Exception as exc:
        # Final safety net: never fail the full Action because UEFA parsing failed.
        print(f"UEFA fallback: parserfeil ({exc}) – fortsetter uten UEFA.")
        return []
