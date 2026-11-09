// Standalone admin page (/static/admin.html): current palette, session, mobile layout.
const { BASE, SHOTS, check, summary, launch } = require("./lib");

(async () => {
  const { browser, page } = await launch({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await page.goto(BASE + "/static/admin.html");
  await page.waitForTimeout(900);

  const pal = await page.evaluate(() => ({
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyColor: getComputedStyle(document.body).color,
    font: getComputedStyle(document.body).fontFamily.slice(0, 40)
  }));
  check("current palette: body background", pal.bodyBg === "rgb(5, 5, 7)", JSON.stringify(pal));
  check("current palette: body text", pal.bodyColor === "rgb(242, 242, 244)", JSON.stringify(pal));
  check("app font stack (not monospace)", !/mono/i.test(pal.font), pal.font);

  check("login form visible", await page.isVisible("#l"));
  // The admin page must not touch the app session keys
  await page.evaluate(() => localStorage.setItem("lc_session_token", "spa-sentinel"));
  await page.fill("#l", "admin");
  await page.fill("#p", process.env.LC_ADMIN_PASSWORD || "");
  await page.click("#l-btn");
  await page.waitForTimeout(2500);

  const loggedIn = await page.evaluate(() => ({
    loginHidden: document.getElementById("scr-login").classList.contains("hidden"),
    mainVisible: !document.getElementById("scr-main").classList.contains("hidden"),
    adminToken: !!localStorage.getItem("lc_admin_token"),
    spa: localStorage.getItem("lc_session_token"),
    chips: document.querySelectorAll("#tabs .chip").length,
    rows: document.querySelectorAll("#content .row").length,
  }));
  check("admin login works", loggedIn.loginHidden && loggedIn.mainVisible, JSON.stringify(loggedIn));
  check("admin keeps its own session keys", loggedIn.adminToken && loggedIn.spa === "spa-sentinel", JSON.stringify(loggedIn));
  check("admin tabs rendered", loggedIn.chips >= 3, "chips=" + loggedIn.chips);
  check("admin content rendered", loggedIn.rows > 0, "rows=" + loggedIn.rows);

  // session survives a reload (no re-login)
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(2500);
  const restored = await page.evaluate(() => ({
    loginHidden: document.getElementById("scr-login").classList.contains("hidden"),
    mainVisible: !document.getElementById("scr-main").classList.contains("hidden"),
  }));
  check("admin session restored after reload", restored.loginHidden && restored.mainVisible, JSON.stringify(restored));

  await page.screenshot({ path: SHOTS + "admin-html-desktop.png" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(800);
  const mob = await page.evaluate(() => {
    const se = document.scrollingElement;
    return {
      overflowX: se.scrollWidth - se.clientWidth,
      chips: document.querySelectorAll("#tabs .chip").length,
      contentWidth: Math.round(document.getElementById("content").getBoundingClientRect().width),
    };
  });
  check("no horizontal overflow on mobile", mob.overflowX <= 2, "overflowX=" + mob.overflowX);
  check("mobile admin keeps its tabs", mob.chips >= 3 && mob.contentWidth <= 390, JSON.stringify(mob));
  await page.screenshot({ path: SHOTS + "admin-html-mobile.png", fullPage: false });

  // logout returns to the login form and drops only the admin session
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.click("#logout-btn");
  await page.waitForTimeout(500);
  await page.click("#cf-yes");
  await page.waitForTimeout(1800);
  const out = await page.evaluate(() => ({
    loginVisible: !document.getElementById("scr-login").classList.contains("hidden"),
    admin: !!localStorage.getItem("lc_admin_token"),
    spa: localStorage.getItem("lc_session_token")
  }));
  check("logout returns to login", out.loginVisible && !out.admin && out.spa === "spa-sentinel", JSON.stringify(out));

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
