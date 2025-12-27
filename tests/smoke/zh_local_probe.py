# zh_scrape_homepage.py
# Saves full rendered homepage HTML after login to inspect DOM stability

import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT_DIR = Path(r"C:\zerohede_tests\zh_snapshot")
OUT_DIR.mkdir(parents=True, exist_ok=True)
HOME_URL = "https://www.zerohedge.com"

options = Options()
options.add_argument("--no-sandbox")
options.add_experimental_option("excludeSwitches", ["enable-automation"])

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://www.zerohedge.com/user/login")
    input("Login manually, then press ENTER when you see the homepage.")

    driver.get(HOME_URL)
    time.sleep(10)

    # Scroll to trigger all lazy content
    last = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(6)
        cur = driver.execute_script("return document.body.scrollHeight")
        if cur == last:
            break
        last = cur

    # Capture final rendered DOM
    html = driver.execute_script("return document.documentElement.outerHTML")
    (OUT_DIR / "homepage_rendered.html").write_text(html, encoding="utf-8")

    print("Snapshot saved: homepage_rendered.html")

finally:
    driver.quit()
