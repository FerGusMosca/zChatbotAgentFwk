# argenprop_smoke_probe.py
"""
Smoke probe for Argenprop listing pages — MULTI-PAGE edition.

Based on the working single-page probe. Changes vs original are MINIMAL:
  - Added AP_MAX_PAGES and AP_PAGE_WAIT env vars
  - Added build_page_url() to generate ?pagina=N URLs
  - Loop in main() calls the same scrape logic N times, same driver
  - All parsing, exports, driver setup, block detection: UNCHANGED

Location: <root>/tests/smoke/argenprop_smoke_probe.py
Outputs:  <root>/exports/argenprop_smoke_*.*
          <root>/exports/debug/ap_page_N.html  +  ap_page_N.png

Usage:
  cd <root>
  python tests/smoke/argenprop_smoke_probe.py

Optional env overrides:
  AP_URL        full first-page URL  (default: departamentos en venta en Belgrano)
  AP_HEADLESS   1 | 0                (default: 0 → visible Chrome)
  AP_PROFILE    path to Chrome user-data-dir  (default: none)
  AP_MAX_PAGES  max pages to scrape  (default: 5, 0 = unlimited)
  AP_PAGE_WAIT  seconds between pages (default: 2)
"""

import csv
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# ─────────────────────────── CONFIG (env-overridable) ──────────────────────────
SEARCH_URL = os.getenv(
    "AP_URL",
    "https://www.argenprop.com/departamento-venta-barrio-belgrano",
)
HEADLESS    = os.getenv("AP_HEADLESS", "0") == "1"
PROFILE_DIR = os.getenv("AP_PROFILE", "")
MAX_PAGES   = int(os.getenv("AP_MAX_PAGES", "5"))   # ← NEW
PAGE_WAIT   = float(os.getenv("AP_PAGE_WAIT", "2")) # ← NEW
# ───────────────────────────────────────────────────────────────────────────────

_ROOT   = Path(__file__).resolve().parents[2]
OUTDIR  = _ROOT / "exports"
STEM    = "argenprop_smoke"

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup


# ══════════════════════════════════════════════════════════
#  Model
# ══════════════════════════════════════════════════════════

@dataclass
class APItem:
    url:         Optional[str] = None
    title:       Optional[str] = None
    price:       Optional[str] = None
    currency:    Optional[str] = None
    location:    Optional[str] = None
    m2_total:    Optional[str] = None
    m2_cover:    Optional[str] = None
    ambientes:   Optional[str] = None
    dormitorios: Optional[str] = None
    banos:       Optional[str] = None
    expensas:    Optional[str] = None
    agency:      Optional[str] = None
    portal_id:          Optional[str] = None
    text_for_embedding: Optional[str] = None   # ← narrativa para RAG / embeddings
    source:             str = "argenprop"


# ══════════════════════════════════════════════════════════
#  Logging
# ══════════════════════════════════════════════════════════

def _build_logger() -> logging.Logger:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lg  = logging.getLogger("ap_smoke")
    lg.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    lg.addHandler(ch)
    fh = logging.FileHandler(OUTDIR / f"{STEM}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    lg.addHandler(fh)
    return lg

log = _build_logger()


# ══════════════════════════════════════════════════════════
#  Block / CF detection  — UNCHANGED
# ══════════════════════════════════════════════════════════

_CF_STRONG = [
    r"cf-browser-verification",
    r"Checking your browser",
    r"Attention Required",
    r"verify you are a human",
    r"/cdn-cgi/challenge",
    r"cf-error",
    r"cf-\w+-captcha",
    r"acceso denegado|access denied",
    r"robot|bot detected",
]
_CF_WEAK = [
    r"cloudflare",
    r"challenge-platform",
]

def detect_block(html: str) -> Tuple[bool, str]:
    for pat in _CF_STRONG:
        if re.search(pat, html, re.IGNORECASE):
            return True, f"strong:{pat}"
    hits = [p for p in _CF_WEAK if re.search(p, html, re.IGNORECASE)]
    if len(hits) >= 2:
        return True, f"weak×{len(hits)}:{hits}"
    if len(html) < 5_000:
        return True, "html_too_short"
    return False, ""


# ══════════════════════════════════════════════════════════
#  Helpers  — UNCHANGED
# ══════════════════════════════════════════════════════════

def _txt(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(strip=True)).strip() if el else ""

def _re_first(pattern: str, text: str, group: int = 1) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group).strip() if m else ""

