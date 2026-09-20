const path = require("path");
const fs = require("fs");
const pwPath = process.env.LOCALAPPDATA + "\\npm-cache\\_npx\\0b9ff77863cb6e9f\\node_modules\\playwright";
const { chromium } = require(pwPath);

const dir = "D:\\opencode\\LC_PROJECT\\experiments\\ui";
const shots = path.join(dir, "shots");
if (!fs.existsSync(shots)) fs.mkdirSync(shots, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const errors = [];
  const file = (v) => "file:///" + path.join(dir, v + ".html").replace(/\\/g, "/");

  for (const v of ["v1", "v2", "v3", "v4"]) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on("pageerror", e => errors.push(v + " pageerror: " + e.message));
    page.on("console", m => { if (m.type() === "error") errors.push(v + " console: " + m.text()); });
    await page.goto(file(v), { waitUntil: "load" });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(shots, v + "-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(shots, v + "-mobile.png") });
    await page.close();
  }

  {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on("pageerror", e => errors.push("v5 pageerror: " + e.message));
    page.on("console", m => { if (m.type() === "error") errors.push("v5 console: " + m.text()); });
    await page.goto(file("v5"), { waitUntil: "load" });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(shots, "v5-desktop.png") });
    await page.close();

    const m = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
    m.on("pageerror", e => errors.push("v5 pageerror: " + e.message));
    m.on("console", c => { if (c.type() === "error") errors.push("v5 console: " + c.text()); });
    await m.goto(file("v5"), { waitUntil: "load" });
    await m.waitForTimeout(400);
    await m.screenshot({ path: path.join(shots, "v5-mobile-list.png") });
    await m.click("#chats .chat:first-child");
    await m.waitForTimeout(350);
    await m.screenshot({ path: path.join(shots, "v5-mobile-chat.png") });
    await m.click("#hamburger");
    await m.waitForTimeout(300);
    await m.screenshot({ path: path.join(shots, "v5-mobile-menu.png") });
    await m.close();
  }

  await browser.close();
  console.log(errors.length ? "ERRORS:\n" + errors.join("\n") : "no console errors");
  const names = [];
  for (const v of ["v1", "v2", "v3", "v4"]) for (const k of ["desktop", "mobile"]) names.push(v + "-" + k);
  names.push("v5-desktop", "v5-mobile-list", "v5-mobile-chat", "v5-mobile-menu");
  for (const n of names) {
    const f = path.join(shots, n + ".png");
    console.log(f, fs.existsSync(f) ? fs.statSync(f).size + " bytes" : "MISSING");
  }
})();
