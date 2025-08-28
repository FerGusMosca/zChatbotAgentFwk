from __future__ import annotations
import re
import time
from pathlib import Path
from typing import Optional, Dict, Iterable, Callable, List

from common.util.settings.env_deploy_reader import EnvDeployReader

# ==== Use the SAME driver style as your working probe ====
USE_PLAIN_SELENIUM = True

if USE_PLAIN_SELENIUM:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
else:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By

from selectolax.parser import HTMLParser, Node
from logic.intents.demos.intents_execution.real_state_parsers.models import ZpListing


# =============== URL helpers (match the probe) ===============

def build_seo_landing(barrio: str, op: str) -> str:
    seg = "alquiler" if op == "alquiler" else "venta"
    slug = (barrio or "").replace(" ", "-")
    return f"https://www.argenprop.com/departamento-{seg}-barrio-{slug}"

def build_catalog(barrio: str, op: str, page: int = 1) -> str:
    seg = "alquiler" if op == "alquiler" else "venta"
    slug = (barrio or "").replace(" ", "-")
    base = f"https://www.argenprop.com/departamentos/{seg}/{slug}"
    return base if page == 1 else f"{base}?pagina={page}"

def page_url(base: str, page: int) -> str:
    return base if page == 1 else f"{base}?pagina={page}"

def normalize_href(href: str) -> str:
    if not href:
        return ""
    return "https://www.argenprop.com" + href if href.startswith("/") else href


# =============== Predicates (probe-like, permissive) ===============

HOST_RE  = re.compile(r"argenprop\.com", re.IGNORECASE)
PATH_RE  = re.compile(r"/(propiedad|departamento|casa|ph|oficina|local)", re.IGNORECASE)
NUMID_RE = re.compile(r"-([0-9]{6,})(?:\.html)?$", re.IGNORECASE)

def is_ap_url(url: str) -> bool:
    return bool(url and (url.startswith("/") or HOST_RE.search(url)))

def looks_like_property(url: str) -> bool:
    """
    Accepts both catalog and detail-like URLs (broad, like the probe).
    Detail URLs often end with -<digits>.html, but we DO NOT require it here.
    """
    if not url:
        return False
    u = normalize_href(url)
    return bool(PATH_RE.search(u) or NUMID_RE.search(u))


# ======================= SCRAPER CLASS =======================

