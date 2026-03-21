# zonaprop_smoke_probe.py
"""
Smoke probe for Zonaprop listing pages — multi-page with Cloudflare bypass.

Key design (inspired by DownloadZonapropPropertyDemo):
  - undetected_chromedriver  →  bypasses Cloudflare Turnstile
  - Single driver reused across ALL pages  →  cookies/session stay alive
  - driver.get(url) con URL explícita por página  →  no depende del botón Next
  - Anti-detection extras: scroll, lazy-load trigger, cookie accept

Covers:
  - Cloudflare / block detection
  - Card parsing  (precio, m², ambientes, dormitorios, ubicación, agencia)
  - Pagination por URL  (-pagina-2.html, -pagina-3.html …)
  - Export to TXT / CSV / JSON  →  <root>/exports/

Location: <root>/tests/smoke/zonaprop_smoke_probe.py
Outputs:  <root>/exports/zonaprop_smoke_*.*
          <root>/exports/debug/zp_page_N.html  +  zp_page_N.png

Usage:
  cd <root>
  python tests/smoke/zonaprop_smoke_probe.py

Optional env overrides:
  ZP_URL          full first-page URL  (default: departamentos en venta en Belgrano)
  ZP_HEADLESS     1 | 0                (default: 0 → visible Chrome)
  ZP_MAX_PAGES    max pages to scrape  (default: 5, 0 = unlimited)
  ZP_PAGE_WAIT    seconds between pages (default: 2)
  UC_VERSION_MAIN force Chrome major version for undetected_chromedriver
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
from typing import Dict, List, Optional, Tuple

# ─────────────────────────── CONFIG ──────────────────────────────────────────
SEARCH_URL = os.getenv(
    "ZP_URL",
    "https://www.zonaprop.com.ar/departamentos-venta-belgrano.html",
)
HEADLESS  = os.getenv("ZP_HEADLESS", "0") == "1"
MAX_PAGES = int(os.getenv("ZP_MAX_PAGES", "5"))    # 0 = sin límite
PAGE_WAIT = float(os.getenv("ZP_PAGE_WAIT", "2"))  # segundos entre páginas
UC_VER    = os.getenv("UC_VERSION_MAIN", "").strip()

_ROOT  = Path(__file__).resolve().parents[2]
OUTDIR = _ROOT / "exports"
STEM   = "zonaprop_smoke"
# ─────────────────────────────────────────────────────────────────────────────

import undetected_chromedriver as uc
from selenium.common.exceptions import SessionNotCreatedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup


# ══════════════════════════════════════════════════════════
#  Model
# ══════════════════════════════════════════════════════════

@dataclass
class ZPItem:
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
    source:             str = "zonaprop"


# ══════════════════════════════════════════════════════════
#  Logging
# ══════════════════════════════════════════════════════════

def _build_logger() -> logging.Logger:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lg  = logging.getLogger("zp_smoke")
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
#  URL builder  (mismo patrón que DownloadZonapropPropertyDemo)
# ══════════════════════════════════════════════════════════

def build_page_url(base_url: str, page: int) -> str:
    """
    Página 1 → url original
    Página N → quita .html, agrega -pagina-N.html
    Ej: .../departamentos-venta-belgrano.html → ...-pagina-2.html
    """
    if page == 1:
        return base_url
    clean = re.sub(r"(-pagina-\d+)?\.html$", "", base_url)
    return f"{clean}-pagina-{page}.html"


# ══════════════════════════════════════════════════════════
#  Driver  (undetected_chromedriver + auto-retry de versión)
# ══════════════════════════════════════════════════════════

def _make_opts() -> uc.ChromeOptions:
    """Siempre devuelve un objeto ChromeOptions NUEVO (no se puede reusar entre boots)."""
    opts = uc.ChromeOptions()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--lang=es-AR,es")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    return opts


def build_driver():
    def _boot(ver):
        # Cada intento necesita su propio ChromeOptions nuevo
        return uc.Chrome(options=_make_opts()) if ver is None \
               else uc.Chrome(options=_make_opts(), version_main=ver)

    # Detectar versión de Chrome ANTES de arrancar uc para evitar
    # el primer intento ciego que deja procesos colgados/puertos ocupados.
    forced = None
    if UC_VER:
        forced = int(UC_VER)
    else:
        import subprocess, shutil
        _candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
        ]
        _which_chrome = shutil.which("google-chrome") or shutil.which("chromium") or ""
        if _which_chrome:
            _candidates.append(_which_chrome)
        for candidate in _candidates:
            if candidate and Path(candidate).exists():
                try:
                    out = subprocess.check_output(
                        [candidate, "--version"], stderr=subprocess.DEVNULL, timeout=5
                    ).decode()
                    _m = re.search(r"(\d+)\.\d+\.\d+", out)
                    if _m:
                        forced = int(_m.group(1))
                        log.info("chrome.version.detected | version_main=%d", forced)
                        break
                except Exception:
                    pass

    try:
        driver = _boot(forced)
    except SessionNotCreatedException as e:
        _m2 = re.search(r"Current browser version is (\d+)", str(e))
        if not _m2:
            raise
        local_ver = int(_m2.group(1))
        log.warning("uc.retry | version_main=%d", local_ver)
        driver = _boot(local_ver)

    driver.set_window_size(1366, 900)

    # Simular que viene de Google
    try:
        driver.execute_cdp_cmd(
            "Network.setExtraHTTPHeaders",
            {"headers": {"Referer": "https://www.google.com/"}}
        )
    except Exception:
        pass

    return driver


# ══════════════════════════════════════════════════════════
#  Block detection
# ══════════════════════════════════════════════════════════

_CF_PATTERNS = [
    r"cloudflare", r"cf-browser-verification", r"Checking your browser",
    r"Attention Required", r"verify you are a human", r"challenge-platform",
    r"/cdn-cgi/challenge", r"cf-error", r"cf-\w+-captcha",
    r"robot|bot detected|acceso denegado|access denied",
]

def detect_block(html: str) -> Tuple[bool, str]:
    for pat in _CF_PATTERNS:
        if re.search(pat, html, re.IGNORECASE):
            return True, pat
    if len(html) < 5_000:
        return True, "html_too_short"
    return False, ""


# ══════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════

def _txt(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(strip=True)).strip() if el else ""

def _re_first(pattern: str, text: str, group=1, default="") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group).strip() if m else default

def save_debug(html: str, driver, page_num: int):
    d = OUTDIR / "debug"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"zp_page_{page_num}.html").write_text(html, encoding="utf-8")
    try:
        driver.save_screenshot(str(d / f"zp_page_{page_num}.png"))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
#  Page loader  (scroll + cookie accept — igual que demo)
# ══════════════════════════════════════════════════════════

_WAIT_SEL = (
    "[data-qa*='posting'], [data-testid*='posting'], "
    "article[class*='posting'], div[class*='posting'], "
    "#g-recaptcha, .cf-browser-verification"
)

def load_page(driver, url: str, page_num: int) -> str:
    """Navega a url con el driver ya activo. Scroll + acepta cookies. Retorna page_source."""
    driver.get(url)

    try:
        WebDriverWait(driver, 14).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, _WAIT_SEL))
        )
    except TimeoutException:
        log.warning("wait.timeout | page=%d", page_num)

    # Aceptar cookies si aparece popup
    for xpath in [
        "//button[contains(.,'Acept')]",
        "//button[contains(.,'Entendido')]",
        "//button[contains(.,'continuar')]",
    ]:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            if btns and btns[0].is_displayed():
                btns[0].click()
                break
        except Exception:
            pass

    # Scroll para trigger lazy-load
    try:
        for _ in range(4):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(0.35)
    except Exception:
        pass

    return driver.page_source or ""


# ══════════════════════════════════════════════════════════
#  Card parsing
# ══════════════════════════════════════════════════════════

_CARD_SELECTORS = [
    "div[data-qa='posting PROPERTY']",
    "article[class*='posting']",
    "li[class*='posting']",
    "div[class*='posting']",
    "[data-qa*='posting-card']",
    "[data-testid*='posting']",
    "article.card",
]

def _find_cards(soup: BeautifulSoup) -> list:
    for sel in _CARD_SELECTORS:
        cards = soup.select(sel)
        if cards:
            log.debug("cards.sel=%r count=%d", sel, len(cards))
            return cards
    return []

def build_embedding_text(it: "ZPItem") -> str:
    """
    Narrativa en lenguaje natural para pasar por embeddings y hacer RAG.
    ZonaProp tiene ambientes bien parseado y precio separado de expensas.
    """
    parts = []

    parts.append("Departamento en venta en Belgrano, Buenos Aires.")

    if it.title and len(it.title) > 10:
        parts.append(it.title.strip(".") + ".")

    if it.price and it.currency:
        parts.append(f"Precio: {it.currency} {it.price}.")

    if it.expensas:
        parts.append(f"Expensas: {it.expensas}.")

    amb_parts = []
    if it.ambientes:   amb_parts.append(f"{it.ambientes} ambientes")
    if it.dormitorios: amb_parts.append(f"{it.dormitorios} dormitorios")
    if it.banos:       amb_parts.append(f"{it.banos} baños")
    if amb_parts:
        parts.append("Distribución: " + ", ".join(amb_parts) + ".")

    m2_parts = []
    if it.m2_total:  m2_parts.append(f"{it.m2_total} m² totales")
    if it.m2_cover and it.m2_cover != it.m2_total:
        m2_parts.append(f"{it.m2_cover} m² cubiertos")
    if m2_parts:
        parts.append("Superficie: " + ", ".join(m2_parts) + ".")

    if it.location:
        parts.append(f"Ubicación: {it.location}.")

    if it.agency:
        parts.append(f"Inmobiliaria: {it.agency}.")

    return " ".join(parts)


def _parse_card(card) -> Optional[ZPItem]:
    a_tag = card.select_one("a[href]")
    if not a_tag:
        return None
    href = a_tag.get("href", "")
    url  = href if href.startswith("http") else f"https://www.zonaprop.com.ar{href}"

    pid_m     = re.search(r"-(\d{6,})\.", url)
    portal_id = pid_m.group(1) if pid_m else None

    title_el = card.select_one("[data-qa='POSTING_CARD_DESCRIPTION'], h2, h3")
    title    = _txt(title_el) or None

    price_el  = card.select_one("[data-qa='POSTING_CARD_PRICE'], [class*='price']")
    price_raw = _txt(price_el)
    currency  = "USD" if re.search(r"USD|U\$S", price_raw) else ("ARS" if "$" in price_raw else None)
    price     = re.sub(r"(USD|U\$S|ARS|\$)", "", price_raw).strip() or None

    exp_el   = card.select_one("[data-qa='POSTING_CARD_EXPENSES'], [class*='expense']")
    expensas = _txt(exp_el) or None

    loc_el   = card.select_one("[data-qa='POSTING_CARD_LOCATION'], [class*='location'], [class*='address']")
    location = _txt(loc_el) or None

    feat_el   = card.select_one("[data-qa='POSTING_CARD_FEATURES'], [class*='feature'], [class*='main-features']")
    feat_text = _txt(feat_el)

    ambientes   = _re_first(r"(\d+)\s*amb", feat_text) or None
    dormitorios = _re_first(r"(\d+)\s*dorm", feat_text) or None
    banos       = _re_first(r"(\d+)\s*ba[ñn]", feat_text) or None
    m2_total    = _re_first(r"(\d[\d\.]+)\s*m²?\s*tot", feat_text) or \
                  _re_first(r"(\d[\d\.]+)\s*m²", feat_text) or None
    m2_cover    = _re_first(r"(\d[\d\.]+)\s*m²?\s*cub", feat_text) or None

    ag_el  = card.select_one("[data-qa='POSTING_CARD_PUBLISHER'], [class*='agency'], [class*='publisher']")
    agency = _txt(ag_el) or None

    item = ZPItem(
        url=url, title=title, price=price, currency=currency,
        location=location, m2_total=m2_total, m2_cover=m2_cover,
        ambientes=ambientes, dormitorios=dormitorios, banos=banos,
        expensas=expensas, agency=agency, portal_id=portal_id,
    )
    item.text_for_embedding = build_embedding_text(item)
    return item

def parse_cards(soup: BeautifulSoup) -> List[ZPItem]:
    items: List[ZPItem] = []
    seen:  set          = set()
    for card in _find_cards(soup):
        try:
            it = _parse_card(card)
        except Exception as e:
            log.debug("card.parse.error | %s", e)
            continue
        if it and it.url and it.url not in seen:
            seen.add(it.url)
            items.append(it)
    return items


# ══════════════════════════════════════════════════════════
#  Exports
# ══════════════════════════════════════════════════════════

_CSV_COLS = [
    "url","title","price","currency","location",
    "m2_total","m2_cover","ambientes","dormitorios","banos",
    "expensas","agency","portal_id","text_for_embedding","source",
]

def write_txt(path: Path, items: List[ZPItem], pages: int):
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# Zonaprop Smoke Probe\n# URL base: {SEARCH_URL}\n")
        f.write(f"# Páginas scrapeadas: {pages} | Items totales: {len(items)}\n\n")
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

def write_csv(path: Path, items: List[ZPItem]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLS)
        w.writeheader()
        for it in items:
            w.writerow(asdict(it))

def write_json(path: Path, items: List[ZPItem], pages: int):
    payload = {"meta": {"url": SEARCH_URL, "pages": pages, "count": len(items)},
               "items": [asdict(it) for it in items]}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════

def main() -> int:
    log.info("probe.start | url=%s  headless=%s  max_pages=%s  page_wait=%.1fs",
             SEARCH_URL, HEADLESS, MAX_PAGES or "unlimited", PAGE_WAIT)

    try:
        driver = build_driver()
    except Exception as e:
        log.error("chrome.init.error | %s", e)
        return 2

    acc: Dict[str, ZPItem] = {}  # dedup por portal_id o url
    pages_done  = 0
    any_blocked = False

    try:
        limit = MAX_PAGES if MAX_PAGES > 0 else 10_000
        for page_num in range(1, limit + 1):
            url = build_page_url(SEARCH_URL, page_num)
            log.info("─── PAGE %d | %s", page_num, url)

            # ── Cargar página con el MISMO driver (sesión viva) ──
            html = load_page(driver, url, page_num)
            save_debug(html, driver, page_num)

            blocked, reason = detect_block(html)
            if blocked:
                log.warning("block.detected | page=%d reason=%s", page_num, reason)
                any_blocked = True

            soup  = BeautifulSoup(html, "html.parser")
            items = parse_cards(soup)
            log.info("parse | page=%d found=%d", page_num, len(items))

            new = 0
            for it in items:
                key = f"zp:{it.portal_id or it.url}"
                if key not in acc:
                    acc[key] = it
                    new += 1

            log.info("new=%d | total_acc=%d", new, len(acc))
            pages_done = page_num

            for it in items[:3]:
                log.info("  · %s %s | amb=%s | %s",
                         it.currency, it.price, it.ambientes, (it.location or "")[:50])

            # Stop conditions
            if blocked and new == 0:
                log.warning("stopping | blocked + no items")
                break
            if new == 0:
                log.info("stopping | no new items (última página)")
                break

            if page_num < limit:
                log.info("sleeping %.1fs…", PAGE_WAIT)
                time.sleep(PAGE_WAIT)

        # ── Exports ──────────────────────────────────────────
        all_items = list(acc.values())
        if all_items:
            write_txt(OUTDIR / f"{STEM}.txt",  all_items, pages_done)
            write_csv(OUTDIR / f"{STEM}.csv",  all_items)
            write_json(OUTDIR / f"{STEM}.json", all_items, pages_done)
            for suf in ("txt", "csv", "json"):
                p = OUTDIR / f"{STEM}.{suf}"
                log.info("export.ok | %s (%d bytes)", p, p.stat().st_size)
            log.info("probe.end | OK pages=%d count=%d blocked=%s",
                     pages_done, len(all_items), any_blocked)
            print(f"\nOK | pages={pages_done} | count={len(all_items)} | blocked={any_blocked}")
            return 0
        else:
            log.warning("probe.end | NO_RESULTS pages=%d blocked=%s", pages_done, any_blocked)
            print(f"\nNO_RESULTS | pages={pages_done} | count=0 | blocked={any_blocked}")
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