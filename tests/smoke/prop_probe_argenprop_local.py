# prop_probe_argenprop_local.py — SOLO SELENIUM, VISIBLE, PERFIL DEDICADO, LOG CONCISO
import time
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

# URLs candidatas (deja ambas, prueba la que abre con cards en tu local)
URLS = [
    "https://www.argenprop.com/departamento-venta-belgrano",
    "https://www.argenprop.com/departamentos-en-venta-en-belgrano",
]

OUT = Path("../../exports/debug"); OUT.mkdir(parents=True, exist_ok=True)
PROFILE_DIR = Path(r"C:\Bias_Algos\APProfile")  # perfil NUEVO y exclusivo p/ Argenprop
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

def make_driver():
    opts = uc.ChromeOptions()
    # NO headless: queremos ver la ventana y evitar fricciones
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=es-AR")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    d = uc.Chrome(options=opts)
    d.set_window_size(1366, 900)
    return d

def scroll(drv, n=6, wait=0.4):
    for _ in range(n):
        drv.execute_script("window.scrollBy(0, 1200);"); time.sleep(wait)

def count_cards(drv) -> int:
    # Selectores amplios para cards/listings en Argenprop (robustos a cambios)
    SELS = [
        "article[class*='card']",
        "li[class*='card']",
        "div[class*='card']",
        "div[class*='listing'] article",
        "[data-testid*='card']",
        "[data-qa*='card']",
        "a[href*='/propiedades/']",
    ]
    total = 0
    for s in SELS:
        total = max(total, len(drv.find_elements(By.CSS_SELECTOR, s)))
    return total

def is_challenge(html: str) -> bool:
    h = (html or "").lower()
    return ("cdn-cgi/challenge" in h) or ("verifying you are human" in h) or ("cf-turnstile" in h) or ("cloudflare" in h)

if __name__ == "__main__":
    d = make_driver()
    try:
        ok = False
        for idx, url in enumerate(URLS, 1):
            print(f"TRY{idx}| {url}")
            d.get(url); time.sleep(2.0)
            # esperar si hubiese challenge simple
            for _ in range(3):
                if not is_challenge(d.page_source): break
                time.sleep(2.5)

            scroll(d)
            cards = count_cards(d)
            (OUT / f"argenprop_try{idx}.html").write_text(d.page_source, encoding="utf-8")
            d.save_screenshot(str(OUT / f"argenprop_try{idx}.png"))
            print(f"TRY{idx}|challenge={is_challenge(d.page_source)} cards={cards}")
            if cards > 0:
                ok = True
                break

        print("RESULT|PASS" if ok else "RESULT|FAIL")
    finally:
        d.quit()