class DownloadArgenpropPropertyDemo:
    """
    Argenprop scraper — mirrors argenprop_local_probe behavior:

    Flow:
    1) Open SEO landing (/departamento-venta-barrio-<slug>).
    2) If a "ver-mas-anuncios" link exists, follow it (landing → catalog).
    3) Parse anchors broadly (PATH_RE) and lift to a card-ish container to extract fields.
    4) If page produced 0 items, fallback to the catalog URL (/departamentos/venta/<slug>).
    5) Export ONE TXT to exports/.
    """

    def __init__(
        self,
        logger,
        outdir: str = "exports",
        max_pages: int = int(EnvDeployReader.get("PAGES_TO_DOWNLOAD")),
        sleep_secs: float = 0.8,
        listing_validator: Optional[Callable[[ZpListing, str], bool]] = None,
        *,
        headless: bool = False,
        profile_dir: Optional[str] = None,  # TIP: start with None to avoid logged-in redirects
        dump_debug_html: bool = True,
    ):
        if listing_validator is None:
            raise ValueError("listing_validator is required.")

        self.logger = logger
        self.outdir = Path(outdir); self.outdir.mkdir(parents=True, exist_ok=True)
        self.max_pages = max_pages
        self.sleep_secs = sleep_secs
        self.listing_validator = listing_validator

        self.headless = headless
        self.profile_dir = Path(profile_dir) if profile_dir else None
        if self.profile_dir:
            self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.dump_debug_html = dump_debug_html
        self._pages_scanned = 0

    # ---------------- Driver ----------------

    def _make_driver(self):
        if USE_PLAIN_SELENIUM:
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1280,900")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--lang=es-AR")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            if self.profile_dir:
                options.add_argument(f"--user-data-dir={self.profile_dir}")
            drv = webdriver.Chrome(options=options)
            return drv
        else:
            opts = uc.ChromeOptions()
            if self.headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--lang=es-AR")
            if self.profile_dir:
                opts.add_argument(f"--user-data-dir={self.profile_dir}")
                opts.add_argument("--profile-directory=Default")
            drv = uc.Chrome(options=opts)
            drv.set_window_size(1366, 900)
            try:
                drv.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Referer": "https://www.google.com/"}})
            except Exception:
                pass
            return drv

    def _fetch_html(self, url: str) -> str:
        """Open URL, best-effort close cookie banner, lazy-scroll, dump, return HTML."""
        driver = None
        try:
            driver = self._make_driver()
            self.logger.info(f"ap.nav | GET {url}")
            driver.get(url)

            # Cookie banner (best effort)
            try:
                for xp in (
                    "//button[contains(.,'Acepto') or contains(.,'Aceptar')]",
                    "//div[contains(@class,'cookie') or contains(.,'cookie') or contains(.,'cookies')]//button",
                    "//button[contains(.,'Entendido') or contains(.,'Continuar')]",
                ):
                    btns = driver.find_elements(By.XPATH, xp)
                    if btns and btns[0].is_displayed():
                        btns[0].click()
                        self.logger.info("ap.cookie.banner.closed")
                        break
            except Exception:
                self.logger.info("ap.cookie.banner.skip")

            # Render + lazy
            time.sleep(2.0)
            for _ in range(8):
                driver.execute_script("window.scrollBy(0, 1400);")
                time.sleep(0.35)

            html = driver.page_source or ""

            if self.dump_debug_html:
                dbg = self.outdir / "debug"
                dbg.mkdir(parents=True, exist_ok=True)
                (dbg / "ap_last_page.html").write_text(html, encoding="utf-8")
                try:
                    driver.save_screenshot(str(dbg / "ap_last_page.png"))
                except Exception:
                    pass

            return html
        except Exception as e:
            self.logger.exception(f"ap.selenium.error | {e!r}")
            return ""
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # ---------------- Probe-like parsing ----------------

    def _parse_probe_like(self, doc: HTMLParser) -> List[ZpListing]:
        """
        Broadly scan anchors like the probe, accept property-like URLs,
        climb 2–3 parents to get a 'card-ish' container, and extract fields.
        """
        items: List[ZpListing] = []
        anchors = doc.css("a[href]")
        self.logger.info(f"ap.parse.scan | anchors={len(anchors)}")

        # collect a few samples for visibility
        samp_any: List[str] = []
        samp_prop: List[str] = []

        for a in anchors:
            href = a.attributes.get("href") or ""
            full = normalize_href(href)
            if len(samp_any) < 10:
                samp_any.append(full)

            if not is_ap_url(full) or not looks_like_property(full):
                continue
            if len(samp_prop) < 10:
                samp_prop.append(full)

            # climb to card-ish container
            card = a
            for _ in range(3):
                if getattr(card, "parent", None):
                    card = card.parent

            # title
            title = (a.text(strip=True) if hasattr(a, "text") else None)
            if not title:
                h = card.css_first("h2") or card.css_first("h3")
                title = (h.text(strip=True) if h else None)

            # price (very permissive)
            price = None
            for p in card.css("span, p, div"):
                t = p.text(strip=True)
                if t and re.search(r"\$\s?[\d\.]", t):
                    price = t; break

            # location
            location = None
            for p in card.css("p, span, div"):
                t = p.text(strip=True)
                if t and re.search(r"(Belgrano|CABA|Capital|Buenos Aires)", t, re.IGNORECASE):
                    location = t; break

            # details
            details = None
            for p in card.css("ul, div, p"):
                t = p.text(strip=True)
                if t and re.search(r"(amb|m²|m2|dorm|bañ)", t, re.IGNORECASE):
                    details = t; break

            # agency
            agency = None
            for p in card.css("span, div, p"):
                t = p.text(strip=True)
                if t and re.search(r"(inmobiliaria|realtor|broker|propiedades|sociedad)", t, re.IGNORECASE):
                    agency = t; break

            # portal id (optional)
            m = NUMID_RE.search(full)
            portal_id = m.group(1) if m else None

            items.append(ZpListing(
                id=f"ap:{portal_id or full}",
                url=full,
                title=title,
                price=price,
                location=location,
                details=details,
                agency=agency,
                source="argenprop",
                portal_id=portal_id,
            ))

        self.logger.info("ap.diag.samples_any | " + " | ".join(samp_any))
        self.logger.info("ap.diag.samples_prop | " + " | ".join(samp_prop))
        # dedupe by id/url
        out: Dict[str, ZpListing] = {}
        for it in items:
            key = it.id or it.url
            if key and key not in out:
                out[key] = it
        return list(out.values())

    # ---------------- Scrape loop ----------------

    def _scrape(self, barrio: str, operacion: Optional[str]) -> List[ZpListing]:
        op = (operacion or "venta").strip().lower()
        landing = build_seo_landing(barrio, op)
        catalog_base = build_catalog(barrio, op, page=1)

        acc: Dict[str, ZpListing] = {}
        pages_scanned = 0
        t0 = time.monotonic()

        self.logger.info(f"ap.scrape.start | landing={landing} | catalog_base={catalog_base} | max_pages={self.max_pages}")

        # 1) Landing
        html = self._fetch_html(landing)
        if html:
            doc = HTMLParser(html)
            title = (doc.css_first("title").text(strip=True) if doc.css_first("title") else "")
            self.logger.info(f"ap.diag.landing | title={title!r} bytes={len(html.encode('utf-8'))}")

            # follow "ver más anuncios" if present
            more_a = doc.css_first("a[href*='ver-mas-anuncios']")
            if more_a:
                target = normalize_href(more_a.attributes.get("href") or "")
                self.logger.info(f"ap.landing.more_link | {target}")
                html = self._fetch_html(target)
                doc = HTMLParser(html) if html else doc

            # parse like the probe on current DOM
            items = self._parse_probe_like(doc)
            self.logger.info(f"ap.landing.items | found={len(items)}")
            for it in items:
                key = it.id or it.url
                if key not in acc:
                    acc[key] = it

        # 2) Fallback to catalog if landing produced zero
        if not acc:
            self.logger.info("ap.fallback.catalog | landing gave 0 items, going to catalog 1..N")
            for page in range(1, self.max_pages + 1):
                url = page_url(catalog_base, page)
                html = self._fetch_html(url)
                if not html:
                    break
                doc = HTMLParser(html)
                items = self._parse_probe_like(doc)
                self.logger.info(f"ap.catalog.items | page={page} found={len(items)}")
                pages_scanned = page
                new_items = 0
                for it in items:
                    key = it.id or it.url
                    if key not in acc:
                        acc[key] = it
                        new_items += 1
                self.logger.info(f"ap.page.done | page={page} new={new_items} total={len(acc)}")
                if new_items == 0:
                    break
                time.sleep(self.sleep_secs)

        self._pages_scanned = pages_scanned
        self.logger.info(f"ap.scrape.end | pages_scanned={pages_scanned} total={len(acc)} dt={time.monotonic()-t0:.1f}s")
        return list(acc.values())

    # ---------------- Public API ----------------

    def run(self, barrio: str, operacion: Optional[str] = None, export: bool = True) -> dict:
        try:
            op = (operacion or "venta").strip().lower()
            nb_raw = (barrio or "").strip()
            is_all_caba = (nb_raw == "")
            nb_for_url = ("capital federal" if is_all_caba else nb_raw).lower()
            target_for_validator = ("caba" if is_all_caba else nb_raw.lower())

            listings = self._scrape(nb_for_url, op)

            kept: List[ZpListing] = []
            for it in listings:
                try:
                    if self.listing_validator(it, target_for_validator):
                        kept.append(it)
                except Exception as ex:
                    self.logger.warning(f"ap.validator.warn | {ex} | url={getattr(it,'url',None)}")

            if not export:
                return {"ok": True, "file": None, "count": len(kept), "listings": kept}

            barrio_tag = ("caba" if is_all_caba else nb_raw.lower())
            fpath = self._export_txt(barrio_tag, kept, op)
            nice_area = ("CABA" if is_all_caba else nb_raw.title())
            msg = f"✅ Downloaded {len(kept)} properties from Argenprop ({nice_area}). File: {fpath.name}"
            return {"ok": True, "file": str(fpath), "count": len(kept), "message": msg}

        except Exception as e:
            self.logger.exception(f"argenprop.run.error | {e!r}")
            return {"ok": False, "message": f"Unhandled error: {e!r}"}

    # ---------------- Export ----------------

    def _export_txt(self, barrio: str, listings: Iterable[ZpListing], operacion: Optional[str]) -> Path:
        ts = time.strftime("%Y%m%d_%H%M")
        suffix = f"_{operacion}" if operacion else ""
        fname = f"{barrio.replace(' ', '_')}{suffix}_ARGENPROP_{ts}.txt"
        fpath = self.outdir / fname

        pages = getattr(self, "_pages_scanned", 0)
        lines = [
            f"# Argenprop — {barrio.title()} ({operacion or 'general'}) — {ts}",
            f"# Pages scanned: {pages}",
            "",
        ]

        seen = set()
        for i, it in enumerate(listings, 1):
            if it.id in seen:
                continue
            seen.add(it.id)
            lines.append(f"## {i}. {it.title or '(no title)'}")
            if it.price:    lines.append(f"- Precio: {it.price}")
            if it.location: lines.append(f"- Ubicación: {it.location}")
            if it.details:  lines.append(f"- Detalles: {it.details}")
            if it.agency:   lines.append(f"- Agencia: {it.agency}")
            lines.append(f"- Portal: {it.source}")
            lines.append(f"- URL: {it.url}")
            lines.append("")

        fpath.write_text("\n".join(lines), encoding="utf-8")
        return fpath
