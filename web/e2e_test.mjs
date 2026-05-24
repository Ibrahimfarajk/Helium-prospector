import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

await mkdir("./screenshots/qa", { recursive: true });

const MAGIC_LINK = process.argv[2];
const BASE = "https://helium-prospector.vercel.app";

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: "dark",
});
const page = await ctx.newPage();

// Track console errors
const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});

let pass = 0, fail = 0;
function check(label, cond) {
  if (cond) { console.log(`  ✓ ${label}`); pass++; }
  else { console.log(`  ✗ FAIL: ${label}`); fail++; }
}

console.log("=== E2E TEST ===\n");

// 1. Login Flow
console.log("[1] Login Flow");
await page.goto(MAGIC_LINK, { waitUntil: "networkidle", timeout: 30000 });
await page.waitForTimeout(2000);
check("Redirect zu Dashboard", page.url() === `${BASE}/` || page.url().endsWith("/"));

// 2. Dashboard
console.log("\n[2] Dashboard");
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
const kpiCount = await page.locator(".tabular-nums").count();
check(`KPI-Cards >= 4 (got ${kpiCount})`, kpiCount >= 4);
check("Tier-T1-Badge sichtbar", await page.locator('text="T1"').first().isVisible());
check("Top-Leads-Liste hat Einträge", (await page.locator('a[href^="/leads/"]').count()) >= 1);
await page.screenshot({ path: "./screenshots/qa/01-dashboard.png" });

// 3. Leads-Liste
console.log("\n[3] Leads-Liste");
await page.goto(`${BASE}/leads`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
const leadsCount = await page.locator("tbody tr").count();
check(`13 Leads in Tabelle (got ${leadsCount})`, leadsCount === 13);
check("Sort-Toggle Score sichtbar", await page.locator('button:has-text("Score")').isVisible());
check("Sort-Toggle hat 4 Optionen (Score/Frische/Datum/Name)",
      (await page.locator('button:has-text("Score"), button:has-text("Frische"), button:has-text("Datum"), button:has-text("Name")').count()) === 4);
await page.screenshot({ path: "./screenshots/qa/02-leads-list.png" });

// 4. Filter T1
console.log("\n[4] Filter T1");
await page.locator('button:has-text("T1")').first().click();
await page.waitForTimeout(1500);
const t1Count = await page.locator("tbody tr").count();
check(`Nur T1-Leads (sollte 4 sein, got ${t1Count})`, t1Count === 4);

// 5. Lead-Detail
console.log("\n[5] Lead-Detail");
const firstLeadHref = await page.locator('a[href^="/leads/"]').first().getAttribute("href");
await page.goto(`${BASE}${firstLeadHref}`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
check("Tier-Badge sichtbar", await page.locator('text=/^T[123]$/').first().isVisible());
check("Posterior wird angezeigt", await page.locator('text=/Posterior \\d+\\.\\d+%/').first().isVisible());
check("Telefon-Card sichtbar", await page.locator('text="TELEFON"').isVisible());
check("Dossier-Block vorhanden", await page.locator('text="Dossier"').isVisible());
check("Druckansicht-Link funktional (href != #)", await page.locator('a[href*="/export"]').first().isVisible());
check("Status-Pipeline 5 Stufen", (await page.locator('button:has(div.size-7)').count()) >= 5);
check("DnC-Button sichtbar", await page.locator('button:has-text("DnC")').isVisible());
check("Notizen-Editor vorhanden", await page.locator('textarea[placeholder*="Notiz"]').isVisible());
await page.screenshot({ path: "./screenshots/qa/03-lead-detail.png" });

// 6. Status-Pipeline-Update-Test
console.log("\n[6] Status-Update");
await page.locator('button:has(div.size-7)').nth(1).click(); // Klick auf "Review"
await page.waitForTimeout(1500);
check("Status Change Toast erschien", await page.locator('text=/Status:/').isVisible({ timeout: 2000 }).catch(() => false));

// 7. Notiz hinzufügen
console.log("\n[7] Notiz hinzufügen");
const noteText = `QA-Test-Notiz ${Date.now()}`;
await page.locator('textarea[placeholder*="Notiz"]').fill(noteText);
await page.locator('button:has-text("Speichern")').click();
await page.waitForTimeout(2000);
const noteVisible = await page.locator(`text="${noteText}"`).first().isVisible({ timeout: 3000 }).catch(() => false);
check("Notiz sichtbar in Timeline", noteVisible);

// 8. Cmd+K
console.log("\n[8] Cmd+K Command-Palette");
await page.keyboard.down("Control");
await page.keyboard.press("KeyK");
await page.keyboard.up("Control");
await page.waitForTimeout(500);
check("Command-Palette geöffnet", await page.locator('input[placeholder*="Aktion suchen"]').isVisible());
check("Navigation-Group sichtbar", await page.locator('text="Navigation"').isVisible());
check("Aktionen-Group sichtbar", await page.locator('text="Aktionen"').isVisible());
await page.screenshot({ path: "./screenshots/qa/04-cmdk.png" });

// Suche
await page.locator('input[placeholder*="Aktion suchen"]').fill("t1");
await page.waitForTimeout(300);
check("Filter findet T1-Items", await page.locator('text=/T1/').first().isVisible());
await page.screenshot({ path: "./screenshots/qa/05-cmdk-filter.png" });
await page.keyboard.press("Escape");

// 9. Pipeline-Runs
console.log("\n[9] Pipeline-Runs");
await page.goto(`${BASE}/runs`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
check("Pipeline-Runs-Tabelle sichtbar", await page.locator('text="STATUS"').isVisible());
check("Success-Badge in Run", await page.locator('text="success"').first().isVisible());

// 10. Settings
console.log("\n[10] Settings");
await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
check("Account-Card sichtbar", await page.locator('text="Account"').isVisible());
check("Admin-Badge sichtbar", await page.locator('text="admin"').isVisible());

// 11. Logout-Flow
console.log("\n[11] Logout-Flow");
// Skip — kann zum Verlust der Session führen

// 12. Mobile-Viewport
console.log("\n[12] Mobile (375x667)");
await page.setViewportSize({ width: 375, height: 667 });
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
const sidebarVisible = await page.locator('aside').isVisible().catch(() => false);
check("Sidebar versteckt auf Mobile", !sidebarVisible);
await page.screenshot({ path: "./screenshots/qa/06-mobile-dashboard.png" });

// Console Errors
console.log("\n[13] Console Errors");
check(`Keine Console-Errors (got ${consoleErrors.length})`, consoleErrors.length === 0);
if (consoleErrors.length) {
  console.log("  Errors:");
  consoleErrors.slice(0, 5).forEach(e => console.log(`    ${e.slice(0, 120)}`));
}

console.log(`\n=== RESULT: ${pass} passed / ${fail} failed ===`);
await browser.close();
process.exit(fail > 0 ? 1 : 0);
