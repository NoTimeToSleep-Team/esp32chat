// Chat creation: a chat must get at least one member, picked through the people picker.
// Run: node tests/ui/chat_create_check.js
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

(async () => {
  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));

  // --- a fresh member account to pick in the modal ---
  let memberLogin = "uichat" + Math.random().toString(36).slice(2, 8);
  let memberId = null;
  const reg = await api("POST", "/auth/register", {
    login: memberLogin,
    password: "uichat-pass-123",
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uichat-" + Date.now(),
    client_kind: "web",
  });
  memberId = reg.json && reg.json.user ? (reg.json.user.id || reg.json.user.user_id) : null;
  check("member account created", !!memberId, JSON.stringify(reg.json).slice(0, 200));

  await login(page, "admin", "7428");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);

  if (!memberId) {
    const list = await api("GET", "/admin/users?session_token=" + encodeURIComponent(adminToken) + "&limit=200");
    const users = (list.json && list.json.items) || [];
    const candidate = users.find(u => u.role !== "admin" && u.status === "active" && u.login !== "admin");
    memberId = candidate ? (candidate.user_id || candidate.id) : null;
    if (candidate) memberLogin = candidate.login;
  }
  check("a second user is available for the picker", !!memberId, "memberId=" + memberId);

  // --- UI: chat page and modal ---
  await page.evaluate(() => { window.location.hash = "#/chat"; });
  await page.waitForTimeout(3000);

  await page.click("#create-chat-btn");
  await page.waitForTimeout(400);
  const modal = await page.evaluate(() => ({
    heading: document.querySelector("#create-chat-modal h3")?.textContent,
    submitDisabled: document.querySelector("#chat-create-submit")?.disabled,
    hasPicker: !!document.querySelector("#chat-member-search"),
    hint: document.querySelector("#chat-members-hint")?.textContent || "",
  }));
  check("create modal is localized and has a member picker", modal.heading === "Новый чат" && modal.hasPicker, JSON.stringify(modal));
  check("create button is disabled until a member is picked", modal.submitDisabled === true, JSON.stringify(modal));
  check("hint asks for at least one member", /хотя бы одного/i.test(modal.hint), modal.hint);

  // title alone is not enough
  await page.fill("#chat-title", "UI Создание " + Math.random().toString(36).slice(2, 6));
  await page.waitForTimeout(200);
  const stillDisabled = await page.evaluate(() => document.querySelector("#chat-create-submit")?.disabled);
  check("title without members still keeps the button disabled", stillDisabled === true);

  // pick a member through the search
  await page.fill("#chat-member-search", memberLogin.slice(0, 12));
  await page.waitForTimeout(1200);
  const picker = await page.evaluate(() => ({
    items: document.querySelectorAll("#chat-member-list .picker-item").length,
    hidden: document.querySelector("#chat-member-list").classList.contains("hidden"),
  }));
  check("people search returns results in the picker", picker.items >= 1 && !picker.hidden, JSON.stringify(picker));

  await page.click("#chat-member-list .picker-item");
  await page.waitForTimeout(400);
  const afterPick = await page.evaluate(() => ({
    chips: document.querySelectorAll("#chat-members-chips .member-chip").length,
    chipText: document.querySelector("#chat-members-chips .member-chip")?.textContent || "",
    submitDisabled: document.querySelector("#chat-create-submit")?.disabled,
  }));
  check("picked member is shown as a chip", afterPick.chips === 1 && afterPick.chipText.includes(memberLogin), JSON.stringify(afterPick));
  check("create button becomes enabled", afterPick.submitDisabled === false);
  await page.screenshot({ path: SHOTS + "chat-create-modal.png" });

  const title = await page.inputValue("#chat-title");
  await page.click("#chat-create-submit");
  await page.waitForTimeout(2500);

  const created = await page.evaluate(() => ({
    inList: Array.from(document.querySelectorAll("#chat-list .chat-item-title")).map(e => e.textContent),
    modalHidden: document.querySelector("#create-chat-modal").classList.contains("hidden"),
    inputValue: document.querySelector("#chat-title").value,
  }));
  check("created chat appears in the chat list", created.inList.includes(title), JSON.stringify(created));
  check("modal is closed and reset after creation", created.modalHidden && created.inputValue === "", JSON.stringify(created));

  // --- API: the chat really has the owner and the member ---
  const chats = await api("GET", "/chat/api/chats?session_token=" + encodeURIComponent(adminToken));
  const chat = ((chats.json && chats.json.items) || []).find(c => c.title === title);
  check("chat exists on the server", !!chat, JSON.stringify(chats.json).slice(0, 200));
  if (chat) {
    const members = await api("GET", `/chat/api/private/${chat.chat_id}/members?session_token=` + encodeURIComponent(adminToken));
    const items = (members.json && members.json.items) || [];
    const ids = items.map(m => m.user_id);
    const roles = items.map(m => m.role).sort();
    check("chat has exactly two members (owner + member)", items.length === 2 && ids.includes(memberId), JSON.stringify(items));
    check("roles are owner and member", roles.join(",") === "member,owner", roles.join(","));
  }

  // --- API: creating without members is refused ---
  const noMembers = await api("POST", "/chat/api/chats", { session_token: adminToken, title: "Без участников " + Date.now() });
  check("server refuses a chat without members (422 members_required)",
    noMembers.status === 422 && noMembers.json && noMembers.json.detail && noMembers.json.detail.code === "members_required",
    noMembers.status + " " + JSON.stringify(noMembers.json).slice(0, 160));

  // --- API: guests cannot be added ---
  check("no page errors", errs.length === 0, errs.join(" | "));

  const code = summary();
  await browser.close();
  process.exit(code);
})();
