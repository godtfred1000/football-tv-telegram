from __future__ import annotations
import json, re, time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

from .config import FOOTBALL_DATA_API_TOKEN
from .tv_fotmob import get_fotmob_broadcasts
from .tv_livesoccertv import get_broadcasts as get_livesoccertv_broadcasts
from .tv_uk import official_uk_broadcaster
from .thesportsdb_cl import get_thesportsdb_cl_matches

OSLO=ZoneInfo("Europe/Oslo")
FD_BASE="https://api.football-data.org/v4"
COMPETITIONS={"PL":"Premier League","CL":"UEFA Champions League"}

class FeedError(RuntimeError): pass

def _football_data_get(path,params=None):
    if not FOOTBALL_DATA_API_TOKEN:
        raise FeedError("FOOTBALL_DATA_API_TOKEN mangler i GitHub Secrets.")
    r=requests.get(f"{FD_BASE}{path}",
        headers={"X-Auth-Token":FOOTBALL_DATA_API_TOKEN},
        params=params or {},timeout=30)
    try: data=r.json()
    except ValueError: data={}
    if r.status_code==401: raise FeedError("football-data.org avviste API-tokenet (401).")
    if r.status_code==403: raise FeedError("football-data.org ga 403.")
    if r.status_code==429: raise FeedError("football-data.org rate limit er nådd (429).")
    if not r.ok:
        raise FeedError(f"football-data.org-feil {r.status_code}: {data.get('message') or r.text[:300]}")
    return data

def _norm_team(v):
    v=(v or "").lower().replace("&"," and ")
    v=re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b"," ",v)
    v=re.sub(r"[^a-z0-9]+"," ",v)
    return re.sub(r"\s+"," ",v).strip()

def _has_tv(b):
    return any(bool(v) for v in b.values())

def _tv_for_cl(home,away,kickoff):
    try:
        b=get_fotmob_broadcasts(home,away,kickoff)
    except Exception as exc:
        print("FotMob TV-feil:",exc)
        b={"NO":[],"SE":[],"DK":[],"AU":[],"UK":[]}
    if _has_tv(b):
        return b
    try:
        print("FotMob fant ingen TV-data; prøver LiveSoccerTV fallback.")
        return get_livesoccertv_broadcasts(home,away,kickoff)
    except Exception as exc:
        print("LiveSoccerTV fallback-feil:",exc)
        return b

def _load_competition_matches(code,name,date_from,date_to):
    params={"dateFrom":date_from,"dateTo":date_to}
    if code=="PL": params["status"]="SCHEDULED,TIMED"
    data=_football_data_get(f"/competitions/{code}/matches",params)
    rows=[]
    for match in data.get("matches") or []:
        if str(match.get("status") or "").upper() in {"CANCELLED","POSTPONED"}:
            continue
        home=(match.get("homeTeam") or {}).get("name") or "Hjemmelag"
        away=(match.get("awayTeam") or {}).get("name") or "Bortelag"
        kickoff=match.get("utcDate")
        if not kickoff: continue
        if code=="PL":
            broadcasts={
                "NO":["Viaplay"],"SE":["Viaplay"],"DK":["Viaplay"],
                "AU":["Stan Sport"],"UK":official_uk_broadcaster(home,away,kickoff)
            }
        else:
            broadcasts=_tv_for_cl(home,away,kickoff)
        rows.append({
            "competition":name,"kickoff":kickoff,"home":home,"away":away,
            "broadcasts":broadcasts,"football_data_match_id":match.get("id"),
            "source":"football-data.org"
        })
        time.sleep(0.1)
    return rows

def _merge_cl_fallback(existing,start,end):
    extra=get_thesportsdb_cl_matches(start,end)
    keys=set()
    for m in existing:
        try:
            d=datetime.fromisoformat(m["kickoff"].replace("Z","+00:00")).astimezone(OSLO).date().isoformat()
        except Exception:
            continue
        keys.add((d,_norm_team(m["home"]),_norm_team(m["away"])))
    for m in extra:
        try:
            d=datetime.fromisoformat(m["kickoff"].replace("Z","+00:00")).astimezone(OSLO).date().isoformat()
        except Exception:
            continue
        key=(d,_norm_team(m["home"]),_norm_team(m["away"]))
        if key in keys: continue
        m["broadcasts"]=_tv_for_cl(m["home"],m["away"],m["kickoff"])
        existing.append(m); keys.add(key)
        time.sleep(0.1)
    return existing

def load_football_data_feed(days=1):
    start=datetime.now(OSLO).date()
    end=start+timedelta(days=max(days,1)-1)
    matches=[]
    for code,name in COMPETITIONS.items():
        matches.extend(_load_competition_matches(code,name,start.isoformat(),end.isoformat()))
    matches=_merge_cl_fallback(matches,start,end)
    matches.sort(key=lambda m:m["kickoff"])
    return {"matches":matches}

def load_feed(demo=False,days=1):
    if demo:
        return json.loads(Path("data/demo_matches.json").read_text(encoding="utf-8"))
    return load_football_data_feed(days=days)
