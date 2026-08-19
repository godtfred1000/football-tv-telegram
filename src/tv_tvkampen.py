from __future__ import annotations
import re, requests
from functools import lru_cache
from bs4 import BeautifulSoup

URL="https://www.tvkampen.com/fotball/champions-league"
HEADERS={"User-Agent":"Mozilla/5.0 AppleWebKit/537.36 Chrome/151 Safari/537.36","Accept-Language":"nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7"}

def _norm(v):
    v=(v or "").lower().replace("&"," and ")
    for a,b in [("ø","o"),("ö","o"),("æ","ae"),("å","a"),("ä","a"),("é","e")]: v=v.replace(a,b)
    v=re.sub(r"\\b(fc|afc|cf|fk|sk|sc|bk)\\b"," ",v)
    v=re.sub(r"[^a-z0-9]+"," ",v)
    return re.sub(r"\\s+"," ",v).strip()

def _variants(name):
    base=_norm(name)
    aliases={"manchester united":{"man utd"},"manchester city":{"man city"},"nottingham forest":{"nottm forest"},"tottenham hotspur":{"tottenham","spurs"},"brighton and hove albion":{"brighton"},"paris saint germain":{"psg"},"dinamo zagreb":{"gnk dinamo"},"bodo glimt":{"bodo/glimt","bodoe/glimt"}}
    return {base}|{_norm(x) for x in aliases.get(base,set())}

def _match_text(text,home,away):
    t=_norm(text)
    return any(v in t for v in _variants(home)) and any(v in t for v in _variants(away))

@lru_cache(maxsize=2)
def _html():
    try:
        r=requests.get(URL,headers=HEADERS,timeout=(8,15))
        if r.ok: return r.text
        print(f"TVkampen: HTTP {r.status_code}")
    except requests.RequestException as exc:
        print(f"TVkampen-feil: {exc}")
    return ""

def _canon(text):
    n=_norm(text)
    if "tv 2 sport premium" in n or "tv2 sport premium" in n: return "TV 2 Sport Premium"
    if "tv 2 sport 2" in n or "tv2 sport 2" in n: return "TV 2 Sport 2"
    if "tv 2 sport 1" in n or "tv2 sport 1" in n: return "TV 2 Sport 1"
    if "tv 2 sport" in n or "tv2 sport" in n: return "TV 2 Sport"
    if "tv 2 direkte" in n or "tv2 direkte" in n: return "TV 2 Direkte"
    if "tv 2 play" in n or "tv2 play" in n: return "TV 2 Play"
    return None

def get_tvkampen_norway(home,away):
    html=_html()
    if not html: return []
    soup=BeautifulSoup(html,"html.parser")
    for node in soup.find_all(["article","li","div","a","section"]):
        text=node.get_text(" ",strip=True)
        if not text or len(text)>1800 or not _match_text(text,home,away): continue
        out=[]; seen=set()
        for s in node.stripped_strings:
            ch=_canon(str(s))
            if ch and ch not in seen:
                seen.add(ch); out.append(ch)
        if out:
            print(f"TVkampen NO: {home} - {away}: {', '.join(out)}")
            return out
    return []

def champions_league_norway_fallback():
    return ["TV 2 Play"]
