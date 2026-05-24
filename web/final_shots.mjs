import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: "dark",
});
const page = await ctx.newPage();

const MAGIC = process.argv[2];
const BASE = "https://helium-prospector.vercel.app";

await page.goto(MAGIC, { waitUntil: "networkidle", timeout: 30000 });
await page.waitForTimeout(2500);

await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await page.screenshot({ path: "./screenshots/qa/FINAL-01-dashboard.png" });

await page.goto(`${BASE}/leads`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await page.screenshot({ path: "./screenshots/qa/FINAL-02-leads.png" });

const href = await page.locator('a[href^="/leads/"]').first().getAttribute("href");
await page.goto(`${BASE}${href}`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.screenshot({ path: "./screenshots/qa/FINAL-03-lead-detail.png", fullPage: true });

console.log("✓ Final screenshots saved");
await browser.close();