def save_debug(html: str, driver, debug_dir: Path, page_num: int = 1):
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"ap_page_{page_num}.html").write_text(html, encoding="utf-8")
    try:
        driver.save_screenshot(str(debug_dir / f"ap_page_{page_num}.png"))
        log.info("debug.saved | dir=%s page=%d", debug_dir, page_num)
    except Exception as e:
        log.warning("screenshot.fail | %s", e)


# ══════════════════════════════════════════════════════════
#  Pagination detection  — UNCHANGED
# ══════════════════════════════════════════════════════════

def detect_pagination(soup: BeautifulSoup) -> dict:
    info = {"found": False, "current": None, "total_pages": None, "next_url": None}

    next_a = soup.select_one(
        "a[rel='next'], "
        "a.pagination__page--next, "
        "a[aria-label='Siguiente'], "
        "li.pagination__item--next > a"
    )
    if next_a:
        info["found"] = True
        href = next_a.get("href", "")
        info["next_url"] = href if href.startswith("http") \
                           else f"https://www.argenprop.com{href}"

    cur = soup.select_one(
        "a.pagination__page--current, "
        "span.pagination__page--current, "
        "li.pagination__item--current"
    )
    if cur:
        info["current"] = _txt(cur)

    page_links = soup.select("a.pagination__page, li.pagination__item > a")
    nums = []
    for a in page_links:
        t = _txt(a)
        if t.isdigit():
            nums.append(int(t))
    if nums:
        info["total_pages"] = str(max(nums))
        info["found"]       = True

    if not info["current"]:
        m = re.search(r"p[áa]gina\s+(\d+)\s+de\s+(\d+)", soup.get_text(), re.IGNORECASE)
        if m:
            info["found"]       = True
            info["current"]     = m.group(1)
            info["total_pages"] = m.group(2)

    return info


# ══════════════════════════════════════════════════════════
#  Card parser  — UNCHANGED
# ══════════════════════════════════════════════════════════

_CARD_SELECTORS = [
    "div.listing__item",
    "div.postings-container > div",
    "li.listing__item",
    "article.card",
]

def _find_cards(soup: BeautifulSoup) -> list:
    for sel in _CARD_SELECTORS:
        cards = soup.select(sel)
        if len(cards) >= 3:
            log.debug("cards.selector | sel=%r count=%d", sel, len(cards))
            return cards
    log.warning("cards.fallback | no selector matched, returning []")
    return []

def build_embedding_text(it: "APItem") -> str:
    """
    Arma una narrativa en lenguaje natural con todos los campos disponibles.
    Diseñada para pasar por un modelo de embeddings y hacer RAG:
      - Sin claves técnicas ni IDs
      - Fluida y densa en términos de búsqueda
      - Incluye sinónimos implícitos (ambientes / dormitorios)
    """
    parts = []

    # Tipo de operación y zona
    parts.append(f"Departamento en venta en Belgrano, Buenos Aires.")

    # Título si es informativo
    if it.title and len(it.title) > 10:
        parts.append(it.title.strip(".") + ".")

    # Precio
    if it.price and it.currency:
        # Limpiar precio concatenado (precio+expensas juntos)
        price_clean = it.price.split(".")[0] if len(it.price) > 10 else it.price
        parts.append(f"Precio: {it.currency} {price_clean}.")

    # Expensas
    if it.expensas:
        parts.append(f"Expensas: {it.expensas}.")

    # Ambientes y dormitorios
    amb_parts = []
    if it.ambientes:
        amb_parts.append(f"{it.ambientes} ambientes")
    if it.dormitorios:
        amb_parts.append(f"{it.dormitorios} dormitorios")
    if it.banos:
        amb_parts.append(f"{it.banos} baños")
    if amb_parts:
        parts.append("Distribución: " + ", ".join(amb_parts) + ".")

    # Superficie
    m2_parts = []
    if it.m2_total:
        m2_parts.append(f"{it.m2_total} m² totales")
    if it.m2_cover and it.m2_cover != it.m2_total:
        m2_parts.append(f"{it.m2_cover} m² cubiertos")
    if m2_parts:
        parts.append("Superficie: " + ", ".join(m2_parts) + ".")

    # Dirección
    if it.location:
        parts.append(f"Ubicación: {it.location}.")

    # Agencia
    if it.agency:
        parts.append(f"Inmobiliaria: {it.agency}.")

    return " ".join(parts)


