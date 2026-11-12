/**
 * Drive the Mock model journey in the TicketNow briefing page.
 *
 * Requires the server from scripts/verify/launch.sh and the playwright
 * package on NODE_PATH (see .cursor/skills/verify-ticketnow/SKILL.md).
 * Uses the system Chrome when CHROME_PATH or `google-chrome` is available.
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, copyFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const playwrightPackage = fileURLToPath(new URL("../../.verify-cache/node_modules/playwright/package.json", import.meta.url));
if (!existsSync(playwrightPackage)) {
  console.error("Playwright is not installed. From the repository root, run:");
  console.error("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --prefix .verify-cache playwright");
  process.exit(1);
}
const { chromium } = createRequire(playwrightPackage)("playwright");

const rootPath = fileURLToPath(new URL("../../", import.meta.url));
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

const SKILLS = [
  "security-first-response",
  "ticket-classification",
  "access-request-policy",
  "priority-matrix",
];

const EXPECTED = [
  { variant: "no_skills", mean: 0.4, correct: 0, total: 12 },
  { variant: "full_skills", mean: 1.0, correct: 12, total: 12 },
  { variant: "without_priority_matrix", mean: 0.5, correct: 2, total: 12 },
];

function closeEnough(left, right) {
  return Math.abs(Number(left) - Number(right)) < 0.001;
}

async function readJson(url) {
  const response = await fetch(url);
  const body = await response.json();
  return { status: response.status, body };
}

const briefing = await readJson(`${base}/api/briefing`);
writeFileSync(`${evidence}/briefing.json`, JSON.stringify(briefing.body, null, 2) + "\n");
if (!briefing.body.modes?.mock?.enabled) {
  const reason = briefing.body.modes?.mock?.reason || "Mock model is disabled.";
  writeFileSync(`${evidence}/proof.json`, JSON.stringify({ ok: false, reason }, null, 2) + "\n");
  console.error(`Mock journey failed before the click: ${reason}`);
  process.exit(1);
}

const executablePath = chromePath();
const launchOptions = {
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
};
if (executablePath) launchOptions.executablePath = executablePath;

const browser = await chromium.launch(launchOptions);
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const started = Date.now();
let postBody = null;
page.on("response", async (response) => {
  if (response.url().endsWith("/api/runs") && response.request().method() === "POST" && postBody === null) {
    postBody = { status: response.status(), body: await response.json().catch(() => null) };
  }
});

try {
  if (!briefing.body.show_mock) {
    throw new Error("Run starts live unless the server was launched with DEMO_SHOW_MOCK=1.");
  }
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.locator("#comparison h2", { hasText: "What the grader awarded" }).waitFor();
  if (await page.locator("#modes, input[name='mode']").count()) {
    throw new Error("A mode control is on the page. Mock is started by Run when DEMO_SHOW_MOCK=1, not by a radio.");
  }
  if (await page.locator("#run-button").isDisabled()) {
    const reason = (await page.locator("#mode-detail").innerText()).trim();
    throw new Error(reason || "Run is disabled. The briefing reason is in briefing.json.");
  }

  for (const name of SKILLS) {
    const box = page.locator(`#picker input[type="checkbox"][value="${name}"]`);
    if (!(await box.isChecked())) await box.check();
  }
  const matrix = page.locator("#picker label.skill-check.wide input[type='checkbox']");
  if (!(await matrix.isChecked())) await matrix.check();
  const summary = (await page.locator(".picker-now").innerText()).replace(/\s+/g, " ").trim();
  if (!summary.includes("No skills") || !summary.includes("All four skills") || !summary.includes("Without the priority matrix")) {
    throw new Error(`Playbook summary did not name the three scored columns: ${summary}`);
  }
  await page.screenshot({ path: `${evidence}/01-mock-selected.png`, fullPage: true });

  await page.locator("#run-button").click();
  await page.locator("#progress:not([hidden])").waitFor();
  await page.locator("#run-button", { hasText: "Running…" }).waitFor();
  await page.screenshot({ path: `${evidence}/02-running.png`, fullPage: true });

  const outcome = await page.waitForFunction(() => {
    const alert = document.querySelector("#alert");
    const heading = alert && !alert.hidden ? alert.querySelector("h2")?.textContent || "" : "";
    if (heading === "This run did not finish") return "failed";
    const banner = document.querySelector("#banner strong")?.textContent || "";
    const button = document.querySelector("#run-button")?.textContent || "";
    if (banner === "Mock model" && button === "Run") return "ok";
    return "";
  }, null, { timeout: 240000 });
  const verdict = await outcome.jsonValue();
  if (verdict !== "ok") {
    const message = await page.locator("#alert").innerText();
    throw new Error(message || "The mock run failed.");
  }

  const means = (await page.locator("#comparison .mean b").allInnerTexts()).map((text) => text.trim());
  const decisions = (await page.locator("#comparison .mean span").allInnerTexts()).map((text) => text.trim());
  if (means.join(",") !== "0.40,1.00,0.50") {
    throw new Error(`On-screen means were ${means.join(", ")}`);
  }
  if (!decisions.includes("0 of 12 decisions correct") || !decisions.includes("12 of 12 decisions correct") || !decisions.includes("2 of 12 decisions correct")) {
    throw new Error(`On-screen decision counts were ${decisions.join(" | ")}`);
  }
  await page.screenshot({ path: `${evidence}/03-scores.png`, fullPage: true });

  const current = await readJson(`${base}/api/runs/current`);
  const run = current.body.run;
  if (!run || run.status !== "succeeded" || run.mode !== "mock") {
    throw new Error(`GET /api/runs/current did not return a succeeded mock run: ${JSON.stringify(current.body)}`);
  }
  const fetched = await readJson(`${base}/api/runs/${run.id}`);
  if (fetched.status !== 200 || fetched.body.status !== "succeeded") {
    throw new Error(`GET /api/runs/${run.id} returned ${fetched.status} ${fetched.body.status}`);
  }
  writeFileSync(`${evidence}/run.json`, JSON.stringify(fetched.body, null, 2) + "\n");
  writeFileSync(`${evidence}/run-id`, `${run.id}\n`);
  if (postBody) writeFileSync(`${evidence}/post-run.json`, JSON.stringify(postBody, null, 2) + "\n");

  const summaryRows = fetched.body.view?.comparison?.summary || [];
  for (const expected of EXPECTED) {
    const row = summaryRows.find((item) => item.variant === expected.variant);
    if (!row || !closeEnough(row.mean_reward, expected.mean) || row.correct !== expected.correct || row.total !== expected.total) {
      throw new Error(`Run JSON summary for ${expected.variant} was ${JSON.stringify(row)}`);
    }
  }
  const logTail = fetched.body.log_tail || "";
  if (!logTail.includes("mean/reward")) {
    throw new Error("The run log tail did not include a mean/reward line.");
  }
  const serverLog = readFileSync(`${evidence}/server.log`, "utf8");
  if (!serverLog.includes("[gym]") || !serverLog.includes("Started a local Ray instance.")) {
    throw new Error("server.log did not show Gym forwarding a local Ray start.");
  }

  const copied = [];
  for (const name of ["no_skills", "full_skills", "without_priority_matrix"]) {
    const source = `${rootPath}results/ui/${run.id}/${name}_aggregate_metrics.json`;
    if (!existsSync(source)) throw new Error(`Missing aggregate metrics at ${source}`);
    const target = `${evidence}/${name}_aggregate_metrics.json`;
    copyFileSync(source, target);
    copied.push(target);
  }

  const proof = {
    ok: true,
    feature: "mock-run",
    base_url: base,
    run_id: run.id,
    elapsed_seconds: Math.round((Date.now() - started) / 100) / 10,
    means,
    decisions,
    chrome: executablePath || "playwright-default",
    artifacts: [
      `${evidence}/01-mock-selected.png`,
      `${evidence}/02-running.png`,
      `${evidence}/03-scores.png`,
      `${evidence}/run.json`,
      `${evidence}/server.log`,
      ...copied,
    ],
  };
  writeFileSync(`${evidence}/proof.json`, JSON.stringify(proof, null, 2) + "\n");
  console.log(JSON.stringify(proof, null, 2));
} catch (error) {
  mkdirSync(evidence, { recursive: true });
  await page.screenshot({ path: `${evidence}/failure.png`, fullPage: true }).catch(() => {});
  const failure = { ok: false, reason: error instanceof Error ? error.message : String(error) };
  writeFileSync(`${evidence}/proof.json`, JSON.stringify(failure, null, 2) + "\n");
  console.error(failure.reason);
  process.exitCode = 1;
} finally {
  await browser.close();
}
