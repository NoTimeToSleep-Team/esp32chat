// Chat gestures: long press menu, swipe-to-reply, double tap reaction, chat list swipes.
// Run: node tests/ui/chat_gestures_check.js
const { BASE, SHOTS, check, summary, launch, launchMobile, login } = require("./lib");

async function api(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  let json = null;
  try { json = await res.json(); } catch (e) {}
  return { status: res.status, json };
}

async function register(prefix) {
  const login = prefix + Math.random().toString(36).slice(2, 8);
  const password = "uigest-pass-123";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uigest-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6),
    client_kind: "web",
  });
  const user = res.json && res.json.user ? res.json.user : null;
  return { login, password, id: user ? (user.id || user.user_id) : null };
}

async function tokenFor(login, password) {
  const res = await api("POST", "/auth/login", { login, password, client_kind: "web" });
  return res.json && res.json.session ? res.json.session.token : null;
}

function touch(client, type, x, y) {
  const points = type === "touchEnd" ? [] : [{ x, y }];
  return client.send("Input.dispatchTouchEvent", { type, touchPoints: points });
}

async function longPress(page, client, x, y, ms) {
  await touch(client, "touchStart", x, y);
  await page.waitForTimeout(ms || 650);
  await touch(client, "touchEnd", 0, 0);
}

async function swipe(page, client, x, y, dx) {
  await touch(client, "touchStart", x, y);
  const steps = 10;
  for (let i = 1; i <= steps; i++) {
    await touch(client, "touchMove", x + (dx * i) / steps, y);
    await page.waitForTimeout(16);
  }
  await touch(client, "touchEnd", 0, 0);
}

async function doubleTap(page, client, x, y) {
  await touch(client, "touchStart", x, y);
  await touch(client, "touchEnd", 0, 0);
  await page.waitForTimeout(120);
  await touch(client, "touchStart", x, y);
  await touch(client, "touchEnd", 0, 0);
}

async function refreshChatList(page) {
  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(700);
  await page.evaluate(() => { window.location.hash = "#/chat"; });
  await page.waitForTimeout(1800);
}

async function openChatByTitle(page, title, chatId) {
  for (let attempt = 0; attempt < 12; attempt++) {
    const clicked = await page.evaluate((t) => {
      const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
      const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(t));
      if (!item) return false;
      item.click();
      return true;
    }, title);
    if (clicked) {
      await page.waitForTimeout(1200);
      const current = await page.evaluate(() => (typeof currentChatId !== "undefined" ? currentChatId : null));
      if (String(current) === String(chatId)) return true;
    }
    await page.waitForTimeout(500);
  }
  return false;
}

