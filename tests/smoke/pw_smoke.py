from playwright.sync_api import sync_playwright

print("import ok")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://example.com", timeout=25000)
    print("title:", page.title())
    browser.close()
print("done")