def _parse_card(card) -> Optional[APItem]:
    a_tag = (
        card.select_one("a[href*='argenprop.com']")
        or card.select_one("a[href^='/']")
    )
    if not a_tag:
        return None
    href = a_tag.get("href", "")
    url  = href if href.startswith("http") else f"https://www.argenprop.com{href}"

    portal_id = card.get("data-id") or card.get("data-posting-id")
    if not portal_id:
        m = re.search(r"-(\d{6,})(?:\.html|$)", url)
        portal_id = m.group(1) if m else None

    title_el = card.select_one(".card__title") or card.select_one("h2, h3")
    title = _txt(title_el) or None

    price_el  = card.select_one(".card__price, .price")
    price_raw = _txt(price_el)
    currency  = "USD" if re.search(r"USD|U\$S|u\$s", price_raw) else \
                "ARS" if "$" in price_raw else None
    price = re.sub(r"[^\d\.]", "", price_raw) or None

    exp_el   = card.select_one(".card__expenses, .expenses")
    expensas = _txt(exp_el) or None

    loc_el   = card.select_one(".card__address, .posting-location")
    location = _txt(loc_el) or None

    feat_el    = card.select_one(".card__main-features, .card__features, ul.card-tags")
    feat_text  = _txt(feat_el)
    feat_items = [_txt(li) for li in (feat_el.select("li") if feat_el else [])]
    feat_joined = " | ".join(feat_items) or feat_text

    ambientes   = _re_first(r"(\d+)\s*amb",             feat_joined) or None
    dormitorios = _re_first(r"(\d+)\s*dorm",            feat_joined) or None
    banos       = _re_first(r"(\d+)\s*ba[ñn]",         feat_joined) or None
    m2_total    = _re_first(r"(\d[\d\.]+)\s*m²?\s*tot", feat_joined) \
                  or _re_first(r"(\d[\d\.]+)\s*m²",     feat_joined) or None
    m2_cover    = _re_first(r"(\d[\d\.]+)\s*m²?\s*cub", feat_joined) or None

    ag_el  = card.select_one(".card__publisher, .publisher-name, .posting-contact")
    agency = _txt(ag_el) or None

    item = APItem(
        url=url, title=title, price=price, currency=currency,
        location=location, m2_total=m2_total, m2_cover=m2_cover,
        ambientes=ambientes, dormitorios=dormitorios, banos=banos,
        expensas=expensas, agency=agency, portal_id=portal_id,
    )
    item.text_for_embedding = build_embedding_text(item)
    return item


def parse_cards(soup: BeautifulSoup) -> List[APItem]:
    raw_cards = _find_cards(soup)
    items: List[APItem] = []
    seen:  set          = set()
    for card in raw_cards:
        try:
            it = _parse_card(card)
        except Exception as e:
            log.debug("card.parse.error | %s", e)
            continue
        if it and it.url and it.url not in seen:
            seen.add(it.url)
            items.append(it)
    return items


