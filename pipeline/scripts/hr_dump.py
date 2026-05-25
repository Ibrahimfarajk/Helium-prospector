"""Single-Run HTML-Dumper für handelsregister.de.

Ziel: EINE Live-Session, dann offline UI-Discovery. Vermeidet IP-Ban-Risiko.

Output:
- ./local_data/hr_dumps/01_landing.html          (Bekanntmachungs-Landing)
- ./local_data/hr_dumps/02_cookies_accepted.html (nach Cookie-Akzept)
- ./local_data/hr_dumps/03_search_form.html      (nach Klick auf Suche)
- ./local_data/hr_dumps/04_results.html          (Such-Ergebnis-Seite)
- ./local_data/hr_dumps/screenshots/             (jeweilige Screenshots)

Conservative Rate-Limit: 10-15 s zwischen Page-Actions.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

DUMP_DIR = Path(__file__).resolve().parent.parent / "local_data" / "hr_dumps"
DUMP_DIR.mkdir(parents=True, exist_ok=True)
(DUMP_DIR / "screenshots").mkdir(exist_ok=True)

PROFILE = Path.home() / ".helium-pipeline" / "browser-profile"
PROFILE.mkdir(parents=True, exist_ok=True)

STEALTH = Stealth()


async def slow(min_s=10, max_s=15):
    """Realistic delay between human actions."""
    delay = random.uniform(min_s, max_s)
    print(f"  ... sleep {delay:.1f}s")
    await asyncio.sleep(delay)


async def dump(page, step: str, label: str):
    html = await page.evaluate("() => document.documentElement.outerHTML")
    (DUMP_DIR / f"{step}_{label}.html").write_text(html, encoding="utf-8")
    await page.screenshot(path=str(DUMP_DIR / "screenshots" / f"{step}_{label}.png"))
    print(f"  -> dumped {step}_{label}.html  ({len(html)} bytes)")
    return html


async def main():
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=True,  # Bash-Tool hat keine GUI — wir prüfen via dump-Files
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="de-DE",
        timezone_id="Europe/Berlin",
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = await ctx.new_page()
    await STEALTH.apply_stealth_async(page)

    try:
        print("[1] Landing-Page laden...")
        await page.goto(
            "https://www.handelsregister.de/rp_web/welcome.xhtml",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        await dump(page, "01", "landing")

        await slow(10, 14)

        print("[2] Sitzungshinweis akzeptieren ('Verstanden' button)...")
        cookie_clicked = False
        for selector in [
            "a.cookie-btn",
            "a:has-text('Verstanden')",
            "#cookieForm\\:j_idt17",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    print(f"  -> clicking: {selector}")
                    await btn.click()
                    cookie_clicked = True
                    break
            except Exception as e:
                print(f"  selector failed {selector}: {e}")
                continue

        if not cookie_clicked:
            print("  WARN: kein Verstanden-Button — bereits akzeptiert?")

        await asyncio.sleep(3)
        await dump(page, "02", "after_cookies")

        await slow(10, 14)

        print("[3] Klick auf Bekanntmachungen-Menü-Link (PrimeFaces AJAX)...")
        # Spezifischer naviForm-Link (nicht der Mobile-Sidebar)
        try:
            await page.locator("#naviForm\\:bekanntmachungenLink").click()
            print("  -> naviForm:bekanntmachungenLink geklickt")
        except Exception as e:
            print(f"  naviForm-click failed: {e}")
        await asyncio.sleep(4)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await dump(page, "03", "bekanntmachungen")

        await slow(10, 14)

        print("[4] Inputs/Buttons inspizieren...")
        inputs = await page.locator("input").all()
        buttons = await page.locator("button").all()
        print(f"  inputs: {len(inputs)}, buttons: {len(buttons)}")
        snap = []
        for i, inp in enumerate(inputs[:40]):
            try:
                ident = await inp.get_attribute("id") or ""
                name = await inp.get_attribute("name") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                itype = await inp.get_attribute("type") or "text"
                if ident or placeholder:
                    snap.append(f"  input[{i}] id={ident[:50]} name={name[:30]} type={itype} ph={placeholder[:30]}")
            except Exception:
                pass
        for i, b in enumerate(buttons[:30]):
            try:
                ident = await b.get_attribute("id") or ""
                txt = (await b.text_content() or "").strip()[:40]
                if txt or ident:
                    snap.append(f"  button[{i}] id={ident[:50]} text={txt}")
            except Exception:
                pass

        (DUMP_DIR / "04_form_inspection.txt").write_text(
            "\n".join(snap), encoding="utf-8"
        )
        print(f"  -> 04_form_inspection.txt geschrieben ({len(snap)} Elemente)")

    except Exception as e:
        print(f"ERROR: {e}")
        await page.screenshot(path=str(DUMP_DIR / "screenshots" / "ERROR.png"))
        raise
    finally:
        print("\nFertig. Inspect:")
        print(f"  {DUMP_DIR}")
        await asyncio.sleep(2)
        await ctx.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
