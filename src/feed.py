from __future__ import annotations
import json, re, time, requests
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import FOOTBALL_DATA_API_TOKEN
from .tv_fotmob import get_fotmob_broadcasts
from .tv_livesoccertv import get_broadcasts as get_livesoccertv_broadcasts
from .tv_tvkampen import get_tvkampen_norway, champions_league_norway_fallback
from .tv_uk import official_uk_broadcaster
from .thesportsdb_cl import get_thesportsdb_cl_matches

OSLO=ZoneInfo("Europe/Oslo")
FD_BASE="https://api.football-data.org/v4"
COMPETITIONS={"PL":"Premier League","CL":"UEFA Champions League"}
TV_COUNTRIES=("NO","SE","DK","AU","UK")

class FeedError(RuntimeError): pass

def _football_data_get(path,params=None):
    if not FOOTBALL_DATA_API_TOKEN: raise FeedError("FOOTBALL_DATA_API_TOKEN mangler i GitHub Secrets.")
    r=requests.get(f"{FD_BASE}{path}",headers={"X-Auth-Token":FOOTBALL_DATA_API_TOKEN},params=params or {},timeout=30)
    try: data=r.json()
    except ValueError: data={}
    if r.status_code==401: raise FeedError("football-data.org avviste API-tokenet (401).")
    if r.status_code==403: raise FeedError("football-data.org ga 403.")
    if r.status_code==429: raise FeedError("football-data.org rate limit er nådd (429).")
    if not r.ok: raise FeedError(f"football-data.org-feil {r.status_code}: {data.get('message') or r.text[:300]}")
    return data

def _norm_team(v):
    v=(v or "").lower().replace("&"," and ")
    v=re.sub(r"\b(fc|afc|cf|fk|sk|sc)\b"," ",v)
    v=re.sub(r"[^a-z0-9]+"," ",v)
    return re.sub(r"\s+"," ",v).strip()

def _team_similar(a,b):
    a=_norm_team(a); b=_norm_team(b)
    if not a or not b: return False
    if a==b: return True
    if min(len(a),len(b))>=4 and (a in b or b in a): return True
    ta=set(a.split()); tb=set(b.split())
    if not ta or not tb: return False
    overlap=len(ta & tb)
    return overlap >= 2 and overlap / min(len(ta),len(tb)) >= 0.67

def _match_day(m):
    try:
        return datetime.fromisoformat(m["kickoff"].replace("Z","+00:00")).astimezone(OSLO).date()
    except Exception:
        return None

def _clean_broadcasters(items):
    """Remove exact and obvious alias duplicates while preserving useful services."""
    out=[]
    seen=set()
    for item in items or []:
        name=re.sub(r"\s+"," ",str(item)).strip()
        if not name:
            continue
        key=name.casefold()
        # Prime Video and Amazon Prime Video are the same service; keep the clearer name.
        if key in {"prime video", "amazon prime video"}:
            key="amazon prime video"
            name="Amazon Prime Video"
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out

def _clean_broadcast_map(b):
    return {code:_clean_broadcasters((b or {}).get(code,[]) or []) for code in TV_COUNTRIES}

def _merge_broadcasts(primary, secondary):
    primary=_clean_broadcast_map(primary)
    secondary=_clean_broadcast_map(secondary)
    for code in TV_COUNTRIES:
        if not primary[code]:
            primary[code]=secondary[code]
    return _clean_broadcast_map(primary)

def _tv_for_cl(home,away,kickoff):
    try:
        b=get_fotmob_broadcasts(home,away,kickoff)
    except Exception as exc:
        print("FotMob TV-feil:",exc)
        b={code:[] for code in TV_COUNTRIES}

    b=_clean_broadcast_map(b)

    try:
        tvk=get_tvkampen_norway(home,away)
        if tvk:
            b["NO"]=_clean_broadcasters(tvk)
        elif not b.get("NO"):
            b["NO"]=_clean_broadcasters(champions_league_norway_fallback())
    except Exception as exc:
        print("TVkampen NO-feil:",exc)

    # FotMob har ofte bare enkelte land. Hent derfor alltid en ekstra kilde
    # når minst ett av landene mangler, og fyll kun inn de tomme feltene.
    if not all(b.get(code) for code in TV_COUNTRIES):
        try:
            extra=get_livesoccertv_broadcasts(home,away,kickoff)
            b=_merge_broadcasts(b,extra)
        except Exception as exc:
            print("LiveSoccerTV fallback-feil:",exc)

    # Stan Sport har de australske Champions League-rettighetene. Enkelte
    # datakilder utelater Australia, så fyll inn Stan Sport når AU mangler.
    if not b.get("AU"):
        b["AU"]=["Stan Sport"]

    return _clean_broadcast_map(b)

def _load_competition_matches(code,name,date_from,date_to):
    params={"dateFrom":date_from,"dateTo":date_to}
    if code=="PL": params["status"]="SCHEDULED,TIMED"
    data=_football_data_get(f"/competitions/{code}/matches",params)
    rows=[]
    for match in data.get("matches") or []:
        if str(match.get("status") or "").upper() in {"CANCELLED","POSTPONED"}: continue
        home=(match.get("homeTeam") or {}).get("name") or "Hjemmelag"
        away=(match.get("awayTeam") or {}).get("name") or "Bortelag"
        kickoff=match.get("utcDate")
        if not kickoff: continue
        if code=="PL":
            broadcasts={"NO":["Viaplay"],"SE":["Viaplay"],"DK":["Viaplay"],"AU":["Stan Sport"],"UK":official_uk_broadcaster(home,away,kickoff)}
            broadcasts=_clean_broadcast_map(broadcasts)
        else:
            broadcasts=_tv_for_cl(home,away,kickoff)
        rows.append({"competition":name,"kickoff":kickoff,"home":home,"away":away,"venue":None,"broadcasts":broadcasts,"football_data_match_id":match.get("id"),"source":"football-data.org"})
        time.sleep(0.1)
    return rows

def _merge_cl_fallback(existing,start,end):
    extra=get_thesportsdb_cl_matches(start,end)
    for m in extra:
        day=_match_day(m)
        duplicate=None
        for current in existing:
            if _match_day(current)!=day:
                continue
            if _team_similar(current.get("home"),m.get("home")) and _team_similar(current.get("away"),m.get("away")):
                duplicate=current
                break

        if duplicate is not None:
            fallback_tv=_tv_for_cl(m["home"],m["away"],m["kickoff"])
            duplicate["broadcasts"]=_merge_broadcasts(duplicate.get("broadcasts"),fallback_tv)
            if not duplicate.get("venue") and m.get("venue"):
                duplicate["venue"]=m["venue"]
            continue

        m["broadcasts"]=_tv_for_cl(m["home"],m["away"],m["kickoff"])
        existing.append(m)
        time.sleep(0.1)
    return existing

def load_football_data_feed(days=1):
    start=datetime.now(OSLO).date(); end=start+timedelta(days=max(days,1)-1); matches=[]
    for code,name in COMPETITIONS.items():
        matches.extend(_load_competition_matches(code,name,start.isoformat(),end.isoformat()))
    matches=_merge_cl_fallback(matches,start,end)
    matches.sort(key=lambda m:m["kickoff"])
    return {"matches":matches}

def load_feed(demo=False,days=1):
    if demo: return json.loads(Path("data/demo_matches.json").read_text(encoding="utf-8"))
    return load_football_data_feed(days=days)
