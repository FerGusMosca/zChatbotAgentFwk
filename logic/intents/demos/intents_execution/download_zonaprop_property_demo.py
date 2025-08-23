# logic/intents/demos/intents_execution/download_zonaprop_property_demo.py
from __future__ import annotations

import re
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Dict

import httpx
from selectolax.parser import HTMLParser

from selenium.webdriver.common.by import By
import undetected_chromedriver as uc


@dataclass
class ZpListing:
    id: str
    url: str
    title: str | None
    price: str | None
    location: str | None
    details: str | None
    agency: str | None


class DownloadZonapropPropertyDemo:
    """
    Zonaprop scraper for a single neighborhood and operation.

    Design:
      - Networking: httpx first; fallback to Selenium (undetected-chromedriver) on 403/!=200.
      - Parsing: defensive selectors; basic dedupe by id/url.
      - Filtering/Classification: **delegated 100% to an external callback** (LLM).
        The scraper itself does NOT decide neighborhood membership.

    Contract:
      - listing_validator: Callable[[ZpListing, str], bool]
        Must return True to keep the listing, False to drop it.
      - The TXT file is written with ONLY listings the validator approved.
    """

    def __init__(
        self,
        logger,
        outdir: str = "exports",
        max_pages: int = 10,
        timeout: float = 20.0,
        sleep_secs: float = 0.8,
        listing_validator: Optional[Callable[[ZpListing, str], bool]] = None,
    ):
        self.logger = logger
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)

        self.max_pages = max_pages
        self.sleep_secs = sleep_secs

        # A validator is REQUIRED because all classification must be LLM-driven.
        if listing_validator is None:
            raise ValueError("listing_validator is required: all classification is delegated to LLM.")
        self.listing_validator = listing_validator

        # Networking strategy
        self.use_browser_fallback = True
        self.debug_browser = True    # show browser on first run (optional)
        self.dump_debug_html = True  # save last HTML/screenshot to exports/debug

        # Basic UA rotation for 403s
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
                timeout=timeout,
                headers=base_headers,
                follow_redirects=True,
                http2=True,
                transport=transport,
            )
        except Exception:
            self.logger.warning("http2_not_available_falling_back_to_http11")
            self.client = httpx.Client(
                timeout=timeout,
                headers=base_headers,
                follow_redirects=True,
                http2=False,
                transport=transport,
            )

    # ----------------------- Public API -----------------------

    def run(self, barrio: str, operacion: Optional[str] = None) -> dict:
        """
        Full scrape → validator filter → export TXT.
        RAW mode support:
          - If `barrio` is empty/None => crawl ALL CABA (use 'capital federal' slug).
          - We still call `listing_validator` (can be a BYPASS that always returns True).
        """
        try:
            # Normalize inputs
            op = (operacion or "venta").strip().lower()
            nb_raw = (barrio or "").strip()
            is_all_caba = (nb_raw == "")

            # Slug to build URLs:
            # - empty barrio => use 'capital federal' (CABA-wide)
            # - non-empty barrio => use the given barrio
            nb_for_url = ("capital federal" if is_all_caba else nb_raw).lower()

            # Do the scrape
            listings = self._scrape(nb_for_url, op)

            # LLM-driven validator (can be BYPASS=True)
            target_for_validator = ("caba" if is_all_caba else nb_raw.lower())
            kept: list[ZpListing] = []
            for it in listings:
                try:
                    if self.listing_validator(it, target_for_validator):
                        kept.append(it)
                except Exception as ex:
                    self.logger.warning(
                        "listing_validator_error",
                        extra={"error": str(ex), "url": it.url},
                    )

            # Export using a friendly tag for filename/header
            barrio_tag = ("caba" if is_all_caba else nb_raw.lower())
            fpath = self._export_txt(barrio_tag, kept, op)

            self.logger.info(
                "zonaprop_download_done",
                extra={
                    "barrio": barrio_tag,
                    "operacion": op,
                    "count": len(kept),
                    "file": str(fpath),
                },
            )

            nice_area = ("CABA" if is_all_caba else nb_raw.title())
            msg = f"✅ Descargué {len(kept)} propiedades de {nice_area} (Zonaprop). Archivo: {fpath.name}"
            return {"ok": True, "file": str(fpath), "count": len(kept), "message": msg}

        except Exception as e:
            self.logger.exception("zonaprop_run_error", extra={"error": repr(e)})
            return {"ok": False, "message": f"Unhandled error: {e!r}"}

    # ----------------------- Helpers -------------------------

    def _build_url(self, barrio: str, page: int, operacion: Optional[str]) -> str:
        """
        Builds the correct Zonaprop search URL for the provided barrio+operation.
        This is NOT a classification step; just URL composition.
        """
        slug = barrio.replace(" ", "-")
        if operacion == "venta":
            base = f"https://www.zonaprop.com.ar/departamentos-en-venta-{slug}"
        elif operacion == "alquiler":
            base = f"https://www.zonaprop.com.ar/departamentos-en-alquiler-{slug}"
        else:
            base = f"https://www.zonaprop.com.ar/departamentos-{slug}"
        return base + (".html" if page == 1 else f"-pagina-{page}.html")

    # ----------------------- Networking ----------------------

    def _get(self, url: str) -> Optional[str]:
        """
        GET with basic anti-403 strategy.
        """
        try:
            r = self.client.get(url)
            if r.status_code == 403:
                self.logger.info("zp_403_detected")
                # rotate UA + referer and retry once
                self._ua_idx = (self._ua_idx + 1) % len(self._ua_pool)
                self.client.headers["User-Agent"] = self._ua_pool[self._ua_idx]
                self.client.headers["Referer"] = "https://www.bing.com/"
                time.sleep(0.8)
                r2 = self.client.get(url)
                if r2.status_code == 200:
                    return r2.text
                self.logger.info("zp_403_persist")
                if self.use_browser_fallback:
                    self.logger.info("zp_fallback_selenium")
                    return self._get_with_selenium(url)
                return None

            if r.status_code == 200:
                return r.text

            self.logger.info("zp_non200", extra={"status": r.status_code})
            if self.use_browser_fallback:
                self.logger.info("zp_fallback_selenium")
                return self._get_with_selenium(url)
            return None

        except Exception as ex:
            self.logger.error("zp_fetch_error", extra={"url": url, "error": str(ex)})
            return None

    def _get_with_selenium(self, url: str) -> Optional[str]:
        """
        Loads the page with a real Chrome (Selenium + undetected-chromedriver).
        Saves debug artifacts if enabled. Returns page_source or None.
        """
        driver = None
        try:
            opts = uc.ChromeOptions()
            if not getattr(self, "debug_browser", False):
                opts.add_argument("--headless=new")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--lang=es-AR")

            ua = self.client.headers.get("User-Agent", "")
            if ua:
                opts.add_argument(f"--user-agent={ua}")

            driver = uc.Chrome(options=opts)
            driver.set_window_size(1366, 900)

            try:
                driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Referer": "https://www.google.com/"}})
            except Exception:
                pass

            driver.get(url)

            # Accept cookies (best-effort)
            try:
                for sel in ["//button[contains(.,'Aceptar')]", "//button[contains(.,'Aceptar todas')]"]:
                    btns = driver.find_elements(By.XPATH, sel)
                    if btns:
                        btns[0].click()
                        break
            except Exception:
                pass

            # Trigger lazy loading
            try:
                for _ in range(6):
                    driver.execute_script("window.scrollBy(0, 1200);")
                    time.sleep(0.4)
            except Exception:
                pass

            html = driver.page_source

            if getattr(self, "dump_debug_html", False) or getattr(self, "debug_browser", False):
                (self.outdir / "debug").mkdir(parents=True, exist_ok=True)
            if getattr(self, "dump_debug_html", False):
                try:
                    (self.outdir / "debug" / "last_page.html").write_text(html, encoding="utf-8")
                except Exception:
                    pass
            if getattr(self, "debug_browser", False):
                try:
                    driver.save_screenshot(str(self.outdir / "debug" / "last_page.png"))
                except Exception:
                    pass

            self.logger.info("zp_selenium_ok")
            return html

        except Exception as e:
            self.logger.error("zp_selenium_error", extra={"url": url, "error": repr(e)})
            return None
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

    # ----------------------- Parsing & Export ----------------

    def _scrape(self, barrio: str, operacion: Optional[str]) -> list[ZpListing]:
        """
        Parse listing cards defensively and dedupe by id/url.
        """
        acc: Dict[str, ZpListing] = {}
        for page in range(1, self.max_pages + 1):
            url = self._build_url(barrio, page, operacion)
            html = self._get(url)
            if not html:
                break

            doc = HTMLParser(html)
            cards = doc.css(
                "article[class*='posting'], article[class*='postings-card'], "
                "li[class*='posting'], div[class*='posting'], "
                "div[data-qa*='posting'], article[data-qa*='posting'], "
                "[data-qa*='posting-card'], [data-testid*='posting']"
            )
            if not cards:
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

            self.logger.info("zp_page_parsed", extra={"url": url, "found": len(cards), "new": new_items, "total": len(acc)})
            if new_items == 0:
                break
            time.sleep(self.sleep_secs)

        return list(acc.values())

    def _parse_card(self, card) -> Optional[ZpListing]:
        """
        Extract critical fields from a result card.
        Note: regex here is only for extracting numeric IDs from URLs, not for classification.
        """
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

        return ZpListing(
            id=lid or url, url=url, title=title, price=price,
            location=location, details=details, agency=agency
        )

    def _export_txt(self, barrio: str, listings: Iterable[ZpListing], operacion: Optional[str]) -> Path:
        """
        Write a clean TXT with only LLM-approved listings.
        """
        ts = time.strftime("%Y%m%d_%H%M")
        suffix = f"_{operacion}" if operacion else ""
        fname = f"{barrio.replace(' ', '_')}{suffix}_{ts}.txt"
        fpath = self.outdir / fname

        lines = [f"# Zonaprop — {barrio.title()} ({operacion or 'general'}) — {ts}\n"]
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
            lines.append(f"- URL: {it.url}")
            lines.append("")
        fpath.write_text("\n".join(lines), encoding="utf-8")
        return fpath
