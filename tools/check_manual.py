"""Visual QA of the single-file HTML manual in a local file:// browser."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright
    manual=ROOT/"docs"/"MANUAL.html"
    source=manual.read_text(encoding="utf-8")
    assert "<style>" in source and "data:image/png;base64," in source
    assert 'src="images/' not in source
    with sync_playwright() as instance:
        browser=instance.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1400,"height":980},device_scale_factor=1)
        page.goto(manual.as_uri(),wait_until="load")
        screenshots=page.locator(".screen img")
        assert screenshots.count()==2
        for picture in screenshots.all():
            assert picture.evaluate("(el)=>el.complete&&el.naturalWidth>200")
        assert page.locator(".cover h1").count()==1
        background=page.locator(".cover").evaluate("(el)=>getComputedStyle(el).backgroundImage")
        assert background!="none", "Hero gradient was not loaded"
        page.screenshot(path=str(ROOT/"docs"/"images"/"manual-preview.png"),full_page=False)
        print("PASS: standalone manual, embedded CSS, 2 real screenshots, local rendering")
        browser.close()


if __name__=="__main__":
    main()
