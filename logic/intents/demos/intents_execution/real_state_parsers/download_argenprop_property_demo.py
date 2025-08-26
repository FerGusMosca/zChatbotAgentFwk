from __future__ import annotations
import re, time
from pathlib import Path
from typing import Optional, Dict, Iterable
import httpx
from selectolax.parser import HTMLParser
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc

from logic.intents.demos.intents_execution.real_state_parsers.models import ZpListing


# reuse the model to keep the coordinator simple


class DownloadArgenpropPropertyDemo:
    """
    Argenprop scraper (venta).
    Design mirrors the Zonaprop scraper:
    - httpx first; fallback to real Chrome (undetected-chromedriver) on non-200/blocks
    - defensive selectors
    - external validator callback (LLM) decides whether to keep a card
    """

    def __init__(
        self,
        logger,
        outdir: str = "exports",
        max_pages: int = 1,
        timeout: float = 20.0,
        sleep_secs: float = 0.8,
        listing_validator=None,
    ):
        if listing_validator is None:
            raise ValueError("listing_validator is required.")
        self.logger = logger
        self.outdir = Path(outdir); self.outdir.mkdir(parents=True, exist_ok=True)
        self.max_pages = max_pages
        self.sleep_secs = sleep_secs
        self.listing_validator = listing_validator

        self.use_browser_fallback = True
        self.debug_browser = True
        self.dump_debug_html = True


        self._ua_pool = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        ]
        base_headers = {
            "User-Agent": self._ua_pool[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
            "Referer": "https://www.google.com/",
        }
        transport = httpx.HTTPTransport(retries=2)
        self.client = httpx.Client(timeout=timeout, headers=base_headers,
                                   follow_redirects=True, http2=True, transport=transport)

    # --------------------- public API ---------------------
    def run(self, barrio: str, operacion: Optional[str] = None, export: bool = True) -> dict:
        try:
            op = (operacion or "venta").strip().lower()
            nb_raw = (barrio or "").strip()
            is_all_caba = (nb_raw == "")
            nb_for_url = ("capital federal" if is_all_caba else nb_raw).lower()

            listings = self._scrape(nb_for_url, op)
            target = ("caba" if is_all_caba else nb_raw.lower())

            kept: list[ZpListing] = []
            for it in listings:
                try:
                    if self.listing_validator(it, target):
                        kept.append(it)
                except Exception as ex:
                    self.logger.warning("ap_listing_validator_error", extra={"error": str(ex), "url": it.url})

            if not export:
                return {"ok": True, "file": None, "count": len(kept), "listings": kept}

            fpath = self._export_txt(("caba" if is_all_caba else nb_raw.lower()), kept, op)
            msg = f"✅ Downloaded {len(kept)} from Argenprop ({'CABA' if is_all_caba else nb_raw.title()}). File: {fpath.name}"
            return {"ok": True, "file": str(fpath), "count": len(kept), "message": msg}

        except Exception as e:
            self.logger.exception("argenprop_run_error", extra={"error": repr(e)})
            return {"ok": False, "message": f"Unhandled error: {e!r}"}

    # --------------------- helpers -----------------------
    def _build_url(self, barrio: str, page: int, operacion: Optional[str]) -> str:
        """
        Argenprop catalog URL:
          https://www.argenprop.com/departamentos/venta/{slug}
          https://www.argenprop.com/departamentos/venta/{slug}?pagina=2
        """
        slug = (barrio or "").replace(" ", "-")
        base = f"https://www.argenprop.com/departamentos/venta/{slug}"
        return base if page == 1 else f"{base}?pagina={page}"

    def _get(self, url: str) -> Optional[str]:
        """
        HTTP fetch with best-effort fallback to a real browser when blocked.
        """
        try:
            r = self.client.get(url)
            if r.status_code == 200:
                return r.text
            if self.use_browser_fallback:
                return self._get_with_selenium(url)
            return None
        except Exception as ex:
            self.logger.error("ap_fetch_error", extra={"url": url, "error": str(ex)})
            return None

    def _get_with_selenium(self, url: str) -> Optional[str]:
        """
        Real Chrome via undetected-chromedriver. Close cookie banner, scroll, always return HTML.
        """
        driver = None
        try:
            opts = uc.ChromeOptions()
            # Headless opcional: comentar si querés ver el browser
            # opts.add_argument("--headless=new")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--lang=es-AR")

            driver = uc.Chrome(options=opts)
            driver.set_window_size(1366, 900)
            driver.get(url)

            # --- cookie banner ---
            try:
                for xp in (
                        "//button[contains(.,'Acepto')]",
                        "//button[contains(.,'Aceptar')]",
                        "//div[contains(@class,'cookie') or contains(@class,'cookies')]//button"
                ):
                    btns = driver.find_elements(By.XPATH, xp)
                    if btns:
                        btns[0].click()
                        self.logger.info("ap_cookie_banner_closed")
                        break
            except Exception:
                self.logger.info("ap_cookie_banner_skip")

            # --- simple lazy-load scroll (sin waits que bloqueen) ---
            import time
            time.sleep(2.0)
            for _ in range(10):
                driver.execute_script("window.scrollBy(0, 1600);")
                time.sleep(0.4)

            html = driver.page_source
            try:
                if self.dump_debug_html:
                    (self.outdir / "debug").mkdir(parents=True, exist_ok=True)
                    (self.outdir / "debug" / "ap_last_page.html").write_text(html, encoding="utf-8")
                    driver.save_screenshot(str(self.outdir / "debug" / "ap_last_page.png"))
            except Exception as ex:
                self.logger.error("ap_debug_dump_failed", extra={"error": str(ex)})

            return html

        except Exception as e:
            self.logger.exception("ap_selenium_error", extra={"url": url})
            return None
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

    def _scrape(self, barrio: str, operacion: Optional[str]) -> list[ZpListing]:
        """HTTP first, Selenium fallback; CSS selectors; regex fallback if needed."""
        acc: Dict[str, ZpListing] = {}
        pages_scanned = 0
        import re

        def parse_cards_from_html(src: str):
            doc = HTMLParser(src)
            # 1) normal cards
            cards = doc.css("div[class*='PostingCard'], article[class*='PostingCard']")
            if cards:
                return "cards", cards, doc
            # 2) title anchors fallback
            anchors = doc.css("a.card-info-title")
            if anchors:
                return "anchors", anchors, doc
            # 3) regex fallback (solo URLs con id tipo -1234567.html)
            urls = re.findall(r'href="(/[^"]*-[0-9]{6,}\.html)"', src)
            urls = list(dict.fromkeys(urls))  # dedupe
            return "regex", urls, doc

        for page in range(1, self.max_pages + 1):
            url = self._build_url(barrio, page, operacion)
            self.logger.info("ap_fetching_page", extra={"url": url, "page": page})

            html = self._get(url)
            mode, nodes, doc = ("", [], None) if not html else parse_cards_from_html(html)

            if not nodes and self.use_browser_fallback:
                self.logger.info("ap_retry_selenium", extra={"url": url, "page": page})
                html = self._get_with_selenium(url)
                mode, nodes, doc = ("", [], None) if not html else parse_cards_from_html(html)

            pages_scanned = page
            if not nodes:
                self.logger.warning("ap_no_cards", extra={"url": url, "page": page})
                try:
                    (self.outdir / "debug").mkdir(parents=True, exist_ok=True)
                    (self.outdir / "debug" / f"ap_page_{page}.html").write_text(html or "", encoding="utf-8")
                except Exception as ex:
                    self.logger.error("ap_debug_dump_failed", extra={"error": str(ex)})
                break

            new_items = 0
            if mode in ("cards", "anchors"):
                for n in nodes:
                    try:
                        it = self._parse_card(n)
                        if not it or not it.url:
                            continue
                        key = it.id or it.url
                        if key not in acc:
                            acc[key] = it
                            new_items += 1
                    except Exception as ex:
                        self.logger.error("ap_parse_card_error", extra={"error": str(ex)})
            else:
                # regex URLs only → arma listings mínimos
                for u in nodes:
                    full = "https://www.argenprop.com" + u if u.startswith("/") else u
                    key = f"ap:{full}"
                    if key not in acc:
                        acc[key] = ZpListing(
                            id=key, url=full, title=None, price=None,
                            location=None, details=None, agency=None,
                            source="argenprop", portal_id=None
                        )
                        new_items += 1

            self.logger.info("ap_page_parsed",
                             extra={"page": page, "found": len(nodes), "new": new_items, "total": len(acc),
                                    "mode": mode})
            if new_items == 0:
                break
            time.sleep(self.sleep_secs)

        self._pages_scanned = pages_scanned
        return list(acc.values())

    def _get_with_selenium(self, url: str) -> Optional[str]:
        """Real Chrome with explicit waits + debug dump + full traceback on error."""
        import time
        import undetected_chromedriver as uc

        driver = None
        try:
            opts = uc.ChromeOptions()
            opts.add_argument("--headless=new")  # set False only si querés ver el navegador
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--lang=es-AR")
            driver = uc.Chrome(options=opts)
            driver.set_window_size(1366, 900)
            driver.get(url)

            # best-effort cookies
            try:
                for xp in ["//button[contains(.,'Aceptar')]", "//button[contains(.,'Aceptar todas')]"]:
                    btns = driver.find_elements(By.XPATH, xp)
                    if btns: btns[0].click(); break
            except Exception:
                pass

            # wait for listing containers or title anchors
            wait = WebDriverWait(driver, 20)
            try:
                # Best-effort: no selector wait; just load + scroll + dump HTML
                time.sleep(3.0)
                for _ in range(10):
                    driver.execute_script("window.scrollBy(0, 1600);")
                    time.sleep(0.5)
                # proceed regardless of selectors

            except Exception:
                # force lazy-load
                for _ in range(8):
                    driver.execute_script("window.scrollBy(0, 1400);")
                    time.sleep(0.6)
                # Best-effort: no selector wait; just load + scroll + dump HTML
                time.sleep(3.0)
                for _ in range(10):
                    driver.execute_script("window.scrollBy(0, 1600);")
                    time.sleep(0.5)
                # proceed regardless of selectors

            html = driver.page_source
            html = driver.page_source
            try:
                if getattr(self, "dump_debug_html", False):
                    (self.outdir / "debug").mkdir(parents=True, exist_ok=True)
                    (self.outdir / "debug" / "ap_last_page.html").write_text(html, encoding="utf-8")
            except Exception as ex:
                self.logger.error("ap_debug_dump_failed", extra={"error": str(ex)})
            return html  # return even if no specific nodes were found


        except Exception:
            # full traceback
            self.logger.exception("ap_selenium_error", extra={"url": url})
            return None
        finally:
            try:
                if driver: driver.quit()
            except Exception:
                pass

    def _parse_card(self, node) -> Optional[ZpListing]:
        """Accepts a PostingCard container or an <a.card-info-title> node; extracts fields defensively."""
        import re

        a = node if getattr(node, "tag", "") == "a" else (
                node.css_first("a.card-info-title") or node.css_first("a[href]")
        )
        if not a:
            return None

        url = a.attributes.get("href")
        if not url:
            return None
        if url.startswith("/"):
            url = "https://www.argenprop.com" + url

        m = re.search(r"-([0-9]{6,})(?:\.html)?$", url)
        portal_id = m.group(1) if m else None

        title = a.text(strip=True) or (
            node.css_first("h2, h3, h4").text(strip=True) if node.css_first("h2, h3, h4") else None)

        price_node = (node.css_first("div[class*='firstPrice']") or
                      node.css_first("div[class*='price'], span[class*='price']") or
                      node.css_first("strong:contains('USD'), span:contains('USD')"))
        price = price_node.text(strip=True) if price_node else None

        loc_node = (node.css_first("div[class*='location'], div[class*='geo'], div[class*='address']") or
                    node.css_first("span:contains('Capital Federal')"))
        location = loc_node.text(strip=True) if loc_node else None

        details_node = (node.css_first("div[class*='main-features'], ul[class*='features'], div[class*='icons']"))
        details = details_node.text(separator=" | ", strip=True) if details_node else None

        agency_node = node.css_first("div[class*='publisher'], div[class*='inmobiliaria'], div[class*='agency']")
        agency = agency_node.text(strip=True) if agency_node else None

        return ZpListing(
            id=f"ap:{portal_id or url}",
            url=url,
            title=title,
            price=price,
            location=location,
            details=details,
            agency=agency,
            source="argenprop",
            portal_id=portal_id,
        )

    def _export_txt(self, barrio: str, listings: Iterable[ZpListing], operacion: Optional[str]) -> Path:
        """
        Writes a TXT file for Argenprop-only results.
        Includes the 'Portal' line for origin traceability.
        """
        import time
        from pathlib import Path

        ts = time.strftime("%Y%m%d_%H%M")
        suffix = f"_{operacion}" if operacion else ""
        fname = f"{barrio.replace(' ', '_')}{suffix}_ARGENPROP_{ts}.txt"
        fpath = self.outdir / fname

        lines = [f"# Argenprop — {barrio.title()} ({operacion or 'general'}) — {ts}\n"]
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
            lines.append(f"- Portal: {it.source}")  # <-- origin
            lines.append(f"- URL: {it.url}")
            lines.append("")

        fpath.write_text("\n".join(lines), encoding="utf-8")
        return fpath
