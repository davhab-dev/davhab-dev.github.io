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
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "cyklisticky-prehled" / "articles.json"
FEEDS = [
    # Nakole odkazuje na HTTP RSS; HTTPS nekdy vraci 403.
    ("NaKole.cz", "http://www.nakole.cz/rss/clanek/", "CS", "Cyklistika"),
    ("MTBS.cz", "https://mtbs.cz/rss_06.mtbs", "CS", "MTB"),
    ("Cykl.cz", "https://cykl.cz/feed/", "CS", "Technika"),
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


class ArticleLinkParser(HTMLParser):
    """Nouzové načtení pouze titulků a odkazů ze stránky MTBS.cz."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.depth = 0
        self.links = []
    def handle_starttag(self, tag, attrs):
        if self.current is not None:
            self.depth += 1
            return
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        url = urllib.parse.urljoin("https://mtbs.cz/", href)
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname in ("mtbs.cz", "www.mtbs.cz") and parsed.path.startswith("/clanek/"):
            self.current = [url, []]
            self.depth = 1
    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)
    def handle_endtag(self, tag):
        if self.current is None:
            return
        self.depth -= 1
        if self.depth == 0:
            url, parts = self.current
            title = clean("".join(parts))
            if 22 <= len(title) <= 240:
                self.links.append((url, title))
            self.current = None

def fetch_mtbs_homepage():
    """Rezervní zdroj, pokud RSS MTBS neodpoví. Datum nevymýšlíme."""
    req = urllib.request.Request(
        "https://mtbs.cz/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; DAVHAB-CyklistickyPrehled/1.1; +https://davhab.com/cyklisticky-prehled/)",
                 "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(req, timeout=22) as response:
        raw = response.read(1_500_000)
        charset = response.headers.get_content_charset() or "utf-8"
    parser = ArticleLinkParser()
    parser.feed(raw.decode(charset, errors="replace"))
    seen = set()
    result = []
    for url, title in parser.links:
        if url in seen:
            continue
        seen.add(url)
        result.append({"title": title, "summary": "", "url": url, "source": "MTBS.cz",
                       "lang": "CS", "category": category(title, "", "MTB"), "published": ""})
        if len(result) >= 30:
            break
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
            if name == "MTBS.cz":
                try:
                    items = fetch_mtbs_homepage()
                    if items:
                        fresh.extend(items)
                        print("MTBS.cz: nouzové načtení titulů z webu:", len(items))
                        continue
                except Exception as fallback_exc:
                    print("CHYBA MTBS.cz (záložní metoda)", fallback_exc)
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
