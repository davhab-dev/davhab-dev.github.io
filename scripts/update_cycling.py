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
HTML_SOURCES = [
    ("MTBIKER.cz", "https://www.mtbiker.cz/clanky", "MTB", "mtbiker"),
    ("RoadCycling.cz", "https://www.roadcycling.cz/archiv", "Závody", "roadcycling"),
    ("CykloRepublic.cz", "https://cyklorepublic.cz/", "Cyklistika", "cyklorepublic"),
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


def listing_date(text):
    """Datum z výpisu; pouze když je skutečně přítomné."""
    today = dt.datetime.now(ZoneInfo("Europe/Prague")).date()
    relative = re.search(r"\b(předevčírem|před\s+\d+\s+(?:dny|dnem|hodinami|hodinou|týdnem)|dnes|včera)\b", text.lower())
    if relative:
        label = relative.group(1)
        if label == "dnes" or "hodin" in label:
            return today.isoformat()
        if label == "včera":
            return (today - dt.timedelta(days=1)).isoformat()
        if label == "předevčírem":
            return (today - dt.timedelta(days=2)).isoformat()
        if "týdnem" in label:
            return (today - dt.timedelta(days=7)).isoformat()
        days = re.search(r"\d+", label)
        if days:
            return (today - dt.timedelta(days=int(days.group()))).isoformat()
    return homepage_date(text)

def valid_listing_url(url, mode):
    parts = urllib.parse.urlsplit(url)
    host, path = (parts.hostname or "").lower(), parts.path
    if mode == "mtbiker":
        return host in ("mtbiker.cz", "www.mtbiker.cz") and bool(re.fullmatch(r"/clanky/\d+/[^/]+\.html", path))
    if mode == "roadcycling":
        return host in ("roadcycling.cz", "www.roadcycling.cz") and path.startswith("/clanek/") and len(path) > 10
    if mode == "cyklorepublic":
        return host in ("cyklorepublic.cz", "www.cyklorepublic.cz") and bool(re.fullmatch(r"/clanky/[^/]+/[^/]+", path))
    if mode == "ivelo":
        return host in ("ivelo.cz", "www.ivelo.cz") and bool(re.fullmatch(r"/[a-z0-9-]{15,}/", path))
    return False

class ListingParser(HTMLParser):
    """Extrahuje pouze skutečné odkazy na články, nikoli sekce a navigaci."""
    def __init__(self, base, mode):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.mode = mode
        self.heading_depth = 0
        self.anchor = None
        self.entries = []
        # MTBIKER ma pred samotnym vypisem blok nejctenejsich clanku.
        self.in_listing = mode != "mtbiker"
    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "h4"):
            self.heading_depth += 1
        if tag == "a" and self.anchor is None and self.in_listing:
            href = dict(attrs).get("href", "")
            url = urllib.parse.urljoin(self.base, href)
            if valid_listing_url(url, self.mode):
                self.anchor = [url, [], bool(self.heading_depth)]
    def handle_data(self, data):
        if self.mode == "mtbiker" and "všechny články a videa" in data.lower():
            self.in_listing = True
        if self.anchor:
            self.anchor[1].append(data)
        elif self.entries:
            # Datum bývá v kartě až za titulkem. Nezachováváme text článku.
            if len(self.entries[-1][3]) < 450:
                self.entries[-1][3].append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.anchor:
            url, chunks, heading = self.anchor
            title = clean(" ".join(chunks))
            if 18 <= len(title) <= 230:
                self.entries.append([url, title, heading, []])
            self.anchor = None
        if tag in ("h2", "h3", "h4"):
            self.heading_depth = max(0, self.heading_depth - 1)

def fetch_html_listing(name, base, fallback, mode):
    req = urllib.request.Request(
        base,
        headers={"User-Agent": "Mozilla/5.0 (compatible; DAVHAB-CyklistickyPrehled/1.2; +https://davhab.com/cyklisticky-prehled/)",
                 "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(req, timeout=22) as response:
        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    parser = ListingParser(base, mode)
    parser.feed(raw.decode(charset, errors="replace"))
    result, seen = [], set()
    for url, title, heading, details in parser.entries:
        if mode == "ivelo" and not heading:
            continue
        if url in seen or title.lower().startswith(("více ", "další ", "přidat ")):
            continue
        if mode == "mtbiker" and re.search(r"\b(jak na běh|běžeck|běh:|lezení|ferraty)\b", title.lower()):
            continue
        seen.add(url)
        date_value = listing_date(" ".join(details))
        result.append({"title": title, "summary": "", "url": url, "source": name,
                       "lang": "CS", "category": category(title, "", fallback), "published": date_value})
        if len(result) >= 45:
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
    for name, url, fallback, mode in HTML_SOURCES:
        try:
            items = fetch_html_listing(name, url, fallback, mode)
            if not items:
                raise ValueError("nenalezeny odkazy na články")
            fresh.extend(items)
            print(name, len(items))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print("CHYBA", name, exc)
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