def parse_regex_fallback(html: str) -> List[APItem]:
    items: List[APItem] = []
    seen:  set          = set()
    for m in re.finditer(r'href="(/[^"]+)"', html):
        href = m.group(1)
        if not re.search(r"/(departamento|casa|ph|oficina|local|terreno|propiedad)", href, re.I):
            continue
        url = f"https://www.argenprop.com{href}"
        if url in seen:
            continue
        seen.add(url)
        pid = re.search(r"-(\d{6,})(?:\.html|$)", url)
        items.append(APItem(url=url, portal_id=pid.group(1) if pid else None))
    return items


# ══════════════════════════════════════════════════════════
#  Exports  — UNCHANGED
# ══════════════════════════════════════════════════════════

_CSV_COLS = [
    "url","title","price","currency","location",
    "m2_total","m2_cover","ambientes","dormitorios","banos",
    "expensas","agency","portal_id","text_for_embedding","source",
]

def write_txt(path: Path, items: List[APItem], pagination: dict):
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# Argenprop Smoke Probe\n# URL: {SEARCH_URL}\n")
        f.write(f"# Items: {len(items)}\n")
        if pagination["found"]:
            f.write(f"# Paginación: pág {pagination['current']} / {pagination['total_pages']}\n")
            if pagination["next_url"]:
                f.write(f"# Next page: {pagination['next_url']}\n")
        f.write("\n")
        for i, it in enumerate(items, 1):
            f.write(f"## {i}. {it.title or '(sin título)'}\n")
            if it.price:       f.write(f"   Precio      : {it.currency or ''} {it.price}\n")
            if it.expensas:    f.write(f"   Expensas    : {it.expensas}\n")
            if it.location:    f.write(f"   Ubicación   : {it.location}\n")
            if it.ambientes:   f.write(f"   Ambientes   : {it.ambientes}\n")
            if it.dormitorios: f.write(f"   Dormitorios : {it.dormitorios}\n")
            if it.banos:       f.write(f"   Baños       : {it.banos}\n")
            if it.m2_total:    f.write(f"   m² totales  : {it.m2_total}\n")
            if it.m2_cover:    f.write(f"   m² cubiertos: {it.m2_cover}\n")
            if it.agency:      f.write(f"   Agencia     : {it.agency}\n")
            if it.portal_id:   f.write(f"   ID portal   : {it.portal_id}\n")
            if it.url:         f.write(f"   URL         : {it.url}\n")
            if it.text_for_embedding: f.write(f"   Embedding   : {it.text_for_embedding}\n")
            f.write("\n")

def write_csv(path: Path, items: List[APItem]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLS)
        w.writeheader()
        for it in items:
            w.writerow(asdict(it))

