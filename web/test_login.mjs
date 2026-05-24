import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

await mkdir("./screenshots", { recursive: true });

const MAGIC_LINK = process.argv[2];
if (!MAGIC_LINK) {
  console.error("Usage: node test_login.mjs <MAGIC_LINK>");
  process.exit(1);
}

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: "dark",
});
const page = await ctx.newPage();

console.log("→ Opening magic link...");
await page.goto(MAGIC_LINK, { waitUntil: "networkidle", timeout: 30000 });
console.log(`→ Landed on: ${page.url()}`);

await page.waitForTimeout(2000);
console.log(`→ After settle: ${page.url()}`);

await page.screenshot({ path: "./screenshots/live-02-after-login.png", fullPage: false });

// Try navigating to leads list explicitly
console.log("\n→ Navigating to /leads...");
await page.goto("https://helium-prospector.vercel.app/leads", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForTimeout(1500);
console.log(`→ Final URL: ${page.url()}`);
await page.screenshot({ path: "./screenshots/live-03-leads-live.png", fullPage: false });

console.log("\n→ Navigating to dashboard...");
await page.goto("https://helium-prospector.vercel.app/", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: "./screenshots/live-04-dashboard-live.png", fullPage: false });

// Open a specific lead
console.log("\n→ Opening first lead...");
const firstLeadHref = await page.locator('a[href^="/leads/"]').first().getAttribute("href").catch(() => null);
if (firstLeadHref) {
  await page.goto(`https://helium-prospector.vercel.app${firstLeadHref}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "./screenshots/live-05-lead-detail-live.png", fullPage: false });
  console.log(`→ Lead opened: ${firstLeadHref}`);
}

// Pipeline runs
console.log("\n→ Pipeline runs...");
await page.goto("https://helium-prospector.vercel.app/runs", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.screenshot({ path: "./screenshots/live-06-runs-live.png", fullPage: false });

await browser.close();
console.log("\n✓ Done");
