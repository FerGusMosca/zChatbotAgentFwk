from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # ventana visible
    page = browser.new_page()
    # URL sin https, sin JS raro
    page.goto("http://neverssl.com", timeout=30000, wait_until="load")
    print("title:", page.title())
    page.wait_for_timeout(3000)
    browser.close()
