from __future__ import annotations
import re
from functools import lru_cache
import requests
from bs4 import BeautifulSoup

COUNTRY_PAGES = {
    "NO": "https://www.fotmob.com/nb/tv-guide/no",
    "SE": "https://www.fotmob.com/sv/tv-guide/se",
    "DK": "https://www.fotmob.com/da/tv-guide/dk",
    "UK": "https://www.fotmob.com/en-GB/tv-guide/gb",
    "AU": "https://www.fotmob.com/en-AU/tv-guide/au",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}
CHANNEL_HINTS = (
    "tv","sport","sports","viaplay","stan","tnt","sky","now","max","hbo",
    "discovery","dazn","prime","apple","paramount","espn","canal","play","vg"
)

def _norm(s):
    s=(s or "").lower().replace("&"," and ")
    for a,b in [("ø","o"),("ö","o"),("æ","ae"),("å","a"),("ä","a")]:
        s=s.replace(a,b)
    s=re.sub(r"\b(fc|afc|cf|fk|sk|sc|bk)\b"," ",s)
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def _variants(name):
    base=_norm(name)
    out={base}
    aliases={
        "manchester united":{"man utd"},
        "manchester city":{"man city"},
        "nottingham forest":{"nottm forest"},
        "tottenham hotspur":{"tottenham","spurs"},
        "brighton and hove albion":{"brighton"},
        "paris saint germain":{"psg"},
        "dinamo zagreb":{"gnk dinamo"},
    }
    out |= {_norm(x) for x in aliases.get(base,set())}
    return {x for x in out if x}

def _match_text(text,home,away):
    t=_norm(text)
    return any(v in t for v in _variants(home)) and any(v in t for v in _variants(away))

def _is_channel(text):
    t=_norm(text)
    return any(_norm(h) in t for h in CHANNEL_HINTS)

@lru_cache(maxsize=10)
def _get_html(country):
    url=COUNTRY_PAGES.get(country)
    if not url:
        return ""
    try:
        r=requests.get(url,headers=HEADERS,timeout=(8,15))
        if r.ok:
            return r.text
        print(f"FotMob TV {country}: HTTP {r.status_code}")
    except requests.Timeout:
        print(f"FotMob TV {country}: timeout")
    except requests.RequestException as exc:
        print(f"FotMob TV {country}: {exc}")
    return ""

def _find_channels(html,home,away):
    soup=BeautifulSoup(html,"html.parser")
    for a in soup.find_all("a"):
        txt=a.get_text(" ",strip=True)
        if not txt or not _match_text(txt,home,away):
            continue
        node=a
        for _ in range(6):
            node=getattr(node,"parent",None)
            if node is None:
                break
            if len(node.get_text(" ",strip=True)) > 1800:
                continue
            chans=[]
            for link in node.find_all("a"):
                t=link.get_text(" ",strip=True)
                if t and not _match_text(t,home,away) and _is_channel(t):
                    chans.append(t)
            if chans:
                seen=set(); result=[]
                for ch in chans:
                    k=_norm(ch)
                    if k and k not in seen:
                        seen.add(k); result.append(ch)
                return result
    return []

def get_fotmob_broadcasts(home,away,kickoff_iso):
    result={"NO":[],"SE":[],"DK":[],"AU":[],"UK":[]}
    for cc in result:
        html=_get_html(cc)
        if html:
            result[cc]=_find_channels(html,home,away)
    print("FotMob TV:",home,"-",away,
          ", ".join(f"{cc}={len(v)}" for cc,v in result.items()))
    return result
