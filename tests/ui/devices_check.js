// Devices page: pairing by 6-digit code. Run: node tests/ui/devices_check.js
const { SHOTS, check, summary, login, launch, launchMobile } = require("./lib");

(async () => {
  // ---------- desktop ----------
  const { browser, page: d } = await launch({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  d.on("pageerror", e => errs.push(e.message));
  await login(d, "admin");
  await d.evaluate(() => { window.location.hash = "#/devices"; });
  await d.waitForTimeout(2000);

  check("route #/devices stays (not redirected)", await d.evaluate(() => window.location.hash === "#/devices"));
  check("devices nav link present", await d.evaluate(() => !!document.querySelector(".nav-links a[href='#/devices']")));
  check("page title rendered", (await d.textContent(".page-title")).trim().length > 0, await d.textContent(".page-title"));
  check("pairing card present", await d.isVisible("#pair-code") && await d.isVisible("#pair-claim-btn"));

  const inputAttrs = await d.evaluate(() => {
    const el = document.querySelector("#pair-code");
    return { type: el.type, inputmode: el.getAttribute("inputmode"), maxlength: el.maxLength };
  });
  check("code input: text + numeric keyboard + max 6", inputAttrs.type === "text" && inputAttrs.inputmode === "numeric" && inputAttrs.maxlength === 6, JSON.stringify(inputAttrs));

  await d.fill("#pair-code", "12ab34");
  const filtered = await d.inputValue("#pair-code");
  check("non-digits stripped", filtered === "1234", filtered);
  check("pair button disabled with <6 digits", await d.isDisabled("#pair-claim-btn"));

  await d.fill("#pair-code", "000123");
  check("leading zeros preserved", (await d.inputValue("#pair-code")) === "000123", await d.inputValue("#pair-code"));
  check("pair button enabled with 6 digits", !(await d.isDisabled("#pair-claim-btn")));

  await d.click("#pair-claim-btn");
  await d.waitForTimeout(2500);
  const errText = (await d.textContent("#pair-msg")).trim();
  const errClass = await d.getAttribute("#pair-msg", "class");
  check("wrong code shows readable error", errText.length > 0 && errClass.includes("err") && !errText.includes("HTTP"), errClass + " | " + errText);
  check("button re-enabled after error", !(await d.isDisabled("#pair-claim-btn")));

  const paired = await d.evaluate(() => ({
    rows: document.querySelectorAll(".paired-row").length,
    empty: !!document.querySelector("#paired-list .empty"),
    hasUnpair: !!document.querySelector(".paired-row button"),
    catalog: !!document.querySelector("#device-grid")
  }));
  check("paired list rendered (rows or empty state)", paired.rows > 0 || paired.empty, JSON.stringify(paired));
  if (paired.rows > 0) check("unpair button present", paired.hasUnpair);
  check("device catalog block present", paired.catalog);
  await d.screenshot({ path: SHOTS + "devices-desktop.png" });

  check("no page errors (desktop)", errs.length === 0, errs.join(" | "));
  await d.close();

  // ---------- mobile ----------
  const { browser: b2, page: m } = await launchMobile();
  const errs2 = [];
  m.on("pageerror", e => errs2.push(e.message));
  await login(m, "admin");
  await m.evaluate(() => { window.location.hash = "#/devices"; });
  await m.waitForTimeout(2000);

  const mob = await m.evaluate(() => {
    const row = document.querySelector(".pair-row");
    const btn = document.querySelector("#pair-claim-btn");
    const inp = document.querySelector("#pair-code");
    const se = document.scrollingElement;
    return {
      rowDir: getComputedStyle(row).flexDirection,
      btnH: Math.round(btn.getBoundingClientRect().height),
      inputFont: parseFloat(getComputedStyle(inp).fontSize),
      inputmode: inp.getAttribute("inputmode"),
      overflowX: se.scrollWidth - se.clientWidth
    };
  });
  check("mobile: pairing row stacked", mob.rowDir === "column", JSON.stringify(mob));
  check("mobile: pair button touch-friendly (>=44px)", mob.btnH >= 44, "h=" + mob.btnH);
  check("mobile: big numeric input", mob.inputFont >= 24 && mob.inputmode === "numeric", JSON.stringify(mob));
  check("mobile: no horizontal overflow", mob.overflowX <= 1, "overflowX=" + mob.overflowX);
  await m.screenshot({ path: SHOTS + "devices-mobile.png" });

  check("no page errors (mobile)", errs2.length === 0, errs2.join(" | "));
  await m.close();
  await b2.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
