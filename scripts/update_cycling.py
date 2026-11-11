#!/usr/bin/env python3
"""Cyklistický přehled: z veřejných RSS vytváří statický JSON bez placených API."""
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "cyklisticky-prehled" / "articles.json"
FEEDS = [
    ("NaKole.cz", "https://www.nakole.cz/rss/clanek/", "CS", "Cyklistika"),
    ("Cyclingnews", "https://www.cyclingnews.com/feeds.xml", "EN", "Závody"),
    ("BikeRadar", "https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/bikeradar-news", "EN", "Technika"),
    ("BikeRadar MTB", "https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/bikeradar-mtb-feed", "EN", "MTB"),
    ("BikeRadar Gravel", "https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/bikeradar-gravel-feed", "EN", "Gravel"),
]
TAGS = [
    ("Gravel", ("gravel", "bikepacking")),
    ("MTB", ("mountain bike", "mountain biking", "xc ", "cross-country", "downhill", "enduro")),
    ("Trénink", ("training", "fitness", "nutrition", "recovery", "workout")),
    ("Servis", ("maintenance", "repair", "workshop", "service", "mechanic")),
    ("Technika", ("tech", "review", "tyre", "tire", "wheel", "groupset", "brake", "gear", "bike test")),
    ("Závody", ("race", "tour de france", "giro", "vuelta", "championship", "worldtour", "cyclocross", "cyclo-cross")),
]
def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()
def child(node, name):
    el = node.find(name)
    return clean(el.text) if el is not None else ""
def date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        try: return dt.datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(dt.timezone.utc).isoformat()
        except Exception: return ""
def category(title, summary, fallback):
    s = (title+" "+summary).lower()
    for cat, words in TAGS:
        if any(word in s for word in words): return cat
    return fallback
def fetch(name, url, lang, fallback):
    req = urllib.request.Request(url, headers={"User-Agent":"DAVHAB-CyklistickyPrehled/1.0 (+https://davhab.com/cyklisticky-prehled/)", "Accept":"application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=22) as res:
        raw = res.read(3_000_000)
    tree = ET.fromstring(raw)
    nodes = tree.findall(".//item")
    atom = False
    if not nodes:
        atom = True
        nodes = tree.findall("{http://www.w3.org/2005/Atom}entry")
    result = []
    for item in nodes[:60]:
        if atom:
            ns="{http://www.w3.org/2005/Atom}"
            title=clean(item.findtext(ns+"title", default=""))
            summary=clean(item.findtext(ns+"summary", default="") or item.findtext(ns+"content", default=""))
            link=next((el.attrib.get("href","") for el in item.findall(ns+"link") if el.attrib.get("rel","alternate")=="alternate"),"")
            if not link: link=next((el.attrib.get("href","") for el in item.findall(ns+"link")),"")
            pub=item.findtext(ns+"published", default="") or item.findtext(ns+"updated", default="")
        else:
            title=child(item,"title")
            summary=clean(item.findtext("description",default=""))
            link=child(item,"link")
            pub=child(item,"pubDate")
        parsed=urllib.parse.urlsplit(link)
        if not title or parsed.scheme not in ("https","http") or not parsed.netloc: continue
        result.append({"title":title[:240], "summary":summary[:220], "url":link, "source":name, "lang":lang, "category":category(title,summary,fallback), "published":date(pub)})
    return result

def main():
    existing=[]
    if DEST.exists():
        try: existing=json.loads(DEST.read_text(encoding="utf-8")).get("articles",[])
        except (ValueError,OSError): pass
    fresh=[]
    errors=[]
    for name,url,lang,cat in FEEDS:
        try:
            items=fetch(name,url,lang,cat)
            if not items: raise ValueError("prázdný RSS kanál")
            fresh.extend(items)
            print(name, len(items))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print("CHYBA",name,exc)
    if not fresh:
        if existing:
            print("Žádný zdroj nedostupný; ponechávám existující data.")
            return
        raise SystemExit("Žádný RSS kanál není dostupný.")
    seen=set()
    articles=[]
    for article in sorted(fresh+existing,key=lambda a:a.get("published",""),reverse=True):
        url=article.get("url","")
        key=urllib.parse.urlsplit(url)._replace(query="",fragment="").geturl().rstrip("/").lower()
        if key in seen or not key: continue
        seen.add(key)
        articles.append(article)
        if len(articles)>=350: break
    DEST.parent.mkdir(parents=True,exist_ok=True)
    payload={"updated":dt.datetime.now(dt.timezone.utc).isoformat(), "articles":articles, "source_errors":errors}
    DEST.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Uloženo",len(articles),"článků")
if __name__=="__main__":main()
