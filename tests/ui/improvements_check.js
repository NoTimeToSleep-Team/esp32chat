// Improvements pass: live list, WebSocket delivery, My Files, locale, dialog a11y.
// Run: node tests/ui/improvements_check.js
const { BASE, check, summary, launch, login } = require("./lib");

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
  const password = "uii-pass-12345";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uii-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6),
    client_kind: "web",
  });
  const user = res.json && res.json.user ? res.json.user : null;
  const token = res.json && res.json.session ? res.json.session.token : null;
  return { login, password, id: user ? (user.id || user.user_id) : null, token };
}

(async () => {
  const u2 = await register("uii-live");
  check("second user registered", !!u2.id && !!u2.token, JSON.stringify(u2).slice(0, 160));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await login(page, "admin");
  const adminToken = await page.evaluate(() => STATE.token);

  const title = "Live " + Math.random().toString(36).slice(2, 6);
  const created = await api("POST", "/chat/api/chats", {
    session_token: adminToken, title, member_ids: [u2.id], chat_type: "group",
  });
  const chatId = created.json.chat.chat_id;
  check("group created", !!chatId, JSON.stringify(created.json).slice(0, 160));

  await api("POST", `/chat/api/chats/${chatId}/messages`, {
    session_token: u2.token, body_text: "live-list-message",
  });
  await page.waitForTimeout(12000);
  const badge = await page.locator(`#chat-list .chat-item[data-chat-id="${chatId}"] .chat-badge`).count();
  check("live update refreshes the chat list and unread badge", badge > 0, `badge=${badge}`);

  await page.locator(`#chat-list .chat-item[data-chat-id="${chatId}"]`).click();
  await page.waitForTimeout(1200);
  const wsMessage = await page.locator("#msg-list .msg", { hasText: "live-list-message" }).count();
  check("opening a chat loads history", wsMessage > 0, `messages=${wsMessage}`);

  await api("POST", `/chat/api/chats/${chatId}/messages`, {
    session_token: u2.token, body_text: "ws-instant-message",
  });
  await page.waitForTimeout(1800);
  const instant = await page.locator("#msg-list .msg", { hasText: "ws-instant-message" }).count();
  check("WebSocket delivers a new message without a 5s poll", instant > 0, `messages=${instant}`);

  const form = new FormData();
  form.append("file", new Blob(["my file"], { type: "text/plain" }), "my-file.txt");
  const upload = await fetch(BASE + "/media/api/attachments?session_token=" + encodeURIComponent(adminToken), { method: "POST", body: form });
  const uploaded = await upload.json();
  check("attachment uploaded", upload.status === 200 && !!uploaded.attachment, JSON.stringify(uploaded).slice(0, 160));

  await page.evaluate(() => { location.hash = "#/account"; });
  await page.waitForTimeout(900);
  const fileRow = await page.locator("#my-files-list .my-file-row").count();
  check("My Files lists uploaded files", fileRow > 0, `rows=${fileRow}`);

  await page.locator("#my-files-list .my-file-row", { hasText: "my-file.txt" }).first().locator(".icon-btn").click();
  await page.waitForTimeout(1200);
  const myFileStill = await page.locator("#my-files-list .my-file-row", { hasText: "my-file.txt" }).count();
  check("My Files deletes an unreferenced file", myFileStill === 0, `rows=${myFileStill}`);

  await page.evaluate(() => { location.hash = "#/chat"; });
  await page.waitForTimeout(700);
  await page.locator("#create-chat-btn").click();
  await page.waitForTimeout(300);
  const dialog = await page.locator("#create-chat-modal").evaluate((node) => ({
    role: node.getAttribute("role"),
    modal: node.getAttribute("aria-modal"),
    hidden: node.classList.contains("hidden"),
  }));
  check("create-chat dialog is accessible", dialog.role === "dialog" && dialog.modal === "true" && dialog.hidden === false, JSON.stringify(dialog));
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const stillThere = await page.locator("#create-chat-modal").count();
  const hiddenAfter = stillThere === 0 || await page.locator("#create-chat-modal").evaluate((node) => node.classList.contains("hidden") || node._closing === true);
  check("Escape closes the dialog", hiddenAfter, String(hiddenAfter));

  const ruCtx = await browser.newContext({ locale: "ru-RU", viewport: { width: 1000, height: 700 } });
  const ruPage = await ruCtx.newPage();
  await ruPage.goto(BASE + "/");
  await ruPage.waitForTimeout(900);
  const ruLang = await ruPage.evaluate(() => LANG);
  check("browser locale selects Russian on first visit", ruLang === "rus", ruLang);
  await ruCtx.close();

  check("no page errors", errs.length === 0, errs.slice(0, 4).join(" | "));
  await browser.close();
  process.exit(summary() ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
