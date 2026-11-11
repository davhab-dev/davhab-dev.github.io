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
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "cyklisticky-prehled" / "articles.json"
FEEDS = [
    # Nakole odkazuje na HTTP RSS; HTTPS nekdy vraci 403.
    ("NaKole.cz", "http://www.nakole.cz/rss/clanek/", "CS", "Cyklistika"),
    ("MTBS.cz", "https://mtbs.cz/rss_06.mtbs", "CS", "MTB"),
    ("Cykl.cz", "https://cykl.cz/feed/", "CS", "Technika"),
    ("iVELO.cz", "https://www.ivelo.cz/feed/", "CS", "Technika"),
    ("BikeAndRide.cz", "https://www.bikeandride.cz/feed/", "CS", "MTB"),
    ("TrailHunter.cz", "https://www.trailhunter.cz/feed/", "CS", "MTB"),
    ("Cyklocestovatel.cz", "https://cyklocestovatel.cz/feed/", "CS", "Cyklistika"),
    ("Cyclingnews", "https://www.cyclingnews.com/feeds.xml", "EN", "Závody"),
    ("BikeRadar", "https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/bikeradar-news", "EN", "Technika"),
    ("BikeRadar MTB", "https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/bikeradar-mtb-feed", "EN", "MTB"),
    ("BikeRadar Gravel", "https://feeds.purplemanager.com/193c804a-a673-47bd-b09b-11baf4822a17/bikeradar-gravel-feed", "EN", "Gravel"),
]
TAGS = [
    ("Gravel", ("gravel", "bikepacking", "gravelisty")),
    ("MTB", ("mountain bike", "mountain biking", "xc ", "cross-country", "downhill", "enduro", "horských kol", "bikery")),
    ("Trénink", ("training", "fitness", "nutrition", "recovery", "workout", "trénink", "regenerac", "výživ")),
    ("Servis", ("maintenance", "repair", "workshop", "service", "mechanic", "oprava", "údržba", "servis kol")),
    ("Technika", ("tech", "review", "tyre", "tire", "wheel", "groupset", "brake", "gear", "bike test", "přilba", "pláště", "komponent", "elektrokol", "technika", "kotoučových brzd", "test:")),
    ("Závody", ("race", "tour de france", "giro", "vuelta", "championship", "worldtour", "cyclocross", "cyclo-cross", "cyklokros", "mistrovství evropy", "světový pohár", "závod")),
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
            raw_title = clean("".join(parts))
            # Karta nekdy obsahuje i autora, datum a perex; oddelime je od titulku.
            title = re.split(r"\s+(?:Dnes|Včera|\d{1,2}\.\d{1,2}\.)", raw_title, maxsplit=1)[0]
            if 18 <= len(title) <= 240:
                self.links.append((url, title, raw_title))
            self.current = None

def homepage_date(text):
    """Vrať skutečné datum uvedené v kartě, jinak neznámé datum."""
    today = dt.datetime.now(ZoneInfo("Europe/Prague")).date()
    if re.search(r"\bDnes\b", text):
        day = today
    elif re.search(r"\bVčera\b", text):
        day = today - dt.timedelta(days=1)
    else:
        match = re.search(r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{4}))?", text)
        if not match:
            return ""
        try:
            day = dt.date(int(match.group(3) or today.year), int(match.group(2)), int(match.group(1)))
            if match.group(3) is None and day > today:
                day = dt.date(today.year - 1, day.month, day.day)
        except ValueError:
            return ""
    return day.isoformat()

class CyklHeadlineParser(HTMLParser):
    """Titulky na Cykl.cz jsou ve značkách h2; datum leží pod titulkem."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_heading = False
        self.link = None
        self.parts = []
        self.current = None
        self.items = []
    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            if self.current:
                self.items.append(self.current)
            self.current = {"url": "", "title": "", "details": []}
            self.in_heading = True
        if tag == "a" and self.in_heading:
            href = dict(attrs).get("href", "")
            url = urllib.parse.urljoin("https://cykl.cz/", href)
            parsed = urllib.parse.urlsplit(url)
            if parsed.hostname in ("cykl.cz", "www.cykl.cz") and parsed.path.strip("/"):
                self.link = url
                self.parts = []
    def handle_data(self, data):
        if self.link is not None:
            self.parts.append(data)
        elif self.current is not None and not self.in_heading:
            self.current["details"].append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            if self.current is not None:
                self.current["url"] = self.link
                self.current["title"] = clean("".join(self.parts))
            self.link = None
        if tag == "h2":
            self.in_heading = False
    def close(self):
        super().close()
        if self.current:
            self.items.append(self.current)

def fetch_cykl_homepage():
    req = urllib.request.Request(
        "https://cykl.cz/",
        headers={"User-Agent": "Mozilla/5.0 (compatible; DAVHAB-CyklistickyPrehled/1.1; +https://davhab.com/cyklisticky-prehled/)",
                 "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(req, timeout=22) as response:
        raw = response.read(1_500_000)
        charset = response.headers.get_content_charset() or "utf-8"
    parser = CyklHeadlineParser()
    parser.feed(raw.decode(charset, errors="replace"))
    parser.close()
    result = []
    seen = set()
    for item in parser.items:
        title, url = item["title"], item["url"]
        if not (15 <= len(title) <= 240) or not url or url in seen:
            continue
        seen.add(url)
        result.append({"title": title, "summary": "", "url": url, "source": "Cykl.cz",
                       "lang": "CS", "category": category(title, "", "Cyklistika"),
                       "published": homepage_date(" ".join(item["details"]))})
        if len(result) >= 40:
            break
    return result

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
    for url, title, card_text in parser.links:
        if url in seen:
            continue
        seen.add(url)
        result.append({"title": title, "summary": "", "url": url, "source": "MTBS.cz",
                       "lang": "CS", "category": category(title, "", "MTB"), "published": homepage_date(card_text)})
        if len(result) >= 30:
            break
    return result

def main():
    existing=[]
    if DEST.exists():
        try: existing=json.loads(DEST.read_text(encoding="utf-8")).get("articles",[])
        except (ValueError,OSError): pass
    # Odstranime historicke chybne zaznamy bez datumu; aktualni se znovu nactou.
    existing=[a for a in existing if not (a.get("source")=="MTBS.cz" and not a.get("published"))]
    fresh=[]
    errors=[]
    for name,url,lang,cat in FEEDS:
        try:
            items=fetch(name,url,lang,cat)
            if not items: raise ValueError("prázdný RSS kanál")
            fresh.extend(items)
            print(name, len(items))
        except Exception as exc:
            if name in ("MTBS.cz", "Cykl.cz"):
                try:
                    items = fetch_mtbs_homepage() if name == "MTBS.cz" else fetch_cykl_homepage()
                    if items:
                        fresh.extend(items)
                        print(f"{name}: nouzové načtení titulů z webu:", len(items))
                        continue
                except Exception as fallback_exc:
                    print(f"CHYBA {name} (záložní metoda)", fallback_exc)
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
