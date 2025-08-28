# prop_probe_local_ok.py — SOLO SELENIUM, PERFIL DEDICADO, NO-HEADLESS
import time
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

URL = "https://www.zonaprop.com.ar/departamentos-en-venta-belgrano.html"
OUT = Path("../../exports/debug"); OUT.mkdir(parents=True, exist_ok=True)
PROFILE_DIR = Path(r"C:\Bias_Algos\ZPProfile")  # perfil NUEVO y exclusivo del bot
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

def make_driver():
    opts = uc.ChromeOptions()
    # NO headless para local: se ve la ventana y evitamos fricciones de CF
    # (si querés, luego cambiás a "--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=es-AR")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    d = uc.Chrome(options=opts)
    d.set_window_size(1366, 900)
    try:
        d.execute_cdp_cmd("Network.setExtraHTTPHeaders",
                          {"headers": {"Referer": "https://www.google.com/"}})
    except Exception:
        pass
    return d

def scroll_for_cards(drv, n=6, wait=0.35):
    for _ in range(n):
        drv.execute_script("window.scrollBy(0, 1200);")
        time.sleep(wait)

def count_cards(drv) -> int:
    sel = "[data-qa*='posting'], [data-testid*='posting'], article[class*='posting']"
    return len(drv.find_elements(By.CSS_SELECTOR, sel))

if __name__ == "__main__":
    d = make_driver()
    t0 = time.time()
    try:
        d.get(URL)
        time.sleep(2.0)            # deja cargar
        scroll_for_cards(d)        # fuerza lazy-load
        cards = count_cards(d)
        (OUT / "local_ok.html").write_text(d.page_source, encoding="utf-8")
        d.save_screenshot(str(OUT / "local_ok.png"))
        print(f"OK|cards={cards} t={time.time()-t0:.1f}s")
    finally:
        d.quit()
