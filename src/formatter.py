from __future__ import annotations
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
from .config import ALLOWED_COMPETITIONS, COUNTRIES

OSLO=ZoneInfo("Europe/Oslo")

def parse_dt(value):
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None: dt=dt.replace(tzinfo=OSLO)
    return dt.astimezone(OSLO)

def competition_icon(name):
    return "🏆" if "Champions" in name else "⚽"

def matches_for_day(feed,day=None):
    if day is None: day=datetime.now(OSLO).date()
    result=[]
    for match in feed.get("matches",[]):
        if match.get("competition","") not in ALLOWED_COMPETITIONS: continue
        kickoff=parse_dt(match["kickoff"])
        if kickoff.date()==day:
            copy=dict(match); copy["_kickoff_dt"]=kickoff; result.append(copy)
    return sorted(result,key=lambda m:m["_kickoff_dt"])

def format_daily_message(matches,demo=False):
    if not matches: return ""
    date_label=matches[0]["_kickoff_dt"].strftime("%d.%m.%Y")
    title=f"📺 <b>FOTBALL PÅ TV – {date_label}</b>"
    if demo: title="🧪 <b>DEMO</b> – "+title.replace("<b>","").replace("</b>","")
    chunks=[title,""]; current_comp=None
    for match in matches:
        comp=escape(match["competition"])
        if comp!=current_comp:
            if current_comp is not None: chunks.append("")
            chunks.append(f"{competition_icon(comp)} <b>{comp.upper()}</b>")
            current_comp=comp
        kickoff=match["_kickoff_dt"].strftime("%H:%M")
        home=escape(match["home"]); away=escape(match["away"])
        chunks.append(f"\n🕘 <b>{kickoff}</b>  {home} – {away}")
        venue=match.get("venue")
        if venue: chunks.append(f"🏟 {escape(str(venue))}")
        broadcasts=match.get("broadcasts",{})
        for code,(flag,country) in COUNTRIES.items():
            channels=broadcasts.get(code) or []
            value=", ".join(escape(str(x)) for x in channels) if channels else "Ikke oppført"
            chunks.append(f"{flag} {country}: {value}")
    chunks += ["","⏰ Tidene vises i norsk tid.","ℹ️ TV-oppsett kan endres av rettighetshaver."]
    return "\n".join(chunks)
