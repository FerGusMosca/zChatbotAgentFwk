# argenprop_local_probe.py
"""
Local probe for Argenprop pages:
- Opens a search URL in Chrome (non-headless by default) with optional user profile.
- Detects Cloudflare challenge heuristically.
- Dumps HTML/PNG to exports/debug/.
- Tries multiple parsing strategies (CSS and regex) to extract basic listing fields.
- Writes artifacts: TXT/CSV/JSON if any listings were parsed.
- Detailed logs to console and to exports/argenprop_local_probe.log

Usage:
  python argenprop_local_probe.py
  (Optionally adjust CONFIG below: PROFILE_DIR, HEADLESS, SEARCH_URL)
"""

import csv
import json
import logging
import re
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

# ------------ CONFIG ------------
HEADLESS = False
PROFILE_DIR = r"C:\Bias_Algos\APProfile"  # set to None to disable custom profile
SEARCH_URL = "https://www.argenprop.com/departamento-venta-barrio-belgrano"
OUTDIR = Path("../../exports")
STEM = "argenprop_local_probe"
# --------------------------------

# Selenium & parser
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from bs4 import BeautifulSoup

# ------------- Model -------------

@dataclass
class APItem:
    url: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    location: Optional[str] = None
    details: Optional[str] = None
    agency: Optional[str] = None
    source: str = "argenprop"
    portal_id: Optional[str] = None  # try to extract numeric id if present

# --------- Logging setup ---------

LOG_PATH = OUTDIR / f"{STEM}.log"

def build_logger() -> logging.Logger:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger("ap_local_probe")
    lg.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    lg.addHandler(ch)

    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    lg.addHandler(fh)
    return lg

log = build_logger()

# --------- Helpers ---------

def cf_detect(html: str) -> Tuple[bool, str]:
    """Heuristic Cloudflare/challenge detection."""
    patterns = [
        r"cloudflare", r"cf-browser-verification", r"Checking your browser",
        r"Attention Required", r"verify you are a human", r"challenge-platform",
        r"/cdn-cgi/challenge", r"cf-error", r"cf-\w+-captcha"
    ]
    for pat in patterns:
        if re.search(pat, html, flags=re.IGNORECASE):
            return True, pat
    return False, ""

def extract_text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(strip=True)) if el else ""

def save_artifacts(html: str, driver, debug_dir: Path):
    debug_dir.mkdir(parents=True, exist_ok=True)
    html_path = debug_dir / "ap_local_page.html"
    png_path = debug_dir / "ap_local_page.png"
    html_path.write_text(html, encoding="utf-8")
    try:
        driver.save_screenshot(str(png_path))
    except Exception as e:
        log.warning("screenshot.warn | %s", e)
    log.info("dump.ok | html=%s png=%s", html_path, png_path)

# --------- Parsers ---------

def parse_with_css(soup: BeautifulSoup) -> List[APItem]:
    """
    Try a few CSS strategies known to show up on Argenprop.
    We keep it permissive to survive minor DOM changes.
    """
    items: List[APItem] = []

    # Strategy 1: cards with anchors to property pages
    # Heuristic: any <a> to argenprop.com that looks like a property detail
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        # Normalize absolute URLs
        if href.startswith("/"):
            url = f"https://www.argenprop.com{href}"
        else:
            url = href

        if "argenprop.com" not in url:
            continue
        # A coarse filter for property-like paths
        if not re.search(r"/(propiedad|departamento|casa|ph|oficina|local)", url, re.IGNORECASE):
            continue

        # Walk up to a card-ish container to gather data
        card = a
        for _ in range(3):
            if card.parent:
                card = card.parent

        title = extract_text(card.find(["h2", "h3"])) or extract_text(a)
        price = extract_text(card.find(lambda tag: tag.name in ["span", "p", "div"] and re.search(r"\$\s?[\d\.]", tag.get_text())))
        location = extract_text(card.find(lambda tag: tag.name in ["p","span","div"] and re.search(r"(Belgrano|CABA|Capital|Buenos Aires)", tag.get_text(), re.IGNORECASE)))
        details = extract_text(card.find(lambda tag: tag.name in ["ul","div","p"] and re.search(r"(amb|m²|m2|dorm|bañ)", tag.get_text(), re.IGNORECASE)))
        agency = extract_text(card.find(lambda tag: tag.name in ["span","div","p"] and re.search(r"(inmobiliaria|realtor|broker|propiedades|sociedad)", tag.get_text(), re.IGNORECASE)))

        # Extract portal_id if embedded in URL (?id=12345 or /ID-12345)
        m = re.search(r"(?:id=|ID-)(\d+)", url, re.IGNORECASE)
        portal_id = m.group(1) if m else None

        # Build item (avoid duplicates by url)
        items.append(APItem(
            url=url, title=title or None, price=price or None, location=location or None,
            details=details or None, agency=agency or None, portal_id=portal_id
        ))

    # Deduplicate by URL
    seen = set()
    deduped: List[APItem] = []
    for it in items:
        if not it.url or it.url in seen:
            continue
        seen.add(it.url)
        deduped.append(it)

    return deduped

