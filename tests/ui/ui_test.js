// Desktop SPA smoke suite. Run: node tests/ui/ui_test.js
const fs = require("fs");
const os = require("os");
const path = require("path");
const { BASE, SHOTS, check, summary, launch } = require("./lib");

(async () => {
  const { browser, page } = await launch({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));

  console.log("=== login ===");
  await page.goto(BASE + "/");
  await page.waitForTimeout(700);
  check("static login visible", await page.isVisible("#static-login"));
  await page.fill("#sl", "admin");
  await page.fill("#sp", "7428");
  await page.click("#sbtn");
  await page.waitForTimeout(2500);
  check("nav visible after login", await page.isVisible(".nav"));
  check("nav-user = admin", (await page.textContent("#nav-user")).trim() === "admin", await page.textContent("#nav-user"));
  check("chat page rendered", await page.isVisible("#chat-list"));

  console.log("=== chat: open / search / send / edit / delete ===");
  const items = await page.$$("#chat-list .chat-item");
  check("chat list has items", items.length > 0, "n=" + items.length);
  if (items.length) {
    await items[0].click();
    await page.waitForTimeout(1200);
    check("messages panel open", await page.isVisible("#msg-input"));

    const mobileOnly = await page.evaluate(() => {
      return ["#chat-menu-btn", "#chat-dm-btn", "#chat-refresh-m", "#chat-new-btn"].map(sel => {
        const el = document.querySelector(sel);
        return el ? getComputedStyle(el).display : "missing";
      });
    });
    check("mobile-only buttons hidden on desktop", mobileOnly.every(v => v === "none"), mobileOnly.join(","));

    const total = await page.evaluate(() => document.querySelectorAll("#chat-list .chat-item").length);
    await page.fill("#chat-search-input", "zzzzzzz");
    await page.waitForTimeout(300);
    const visibleAfterNoMatch = await page.evaluate(() => Array.from(document.querySelectorAll("#chat-list .chat-item")).filter(e => e.style.display !== "none").length);
    check("chat search filters out everything", visibleAfterNoMatch === 0, "visible=" + visibleAfterNoMatch + " total=" + total);
    await page.fill("#chat-search-input", "");
    await page.waitForTimeout(300);
    const visibleAfterReset = await page.evaluate(() => Array.from(document.querySelectorAll("#chat-list .chat-item")).filter(e => e.style.display !== "none").length);
    check("chat search reset restores list", visibleAfterReset === total, visibleAfterReset + "/" + total);

    const uniq = "ui-msg-" + Date.now();
    await page.fill("#msg-input", uniq);
    await page.click("#send-btn");
    await page.waitForTimeout(1500);
    const lastText = await page.evaluate(() => {
      const els = document.querySelectorAll("#msg-list .msg .msg-text");
      return els.length ? els[els.length - 1].textContent : "";
    });
    check("sent message appears", lastText.includes(uniq), lastText.slice(0, 60));

    const editClicked = await page.evaluate((needle) => {
      const msgs = Array.from(document.querySelectorAll("#msg-list .msg"));
      const target = msgs.reverse().find(m => ((m.querySelector(".msg-text") || {}).textContent || "").includes(needle));
      if (!target) return false;
      const btn = Array.from(target.querySelectorAll(".msg-actions button")).find(b => (b.getAttribute("title") || "").toLowerCase().includes("редак"));
      if (!btn) return false;
      btn.click();
      return true;
    }, uniq);
    check("edit button clicked", editClicked);
    if (editClicked) {
      await page.waitForTimeout(800);
      check("edit modal opens (no native prompt)", await page.isVisible("#edit-text"));
      await page.fill("#edit-text", "ui-edited");
      await page.click("#edit-save");
      await page.waitForTimeout(2000);
      const edited = await page.evaluate(() => Array.from(document.querySelectorAll("#msg-list .msg .msg-text")).map(e => e.textContent).join(" | "));
      check("edit applied (modal save)", edited.includes("ui-edited"), edited.slice(0, 80));

      const targetMid = await page.evaluate(() => {
        const msgs = Array.from(document.querySelectorAll("#msg-list .msg"));
        const target = msgs.reverse().find(m => ((m.querySelector(".msg-text") || {}).textContent || "").includes("ui-edited"));
        return target ? target.dataset.mid : null;
      });
      const delClicked = await page.evaluate(() => {
        const msgs = Array.from(document.querySelectorAll("#msg-list .msg"));
        const target = msgs.reverse().find(m => ((m.querySelector(".msg-text") || {}).textContent || "").includes("ui-edited"));
        if (!target) return false;
        const btn = Array.from(target.querySelectorAll(".msg-actions button")).find(b => (b.getAttribute("title") || "").toLowerCase().includes("удал"));
        if (!btn) return false;
        btn.click();
        return true;
      });
      check("delete button clicked", delClicked);
      if (delClicked) {
        await page.waitForTimeout(500);
        check("delete confirm overlay appears", await page.isVisible("#cfm-yes"));
        await page.click("#cfm-yes");
        await page.waitForTimeout(1500);
        const stillThere = await page.evaluate((mid) => !!document.querySelector('#msg-list .msg[data-mid="' + mid + '"]'), targetMid);
        check("delete removes message", !stillThere, "mid=" + targetMid);
      }
    }
  }

  console.log("=== chat: photo attachment ===");
  const pngPath = path.join(os.tmpdir(), "lc_ui_photo.png");
  fs.writeFileSync(pngPath, Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64"));
  if (items.length) {
    await page.setInputFiles("#msg-file", pngPath);
    await page.waitForTimeout(800);
    await page.click("#send-btn");
    await page.waitForTimeout(2500);
    const hasImage = await page.evaluate(() => {
      const msgs = document.querySelectorAll("#msg-list .msg");
      if (!msgs.length) return false;
      return !!msgs[msgs.length - 1].querySelector(".attachment img");
    });
    check("photo attachment rendered in message", hasImage);
  }

  console.log("=== devices page ===");
  await page.evaluate(() => { window.location.hash = "#/devices"; });
  await page.waitForTimeout(2000);
  check("devices route stays", await page.evaluate(() => window.location.hash === "#/devices"));
  check("pairing card on devices page", await page.isVisible("#pair-code") && await page.isVisible("#pair-claim-btn"));
  check("paired list block rendered", await page.evaluate(() => !!document.querySelector("#paired-list .paired-row, #paired-list .empty")));

  console.log("=== account / admin / logout ===");
  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(1500);
  check("account page rendered", await page.isVisible("#content .page-title"));
  await page.evaluate(() => { window.location.hash = "#/admin"; });
  await page.waitForTimeout(2000);
  check("admin page rendered (tabs)", await page.evaluate(() => document.querySelectorAll("#content .tabs .tab").length > 0));
  await page.screenshot({ path: SHOTS + "ui-test-admin.png" });

  await page.click("#logout-btn");
  await page.waitForTimeout(2000);
  const afterLogout = await page.evaluate(() => ({
    hash: window.location.hash,
    navVisible: getComputedStyle(document.querySelector(".nav")).display !== "none",
    token: localStorage.getItem("lc_session_token"),
    loginVisible: !!document.querySelector("#login-login") || (!!document.querySelector("#static-login") && getComputedStyle(document.querySelector("#static-login")).display !== "none")
  }));
  check("logout returns to login", afterLogout.hash === "#/login" && !afterLogout.navVisible && !afterLogout.token && afterLogout.loginVisible, JSON.stringify(afterLogout));

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
