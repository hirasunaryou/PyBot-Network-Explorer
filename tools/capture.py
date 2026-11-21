"""Real-browser screenshot and end-to-end UI checks (CI-only Playwright dependency).

The APPLICATION is Python standard library only. Playwright is installed
in GitHub Actions exclusively to test and document the real live UI.
"""
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network.bootstrap import ensure_upstream,PROJECT_ROOT
from network.server import serve


def main():
    from playwright.sync_api import sync_playwright
    source=ensure_upstream()
    url,server=serve(source)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    assets=PROJECT_ROOT/"docs"/"images"
    assets.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page(viewport={"width":1600,"height":1050},device_scale_factor=1)
            page.emulate_media(color_scheme="dark")
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(url,wait_until="domcontentloaded")
            page.locator('.system-indicator').get_by_text("PyBot取得済み").wait_for(timeout=180000)
            assert page.locator(".graph-node").count()==7
            assert "files" in page.locator("#statusLine").inner_text() or "ファイル" in page.locator("#statusLine").inner_text()
            page.screenshot(path=str(assets/"overview.png"),full_page=True)
            print("System graph: 7 grouped nodes; real screenshot captured")

            page.locator('button[data-mode="files"]').click()
            assert page.locator(".graph-node").count()>20
            page.locator('.graph-node[data-group="knowledge"]').first.click()
            assert page.locator("#selectedTitle").inner_text()
            page.screenshot(path=str(assets/"files.png"),full_page=True)
            print("Static file view: graph nodes and inspector passed")

            page.locator('#questionInput').fill('Do you know how to calculate mean?')
            page.locator("#sendQuestion").click()
            page.locator(".chat-turn:not(.user)").first.wait_for(timeout=180000)
            assert "The mean, which is what most people mean" in page.locator(".chat-turn:not(.user) .chat-bubble").first.inner_text()
            assert "answers" in page.locator("#candidateMeta").inner_text()
            page.locator("#visualize").click()
            page.locator("#graphSource .evidence-key.dynamic").wait_for(timeout=180000)
            assert page.locator("#timeline").is_enabled()
            assert page.locator(".graph-node").count()>15
            assert page.locator(".graph-link.observed").count()>0
            assert page.locator(".origin-found").count()>0
            page.locator(".origin-found button").first.click()
            assert "bot/knowledge/maths.py" in page.locator("#sourcePath").inner_text()
            assert "5101" in page.locator("#sourcePath").inner_text()
            print("Answer origin links to exact maths.py L5101")

            page.locator("#goNext").click()
            assert page.locator("#timeline").input_value()=="1"
            page.locator("#goFirst").click()
            assert page.locator("#timeline").input_value()=="0"
            page.locator("#play").click()
            page.wait_for_timeout(550)
            assert int(page.locator("#timeline").input_value())>=1
            page.locator("#play").click()
            maximum=int(page.locator("#timeline").get_attribute("max"))
            middle=maximum//2
            page.locator("#timeline").evaluate("""(el,value) => {
              el.value=String(value);
              el.dispatchEvent(new Event("input",{bubbles:true}));
            }""",middle)
            assert int(page.locator("#timeline").input_value())==middle
            page.locator("#goLast").click()
            assert int(page.locator("#timeline").input_value())==maximum
            page.locator("#goFirst").click()
            page.screenshot(path=str(assets/"trace.png"),full_page=True)
            print("Dynamic trace: play/pause, scrub, first/last, provenance and screenshot passed")

            page.locator("#themeButton").click()
            assert page.locator("html").get_attribute("data-theme")=="light"
            page.screenshot(path=str(assets/"light.png"),full_page=True)
            assert not errors,errors
            print("Light mode and page JS errors: PASS")

            small=browser.new_page(viewport={"width":390,"height":844})
            small.emulate_media(color_scheme="light")
            small.goto(url,wait_until="domcontentloaded")
            small.locator(".graph-node").first.wait_for(timeout=180000)
            width=small.locator("html").evaluate("(e)=>({client:e.clientWidth,scroll:e.scrollWidth})")
            assert width["scroll"]<=width["client"]+1,width
            small.close()
            print("390px responsive viewport: PASS")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__=="__main__":
    main()
