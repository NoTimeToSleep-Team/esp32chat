// Groups and channels: types, roles, invites, join requests, slow mode, pin, join links.
// Run: node tests/ui/chat_groups_check.js
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
  const password = "uigrp-pass-123";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uigrp-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6),
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
  const u1 = await register("uig1");
  const u2 = await register("uig2");
  const u3 = await register("uig3");
  check("three test users registered", !!u1.id && !!u2.id && !!u3.id, JSON.stringify([u1.id, u2.id, u3.id]));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await login(page, "admin", "7428");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);

  // --- create a public channel through the UI ---
  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(500);
  await page.evaluate(() => { window.location.hash = "#/chat"; });
  await page.waitForTimeout(2500);
  await page.click("#create-chat-btn");
  await page.waitForTimeout(400);
  const modal = await page.evaluate(() => ({
    seg: Array.from(document.querySelectorAll("#chat-type-seg .seg-btn")).map(b => b.textContent),
    active: document.querySelector("#chat-type-seg .seg-btn.active")?.dataset.type,
    hint: document.querySelector("#chat-type-hint")?.textContent,
    optionalHidden: document.querySelector("#chat-members-optional")?.classList.contains("hidden"),
  }));
  check("create modal offers group and channel", modal.seg.join(",") === "Группа,Канал" && modal.active === "group", JSON.stringify(modal));
  check("group mode requires members", modal.optionalHidden === true, JSON.stringify(modal));

  await page.click('#chat-type-seg .seg-btn[data-type="channel"]');
  await page.waitForTimeout(300);
  const channelMode = await page.evaluate(() => ({
    hint: document.querySelector("#chat-type-hint")?.textContent || "",
    publicWrap: !document.querySelector("#chat-public-wrap")?.classList.contains("hidden"),
    optionalHidden: document.querySelector("#chat-members-optional")?.classList.contains("hidden"),
  }));
  check("channel mode explains posting rules", /администраторы/i.test(channelMode.hint), JSON.stringify(channelMode));
  check("channel mode shows public link options and members are optional",
    channelMode.publicWrap === true && channelMode.optionalHidden === false, JSON.stringify(channelMode));

  const chanTitle = "Канал " + Math.random().toString(36).slice(2, 6);
  const chanUser = "uichan" + Math.random().toString(36).slice(2, 7);
  await page.fill("#chat-title", chanTitle);
  await page.fill("#chat-member-search", u1.login.slice(0, 12));
  await page.waitForTimeout(1200);
  await page.click("#chat-member-list .picker-item");
  await page.waitForTimeout(300);
  await page.check("#chat-public");
  await page.waitForTimeout(200);
  await page.fill("#chat-username", chanUser);
  await page.click("#chat-create-submit");
  await page.waitForTimeout(2500);

  const afterCreate = await page.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    return { found: !!item, typeIco: !!item && !!item.querySelector(".chat-type-ico"), type: item ? item.dataset.chatType : null };
  }, chanTitle);
  check("channel appears in the chat list with a type icon", afterCreate.found && afterCreate.typeIco && afterCreate.type === "channel", JSON.stringify(afterCreate));

  await page.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, chanTitle);
  await page.waitForTimeout(2000);
  const chanHeader = await page.evaluate(() => ({
    badge: document.querySelector(".chead .badge-type")?.textContent,
    subtitle: document.querySelector(".chead .t2")?.textContent,
    composer: !!document.querySelector("#msg-input"),
  }));
  check("channel header shows the type badge", chanHeader.badge === "Канал", JSON.stringify(chanHeader));
  check("channel header shows subscriber count", /2 подписчиков/.test(chanHeader.subtitle || ""), JSON.stringify(chanHeader));
  check("owner still has the composer in the channel", chanHeader.composer === true, JSON.stringify(chanHeader));
  await page.screenshot({ path: SHOTS + "chat-channel-desktop.png" });

  const chats = await api("GET", "/chat/api/chats?session_token=" + encodeURIComponent(adminToken));
  const chan = ((chats.json && chats.json.items) || []).find(c => c.title === chanTitle);
  check("channel is public with a username", !!(chan && chan.is_public && chan.username === chanUser), JSON.stringify(chan).slice(0, 200));
  const chanId = chan ? chan.chat_id : null;

  // --- subscriber sees a read-only channel ---
  const ctx1 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page1 = await ctx1.newPage();
  page1.on("dialog", d => d.accept());
  await login(page1, u1.login, u1.password);
  await page1.waitForTimeout(2500);
  await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, chanTitle);
  await page1.waitForTimeout(2000);
  const subView = await page1.evaluate(() => ({
    composer: !!document.querySelector("#msg-input"),
    readonly: document.querySelector(".comp-readonly")?.textContent || "",
  }));
  check("subscriber sees a read-only channel", subView.composer === false && /администраторы/i.test(subView.readonly), JSON.stringify(subView));
  await page1.screenshot({ path: SHOTS + "chat-channel-subscriber.png" });

  // --- profile: channel type, settings, invites ---
  await page.click("#chat-more");
  await page.waitForTimeout(1500);
  const profile = await page.evaluate(() => ({
    badge: document.querySelector("#chat-profile-modal .cp-head .badge-type")?.textContent,
    settings: !!document.querySelector("#cp-slow"),
    slowOptions: Array.from(document.querySelectorAll("#cp-slow option")).length,
    invites: !!document.querySelector("#cp-invite-toggle"),
    requests: !!document.querySelector("#cp-requests"),
    subscribers: document.querySelector("#chat-profile-modal .cp-count")?.textContent || "",
    link: document.querySelector("#cp-public-link")?.textContent || "",
  }));
  check("profile shows the channel badge and subscriber count",
    profile.badge === "Канал" && /2 подписчиков/.test(profile.subscribers), JSON.stringify(profile));
  check("profile has chat settings (slow mode)", profile.settings && profile.slowOptions >= 5, JSON.stringify(profile));
  check("profile has invites and join requests sections", profile.invites && profile.requests, JSON.stringify(profile));
  check("public link is shown", profile.link.includes(chanUser), JSON.stringify(profile));
  await page.screenshot({ path: SHOTS + "chat-channel-profile.png" });

  // create an invite through the UI
  await page.click("#cp-invite-toggle");
  await page.waitForTimeout(300);
  await page.fill("#cp-invite-max", "3");
  await page.click("#cp-invite-submit");
  await page.waitForTimeout(1500);
  const inviteRow = await page.evaluate(() => ({
    text: document.querySelector("#cp-invites .cp-invite-code")?.textContent || "",
    meta: document.querySelector("#cp-invites .cp-invite-meta")?.textContent || "",
  }));
  check("invite link is created and listed", /#\/join\//.test(inviteRow.text) && /3 входов/.test(inviteRow.meta), JSON.stringify(inviteRow));
  const inviteCode = inviteRow.text.split("/").pop();

  // u2 joins by the invite link
  const u2Token = await tokenFor(u2.login, u2.password);
  const joined = await api("POST", "/chat/api/join", { session_token: u2Token, code: inviteCode });
  check("user joins the channel by invite", joined.status === 200 && joined.json.join_status === "joined", JSON.stringify(joined).slice(0, 200));

  // --- roles: promote and demote ---
  const promote = await api("POST", `/chat/api/chats/${chanId}/members/${u1.id}/role`, { session_token: adminToken, role: "admin" });
  check("member can be promoted to admin", promote.status === 200, JSON.stringify(promote.json).slice(0, 160));
  await page.click("#cp-close");
  await page.waitForTimeout(300);
  await page.click("#chat-more");
  await page.waitForTimeout(1200);
  const adminBadge = await page.evaluate(() => document.querySelector("#chat-profile-modal .badge-admin")?.textContent);
  check("admin badge is shown in the member list", adminBadge === "Админ", adminBadge);

  // permissions: remove change_info from the admin
  const perms = await api("POST", `/chat/api/chats/${chanId}/members/${u1.id}/permissions`,
    { session_token: adminToken, permissions: { change_info: false } });
  check("admin permissions can be restricted", perms.status === 200, JSON.stringify(perms.json).slice(0, 160));
  const u1Token = await tokenFor(u1.login, u1.password);
  const denied = await api("PATCH", `/chat/api/chats/${chanId}`, { session_token: u1Token, title: "нельзя" });
  check("restricted admin cannot rename the channel", denied.status === 403, denied.status + " " + JSON.stringify(denied.json).slice(0, 140));
  const demote = await api("POST", `/chat/api/chats/${chanId}/members/${u1.id}/role`, { session_token: adminToken, role: "subscriber" });
  check("admin can be demoted back to subscriber", demote.status === 200 && demote.json.member.role === "subscriber", JSON.stringify(demote.json).slice(0, 160));

  // --- join by request ---
  const approvalInvite = await api("POST", `/chat/api/chats/${chanId}/invites`, { session_token: adminToken, requires_approval: true });
  const approvalCode = approvalInvite.json.invite.code;
  const u3Token = await tokenFor(u3.login, u3.password);
  const pending = await api("POST", "/chat/api/join", { session_token: u3Token, code: approvalCode });
  check("join with approval becomes pending", pending.status === 200 && pending.json.join_status === "pending", JSON.stringify(pending).slice(0, 200));

  await page.click("#cp-close");
  await page.waitForTimeout(300);
  await page.click("#chat-more");
  await page.waitForTimeout(1500);
  const requestsUi = await page.evaluate(() => ({
    count: document.querySelector("#cp-requests-count")?.textContent,
    rows: document.querySelectorAll("#cp-requests .cp-member").length,
    buttons: Array.from(document.querySelectorAll("#cp-requests .btn")).map(b => b.textContent),
  }));
  check("join request is listed in the profile", requestsUi.count === "1" && requestsUi.rows === 1, JSON.stringify(requestsUi));
  check("approve and decline buttons are available", requestsUi.buttons.includes("Принять") && requestsUi.buttons.includes("Отклонить"), JSON.stringify(requestsUi));
  await page.screenshot({ path: SHOTS + "chat-channel-requests.png" });

  const approve = await api("POST", `/chat/api/chats/${chanId}/requests/${u3.id}`, { session_token: adminToken, approve: true });
  check("join request can be approved", approve.status === 200 && approve.json.request_status === "approved", JSON.stringify(approve.json).slice(0, 160));

  // --- public join by link (route #/join/<username>) ---
  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page2 = await ctx2.newPage();
  page2.on("dialog", d => d.accept());
  const u2PageErrs = [];
  page2.on("pageerror", e => u2PageErrs.push(e.message));
  await login(page2, u2.login, u2.password);
  await page2.waitForTimeout(2000);
  await page2.evaluate((name) => { window.location.hash = "#/join/" + name; }, chanUser);
  await page2.waitForTimeout(3500);
  const joinedUi = await page2.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    return { inList: !!item, opened: (document.querySelector(".chead .t1") || {}).textContent || "" };
  }, chanTitle);
  check("join by public link opens the chat", joinedUi.inList && joinedUi.opened.includes(chanTitle), JSON.stringify(joinedUi));
  check("no page errors on the joining page", u2PageErrs.length === 0, u2PageErrs.join(" | "));
  await ctx1.close();
  await ctx2.close();

  // --- group with slow mode, history and pin ---
  const grpTitle = "Группа " + Math.random().toString(36).slice(2, 6);
  const createdGroup = await api("POST", "/chat/api/chats", {
    session_token: adminToken, title: grpTitle, member_ids: [u2.id], chat_type: "group", history_visible: false,
  });
  const grpId = createdGroup.json.chat.chat_id;
  check("group with history off is created", createdGroup.status === 200 && createdGroup.json.chat.history_visible === false, JSON.stringify(createdGroup.json).slice(0, 200));
  const slow = await api("PATCH", `/chat/api/chats/${grpId}`, { session_token: adminToken, slow_mode_seconds: 60 });
  check("slow mode can be set on a group", slow.status === 200 && slow.json.chat.slow_mode_seconds === 60, JSON.stringify(slow.json).slice(0, 160));

  const msg = await api("POST", `/chat/api/chats/${grpId}/messages`, { session_token: adminToken, body_text: "важное объявление" });
  const pinned = await api("POST", `/chat/api/chats/${grpId}/pin`, { session_token: adminToken, message_id: msg.json.message.message_id });
  check("message can be pinned", pinned.status === 200 && pinned.json.chat.pinned_message_id === msg.json.message.message_id, JSON.stringify(pinned.json).slice(0, 160));

  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(500);
  await page.evaluate(() => { window.location.hash = "#/chat"; });
  await page.waitForTimeout(2500);
  await page.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, grpTitle);
  await page.waitForTimeout(2000);
  const pinBar = await page.evaluate(() => ({
    visible: !!document.querySelector("#pin-bar"),
    text: document.querySelector("#pin-bar .pin-text")?.textContent || "",
    unpin: !!document.querySelector("#pin-unpin"),
  }));
  check("pinned banner is shown in the chat", pinBar.visible && pinBar.text === "важное объявление" && pinBar.unpin, JSON.stringify(pinBar));
  await page.screenshot({ path: SHOTS + "chat-pinned.png" });

  // --- mobile: channel profile fits ---
  const { browser: mBrowser, page: mPage } = await launchMobile();
  mPage.on("dialog", d => d.accept());
  await login(mPage, "admin", "7428");
  await mPage.waitForTimeout(2500);
  await mPage.click("#chat-list .chat-item");
  await mPage.waitForTimeout(1500);
  await mPage.click("#chat-more");
  await mPage.waitForTimeout(1500);
  const mobile = await mPage.evaluate(() => {
    const modal = document.querySelector("#chat-profile-modal .chat-profile");
    return {
      visible: !!modal,
      overflowX: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth,
      width: modal ? Math.round(modal.getBoundingClientRect().width) : 0,
      viewport: window.innerWidth,
      settings: !!document.querySelector("#cp-slow"),
    };
  });
  check("channel profile fits mobile without horizontal overflow",
    mobile.visible && mobile.overflowX <= 1 && mobile.width <= mobile.viewport, JSON.stringify(mobile));
  await mPage.screenshot({ path: SHOTS + "chat-channel-mobile.png" });
  await mBrowser.close();

  check("no page errors", errs.length === 0, errs.join(" | "));

  const code = summary();
  await browser.close();
  process.exit(code);
})();
