// Mobile chrome / iOS viewport checks. Run: node tests/ui/mobile_chrome_check.js
// Requires the app running on 127.0.0.1:18080 (see tests/ui/README.md).
const { BASE, SHOTS, check, summary, login, launchMobile, swipeFactory } = require("./lib");

(async () => {
  const { browser, ctx, page: m } = await launchMobile();
  const errs = [];
  m.on("pageerror", e => errs.push(e.message));
  await login(m, "admin", "7428");

  const listInfo = await m.evaluate(() => {
    const nav = document.querySelector(".nav");
    const head = document.querySelector(".chat-side-head");
    const list = document.querySelector("#chat-list");
    const r = head.getBoundingClientRect();
    return {
      navVisible: getComputedStyle(nav).display !== "none",
      headBottom: Math.round(r.bottom),
      listTop: Math.round(list.getBoundingClientRect().top),
      hasMenuBtn: !!document.querySelector("#chat-menu-btn"),
      hasNewBtn: !!document.querySelector("#chat-new-btn")
    };
  });
  check("list screen: nav hidden", !listInfo.navVisible, JSON.stringify(listInfo));
  check("list screen: chrome <= 70px", listInfo.listTop <= 70, "listTop=" + listInfo.listTop);
  check("list screen: menu + new chat buttons present", listInfo.hasMenuBtn && listInfo.hasNewBtn);
  await m.screenshot({ path: SHOTS + "mobile-compact-list.png" });

  const icons = await m.evaluate(() => {
    const dm = document.querySelector("#chat-dm-btn");
    const rf = document.querySelector("#chat-refresh-m");
    const cs = getComputedStyle(dm), cr = getComputedStyle(rf);
    return {
      dmText: dm.textContent.trim(),
      rfW: Math.round(rf.getBoundingClientRect().width),
      rfH: Math.round(rf.getBoundingClientRect().height),
      rfFont: parseFloat(cr.fontSize),
      dmBg: cs.backgroundColor
    };
  });
  check("DM button has label", /Личка|DM/.test(icons.dmText), JSON.stringify(icons));
  check("icon buttons >=38px, font >=18px", icons.rfW >= 38 && icons.rfH >= 38 && icons.rfFont >= 18, JSON.stringify(icons));
  check("icon buttons have visible background", icons.dmBg !== "rgba(0, 0, 0, 0)" && icons.dmBg !== "transparent", icons.dmBg);

  const cdp = await ctx.newCDPSession(m);
  const swipe = swipeFactory(cdp);

  const docLock = await m.evaluate(() => {
    const se = document.scrollingElement;
    return {
      bodyPos: getComputedStyle(document.body).position,
      docScrollH: se.scrollHeight, docClientH: se.clientHeight,
      appH: getComputedStyle(document.documentElement).getPropertyValue("--app-h").trim()
    };
  });
  check("page locked in chat mode (body fixed)", docLock.bodyPos === "fixed", JSON.stringify(docLock));
  check("document has no scrollable overflow", docLock.docScrollH <= docLock.docClientH + 1, JSON.stringify(docLock));
  check("app height variable set", /^\d+px$/.test(docLock.appH), docLock.appH);

  await swipe(195, 120, 500);
  await m.waitForTimeout(400);
  const afterDrag = await m.evaluate(() => {
    const se = document.scrollingElement;
    const head = document.querySelector(".chat-side-head").getBoundingClientRect();
    return { docTop: se.scrollTop, headTop: Math.round(head.top) };
  });
  check("page stays put when dragging header", afterDrag.docTop === 0 && afterDrag.headTop === 0, JSON.stringify(afterDrag));

  await m.evaluate(() => {
    document.documentElement.style.setProperty("--app-h", "420px");
    document.documentElement.style.setProperty("--app-top", "100px");
  });
  await m.waitForTimeout(250);
  const kb = await m.evaluate(() => {
    const body = document.body.getBoundingClientRect();
    const side = document.querySelector(".chat-side").getBoundingClientRect();
    const list = document.querySelector("#chat-list").getBoundingClientRect();
    return { bodyTop: Math.round(body.top), bodyH: Math.round(body.height), sideTop: Math.round(side.top), sideH: Math.round(side.height), listBottom: Math.round(list.bottom) };
  });
  check("app follows visible viewport (keyboard emulation)", kb.bodyTop === 100 && Math.abs(kb.bodyH - 420) < 3 && kb.sideTop === 100 && Math.abs(kb.sideH - 420) < 3 && kb.listBottom <= 520 && kb.listBottom > 440, JSON.stringify(kb));
  await m.evaluate(() => {
    document.documentElement.style.removeProperty("--app-h");
    document.documentElement.style.removeProperty("--app-top");
  });
  await m.waitForTimeout(300);
  const kbRestored = await m.evaluate(() => {
    const body = document.body.getBoundingClientRect();
    return { bodyTop: Math.round(body.top), bodyH: Math.round(body.height) };
  });
  check("app restores after keyboard closes", kbRestored.bodyTop === 0 && Math.abs(kbRestored.bodyH - 844) < 3, JSON.stringify(kbRestored));

  const s0 = await m.evaluate(() => document.querySelector("#chat-list").scrollTop);
  await swipe(195, 700, 250);
  await m.waitForTimeout(500);
  const s1 = await m.evaluate(() => document.querySelector("#chat-list").scrollTop);
  check("list scrolls by touch", s1 > s0, s0 + " -> " + s1);
  await m.evaluate(() => { document.querySelector("#chat-list").scrollTop = 0; });

  await m.click("#chat-list .chat-item");
  await m.waitForTimeout(1200);
  const chatInfo = await m.evaluate(() => {
    const nav = document.querySelector(".nav");
    const chead = document.querySelector(".chead");
    const pin = document.querySelector(".pin-bar");
    const list = document.querySelector("#msg-list");
    const comp = document.querySelector(".comp-field").getBoundingClientRect();
    return {
      navVisible: getComputedStyle(nav).display !== "none",
      listTop: Math.round(list.getBoundingClientRect().top),
      headBottom: Math.round(chead.getBoundingClientRect().bottom),
      pinH: pin ? Math.round(pin.getBoundingClientRect().height) : 0,
      compBottom: Math.round(comp.bottom),
      winH: window.innerHeight
    };
  });
  check("chat screen: nav hidden", !chatInfo.navVisible, JSON.stringify(chatInfo));
  check("chat screen: chrome <= 60px", chatInfo.listTop - chatInfo.headBottom - chatInfo.pinH <= 12, "gap=" + (chatInfo.listTop - chatInfo.headBottom - chatInfo.pinH));
  check("chat screen: composer at bottom", chatInfo.compBottom <= chatInfo.winH + 1 && chatInfo.compBottom > chatInfo.winH - 80, "compBottom=" + chatInfo.compBottom);
  await m.screenshot({ path: SHOTS + "mobile-compact-chat.png" });

  const c0 = await m.evaluate(() => { const l = document.querySelector("#msg-list"); return { top: l.scrollTop, max: l.scrollHeight - l.clientHeight }; });
  if (c0.max > 100) {
    await swipe(195, 250, 700);
    await m.waitForTimeout(900);
    const c1 = await m.evaluate(() => { const l = document.querySelector("#msg-list"); return { top: l.scrollTop, max: l.scrollHeight - l.clientHeight, older: !!l.querySelector(".load-older") }; });
    check("chat scrolls by touch", c1.top < c0.top, JSON.stringify({ c0, c1 }));
    await m.waitForTimeout(1500);
    const c2 = await m.evaluate(() => { const l = document.querySelector("#msg-list"); return { top: l.scrollTop, max: l.scrollHeight - l.clientHeight }; });
    check("chat position stable after older load", Math.abs(c2.top - c1.top) < 80, JSON.stringify({ c1, c2 }));
  } else {
    check("chat scrolls by touch", true, "skipped, few messages");
    check("chat position stable after older load", true, "skipped, few messages");
  }

  // edit message via in-app modal (native prompt does not work in iOS portal)
  // polls have no editable text bubble, so fall back to sending a fresh message
  const hasEditableOut = await m.evaluate(() =>
    Array.from(document.querySelectorAll("#msg-list .msg.out")).some(x => x.querySelector(".msg-text")));
  if (!hasEditableOut) {
    await m.fill("#msg-input", "mobile edit target " + Date.now());
    await m.click("#send-btn");
    await m.waitForTimeout(2000);
  }
  const editOpened = await m.evaluate(() => {
    const msgs = Array.from(document.querySelectorAll("#msg-list .msg"));
    for (let i = msgs.length - 1; i >= 0; i--) {
      const mid = Number(msgs[i].dataset.mid);
      if (mid && msgs[i].classList.contains("out") && msgs[i].querySelector(".msg-text")) { openMsgMenu(mid, null); return true; }
    }
    return false;
  });
  await m.waitForTimeout(500);
  const hasEditItem = await m.isVisible('.msg-menu .msg-menu-item[data-act="edit"]');
  if (hasEditItem) await m.click('.msg-menu .msg-menu-item[data-act="edit"]');
  await m.waitForTimeout(700);
  const editModal = await m.isVisible("#edit-text");
  check("edit modal opens on mobile", editOpened && hasEditItem && editModal);
  if (editModal) {
    await m.fill("#edit-text", "mobile-edited");
    await m.click("#edit-save");
    let edited = "";
    for (let i = 0; i < 10; i++) {
      await m.waitForTimeout(600);
      edited = await m.evaluate(() => Array.from(document.querySelectorAll("#msg-list .msg .msg-text")).map(e => e.textContent).join(" | "));
      if (edited.includes("mobile-edited")) break;
    }
    check("edit saved from mobile", edited.includes("mobile-edited"), edited.slice(0, 80));
  }

  await m.click("#chat-back");
  await m.waitForTimeout(600);
  await m.click("#chat-menu-btn");
  await m.waitForTimeout(500);
  const menuInfo = await m.evaluate(() => ({
    navVisible: getComputedStyle(document.querySelector(".nav")).display !== "none",
    menuOpen: document.querySelector("#nav-links").classList.contains("open")
  }));
  check("menu opens from chat list button", menuInfo.navVisible && menuInfo.menuOpen, JSON.stringify(menuInfo));
  await m.screenshot({ path: SHOTS + "mobile-compact-menu.png" });
  await m.click("#nav-links a[href='#/chat']");
  await m.waitForTimeout(500);
  const closed = await m.evaluate(() => ({
    menuOpen: document.querySelector("#nav-links").classList.contains("open"),
    navVisible: getComputedStyle(document.querySelector(".nav")).display !== "none"
  }));
  check("menu closes on link click and nav hides", !closed.menuOpen && !closed.navVisible, JSON.stringify(closed));

  await m.click("#chat-list .chat-item");
  await m.waitForTimeout(1000);
  await m.click("#chat-back");
  await m.waitForTimeout(600);
  await m.click("#chat-new-btn");
  await m.waitForTimeout(600);
  check("new chat modal opens from list header", await m.isVisible("#create-chat-modal"));
  await m.evaluate(() => { document.querySelectorAll(".overlay").forEach(o => o.classList.add("hidden")); });
  await m.click("#chat-dm-btn");
  await m.waitForTimeout(700);
  check("DM modal opens from list header", await m.isVisible("#dm-modal"));
  await m.evaluate(() => { document.querySelectorAll(".overlay").forEach(o => o.classList.add("hidden")); });

  await m.evaluate(() => { window.location.hash = "#/account"; });
  await m.waitForTimeout(1500);
  const otherPage = await m.evaluate(() => ({
    bodyPos: getComputedStyle(document.body).position,
    chatMode: document.body.classList.contains("chat-mode")
  }));
  check("other pages scroll normally (body static)", otherPage.bodyPos === "static" && !otherPage.chatMode, JSON.stringify(otherPage));

  // regression: a support ticket view must not lock scrolling on other pages
  await m.evaluate(() => { window.location.hash = "#/support"; });
  await m.waitForTimeout(2200);
  const ticketOpened = await m.evaluate(() => {
    const item = document.querySelector(".ticket-item");
    if (item) { item.click(); return true; }
    return false;
  });
  await m.waitForTimeout(1500);
  await m.evaluate(() => { window.location.hash = "#/blog"; });
  await m.waitForTimeout(1800);
  const lockState = await m.evaluate(() => ({
    bodyOverflow: getComputedStyle(document.body).overflowY,
    hasSupClass: document.body.classList.contains("sup-thread"),
    docH: document.scrollingElement.scrollHeight,
    winH: document.scrollingElement.clientHeight
  }));
  check("scroll is unlocked after leaving support", ticketOpened && lockState.bodyOverflow !== "hidden" && !lockState.hasSupClass, JSON.stringify(lockState));
  if (lockState.docH > lockState.winH + 2) {
    const b0 = await m.evaluate(() => document.scrollingElement.scrollTop);
    await swipe(195, 700, 320);
    await m.waitForTimeout(600);
    const b1 = await m.evaluate(() => document.scrollingElement.scrollTop);
    check("other pages scroll after visiting support", b1 > b0, b0 + " -> " + b1);
  } else {
    check("other pages scroll after visiting support", true, "skipped, page fits");
  }

  // #/admin opens the standalone admin page (the SPA admin was removed)
  await m.evaluate(() => { window.location.hash = "#/admin"; });
  await m.waitForTimeout(2000);
  const adminRedirect = await m.evaluate(() => ({ path: location.pathname, loginVisible: !!document.getElementById("l") }));
  check("admin opens the standalone page", adminRedirect.path === "/admin" && adminRedirect.loginVisible, JSON.stringify(adminRedirect));

  await m.close();
  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
