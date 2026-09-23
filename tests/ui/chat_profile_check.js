// Chat profile: title/description edit, photo, members, ownership, leave, delete.
// Run: node tests/ui/chat_profile_check.js
const fs = require("fs");
const os = require("os");
const path = require("path");
const { BASE, SHOTS, check, summary, launch, launchMobile, login } = require("./lib");

const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

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
  const password = "uiprof-pass-123";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uiprof-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6),
    client_kind: "web",
  });
  const user = res.json && res.json.user ? res.json.user : null;
  return { login, password, id: user ? (user.id || user.user_id) : null };
}

async function loginToken(login, password) {
  const res = await api("POST", "/auth/login", { login, password, client_kind: "web" });
  return res.json && res.json.session ? res.json.session.token : null;
}

(async () => {
  const pngPath = path.join(os.tmpdir(), "lc_chat_profile.png");
  fs.writeFileSync(pngPath, Buffer.from(PNG_B64, "base64"));

  const member1 = await register("uicp1");
  const member2 = await register("uicp2");
  check("two test members registered", !!member1.id && !!member2.id, JSON.stringify([member1, member2]));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await login(page, "admin", "7428");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);
  const adminId = await page.evaluate(() => STATE.user.id);

  const title = "Профиль " + Math.random().toString(36).slice(2, 6);
  const created = await api("POST", "/chat/api/chats", {
    session_token: adminToken, title, description: "старое описание", member_ids: [member1.id],
  });
  const chatId = created.json && created.json.chat ? created.json.chat.chat_id : null;
  check("chat created for the profile test", !!chatId, JSON.stringify(created.json).slice(0, 200));

  // open the chat and its profile
  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(600);
  await page.evaluate(() => { window.location.hash = "#/chat"; });
  await page.waitForTimeout(3000);
  const itemClicked = await page.evaluate((t) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent === t);
    if (!item) return false;
    item.click();
    return true;
  }, title);
  check("chat opened from the list", itemClicked);
  await page.waitForTimeout(1500);

  await page.click("#chat-more");
  await page.waitForTimeout(1200);
  const profile = await page.evaluate(() => ({
    visible: !!document.querySelector("#chat-profile-modal"),
    heading: document.querySelector("#chat-profile-modal .cp-head h3")?.textContent,
    members: document.querySelectorAll("#chat-profile-modal .cp-member").length,
    ownerBadge: document.querySelector("#chat-profile-modal .badge-owner")?.textContent,
    titleValue: document.querySelector("#cp-title")?.value,
    hasAvatar: !!document.querySelector("#cp-avatar img"),
  }));
  check("chat profile modal opens", profile.visible && profile.heading === "Профиль чата", JSON.stringify(profile));
  check("members list shows both participants", profile.members === 2, JSON.stringify(profile));
  check("owner is clearly marked", profile.ownerBadge === "Владелец", JSON.stringify(profile));
  check("title is prefilled", profile.titleValue === title, JSON.stringify(profile));
  await page.screenshot({ path: SHOTS + "chat-profile-desktop.png" });

  // title + description
  const newTitle = title + " v2";
  await page.fill("#cp-title", newTitle);
  await page.waitForTimeout(200);
  await page.click("#cp-title-save");
  await page.waitForTimeout(1200);
  const headerTitle = await page.evaluate(() => document.querySelector(".chead .t1")?.textContent);
  check("title is updated in the chat header", headerTitle === newTitle, headerTitle);

  await page.fill("#cp-desc", "новое описание");
  await page.waitForTimeout(200);
  await page.click("#cp-desc-save");
  await page.waitForTimeout(1200);
  const headerDesc = await page.evaluate(() => document.querySelector(".chead .t2")?.textContent);
  check("description is updated in the chat header", headerDesc === "новое описание", headerDesc);

  // photo
  await page.setInputFiles("#cp-avatar-file", pngPath);
  await page.waitForTimeout(3000);
  const afterPhoto = await page.evaluate(() => ({
    img: !!document.querySelector("#cp-avatar img"),
    removeBtn: !!document.querySelector("#cp-avatar-remove"),
  }));
  check("chat photo is uploaded and shown", afterPhoto.img && afterPhoto.removeBtn, JSON.stringify(afterPhoto));

  const chatsAfterPhoto = await api("GET", "/chat/api/chats?session_token=" + encodeURIComponent(adminToken));
  const chatRow = ((chatsAfterPhoto.json && chatsAfterPhoto.json.items) || []).find(c => c.chat_id === chatId);
  check("server reports has_avatar=true", !!(chatRow && chatRow.has_avatar), JSON.stringify(chatRow));

  // add a member
  await page.click("#cp-add-open");
  await page.waitForTimeout(300);
  await page.fill("#cp-add-search", member2.login.slice(0, 12));
  await page.waitForTimeout(1200);
  const pickerItems = await page.evaluate(() => document.querySelectorAll("#cp-add-list .picker-item").length);
  check("add-member picker finds the user", pickerItems >= 1, "items=" + pickerItems);
  await page.click("#cp-add-list .picker-item");
  await page.waitForTimeout(300);
  await page.click("#cp-add-submit");
  await page.waitForTimeout(2000);
  const afterAdd = await page.evaluate(() => ({
    members: document.querySelectorAll("#chat-profile-modal .cp-member").length,
    count: document.querySelector("#cp-members-count")?.textContent,
  }));
  check("member is added to the chat", afterAdd.members === 3 && afterAdd.count === "3", JSON.stringify(afterAdd));

  // remove that member again
  const removed = await page.evaluate((login2) => {
    const rows = Array.from(document.querySelectorAll("#chat-profile-modal .cp-member"));
    const row = rows.find(r => (r.querySelector(".cp-member-name") || {}).textContent.includes(login2));
    if (!row) return false;
    const btn = row.querySelector(".cp-member-actions .icon-btn");
    if (!btn) return false;
    btn.click();
    return true;
  }, member2.login);
  check("remove button is available for the member", removed);
  await page.waitForTimeout(2500);
  const afterRemove = await page.evaluate(() => ({
    members: document.querySelectorAll("#chat-profile-modal .cp-member").length,
    count: document.querySelector("#cp-members-count")?.textContent,
  }));
  check("member is removed from the chat", afterRemove.members === 2 && afterRemove.count === "2", JSON.stringify(afterRemove));

  // remove photo
  await page.click("#cp-avatar-remove");
  await page.waitForTimeout(2000);
  const afterRemovePhoto = await page.evaluate(() => ({
    img: !!document.querySelector("#cp-avatar img"),
  }));
  check("chat photo is removed", afterRemovePhoto.img === false, JSON.stringify(afterRemovePhoto));

  // leave: member1 leaves the chat (via API with own token)
  const member1Token = await loginToken(member1.login, member1.password);
  const leave = await api("POST", `/chat/api/chats/${chatId}/leave`, { session_token: member1Token });
  check("member can leave the chat", leave.status === 200, leave.status + " " + JSON.stringify(leave.json).slice(0, 140));
  const afterLeave = await api("GET", `/chat/api/chats/${chatId}/members?session_token=` + encodeURIComponent(adminToken));
  const leftIds = ((afterLeave.json && afterLeave.json.items) || []).map(m => m.user_id);
  check("left member is gone from the member list", !leftIds.includes(member1.id), JSON.stringify(leftIds));

  // owner cannot leave
  const ownerLeave = await api("POST", `/chat/api/chats/${chatId}/leave`, { session_token: adminToken });
  check("owner cannot leave without transferring ownership", ownerLeave.status === 409, ownerLeave.status + " " + JSON.stringify(ownerLeave.json).slice(0, 140));

  // transfer ownership to member1 and back
  const back = await api("POST", `/chat/api/chats/${chatId}/members`, { session_token: adminToken, user_id: member1.id });
  check("member1 re-added for the ownership test", back.status === 200, JSON.stringify(back.json).slice(0, 120));
  const transfer = await api("POST", `/chat/api/chats/${chatId}/owner`, { session_token: adminToken, target_user_id: member1.id });
  check("ownership is transferred", transfer.status === 200 && transfer.json.chat.owner_user_id === member1.id,
    transfer.status + " " + JSON.stringify(transfer.json).slice(0, 160));
  const transferBack = await api("POST", `/chat/api/chats/${chatId}/owner`, { session_token: adminToken, target_user_id: adminId });
  check("ownership is transferred back to admin", transferBack.status === 200 && transferBack.json.chat.owner_user_id === adminId,
    transferBack.status + " " + JSON.stringify(transferBack.json).slice(0, 160));

  // delete the chat
  const del = await api("DELETE", `/chat/api/chats/${chatId}`, { session_token: adminToken });
  check("owner can delete the chat", del.status === 200, del.status + " " + JSON.stringify(del.json).slice(0, 140));
  const gone = await api("GET", `/chat/api/chats/${chatId}?session_token=` + encodeURIComponent(adminToken));
  check("deleted chat is not available anymore", gone.status === 404, gone.status + " " + JSON.stringify(gone.json).slice(0, 140));

  check("no page errors", errs.length === 0, errs.join(" | "));

  // mobile: the profile modal must fit the screen
  const { browser: mBrowser, page: mPage } = await launchMobile();
  const mErrs = [];
  mPage.on("pageerror", e => mErrs.push(e.message));
  mPage.on("dialog", d => d.accept());
  await login(mPage, "admin", "7428");
  await mPage.waitForTimeout(3000);
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
      members: document.querySelectorAll("#chat-profile-modal .cp-member").length,
    };
  });
  check("profile modal opens on mobile without horizontal overflow",
    mobile.visible && mobile.overflowX <= 1 && mobile.width <= mobile.viewport, JSON.stringify(mobile));
  check("member rows are rendered on mobile", mobile.members >= 1, JSON.stringify(mobile));
  await mPage.screenshot({ path: SHOTS + "chat-profile-mobile.png" });
  check("no mobile page errors", mErrs.length === 0, mErrs.join(" | "));
  await mBrowser.close();

  const code = summary();
  await browser.close();
  process.exit(code);
})();
