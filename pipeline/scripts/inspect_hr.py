"""Debug-Skript: lade handelsregister.de Bekanntmachungen + speichere HTML."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        locale="de-DE",
        viewport={"width": 1366, "height": 768},
    )
    page = await ctx.new_page()

    print("# 1. Bekanntmachungs-Landing-Page")
    await page.goto(
        "https://www.handelsregister.de/rp_web/bekanntmachungen.xhtml",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    await page.wait_for_selector("body", timeout=10_000)
    await asyncio.sleep(3)

    html = await page.evaluate("() => document.documentElement.outerHTML")
    Path("./debug_hr_landing.html").write_text(html, encoding="utf-8")
    print(f"  -> {len(html)} bytes (debug_hr_landing.html)")

    # Form-Elemente listen
    inputs = await page.locator("input").all()
    print(f"\n# 2. Inputs gefunden: {len(inputs)}")
    for i, inp in enumerate(inputs[:30]):
        try:
            name = await inp.get_attribute("name") or ""
            iid = await inp.get_attribute("id") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            itype = await inp.get_attribute("type") or "text"
            print(f"  [{i}] id={iid[:60]:60} name={name[:30]:30} type={itype:10} placeholder={placeholder[:30]}")
        except Exception as e:
            print(f"  [{i}] err: {e}")

    buttons = await page.locator("button, input[type='submit']").all()
    print(f"\n# 3. Buttons gefunden: {len(buttons)}")
    for i, btn in enumerate(buttons[:15]):
        try:
            txt = (await btn.text_content() or "").strip()[:50]
            iid = await btn.get_attribute("id") or ""
            print(f"  [{i}] id={iid[:60]:60} text={txt}")
        except Exception:
            pass

    # Selektoren-Test für Ergebnis-Container
    for sel in (
        "tr.ui-datatable-row",
        ".ui-datatable",
        ".search-result",
        ".bekanntmachung",
        "table",
        "form",
    ):
        cnt = await page.locator(sel).count()
        print(f"  selector {sel:30} → {cnt}")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