def parse_with_regex(html: str) -> List[APItem]:
    """
    Fallback: permissive regex to fish URLs to properties + shallow context lines.
    """
    items: List[APItem] = []
    for m in re.finditer(r'href="([^"]+)"', html, re.IGNORECASE):
        href = m.group(1)
        if href.startswith("/"):
            url = f"https://www.argenprop.com{href}"
        else:
            url = href
        if "argenprop.com" not in url:
            continue
        if not re.search(r"/(propiedad|departamento|casa|ph|oficina|local)", url, re.IGNORECASE):
            continue
        items.append(APItem(url=url))
    # Dedup
    seen = set()
    out: List[APItem] = []
    for it in items:
        if not it.url or it.url in seen:
            continue
        seen.add(it.url)
        out.append(it)
    return out

# --------- Export ---------

def write_txt(path: Path, items: List[APItem]):
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# Argenprop Local Probe\n# URL: {SEARCH_URL}\n# Items: {len(items)}\n\n")
        for i, it in enumerate(items, 1):
            f.write(f"## {i}. {it.title or '(no title)'}\n")
            if it.price:    f.write(f"- Precio: {it.price}\n")
            if it.location: f.write(f"- Ubicación: {it.location}\n")
            if it.details:  f.write(f"- Detalles: {it.details}\n")
            if it.agency:   f.write(f"- Agencia: {it.agency}\n")
            if it.url:      f.write(f"- URL: {it.url}\n")
            f.write("\n")

def write_csv(path: Path, items: List[APItem]):
    cols = ["url","title","price","location","details","agency","source","portal_id"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for it in items:
            w.writerow(asdict(it))

def write_json(path: Path, items: List[APItem]):
    with path.open("w", encoding="utf-8") as f:
        json.dump([asdict(it) for it in items], f, ensure_ascii=False, indent=2)

# --------- Main probe ---------

def main():
    log.info("probe.start | url=%s headless=%s profile_dir=%s", SEARCH_URL, HEADLESS, PROFILE_DIR)
    debug_dir = OUTDIR / "debug"
    txt_path  = OUTDIR / f"{STEM}.txt"
    csv_path  = OUTDIR / f"{STEM}.csv"
    json_path = OUTDIR / f"{STEM}.json"

    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # helpful to reduce bot detection noise
    options.add_argument("--lang=es-AR")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    if PROFILE_DIR:
        options.add_argument(f"--user-data-dir={PROFILE_DIR}")
        # optional named profile:
        # options.add_argument("--profile-directory=Default")

    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as e:
        log.error("chrome.init.error | %s", e)
        return 2

    try:
        driver.get(SEARCH_URL)
        # wait a bit for client-side rendering / potential challenge to show up
        time.sleep(2.0)

        # A gentle explicit wait for any anchor to argenprop (avoid hard selectors)
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='argenprop.com']"))
            )
        except TimeoutException:
            log.warning("wait.warn | no anchors to argenprop.com after 8s")

        html = driver.page_source or ""
        save_artifacts(html, driver, debug_dir)

        # CF detection
        cf, pat = cf_detect(html)
        if cf:
            log.warning("cf.detected | pattern=%s | parsing will likely return zero", pat)

        # Parse strategies
        soup = BeautifulSoup(html, "html.parser")

        items_css = parse_with_css(soup)
        log.info("parse.css | found=%d", len(items_css))

        if not items_css:
            items_regex = parse_with_regex(html)
            log.info("parse.regex | found=%d", len(items_regex))
        else:
            items_regex = []

        # Choose best
        items = items_css if items_css else items_regex

        # Report top 5 sample
        for i, it in enumerate(items[:5], start=1):
            log.info("sample.%d | title=%r price=%r loc=%r url=%s",
                     i, it.title, it.price, it.location, it.url)

        # Exports if any
        if items:
            write_txt(txt_path, items)
            write_csv(csv_path, items)
            write_json(json_path, items)
            log.info("write.ok | txt=%s size=%d", txt_path, txt_path.stat().st_size)
            log.info("write.ok | csv=%s size=%d", csv_path, csv_path.stat().st_size)
            log.info("write.ok | json=%s size=%d", json_path, json_path.stat().st_size)
            log.info("probe.end | success=True count=%d", len(items))
            print(f"OK | count={len(items)}")
            return 0
        else:
            log.info("probe.end | success=False count=0 (likely CF or selector drift)")
            print("NO_RESULTS | count=0")
            return 1

    except Exception as e:
        log.error("probe.error | %s", e)
        log.debug("traceback:\n%s", traceback.format_exc())
        return 3
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    sys.exit(main())
