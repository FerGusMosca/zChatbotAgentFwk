# tools/prop_probe.py
import sys, time, pathlib, re
from pathlib import Path

AB_MARKERS = [
    "are you human", "captcha", "hcaptcha", "recaptcha",
    "access denied", "temporarily blocked", "403 forbidden", "/cdn-cgi/bm/"
]

LIST_URL = "https://www.zonaprop.com.ar/departamentos-en-venta-capital-federal.html"

def anti_bot(html: str):
    h = (html or "").lower()
    return [m for m in AB_MARKERS if m in h]

def save_artifacts(prefix: str, html: str, driver=None):
    out = Path("../../exports/debug")
    out.mkdir(parents=True, exist_ok=True)
    if html:
        (out / f"{prefix}.html").write_text(html, encoding="utf-8")
    if driver:
        driver.save_screenshot(str(out / f"{prefix}.png"))
    print(f"[artifacts] exports/debug/{prefix}.html" + (" + .png" if driver else ""))

# ---------- HTTP probe ----------
def http_probe(url: str):
    import httpx
    print("[http] GET:", url)
    with httpx.Client(http2=True, timeout=15, headers={
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "accept-language": "es-AR,es;q=0.9,en;q=0.8",
    }) as cli:
        r = cli.get(url)
    print("[http] status:", r.status_code)
    save_artifacts("probe_http", r.text)
    marks = anti_bot(r.text)
    href = None
    if r.status_code == 200 and not marks:
        # muuuuy simple: primer href que parezca propiedad
        m = re.search(r'href="([^"]*propiedad-[^"]+)"', r.text)
        href = (m.group(1) if m else None)
    return r.status_code, marks, href

# ---------- Selenium probe ----------
def selenium_probe(url: str, headless=True):
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    print("[sel] open:", url, "| headless:", headless)
    opts = uc.ChromeOptions()
    if headless: opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--disable-gpu"); opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=es-AR")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    drv = None
    try:
        drv = uc.Chrome(options=opts)
        drv.get(url)
        # intenta aceptar cookies si aparecen
        for xp in ("//button[contains(.,'Aceptar')]","//button[contains(.,'Accept')]",
                   "//button[contains(.,'Entendido')]"):
            try: drv.find_element(By.XPATH, xp).click(); break
            except: pass

        # si es listado, abre la primera propiedad
        try:
            WebDriverWait(drv, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='propiedad-']")))
            href = drv.find_element(By.CSS_SELECTOR, "a[href*='propiedad-']").get_attribute("href")
            print("[sel] first property:", href)
            drv.get(href)
        except Exception:
            pass

        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1.0)
        html = drv.page_source
        save_artifacts("probe_selenium", html, driver=drv)
        marks = anti_bot(html)
        ua = drv.execute_script("return navigator.userAgent")
        wd = drv.execute_script("return navigator.webdriver")
        print("[sel] title:", (drv.title or "")[:120])
        print("[sel] webdriver flag:", wd, "| UA:", ua[:60], "...")
        return marks, True
    finally:
        if drv:
            drv.quit()
            print("[sel] quit ok")

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else LIST_URL

    status, marks, href = http_probe(url)
    if marks or status != 200 or not href:
        print("[http] blocked or no href → fallback selenium")
        marks2, ok = selenium_probe(url, headless=False)  # primero visible para ver qué pasa
        print("[result] selenium antibot markers:", marks2)
    else:
        print("[http] OK. first property:", href)

if __name__ == "__main__":
    main()
