# logic/intents/demos/intents_execution/download_zonaprop_property_demo.py
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Iterable, Optional, Dict

import httpx
from selectolax.parser import HTMLParser
from selenium.common import SessionNotCreatedException

from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

from common.util.settings.env_deploy_reader import EnvDeployReader
from logic.intents.demos.intents_execution.real_state_parsers.models import ZpListing


class DownloadZonapropPropertyDemo:
    """
    Zonaprop scraper for a single neighborhood + operation.

    Design
    ------
    - Two fetching modes:
        * "http": try httpx first and fallback to Selenium on 403/non-200.
        * "selenium": use Selenium from the start and reuse a single browser.
    - Parsing: robust CSS selectors.
    - Filtering: fully delegated to `listing_validator`.

    .env_deploy_* flags
    -----------------
    - PAGES_TO_DOWNLOAD      -> max pages to scan
    - ZP_FETCH_MODE          -> "selenium" | "http" (default "http")
    - SELENIUM_HEADLESS      -> "true" | "false" (default "true")
    """

    def __init__(
        self,
        logger,
        outdir: str = "exports",
        max_pages: int = int(EnvDeployReader.get("PAGES_TO_DOWNLOAD")),
        timeout: float = 20.0,
        sleep_secs: float = 0.8,
        listing_validator: Optional[Callable[[ZpListing, str], bool]] = None,
    ):
        self.logger = logger
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)

        self.max_pages = max_pages
        self.sleep_secs = sleep_secs

        if listing_validator is None:
            raise ValueError("listing_validator is required (external LLM-based filtering).")
        self.listing_validator = listing_validator

        # Fetch mode & headless flags
        self.fetch_mode = (EnvDeployReader.get("ZP_FETCH_MODE") or "http").strip().lower()
        self.headless = (str(EnvDeployReader.get("SELENIUM_HEADLESS") or "true").lower() == "true")
        self.uc_version_main = EnvDeployReader.get("UC_VERSION_MAIN")

        # Debug opts (keep minimal in prod)
        self.debug_browser = not self.headless
        self.dump_debug_html = False

        # UA pool for httpx anti-403 rotation
        self._ua_pool = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        ]
        self._ua_idx = 0

        base_headers = {
            "User-Agent": self._ua_pool[self._ua_idx],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Connection": "keep-alive",
            "Referer": "https://www.google.com/",
        }

        transport = httpx.HTTPTransport(retries=2)
        try:
            self.client = httpx.Client(
                timeout=timeout, headers=base_headers, follow_redirects=True, http2=True, transport=transport
            )
        except Exception:
            self.logger.warning("http2_not_available_falling_back_to_http11")
            self.client = httpx.Client(
                timeout=timeout, headers=base_headers, follow_redirects=True, http2=False, transport=transport
            )

    # ----------------------- Public API -----------------------

    def run(self, barrio: str, operacion: Optional[str] = None, export: bool = True) -> dict:
        """Scrape -> external validation -> optional TXT export."""
        try:
            op = (operacion or "venta").strip().lower()
            nb_raw = (barrio or "").strip()
            is_all_caba = (nb_raw == "")
            nb_for_url = ("capital federal" if is_all_caba else nb_raw).lower()

            # Scrape
            listings = self._scrape(nb_for_url, op)

            # External validation (keep only accepted)
            target_for_validator = ("caba" if is_all_caba else nb_raw.lower())
            kept: list[ZpListing] = []
            for it in listings:
                try:
                    if self.listing_validator(it, target_for_validator):
                        kept.append(it)
                except Exception as ex:
                    self.logger.warning("listing_validator_error", extra={"error": str(ex), "url": it.url})

            if not export:
                return {"ok": True, "file": None, "count": len(kept), "listings": kept}

            # Export TXT
            barrio_tag = ("caba" if is_all_caba else nb_raw.lower())
            fpath = self._export_txt(barrio_tag, kept, op)
            nice_area = ("CABA" if is_all_caba else nb_raw.title())
            msg = f"✅ Descargué {len(kept)} propiedades de {nice_area} (Zonaprop). Archivo: {fpath.name}"
            return {"ok": True, "file": str(fpath), "count": len(kept), "message": msg}

        except Exception as e:
            self.logger.exception("zonaprop_run_error", extra={"error": repr(e)})
            return {"ok": False, "message": f"Unhandled error: {e!r}"}

    # ----------------------- URL builder ----------------------

    def _build_url(self, barrio: str, page: int, operacion: Optional[str]) -> str:
        """Compose Zonaprop URL for (barrio, operacion, page)."""
        slug = barrio.replace(" ", "-")
        if operacion == "venta":
            base = f"https://www.zonaprop.com.ar/departamentos-en-venta-{slug}"
        elif operacion == "alquiler":
            base = f"https://www.zonaprop.com.ar/departamentos-en-alquiler-{slug}"
        else:
            base = f"https://www.zonaprop.com.ar/departamentos-{slug}"
        return base + (".html" if page == 1 else f"-pagina-{page}.html")

    # ----------------------- Fetching -------------------------

    def _make_driver(self):
        """Create a undetected-chromedriver instance; auto-retry with version_main that matches local Chrome."""
        opts = uc.ChromeOptions()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--lang=es-AR")

        ua = self.client.headers.get("User-Agent", "")
        if ua:
            opts.add_argument(f"--user-agent={ua}")

        # helper: arranca uc con o sin version_main
        def _boot(ver: int | None):
            if ver is None:
                return uc.Chrome(options=opts)
            return uc.Chrome(options=opts, version_main=ver)

        # 1) si viene forzado por config, usarlo
        forced_ver = None
        try:
            if self.uc_version_main:
                forced_ver = int(str(self.uc_version_main).strip())
        except Exception:
            forced_ver = None

        try:
            driver = _boot(forced_ver)
        except SessionNotCreatedException as e:
            # 2) si falla por mismatch, detectar la versión de Chrome instalada y reintentar
            m = re.search(r"Current browser version is (\d+)", str(e))
            if not m:
                raise
            local_ver = int(m.group(1))
            self.logger.warning("uc_retry_with_version_main", extra={"version_main": local_ver})
            driver = _boot(local_ver)

        driver.set_window_size(1366, 900)
        try:
            driver.execute_cdp_cmd(
                "Network.setExtraHTTPHeaders", {"headers": {"Referer": "https://www.google.com/"}}
            )
        except Exception:
            pass

        return driver

    def _get_with_selenium(self, url: str, driver=None) -> Optional[str]:
        """
        Load page with Selenium. If a driver is provided, reuse it;
        otherwise create a temporary one. Return page_source or None.
        """
        local_driver = None
        if driver is None:
            local_driver = self._make_driver()
            driver = local_driver

        try:
            driver.get(url)
            ua_js = driver.execute_script("return navigator.userAgent")
            is_webdriver = driver.execute_script("return !!window.navigator.webdriver")
            cards = driver.find_elements(By.CSS_SELECTOR,
                                         "[data-qa*='posting'], [data-testid*='posting'], article[class*='posting']")

            self.logger.info("zp_dbg",
                             extra={
                                 "ua_js": ua_js,
                                 "webdriver": is_webdriver,
                                 "cards_found": len(cards)
                             })
            # snapshots
            dbg = self.outdir / "debug"
            dbg.mkdir(parents=True, exist_ok=True)
            (dbg / "bot_vps_page1.html").write_text(driver.page_source, encoding="utf-8")
            driver.save_screenshot(str(dbg / "bot_vps_page1.png"))

            # Accept cookies (best effort)
            try:
                for sel in [
                    "//button[contains(.,'Acept')]",   # 'Aceptar', 'Aceptar todas'
                    "//button[contains(.,'Entendido')]",
                    "//button[contains(.,'continuar')]",
                ]:
                    btns = driver.find_elements(By.XPATH, sel)
                    if btns and btns[0].is_displayed():
                        btns[0].click()
                        break
            except Exception:
                pass

            # Trigger lazy loading
            try:
                for _ in range(4):
                    driver.execute_script("window.scrollBy(0, 1000);")
                    time.sleep(0.35)
            except Exception:
                pass

            html = driver.page_source

            # Optional debug dump
            if self.dump_debug_html or self.debug_browser:
                (self.outdir / "debug").mkdir(parents=True, exist_ok=True)
            if self.dump_debug_html:
                try:
                    (self.outdir / "debug" / "last_page.html").write_text(html, encoding="utf-8")
                    driver.save_screenshot(str(self.outdir / "debug" / "last_page.png"))
                except Exception:
                    pass

            self.logger.info("zp_selenium_ok")
            return html

        except Exception as e:
            self.logger.error("zp_selenium_error", extra={"url": url, "error": repr(e)})
            return None
        finally:
            if local_driver:
                try:
                    local_driver.quit()
                except Exception:
                    pass

    def _get(self, url: str) -> Optional[str]:
        """
        If fetch_mode=selenium -> always Selenium.
        Else -> httpx first with anti-403 rotation and Selenium fallback.
        """
        if self.fetch_mode == "selenium":
            return self._get_with_selenium(url)

        try:
            r = self.client.get(url)
            if r.status_code == 403:
                self.logger.info("zp_403_detected")
                self._ua_idx = (self._ua_idx + 1) % len(self._ua_pool)
                self.client.headers["User-Agent"] = self._ua_pool[self._ua_idx]
                self.client.headers["Referer"] = "https://www.bing.com/"
                time.sleep(0.8)

                r2 = self.client.get(url)
                if r2.status_code == 200:
                    return r2.text

                self.logger.info("zp_403_persist")
                self.logger.info("zp_fallback_selenium")
                return self._get_with_selenium(url)

            if r.status_code == 200:
                return r.text

            self.logger.info("zp_non200", extra={"status": r.status_code})
            self.logger.info("zp_fallback_selenium")
            return self._get_with_selenium(url)

        except Exception as ex:
            self.logger.error("zp_fetch_error", extra={"url": url, "error": str(ex)})
            return None

    # ----------------------- Scrape loop ----------------------

    def _scrape(self, barrio: str, operacion: Optional[str]) -> list[ZpListing]:
        """
        Iterate pages, fetch HTML, parse cards, and accumulate unique listings.
        When in selenium mode, reuse a single driver across all pages.
        """
        acc: Dict[str, ZpListing] = {}
        pages_scanned = 0

        driver = None
        if self.fetch_mode == "selenium":
            driver = self._make_driver()

        try:
            for page in range(1, self.max_pages + 1):
                url = self._build_url(barrio, page, operacion)
                self.logger.info("Bajando ZonaProp Page %d", page, extra={"url": url})

                if self.fetch_mode == "selenium":
                    html = self._get_with_selenium(url, driver=driver)
                else:
                    html = self._get(url)

                if not html:
                    break

                pages_scanned = page
                doc = HTMLParser(html)
                cards = doc.css(
                    "article[class*='posting'], article[class*='postings-card'], "
                    "li[class*='posting'], div[class*='posting'], "
                    "div[data-qa*='posting'], article[data-qa*='posting'], "
                    "[data-qa*='posting-card'], [data-testid*='posting']"
                )
                if not cards:
                    try:
                        (self.outdir / "debug").mkdir(parents=True, exist_ok=True)
                        (self.outdir / "debug" / f"page-{page}-empty.html").write_text(html, encoding="utf-8")
                    except Exception:
                        pass
                    self.logger.info("zp_no_cards", extra={"url": url})
                    break

                new_items = 0
                for c in cards:
                    item = self._parse_card(c)
                    if not item:
                        continue
                    key = item.id or item.url
                    if key and key not in acc:
                        acc[key] = item
                        new_items += 1

                self.logger.info(
                    "zp_page_parsed",
                    extra={"url": url, "page": page, "found": len(cards), "new": new_items, "total": len(acc)}
                )

                if new_items == 0:
                    break

                time.sleep(self.sleep_secs)

            self._pages_scanned = pages_scanned
            return list(acc.values())

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # ----------------------- Parsing & Export -----------------

    def _parse_card(self, card) -> Optional[ZpListing]:
        """Extract robust fields from a result card and return a ZpListing."""
        a = card.css_first("a[href]")
        url = a.attributes.get("href") if a else None
        if url and url.startswith("/"):
            url = "https://www.zonaprop.com.ar" + url

        lid = None
        for attr in ("data-id", "data-posting-id", "data-qa"):
            if attr in card.attributes:
                lid = card.attributes.get(attr)
                break
        if not lid and url:
            m = re.search(r"-([0-9]{6,})\.html", url)
            if m:
                lid = m.group(1)

        title_node = card.css_first("h2, h3")
        title = title_node.text(strip=True) if title_node else None

        price_node = (
            card.css_first("[class*='price']") or
            card.css_first("strong:contains('USD'), strong:contains('$'), span:contains('USD'), span:contains('$')")
        )
        price = price_node.text(strip=True) if price_node else None

        loc_node = card.css_first("[class*='location'], [class*='address'], [class*='neighborhood']")
        location = loc_node.text(strip=True) if loc_node else None

        details_node = card.css_first("[class*='main-features'], [class*='features']")
        details = details_node.text(separator=" | ", strip=True) if details_node else None

        agency_node = card.css_first("[class*='agency'], [class*='realtor'], [class*='publisher']")
        agency = agency_node.text(strip=True) if agency_node else None

        if not url:
            return None

        portal_id = lid
        unique_id = f"zp:{portal_id or url}"

        return ZpListing(
            id=unique_id,
            url=url,
            title=title,
            price=price,
            location=location,
            details=details,
            agency=agency,
            source="zonaprop",
            portal_id=portal_id,
        )

    def _export_txt(self, barrio: str, listings: Iterable[ZpListing], operacion: Optional[str]) -> Path:
        """Write a TXT with the kept listings (already validated by caller)."""
        ts = time.strftime("%Y%m%d_%H%M")
        suffix = f"_{operacion}" if operacion else ""
        fname = f"{barrio.replace(' ', '_')}{suffix}_ZONAPROP_{ts}.txt"
        fpath = self.outdir / fname

        pages = getattr(self, "_pages_scanned", 0)
        lines = [
            f"# Zonaprop — {barrio.title()} ({operacion or 'general'}) — {ts}",
            f"# Pages scanned: {pages}",
            ""
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
