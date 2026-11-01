// Standalone admin page (/static/admin.html): palette, session, mobile layout.
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
  // The admin page must not touch the app session keys
  await page.evaluate(() => localStorage.setItem("lc_session_token", "spa-sentinel"));
  await page.fill("#l", "admin");
  await page.fill("#p", process.env.LC_ADMIN_PASSWORD || "");
  await page.evaluate(() => document.querySelector("#login form").dispatchEvent(new Event("submit", { cancelable: true })));
  await page.waitForTimeout(2500);
  const loggedIn = await page.evaluate(() => (document.querySelector("#login").textContent || "").includes("Logged in"));
  check("admin login works", loggedIn, await page.textContent("#login"));
  const storage = await page.evaluate(() => ({
    admin: !!localStorage.getItem("lc_admin_token"),
    spa: localStorage.getItem("lc_session_token")
  }));
  check("admin keeps its own session keys", storage.admin && storage.spa === "spa-sentinel", JSON.stringify(storage));

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

  // session survives a reload (no re-login)
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(2500);
  const restored = await page.evaluate(() => ({
    main: document.getElementById("main").style.display === "block",
    who: (document.querySelector("#login").textContent || "").includes("Logged in")
  }));
  check("admin session restored after reload", restored.main && restored.who, JSON.stringify(restored));

  // tables get a scroll wrapper + labeled cells for the mobile card layout
  await page.evaluate(() => switchTab("users"));
  await page.waitForTimeout(2000);
  const tables = await page.evaluate(() => {
    const t = document.querySelector("#panel-users table");
    return { wrapped: !!t.closest(".tbl"), thead: !!t.querySelector("thead"), label: (t.querySelector("tbody td") || {}).getAttribute ? t.querySelector("tbody td").getAttribute("data-label") : null };
  });
  check("tables wrapped and labeled", tables.wrapped && tables.thead && tables.label === "ID", JSON.stringify(tables));

  await page.screenshot({ path: SHOTS + "admin-html-desktop.png" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(800);
  const mob = await page.evaluate(() => {
    const se = document.scrollingElement;
    const tr = document.querySelector("#panel-users tbody tr");
    const thead = document.querySelector("#panel-users thead");
    return {
      overflowX: se.scrollWidth - se.clientWidth,
      rowDisplay: tr ? getComputedStyle(tr).display : "",
      theadDisplay: thead ? getComputedStyle(thead).display : "",
      rowWidth: tr ? Math.round(tr.getBoundingClientRect().width) : 0
    };
  });
  check("no horizontal overflow on mobile", mob.overflowX <= 2, "overflowX=" + mob.overflowX);
  check("users table stacks into cards on mobile", mob.rowDisplay === "block" && mob.theadDisplay === "none" && mob.rowWidth <= 390, JSON.stringify(mob));
  await page.screenshot({ path: SHOTS + "admin-html-mobile.png", fullPage: false });

  // logout returns to the login form and drops only the admin session
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.evaluate(() => document.querySelector(".btn-logout").click());
  await page.waitForTimeout(1800);
  const out = await page.evaluate(() => ({
    loginVisible: !!document.getElementById("l") && document.getElementById("l").offsetParent !== null,
    admin: !!localStorage.getItem("lc_admin_token"),
    spa: localStorage.getItem("lc_session_token")
  }));
  check("logout returns to login", out.loginVisible && !out.admin && out.spa === "spa-sentinel", JSON.stringify(out));

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
