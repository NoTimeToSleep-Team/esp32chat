// Standalone admin page (/static/admin.html) smoke + palette check.
const { BASE, SHOTS, check, summary, launch } = require("./lib");

(async () => {
  const { browser, page } = await launch({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  await page.goto(BASE + "/static/admin.html");
  await page.waitForTimeout(900);

  const pal = await page.evaluate(() => ({
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyColor: getComputedStyle(document.body).color,
    font: getComputedStyle(document.body).fontFamily.slice(0, 40)
  }));
  check("v5 palette: body background", pal.bodyBg === "rgb(14, 22, 33)", JSON.stringify(pal));
  check("v5 palette: body text", pal.bodyColor === "rgb(241, 245, 249)", JSON.stringify(pal));
  check("app font stack (not monospace)", !/mono/i.test(pal.font), pal.font);

  check("login form visible", await page.isVisible("#l"));
  await page.fill("#l", "admin");
  await page.fill("#p", "7428");
  await page.evaluate(() => document.querySelector("#login form").dispatchEvent(new Event("submit", { cancelable: true })));
  await page.waitForTimeout(2500);
  const loggedIn = await page.evaluate(() => (document.querySelector("#login").textContent || "").includes("Logged in"));
  check("admin login works", loggedIn, await page.textContent("#login"));

  const tabs = await page.$$(".tabs .tab");
  check("tabs rendered", tabs.length >= 4, "n=" + tabs.length);
  if (tabs.length > 1) {
    await tabs[1].click();
    await page.waitForTimeout(1500);
    const active = await page.evaluate(() => {
      const el = document.querySelector(".tabs .tab.active");
      return el ? el.textContent.trim() : null;
    });
    check("tab switch works", !!active, "active=" + active);
  }
  await page.screenshot({ path: SHOTS + "admin-html-desktop.png" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(600);
  const mob = await page.evaluate(() => {
    const se = document.scrollingElement;
    return { overflowX: se.scrollWidth - se.clientWidth, winH: window.innerHeight };
  });
  check("no horizontal overflow on mobile", mob.overflowX <= 2, "overflowX=" + mob.overflowX);
  await page.screenshot({ path: SHOTS + "admin-html-mobile.png", fullPage: true });

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
