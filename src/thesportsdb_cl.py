from __future__ import annotations
import re, requests
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

OSLO=ZoneInfo("Europe/Oslo")
UTC=ZoneInfo("UTC")
API_BASE="https://www.thesportsdb.com/api/v1/json/123"
UCL_LEAGUE_ID="4480"
HEADERS={"User-Agent":"Mozilla/5.0 AppleWebKit/537.36 Chrome/151 Safari/537.36","Accept-Language":"en-GB,en;q=0.9"}

def _norm(v):
    v=(v or "").lower().replace("&"," and ")
    v=re.sub(r"\\b(fc|afc|cf|fk|sk|sc)\\b"," ",v)
    v=re.sub(r"[^a-z0-9]+"," ",v)
    return re.sub(r"\\s+"," ",v).strip()

def _get(path,params):
    try:
        r=requests.get(f"{API_BASE}/{path}",params=params,headers=HEADERS,timeout=(8,15))
        if not r.ok:
            print(f"TheSportsDB HTTP {r.status_code} for {path}")
            return {}
        return r.json()
    except requests.RequestException as exc:
        print(f"TheSportsDB-feil: {exc}")
        return {}
    except ValueError:
        return {}

def _event_to_match(e):
    home=(e.get("strHomeTeam") or "").strip()
    away=(e.get("strAwayTeam") or "").strip()
    if not home or not away: return None
    lid=str(e.get("idLeague") or "")
    lname=str(e.get("strLeague") or "").lower()
    if lid and lid!=UCL_LEAGUE_ID: return None
    if lname and "champions league" not in lname: return None
    kickoff=None
    ts=e.get("strTimestamp")
    if ts:
        try:
            dt=datetime.fromisoformat(str(ts).replace("Z","+00:00"))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=UTC)
            kickoff=dt.astimezone(UTC).isoformat().replace("+00:00","Z")
        except Exception: kickoff=None
    if not kickoff:
        d=e.get("dateEvent") or e.get("dateEventLocal")
        t=e.get("strTime") or e.get("strTimeLocal") or "20:00:00"
        if not d: return None
        try:
            dt=datetime.fromisoformat(f"{d}T{str(t)[:5]}:00").replace(tzinfo=UTC)
            kickoff=dt.isoformat().replace("+00:00","Z")
        except Exception: return None
    venue=(e.get("strVenue") or "").strip()
    city=(e.get("strCity") or "").strip()
    venue_display=venue
    if venue and city and _norm(city) not in _norm(venue): venue_display=f"{venue}, {city}"
    elif not venue and city: venue_display=city
    return {"competition":"UEFA Champions League","kickoff":kickoff,"home":home,"away":away,"venue":venue_display or None,"broadcasts":{"NO":[],"SE":[],"DK":[],"AU":[],"UK":[]},"source":"TheSportsDB","thesportsdb_event_id":e.get("idEvent")}

def get_thesportsdb_cl_matches(date_from:date,date_to:date):
    matches=[]; day=date_from
    while day<=date_to:
        data=_get("eventsday.php",{"d":day.isoformat(),"l":UCL_LEAGUE_ID})
        for e in data.get("events") or []:
            m=_event_to_match(e)
            if m: matches.append(m)
        day+=timedelta(days=1)
    seen=set(); result=[]
    for m in matches:
        try:
            d=datetime.fromisoformat(m["kickoff"].replace("Z","+00:00")).astimezone(OSLO).date().isoformat()
        except Exception: d=m["kickoff"][:10]
        key=(d,_norm(m["home"]),_norm(m["away"]))
        if key in seen: continue
        seen.add(key); result.append(m)
    result.sort(key=lambda x:x["kickoff"])
    print(f"TheSportsDB fallback: fant {len(result)} Champions League-kamp(er) i perioden.")
    return result