(async () => {
  const u1 = await register("uig1");
  check("test users registered", !!u1.id, JSON.stringify(u1));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await login(page, "admin", "7428");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);

  const rand = Math.random().toString(36).slice(2, 6);
  const grpTitle = "G " + rand;
  const created = await api("POST", "/chat/api/chats", {
    session_token: adminToken, title: grpTitle, member_ids: [u1.id], chat_type: "group",
  });
  const chatId = created.json && created.json.chat ? created.json.chat.chat_id : null;
  check("group chat created for gesture tests", !!chatId, JSON.stringify(created.json).slice(0, 160));
  const u1Token = await tokenFor(u1.login, u1.password);
  const unique = "жест " + rand;
  await api("POST", `/chat/api/chats/${chatId}/messages`, { session_token: adminToken, body_text: unique });
  await api("POST", `/chat/api/chats/${chatId}/messages`, { session_token: u1Token, body_text: unique + " от гостя" });

  // --- desktop: hover button + context menu ---
  await refreshChatList(page);
  const openedDesktop = await openChatByTitle(page, grpTitle, chatId);
  check("group chat is opened in the desktop feed", openedDesktop);
  await page.waitForTimeout(1500);
  const feedInfo = await page.evaluate(() => Array.from(document.querySelectorAll("#msg-list .msg .msg-text")).map(e => ({ t: e.textContent, c: Array.from(e.textContent).map(ch => ch.codePointAt(0)).join(",") })));
  check("feed shows the new group messages", feedInfo.some(x => x.t.includes(unique)), JSON.stringify(feedInfo.slice(-2)));
  const adminMid = await page.evaluate((text) => {
    const m = Array.from(document.querySelectorAll("#msg-list .msg")).find(x => ((x.querySelector(".msg-text") || {}).textContent || "").includes(text));
    return m ? Number(m.dataset.mid) : 0;
  }, unique);
  check("message id is resolved for the gesture checks", adminMid > 0, "mid=" + adminMid);
  const msgSel = '#msg-list .msg[data-mid="' + adminMid + '"]';
  const idleOpacity = await page.evaluate((sel) => {
    const a = document.querySelector(sel + " .msg-actions");
    return a ? getComputedStyle(a).opacity : null;
  }, msgSel);
  check("desktop actions are hidden until hover", idleOpacity === "0", "opacity=" + idleOpacity);
  await page.hover(msgSel);
  await page.waitForTimeout(300);
  const hoverOpacity = await page.evaluate((sel) => {
    const a = document.querySelector(sel + ":hover .msg-actions");
    return a ? getComputedStyle(a).opacity : null;
  }, msgSel);
  check("desktop actions appear on hover", hoverOpacity === "1", "opacity=" + hoverOpacity);
  const motionDesktop = await page.evaluate(() => {
    const msg = document.querySelector("#msg-list .msg");
    return { userSelect: msg ? getComputedStyle(msg).userSelect : null };
  });
  check("messages are not selectable (long press fix)", motionDesktop.userSelect === "none", JSON.stringify(motionDesktop));
  const toastAnim = await page.evaluate(() => {
    toast("motion check");
    const el2 = document.querySelector(".toast");
    return el2 ? getComputedStyle(el2).animationName : "";
  });
  check("toasts are animated", /toastIn/.test(toastAnim), toastAnim);
  await page.evaluate(() => { const el2 = document.querySelector(".toast"); if (el2) el2.remove(); });
  await page.click(msgSel + " .msg-more");
  await page.waitForTimeout(400);
  const desktopMenu = await page.evaluate(() => ({
    items: document.querySelectorAll(".msg-menu .msg-menu-item").length,
    reacts: document.querySelectorAll(".msg-menu .react-opt").length,
    sheet: !!document.querySelector(".msg-menu.sheet"),
    anim: (() => { const m = document.querySelector(".msg-menu"); return m ? getComputedStyle(m).animationName : ""; })(),
  }));
  check("actions menu opens on desktop", desktopMenu.items >= 5 && desktopMenu.reacts === 6 && !desktopMenu.sheet, JSON.stringify(desktopMenu));
  check("actions menu has an entrance animation", /menuPop|sheetUp/.test(desktopMenu.anim), desktopMenu.anim);
  await page.click('.msg-menu .react-opt[data-emoji="🔥"]');
  await page.waitForTimeout(1500);
  const reacted = await page.evaluate((text) => {
    const m = Array.from(document.querySelectorAll("#msg-list .msg")).find(x => ((x.querySelector(".msg-text") || {}).textContent || "").includes(text));
    return m ? m.querySelectorAll(".msg-reactions .react").length : 0;
  }, unique);
  check("reaction from the menu is applied", reacted >= 1, "n=" + reacted);
  await page.click('#msg-list .msg[data-mid="' + adminMid + '"]', { button: "right" });
  await page.waitForTimeout(400);
  const ctxItems = await page.evaluate(() => document.querySelectorAll(".msg-menu .msg-menu-item").length);
  check("right click opens the actions menu", ctxItems >= 5, "items=" + ctxItems);
  await page.evaluate(() => { const m = document.querySelector(".msg-menu"); if (m) m.remove(); const b = document.querySelector(".menu-backdrop"); if (b) b.remove(); });
  await page.close();

  // --- mobile: sheet, swipe reply, double tap, list swipes ---
  const { browser: mB, page: mP } = await launchMobile();
  const mErrs = [];
  mP.on("pageerror", e => mErrs.push(e.message));
  mP.on("dialog", d => d.accept());
  await login(mP, "admin", "7428");
  await mP.waitForTimeout(2500);
  await refreshChatList(mP);
  const openedMobile = await openChatByTitle(mP, grpTitle, chatId);
  check("group chat is opened in the mobile feed", openedMobile);
  await mP.waitForTimeout(1500);
  const client = await mP.context().newCDPSession(mP);

  const mobileActions = await mP.evaluate(() => {
    const a = document.querySelector("#msg-list .msg-actions");
    return a ? getComputedStyle(a).display : null;
  });
  check("no always visible action buttons on mobile", mobileActions === "none", "display=" + mobileActions);

  const mid = await mP.evaluate((text) => {
    const m = Array.from(document.querySelectorAll("#msg-list .msg")).find(x => ((x.querySelector(".msg-text") || {}).textContent || "").includes(text));
    return m ? Number(m.dataset.mid) : 0;
  }, unique);
  const mMsgSel = '#msg-list .msg[data-mid="' + mid + '"]';
  const mbox = await mP.locator(mMsgSel).boundingBox();
  const mx = mbox.x + Math.min(60, mbox.width / 2);
  const my = mbox.y + mbox.height / 2;

  await longPress(mP, client, mx, my, 650);
  await mP.waitForTimeout(400);
  const sheet = await mP.evaluate(() => ({
    sheet: !!document.querySelector(".msg-menu.sheet"),
    items: document.querySelectorAll(".msg-menu .msg-menu-item").length,
    reacts: document.querySelectorAll(".msg-menu .react-opt").length,
    backdrop: !!document.querySelector(".menu-backdrop"),
  }));
  check("long press opens the action sheet", sheet.sheet && sheet.items >= 6 && sheet.reacts === 6, JSON.stringify(sheet));
  const selectionText = await mP.evaluate(() => String(window.getSelection() || ""));
  check("long press does not select the page", selectionText === "", JSON.stringify(selectionText));
  const sheetAnim = await mP.evaluate(() => {
    const m = document.querySelector(".msg-menu");
    return m ? getComputedStyle(m).animationName : "";
  });
  check("action sheet has an entrance animation", /sheetUp/.test(sheetAnim), sheetAnim);
  await mP.screenshot({ path: SHOTS + "chat-gestures-sheet.png" });
  await mP.evaluate(() => { const b = document.querySelector(".menu-backdrop"); if (b) b.click(); });
  await mP.waitForTimeout(70);
  const sheetClosing = await mP.evaluate(() => !!document.querySelector(".msg-menu.closing"));
  await mP.waitForTimeout(400);
  const sheetGone = await mP.evaluate(() => !document.querySelector(".msg-menu"));
  check("action sheet closes with animation", sheetClosing && sheetGone, JSON.stringify({ sheetClosing, sheetGone }));

  await swipe(mP, client, mx, my, 95);
  await mP.waitForTimeout(500);
  const replyBar = await mP.evaluate(() => !!document.querySelector("#reply-bar"));
  check("swipe right opens the reply bar", replyBar === true);
  await mP.evaluate(() => { const b = document.querySelector("#reply-cancel"); if (b) b.click(); });
  await mP.waitForTimeout(300);

  await doubleTap(mP, client, mx, my);
  await mP.waitForTimeout(1500);
  const quick1 = await mP.evaluate((id) => {
    const m = document.querySelector('.msg[data-mid="' + id + '"]');
    return m ? Array.from(m.querySelectorAll(".msg-reactions .react")).map(b => b.textContent).join("|") : "";
  }, mid);
  check("double tap adds the quick reaction", quick1.includes("👍"), quick1);
  await doubleTap(mP, client, mx, my);
  await mP.waitForTimeout(1500);
  const quick2 = await mP.evaluate((id) => {
    const m = document.querySelector('.msg[data-mid="' + id + '"]');
    return m ? Array.from(m.querySelectorAll(".msg-reactions .react")).map(b => b.textContent).join("|") : "";
  }, mid);
  check("second double tap removes the quick reaction", !quick2.includes("👍"), quick2);

  // chat list swipes
  await mP.click("#chat-back");
  await mP.waitForTimeout(800);
  const itemSel = '#chat-list .chat-item[data-chat-id="' + chatId + '"]';
  let ibox = await mP.locator(itemSel).boundingBox();
  check("chat list item is present before swipes", !!ibox, itemSel);
  await swipe(mP, client, ibox.x + ibox.width - 30, ibox.y + ibox.height / 2, -130);
  await mP.waitForTimeout(1800);
  const archivedGone = await mP.evaluate((id) => !document.querySelector('#chat-list .chat-item[data-chat-id="' + id + '"]'), chatId);
  const archivedApi = await api("GET", `/chat/api/chats/${chatId}?session_token=${encodeURIComponent(adminToken)}`);
  check("swipe left archives the chat",
    archivedGone && !!(archivedApi.json.view && archivedApi.json.view.is_archived),
    JSON.stringify({ archivedGone, view: archivedApi.json.view && archivedApi.json.view.is_archived }));
  await api("POST", `/chat/api/chats/${chatId}/state`, { session_token: adminToken, is_archived: false });
  await mP.evaluate(() => { if (typeof renderChat === "function") renderChat(); });
  await mP.waitForTimeout(1500);
  ibox = await mP.locator(itemSel).boundingBox();
  await swipe(mP, client, ibox.x + 30, ibox.y + ibox.height / 2, 130);
  await mP.waitForTimeout(1800);
  const mutedApi = await api("GET", `/chat/api/chats/${chatId}?session_token=${encodeURIComponent(adminToken)}`);
  const mutedFlag = await mP.evaluate((id) => {
    const it = document.querySelector('#chat-list .chat-item[data-chat-id="' + id + '"]');
    return it ? !!it.querySelector(".chat-flag") : false;
  }, chatId);
  check("swipe right mutes the chat",
    !!(mutedApi.json.view && mutedApi.json.view.is_muted) && mutedFlag,
    JSON.stringify({ muted: mutedApi.json.view && mutedApi.json.view.is_muted, mutedFlag }));
  await api("POST", `/chat/api/chats/${chatId}/state`, { session_token: adminToken, is_muted: false });

  // chat profile fits mobile width
  await openChatByTitle(mP, grpTitle, chatId);
  await mP.waitForTimeout(1200);
  await mP.click("#chat-more");
  await mP.waitForTimeout(1500);
  const profile = await mP.evaluate(() => {
    const bad = [];
    document.querySelectorAll(".chat-profile .cp-members, .chat-profile .cp-member, .chat-profile .cp-member-wrap, .chat-profile .cp-member-actions, .chat-profile .form-group").forEach(e => {
      if (e.scrollWidth > e.clientWidth + 2) bad.push((e.className || "") + " " + e.scrollWidth + ">" + e.clientWidth);
    });
    return { bad: bad.slice(0, 6), pageOverflow: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth };
  });
  check("chat profile fits mobile width", profile.bad.length === 0 && profile.pageOverflow <= 1, JSON.stringify(profile));
  const profileAnim = await mP.evaluate(() => {
    const m = document.querySelector(".chat-profile");
    return m ? getComputedStyle(m).animationName : "";
  });
  check("chat profile opens with animation", /modalIn/.test(profileAnim), profileAnim);
  await mP.screenshot({ path: SHOTS + "chat-gestures-profile.png" });
  await mP.click("#cp-close");
  await mP.waitForTimeout(70);
  const profileClosing = await mP.evaluate(() => !!document.querySelector("#chat-profile-modal.closing"));
  await mP.waitForTimeout(450);
  const profileGone = await mP.evaluate(() => !document.querySelector("#chat-profile-modal"));
  check("chat profile closes with animation", profileClosing && profileGone, JSON.stringify({ profileClosing, profileGone }));

  // --- back gesture: conversation -> chat list, no login flash ---
  await mP.evaluate(() => {
    const item = document.querySelector("#chat-list .chat-item");
    if (item) item.click();
  });
  await mP.waitForTimeout(1600);
  const conversationOpen = await mP.evaluate(() => {
    const lay = document.getElementById("chat-layout");
    return !!lay && !lay.classList.contains("show-list");
  });
  await mP.goBack();
  await mP.waitForTimeout(600);
  const afterBack = await mP.evaluate(() => ({
    listShown: document.getElementById("chat-layout").classList.contains("show-list"),
    staticLogin: getComputedStyle(document.getElementById("static-login")).display,
    loginRendered: !!document.querySelector("#content .login-page"),
  }));
  check("back gesture from a conversation shows the chat list",
    conversationOpen && afterBack.listShown === true, JSON.stringify({ conversationOpen, afterBack }));
  check("back gesture never shows the login page",
    afterBack.staticLogin === "none" && !afterBack.loginRendered, JSON.stringify(afterBack));
  await mB.close();

  check("no page errors (desktop)", errs.length === 0, errs.join(" | "));
  check("no page errors (mobile)", mErrs.length === 0, mErrs.join(" | "));

  const code = summary();
  await browser.close();
  process.exit(code);
})();