def write_json(path: Path, items: List[APItem], pagination: dict):
    payload = {
        "meta": {"url": SEARCH_URL, "count": len(items), "pagination": pagination},
        "items": [asdict(it) for it in items],
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
#  Driver  — UNCHANGED
# ══════════════════════════════════════════════════════════

def build_driver() -> webdriver.Chrome:
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=es-AR,es")
    opts.add_argument("--disable-extensions")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if PROFILE_DIR:
        opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    return webdriver.Chrome(options=opts)


# ══════════════════════════════════════════════════════════
#  URL builder  ← ÚNICA función nueva
# ══════════════════════════════════════════════════════════

def build_page_url(base_url: str, page: int) -> str:
    """
    Página 1 → URL original sin cambios
    Página N → agrega ?pagina=N (o reemplaza si ya existe)
    """
    if page == 1:
        return base_url
    clean = re.sub(r"[?&]pagina=\d+", "", base_url)
    sep   = "&" if "?" in clean else "?"
    return f"{clean}{sep}pagina={page}"


# ══════════════════════════════════════════════════════════
#  Main  ← loop multi-página, misma lógica interna
# ══════════════════════════════════════════════════════════

_WAIT_SEL = ", ".join([
    "div.listing__item",
    "div.card",
    "article.card",
    "#g-recaptcha",
    ".cf-browser-verification",
])

def main() -> int:
    log.info("probe.start | url=%s  headless=%s  profile=%s  max_pages=%s  page_wait=%.1fs",
             SEARCH_URL, HEADLESS, PROFILE_DIR or "(none)",
             MAX_PAGES if MAX_PAGES > 0 else "unlimited", PAGE_WAIT)

    debug_dir = OUTDIR / "debug"
    txt_path  = OUTDIR / f"{STEM}.txt"
    csv_path  = OUTDIR / f"{STEM}.csv"
    json_path = OUTDIR / f"{STEM}.json"

    try:
        driver = build_driver()
    except WebDriverException as e:
        log.error("chrome.init.error | %s", e)
        return 2

    all_items:  List[APItem] = []
    seen_urls:  set          = set()
    last_pag                 = {"found": False, "current": None, "total_pages": None, "next_url": None}
    any_blocked              = False
    limit                    = MAX_PAGES if MAX_PAGES > 0 else 10_000

    # Página 1 = SEARCH_URL; siguientes = next_url detectado en la paginación
    next_url = SEARCH_URL

    try:
        for page_num in range(1, limit + 1):
            url = next_url
            log.info("─── PAGE %d | %s", page_num, url)

            driver.get(url)
            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, _WAIT_SEL))
                )
            except TimeoutException:
                log.warning("wait.timeout | page=%d", page_num)

            time.sleep(1.5)

            html = driver.page_source or ""
            save_debug(html, driver, debug_dir, page_num)

            blocked, reason = detect_block(html)
            if blocked:
                # Solo loguear — argenprop tiene falsos positivos de CF
                log.warning("block.detected | page=%d reason=%s", page_num, reason)
                any_blocked = True

            soup = BeautifulSoup(html, "html.parser")

            pagination = detect_pagination(soup)
            last_pag   = pagination
            log.info("pagination | found=%s current=%s total=%s next=%s",
                     pagination["found"], pagination["current"],
                     pagination["total_pages"], pagination["next_url"])

            items = parse_cards(soup)
            log.info("parse.css | page=%d found=%d", page_num, len(items))

            if not items:
                items = parse_regex_fallback(html)
                log.info("parse.regex.fallback | page=%d found=%d", page_num, len(items))

            new_items = [it for it in items if it.url not in seen_urls]
            for it in new_items:
                seen_urls.add(it.url)
            all_items.extend(new_items)

            log.info("page.done | page=%d new=%d total=%d blocked=%s",
                     page_num, len(new_items), len(all_items), blocked)

            for i, it in enumerate(new_items[:3], 1):
                log.info("  sample[%d] | price=%s %s | amb=%s | m2=%s | loc=%s",
                         i, it.currency, it.price, it.ambientes,
                         it.m2_total, (it.location or "")[:50])

            # Avanzar usando el next_url real de la paginación
            next_url = pagination.get("next_url") or ""
            if not next_url:
                log.info("stopping | no next_url (última página)")
                break
            if not new_items:
                log.info("stopping | no new items")
                break

            if page_num < limit:
                log.info("sleeping %.1fs…", PAGE_WAIT)
                time.sleep(PAGE_WAIT)

        # ── Exports ──────────────────────────────────────────
        if all_items:
            write_txt(txt_path,  all_items, last_pag)
            write_csv(csv_path,  all_items)
            write_json(json_path, all_items, last_pag)
            for p in (txt_path, csv_path, json_path):
                log.info("export.ok | %s (%d bytes)", p, p.stat().st_size)
            log.info("probe.end | status=OK pages=%d count=%d blocked=%s",
                     page_num, len(all_items), any_blocked)
            print(f"\nOK | pages={page_num} | count={len(all_items)} | blocked={any_blocked}")
            return 0
        else:
            log.warning("probe.end | status=NO_RESULTS blocked=%s", any_blocked)
            print(f"\nNO_RESULTS | count=0 | blocked={any_blocked}")
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