from __future__ import annotations
import re, requests
from datetime import date, datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

OSLO=ZoneInfo("Europe/Oslo")
PARIS=ZoneInfo("Europe/Paris")
URL="https://www.uefa.com/uefachampionsleague/accesslist/"
HEADERS={"User-Agent":"Mozilla/5.0","Accept-Language":"en-GB,en;q=0.9"}
MONTHS={"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
DATE_RE=re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\\s+(\\d{1,2})\\s+([A-Za-z]+)$",re.I)
MATCH_RE=re.compile(r"^(.+?)\\s+(?:vs|v)\\s+(.+?)\\s+\\((\\d{1,2}):(\\d{2})(?:\\s+or\\s+\\d{1,2}:\\d{2})?\\)$",re.I)

def _lines():
    r=requests.get(URL,headers=HEADERS,timeout=35)
    if not r.ok:
        print(f"UEFA HTTP {r.status_code}")
        return []
    soup=BeautifulSoup(r.text,"html.parser")
    return [re.sub(r"\\s+"," ",x).strip() for x in soup.get_text("\\n",strip=True).splitlines() if x.strip()]

def _norm(s):
    s=(s or "").lower().replace("&"," and ")
    s=re.sub(r"\\b(fc|afc|cf|fk|sk|sc)\\b"," ",s)
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return re.sub(r"\\s+"," ",s).strip()

def get_uefa_matches(date_from:date,date_to:date):
    lines=_lines()
    current=None
    in_playoff=False
    out=[]
    for line in lines:
        low=line.lower()
        if low in {"play-off round","playoff round"}:
            in_playoff=True
            continue
        if not in_playoff:
            continue
        if low.startswith("league phase draw"):
            break
        dm=DATE_RE.match(line)
        if dm:
            m=MONTHS.get(dm.group(3).lower())
            if m: current=date(2026,m,int(dm.group(2)))
            continue
        if current is None:
            continue
        mm=MATCH_RE.match(line)
        if not mm:
            continue
        home,away=mm.group(1).strip(),mm.group(2).strip()
        hour,minute=int(mm.group(3)),int(mm.group(4))
        local=datetime(current.year,current.month,current.day,hour,minute,tzinfo=PARIS)
        kickoff=local.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00","Z")
        oslo_day=datetime.fromisoformat(kickoff.replace("Z","+00:00")).astimezone(OSLO).date()
        if date_from <= oslo_day <= date_to:
            out.append({"competition":"UEFA Champions League","kickoff":kickoff,"home":home,"away":away,"broadcasts":{"NO":[],"SE":[],"DK":[],"AU":[],"UK":[]},"source":"UEFA"})
    seen=set(); result=[]
    for m in out:
        key=(m["kickoff"][:10],_norm(m["home"]),_norm(m["away"]))
        if key in seen: continue
        seen.add(key); result.append(m)
    result.sort(key=lambda x:x["kickoff"])
    print(f"UEFA fallback: fant {len(result)} CL play-off-kamp(er).")
    return result
