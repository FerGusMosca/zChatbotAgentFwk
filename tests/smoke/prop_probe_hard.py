# prop_probe_hard.py
import time, re
from pathlib import Path
import httpx
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

OUT = Path("../../exports/debug"); OUT.mkdir(parents=True, exist_ok=True)

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
URL = "https://www.zonaprop.com.ar/departamentos-en-venta-belgrano.html"

def is_challenge(html: str) -> bool:
    if not html: return True
    h = html.lower()
    return ("cdn-cgi/challenge" in h) or ("un momento" in h and "verificando" in h) or ("cloudflare" in h)

def make_driver(ua: str):
    opts = uc.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"--user-agent={ua}")
    opts.add_argument("--no-sandbox"); opts.add_argument("--disable-dev-shm-usage")
    d = uc.Chrome(options=opts); d.set_window_size(1366, 900)
    try: d.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Referer":"https://www.google.com/"}})
    except: pass
    return d

def google_hop(d):
    d.delete_all_cookies()
    d.get("https://www.google.com")
    time.sleep(1.0)

def scroll_probe(d, n=5, wait=0.35):
    for _ in range(n):
        d.execute_script("window.scrollBy(0, 1000);")
        time.sleep(wait)

def has_cards(d) -> bool:
    cards = d.find_elements(By.CSS_SELECTOR, "[data-qa*='posting'], [data-testid*='posting'], article[class*='posting']")
    return len(cards) > 0

def httpx_403_then_selenium_flow():
    # 1) httpx -> forzar 403 patrón del bot
    ua = UA_POOL[0]
    client = httpx.Client(follow_redirects=True, headers={"User-Agent": ua, "Referer": "https://www.google.com/"}, timeout=15.0)
    r = client.get(URL)
    print("httpx_first:", r.status_code)

    # 2) Cooldown + rotar UA + Referer distinto
    time.sleep(3.5)
    ua2 = UA_POOL[1]
    client.headers["User-Agent"] = ua2
    client.headers["Referer"] = "https://www.bing.com/"
    r2 = client.get(URL)
    print("httpx_second:", r2.status_code)

    # 3) Selenium: google hop -> target -> scroll -> verificar cards/challenge
    d = make_driver(ua2)
    try:
        google_hop(d)
        d.get(URL); time.sleep(1.2); scroll_probe(d)
        html = d.page_source
        (OUT / "probe_hard_page.html").write_text(html, encoding="utf-8")
        d.save_screenshot(str(OUT / "probe_hard_page.png"))
        print("challenge?", is_challenge(html), "| cards?", has_cards(d))
    finally:
        d.quit()

if __name__ == "__main__":
    httpx_403_then_selenium_flow()
