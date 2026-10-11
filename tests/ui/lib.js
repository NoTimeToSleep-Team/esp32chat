const path = require("path");
const pwPath = process.env.LOCALAPPDATA + "\\npm-cache\\_npx\\0b9ff77863cb6e9f\\node_modules\\playwright";
const { chromium } = require(pwPath);

const BASE = process.env.LC_BASE || "http://127.0.0.1:18080";
const SHOTS = path.join(__dirname, "..", "..", "experiments", "ui", "shots") + path.sep;

let pass = 0;
let fail = 0;

function check(name, ok, extra) {
  if (ok) { pass++; console.log("  ok  " + name); }
  else { fail++; console.log("FAIL  " + name + "  " + (extra === undefined ? "" : extra)); }
}

function summary() {
  console.log("RESULT: " + pass + " passed, " + fail + " failed");
  return fail;
}

async function login(page, user, password, settleMs) {
  // Suites assert Russian-localized labels; the app itself defaults to English.
  // Set the language before app scripts run, then re-apply once the app is up.
  await page.addInitScript(() => { try { localStorage.setItem("lc_lang", "rus"); } catch (e) {} });
  await page.goto(BASE + "/");
  await page.waitForTimeout(700);
  await page.fill("#sl", user || "admin");
  await page.fill("#sp", password || "7428");
  await page.click("#sbtn");
  await page.waitForTimeout(settleMs || 2500);
  await page.evaluate(() => {
    try {
      localStorage.setItem("lc_lang", "rus");
      if (typeof applyLang === "function") { window.LANG = "rus"; applyLang(); }
    } catch (e) {}
  });
  await page.waitForTimeout(300);
}

async function launch(opts) {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage(opts || { viewport: { width: 1280, height: 800 } });
  return { browser, page };
}

async function launchMobile() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  return { browser, ctx, page };
}

function swipeFactory(cdp) {
  return async function swipe(x, y1, y2, steps) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: y1 }] });
    const n = steps || 10;
    for (let i = 1; i <= n; i++) {
      const y = y1 + (y2 - y1) * i / n;
      await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y }] });
      await new Promise(r => setTimeout(r, 16));
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  };
}

module.exports = { chromium, BASE, SHOTS, check, summary, login, launch, launchMobile, swipeFactory };
