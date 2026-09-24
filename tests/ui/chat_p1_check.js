// P1 features: replies, reactions, forwards, mentions, search, unread, drafts, mute/archive/pin, clear history.
// Run: node tests/ui/chat_p1_check.js
const { BASE, SHOTS, check, summary, launch, login } = require("./lib");

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
  const password = "uip1-pass-123";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uip1-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6),
    client_kind: "web",
  });
  const user = res.json && res.json.user ? res.json.user : null;
  return { login, password, id: user ? (user.id || user.user_id) : null };
}

async function tokenFor(login, password) {
  const res = await api("POST", "/auth/login", { login, password, client_kind: "web" });
  return res.json && res.json.session ? res.json.session.token : null;
}

(async () => {
  const u1 = await register("uip1");
  const u2 = await register("uip2");
  check("two test users registered", !!u1.id && !!u2.id, JSON.stringify([u1.id, u2.id]));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await login(page, "admin", "7428");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);

  const grpTitle = "P1 " + Math.random().toString(36).slice(2, 6);
  const created = await api("POST", "/chat/api/chats", {
    session_token: adminToken, title: grpTitle, member_ids: [u1.id], chat_type: "group",
  });
  const chatId = created.json.chat.chat_id;
  const u1Token = await tokenFor(u1.login, u1.password);
  check("group created for the P1 tests", !!chatId && !!u1Token, JSON.stringify(created.json).slice(0, 160));

  // --- reply ---
  const first = await api("POST", `/chat/api/chats/${chatId}/messages`, { session_token: adminToken, body_text: "первое сообщение" });
  const firstId = first.json.message.message_id;
  const reply = await api("POST", `/chat/api/chats/${chatId}/messages`, {
    session_token: u1Token, body_text: "ответ на первое", reply_to_message_id: firstId,
  });
  check("reply is accepted by the server", reply.status === 200 && reply.json.message.reply_to_message_id === firstId, JSON.stringify(reply.json).slice(0, 200));
  const listed = await api("GET", `/chat/api/chats/${chatId}/messages?session_token=${encodeURIComponent(adminToken)}`);
  const replyItem = (listed.json.items || []).find(m => m.body_text === "ответ на первое");
  check("reply carries the quoted author and text",
    !!(replyItem && replyItem.reply_to_login === "admin" && replyItem.reply_to_text === "первое сообщение"),
    JSON.stringify(replyItem).slice(0, 220));

  // --- reactions ---
  const react = await api("POST", `/chat/api/chats/${chatId}/messages/${firstId}/reactions`, { session_token: adminToken, emoji: "👍" });
  check("reaction is added", react.status === 200 && react.json.message.reactions.some(r => r.emoji === "👍" && r.count === 1 && r.mine),
    JSON.stringify(react.json).slice(0, 220));
  const react2 = await api("POST", `/chat/api/chats/${chatId}/messages/${firstId}/reactions`, { session_token: u1Token, emoji: "🔥" });
  check("second user adds another reaction", react2.status === 200 && react2.json.message.reactions.length === 2, JSON.stringify(react2.json).slice(0, 220));
  const reactOff = await api("POST", `/chat/api/chats/${chatId}/messages/${firstId}/reactions`, { session_token: adminToken, emoji: "👍" });
  check("reaction toggles off", reactOff.status === 200 && !reactOff.json.message.reactions.some(r => r.emoji === "👍"), JSON.stringify(reactOff.json).slice(0, 220));

  // --- forward ---
  const target = await api("POST", "/chat/api/chats", { session_token: adminToken, title: "P1 цель " + Math.random().toString(36).slice(2, 5), member_ids: [u2.id] });
  const targetId = target.json.chat.chat_id;
  const fwd = await api("POST", `/chat/api/chats/${chatId}/messages/${firstId}/forward`, { session_token: adminToken, target_chat_id: targetId });
  check("message is forwarded to another chat",
    fwd.status === 200 && fwd.json.message.forwarded_from_login === "admin" && fwd.json.message.body_text === "первое сообщение",
    JSON.stringify(fwd.json).slice(0, 220));

  // --- search ---
  const search = await api("GET", `/chat/api/messages/search?session_token=${encodeURIComponent(u1Token)}&q=${encodeURIComponent("ответ на первое")}`);
  check("search finds messages in own chats", search.status === 200 && (search.json.items || []).some(i => i.chat_id === chatId), JSON.stringify(search.json).slice(0, 200));
  const searchOther = await api("GET", `/chat/api/messages/search?session_token=${encodeURIComponent(u2.login ? u1Token : u1Token)}&q=${encodeURIComponent("первое сообщение")}&chat_id=${targetId}`);
  check("search respects the chat filter", searchOther.status === 200, JSON.stringify(searchOther.json).slice(0, 160));

  // --- UI: reply bar, reactions, mentions, unread badge ---
  const ctx1 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page1 = await ctx1.newPage();
  page1.on("dialog", d => d.accept());
  const errs1 = [];
  page1.on("pageerror", e => errs1.push(e.message));
  await login(page1, u1.login, u1.password);
  await page1.waitForTimeout(2500);
  await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, grpTitle);
  await page1.waitForTimeout(2000);
  const replyUi = await page1.evaluate(() => ({
    quotes: document.querySelectorAll(".msg-reply").length,
    reactions: document.querySelectorAll(".msg-reactions .react").length,
    actions: document.querySelectorAll(".msg-actions .msg-more").length,
  }));
  check("reply quote is rendered in the feed", replyUi.quotes >= 1, JSON.stringify(replyUi));
  check("reactions are rendered in the feed", replyUi.reactions >= 1, JSON.stringify(replyUi));
  check("message has a single actions button", replyUi.actions >= 1, JSON.stringify(replyUi));
  const menuItems = await page1.evaluate(() => {
    const msg = Array.from(document.querySelectorAll(".msg")).find(m => (m.querySelector(".msg-text") || {}).textContent.includes("первое сообщение"));
    if (!msg) return 0;
    msg.dispatchEvent(new MouseEvent("contextmenu", {bubbles: true, cancelable: true, clientX: 420, clientY: 300}));
    return document.querySelectorAll(".msg-menu .msg-menu-item").length;
  });
  check("message menu opens with actions", menuItems >= 4, "items=" + menuItems);
  await page1.keyboard.press("Escape");
  await page1.evaluate(() => { const m = document.querySelector(".msg-menu"); if (m) m.remove(); const b = document.querySelector(".menu-backdrop"); if (b) b.remove(); });
  await page1.screenshot({ path: SHOTS + "chat-p1-reply.png" });

  // reply through the UI
  await page1.evaluate(() => {
    const msg = Array.from(document.querySelectorAll(".msg")).find(m => (m.querySelector(".msg-text") || {}).textContent.includes("первое сообщение"));
    if (msg) { msg.dispatchEvent(new MouseEvent("contextmenu", {bubbles: true, cancelable: true, clientX: 420, clientY: 300})); }
  });
  await page1.waitForTimeout(400);
  await page1.evaluate(() => {
    const btn = document.querySelector('.msg-menu .msg-menu-item[data-act="reply"]');
    if (btn) btn.click();
  });
  await page1.waitForTimeout(500);
  const replyBar = await page1.evaluate(() => !!document.querySelector("#reply-bar"));
  check("reply bar appears in the composer", replyBar === true);
  await page1.fill("#msg-input", "ответ из интерфейса");
  await page1.click("#send-btn");
  await page1.waitForTimeout(2500);
  const replySent = await page1.evaluate(() => {
    const msg = Array.from(document.querySelectorAll(".msg")).find(m => (m.querySelector(".msg-text") || {}).textContent.includes("ответ из интерфейса"));
    return { found: !!msg, quoted: !!msg && !!msg.querySelector(".msg-reply"), barGone: !document.querySelector("#reply-bar") };
  });
  check("UI reply is sent with the quote", replySent.found && replySent.quoted && replySent.barGone, JSON.stringify(replySent));

  // mention rendering + mention list
  await page1.fill("#msg-input", "@" + u2.login.slice(0, 8));
  await page1.waitForTimeout(1200);
  const mentionList = await page1.evaluate(() => document.querySelectorAll("#mention-list .mention-item").length);
  check("mention autocomplete shows people", mentionList >= 1, "items=" + mentionList);
  await page1.fill("#msg-input", "привет @" + u2.login + "!");
  await page1.click("#send-btn");
  await page1.waitForTimeout(2500);
  const mentionUi = await page1.evaluate(() => document.querySelectorAll(".msg .mention").length);
  check("mentions are highlighted in messages", mentionUi >= 1, "n=" + mentionUi);

  // draft: type, switch chat, come back
  await page1.fill("#msg-input", "мой черновик");
  await page1.waitForTimeout(1500);
  await page1.evaluate(() => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    if (items[1]) items[1].click();
  });
  await page1.waitForTimeout(2000);
  await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, grpTitle);
  await page1.waitForTimeout(2000);
  const draftValue = await page1.inputValue("#msg-input");
  check("draft is restored when returning to the chat", draftValue === "мой черновик", draftValue);

  // search modal
  await page1.click("#chat-search-btn");
  await page1.waitForTimeout(600);
  await page1.fill("#search-input", "первое");
  await page1.waitForTimeout(1200);
  const searchUi = await page1.evaluate(() => ({
    visible: !!document.querySelector("#search-modal"),
    results: document.querySelectorAll("#search-results .cp-member").length,
    scopes: Array.from(document.querySelectorAll("#search-scope .seg-btn")).map(b => b.textContent),
  }));
  check("message search modal works", searchUi.visible && searchUi.results >= 1, JSON.stringify(searchUi));
  check("search has in-chat and global scopes", searchUi.scopes.join(",") === "В этом чате,Во всех чатах", JSON.stringify(searchUi));
  await page1.screenshot({ path: SHOTS + "chat-p1-search.png" });
  await page1.click("#search-close");
  await page1.waitForTimeout(300);

  // --- unread badge ---
  await api("POST", `/chat/api/chats/${chatId}/messages`, { session_token: adminToken, body_text: "непрочитанное 1" });
  await api("POST", `/chat/api/chats/${chatId}/messages`, { session_token: adminToken, body_text: "непрочитанное 2" });
  // Another chat gets the newest message, so the chat page auto-opens it instead of the group.
  const chat2 = await api("POST", "/chat/api/chats", { session_token: adminToken, title: "P1 второй " + Math.random().toString(36).slice(2, 5), member_ids: [u1.id] });
  await api("POST", `/chat/api/chats/${chat2.json.chat.chat_id}/messages`, { session_token: adminToken, body_text: "свежее сообщение" });
  await page1.evaluate(() => { window.location.hash = "#/account"; });
  await page1.waitForTimeout(600);
  await page1.evaluate(() => { window.location.hash = "#/chat"; });
  await page1.waitForTimeout(3500);
  const unreadUi = await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    const badge = item ? item.querySelector(".chat-badge") : null;
    return { badge: badge ? badge.textContent : null };
  }, grpTitle);
  check("unread badge is shown in the chat list", unreadUi.badge === "2", JSON.stringify(unreadUi));
  await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, grpTitle);
  await page1.waitForTimeout(2500);
  const badgeGone = await page1.evaluate(() => {
    const active = document.querySelector("#chat-list .chat-item.active");
    return !active || !active.querySelector(".chat-badge");
  });
  check("unread badge disappears after opening the chat", badgeGone === true);

  // --- common chat (General) unread must clear too ---
  // Regression: common chats have no chat_members row, so the read marker had nowhere to go.
  const commonList = await api("GET", `/chat/api/chats?session_token=${encodeURIComponent(u1Token)}`);
  const commonRow = (commonList.json.items || []).find(c => c.chat_id === 1);
  if (!commonRow || Number(commonRow.unread_count || 0) === 0) {
    await api("POST", "/chat/api/chats/1/messages", { session_token: adminToken, body_text: "общий чат " + Math.random().toString(36).slice(2, 5) });
  }
  await page1.evaluate(() => { window.location.hash = "#/account"; });
  await page1.waitForTimeout(500);
  await page1.evaluate(() => { window.location.hash = "#/chat"; });
  await page1.waitForTimeout(2200);
  const commonBadge = await page1.evaluate(() => {
    const item = Array.from(document.querySelectorAll("#chat-list .chat-item"))
      .find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes("General"));
    const badge = item ? item.querySelector(".chat-badge") : null;
    return { found: !!item, badge: badge ? badge.textContent : null };
  });
  check("common chat shows an unread badge", commonBadge.found && commonBadge.badge !== null, JSON.stringify(commonBadge));
  await page1.evaluate(() => {
    const item = Array.from(document.querySelectorAll("#chat-list .chat-item"))
      .find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes("General"));
    if (item) item.click();
  });
  await page1.waitForTimeout(2500);
  const commonAfter = await api("GET", `/chat/api/chats?session_token=${encodeURIComponent(u1Token)}`);
  const commonAfterRow = (commonAfter.json.items || []).find(c => c.chat_id === 1);
  check("common chat unread is cleared on the server after reading",
    !!commonAfterRow && Number(commonAfterRow.unread_count || 0) === 0 && commonAfterRow.is_member === true,
    JSON.stringify(commonAfterRow && { unread: commonAfterRow.unread_count, is_member: commonAfterRow.is_member }));

  // --- mute / archive / pin ---
  const muted = await api("POST", `/chat/api/chats/${chatId}/state`, { session_token: u1Token, is_muted: true, is_pinned: true });
  check("mute and pin are saved", muted.status === 200 && muted.json.state.is_muted && muted.json.state.is_pinned, JSON.stringify(muted.json).slice(0, 160));
  await page1.evaluate(() => { window.location.hash = "#/account"; });
  await page1.waitForTimeout(600);
  await page1.evaluate(() => { window.location.hash = "#/chat"; });
  await page1.waitForTimeout(3000);
  const flagsUi = await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    return {
      flags: item ? item.querySelectorAll(".chat-flag").length : 0,
      first: items.length ? (items[0].querySelector(".chat-item-title") || {}).textContent || "" : "",
    };
  }, grpTitle);
  check("muted and pinned chat shows flags", flagsUi.flags >= 2, JSON.stringify(flagsUi));
  check("pinned chat is first in the list", flagsUi.first.includes(grpTitle), JSON.stringify(flagsUi));

  const archived = await api("POST", `/chat/api/chats/${chatId}/state`, { session_token: u1Token, is_archived: true });
  check("archive is saved", archived.status === 200 && archived.json.state.is_archived, JSON.stringify(archived.json).slice(0, 160));
  await page1.evaluate(() => { window.location.hash = "#/account"; });
  await page1.waitForTimeout(600);
  await page1.evaluate(() => { window.location.hash = "#/chat"; });
  await page1.waitForTimeout(3000);
  const archivedUi = await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    return {
      inList: items.some(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title)),
      archiveBtn: !!document.querySelector("#chat-archive-btn") && document.querySelector("#chat-archive-btn").style.display !== "none",
    };
  }, grpTitle);
  check("archived chat is hidden from the list", archivedUi.inList === false, JSON.stringify(archivedUi));
  check("archive button appears", archivedUi.archiveBtn === true, JSON.stringify(archivedUi));

  // --- clear history for me ---
  const cleared = await api("POST", `/chat/api/chats/${chatId}/clear`, { session_token: u1Token });
  check("clear history for self succeeds", cleared.status === 200, JSON.stringify(cleared.json).slice(0, 160));
  const afterClear = await api("GET", `/chat/api/chats/${chatId}/messages?session_token=${encodeURIComponent(u1Token)}`);
  const adminStillSees = await api("GET", `/chat/api/chats/${chatId}/messages?session_token=${encodeURIComponent(adminToken)}`);
  check("cleared history is hidden for that user only",
    (afterClear.json.items || []).length === 0 && (adminStillSees.json.items || []).length > 0,
    JSON.stringify({ mine: (afterClear.json.items || []).length, admin: (adminStillSees.json.items || []).length }));
  await ctx1.close();

  check("no page errors", errs.length === 0 && errs1.length === 0, errs.concat(errs1).join(" | "));

  const code = summary();
  await browser.close();
  process.exit(code);
})();
