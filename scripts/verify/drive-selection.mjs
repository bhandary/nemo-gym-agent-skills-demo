/**
 * Drive the playbook checkbox journey. Does not start a run.
 * The page has no mode control. Run would start live, so this script never clicks it.
 */
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const playwrightPackage = fileURLToPath(new URL("../../.verify-cache/node_modules/playwright/package.json", import.meta.url));
if (!existsSync(playwrightPackage)) {
  console.error("Playwright is not installed. From the repository root, run:");
  console.error("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --prefix .verify-cache playwright");
  process.exit(1);
}
const { chromium } = createRequire(playwrightPackage)("playwright");
const activePath = new URL("../../.verify-evidence/active", import.meta.url);
const evidence = process.env.VERIFY_EVIDENCE || readFileSync(activePath, "utf8").trim();
const launch = JSON.parse(readFileSync(`${evidence}/launch.json`, "utf8"));
const base = process.env.VERIFY_BASE_URL || launch.base_url;
function chromePath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    const found = spawnSync("sh", ["-c", `command -v ${name}`], { encoding: "utf8" });
    const path = (found.stdout || "").trim();
    if (found.status === 0 && path) return path;
  }
  return "";
}

async function headersOf(page) {
  return page.locator("#comparison [role='columnheader']").evaluateAll((nodes) =>
    nodes.map((node) => (node.textContent || "").trim()).filter((text) => text && text !== "Ticket"),
  );
}

async function captionOf(page) {
  return (await page.locator(".picker-now").innerText()).replace(/\s+/g, " ").trim();
}

async function expectColumns(page, labels) {
  const headers = await headersOf(page);
  const caption = await captionOf(page);
  const expected = `The comparison shows ${labels.join(", ")}.`;
  if (headers.join("|") !== labels.join("|")) {
    throw new Error(`headers ${headers.join("|")} expected ${labels.join("|")}`);
  }
  if (caption !== expected) throw new Error(`caption ${caption} expected ${expected}`);
}

async function setSkills(page, names) {
  const boxes = page.locator("#picker .skill-checks input[type='checkbox']");
  const count = await boxes.count();
  for (let index = 0; index < count; index += 1) {
    const box = boxes.nth(index);
    const value = await box.getAttribute("value");
    const want = names.includes(value);
    if ((await box.isChecked()) !== want) await box.setChecked(want);
  }
}

const executablePath = chromePath();
const browser = await chromium.launch({
  headless: true,
  executablePath: executablePath || undefined,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const shots = [];

try {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.locator("#comparison h2", { hasText: "What the grader awarded" }).waitFor();
  if (await page.locator("#modes, input[name='mode']").count()) {
    throw new Error("A mode control is still on the page.");
  }
  if (await page.locator("#banner").isVisible()) {
    throw new Error("The score banner is visible before a run. Launch without DEMO_SHOW_RECORDED.");
  }
  const runLabel = (await page.locator("#run-button").innerText()).trim();
  if (runLabel !== "Run") throw new Error(`run button ${runLabel}`);
  const pageShot = `${evidence}/00-page.png`;
  await page.screenshot({ path: pageShot });
  shots.push(pageShot);

  const all = [
    "security-first-response",
    "ticket-classification",
    "access-request-policy",
    "priority-matrix",
  ];
  await setSkills(page, all);
  const matrix = page.locator("#picker label.skill-check.wide input[type='checkbox']");
  if (!(await matrix.isChecked())) await matrix.check();
  await expectColumns(page, ["No skills", "All four skills", "Without the priority matrix"]);
  const means = (await page.locator("#comparison .mean b").allInnerTexts()).map((text) => text.trim());
  if (means.join(",") !== "0.40,1.00,0.50") throw new Error(`default means ${means.join(",")}`);
  const first = `${evidence}/01-all-four.png`;
  await page.screenshot({ path: first, fullPage: true });
  shots.push(first);

  await setSkills(page, all.filter((name) => name !== "access-request-policy"));
  await expectColumns(page, ["No skills", "Without Access request policy", "Without the priority matrix"]);
  if (await page.locator("#comparison .column-note").count()) {
    throw new Error("The live preview still shows a recorded-sample note.");
  }
  const accessMeans = (await page.locator("#comparison .mean b").allInnerTexts()).map((text) => text.trim());
  if (accessMeans.join(",") !== "0.40,—,—") throw new Error(`access means ${accessMeans.join(",")}`);
  await page.locator("#trace [role='tab']", { hasText: "Agent decision" }).click();
  const walkTitles = (await page.locator("#trace .compare-card h3").allInnerTexts()).map((text) => text.trim());
  if (walkTitles.join("|") !== "No skills|Without Access request policy|Without the priority matrix") {
    throw new Error(`walk titles ${walkTitles.join("|")}`);
  }
  const second = `${evidence}/02-without-access.png`;
  await page.screenshot({ path: second, fullPage: true });
  shots.push(second);

  await setSkills(page, []);
  await expectColumns(page, ["No skills"]);
  if (await page.locator("#comparison .column-note").count()) {
    throw new Error("All playbooks off still shows a missing-mix note.");
  }
  if (await matrix.isEnabled()) throw new Error("The matrix comparison stayed enabled with every playbook off.");
  if (await page.locator("#matrix-why").isHidden()) throw new Error("The matrix explanation is hidden.");
  const third = `${evidence}/03-no-skills.png`;
  await page.screenshot({ path: third, fullPage: true });
  shots.push(third);

  await setSkills(page, all.filter((name) => name !== "priority-matrix"));
  await expectColumns(page, ["No skills", "Without the priority matrix"]);
  if (await matrix.isEnabled()) throw new Error("The matrix comparison stayed enabled.");
  const matrixMeans = (await page.locator("#comparison .mean b").allInnerTexts()).map((text) => text.trim());
  if (matrixMeans.join(",") !== "0.40,0.50") throw new Error(`matrix-off means ${matrixMeans.join(",")}`);
  const fourth = `${evidence}/04-matrix-off.png`;
  await page.screenshot({ path: fourth, fullPage: true });
  shots.push(fourth);

  const proof = { ok: true, feature: "skill-selection", base_url: base, shots };
  writeFileSync(`${evidence}/selection-proof.json`, JSON.stringify(proof, null, 2) + "\n");
  console.log(JSON.stringify(proof, null, 2));
} catch (error) {
  await page.screenshot({ path: `${evidence}/selection-failure.png`, fullPage: true }).catch(() => {});
  const failure = { ok: false, reason: error instanceof Error ? error.message : String(error) };
  writeFileSync(`${evidence}/selection-proof.json`, JSON.stringify(failure, null, 2) + "\n");
  console.error(failure.reason);
  process.exitCode = 1;
} finally {
  await browser.close();
}
