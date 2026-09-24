// Auto-moderation: word-list detector files reports into the normal queue.
// Run: node tests/ui/chat_automod_check.js
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
  const password = "automod-pass-123";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: prefix + "-" + Date.now(),
    client_kind: "web",
  });
  const user = res.json && res.json.user ? res.json.user : null;
  return { login, password, id: user ? user.id : null };
}

async function tokenFor(login, password) {
  const res = await api("POST", "/auth/login", { login, password, client_kind: "web" });
  return res.json && res.json.session ? res.json.session.token : null;
}

async function listAutoReports(adminToken) {
  const res = await api("GET", `/reports/api/list?session_token=${encodeURIComponent(adminToken)}&limit=100`);
  return (res.json.reports || []).filter(r => r.source === "auto");
}

async function setAutomod(adminToken, payload) {
  return api("POST", "/reports/api/auto-moderation", { session_token: adminToken, ...payload });
}

(async () => {
  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());

  await login(page, "admin", "7428");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);
  check("admin session is ready", !!adminToken);

  const u1 = await register("bgam");
  const u1Token = await tokenFor(u1.login, u1.password);
  check("test user registered", !!u1Token, JSON.stringify(u1));

  // open the common chat once: the read marker lazily creates the membership row
  const seed = await api("GET", "/chat/api/chats/1/messages?session_token=" + encodeURIComponent(u1Token) + "&limit=1");
  const lastSeed = (seed.json.items || [])[seed.json.items.length - 1];
  await api("POST", "/chat/api/chats/1/read", { session_token: u1Token, message_id: lastSeed ? lastSeed.message_id : 1 });

  // --- settings API ---
  const cfg = await api("GET", `/reports/api/auto-moderation?session_token=${encodeURIComponent(adminToken)}`);
  check("settings GET works", cfg.status === 200 && cfg.json.status === "ok" && typeof cfg.json.settings.enabled === "boolean", JSON.stringify(cfg.json).slice(0, 140));
  check("base dictionary is shipped", cfg.json.base_count > 50, "base_count=" + cfg.json.base_count);
  const saved = await setAutomod(adminToken, { enabled: true, extra_words: "", whitelist: "" });
  check("settings POST works", saved.status === 200 && saved.json.settings.enabled === true, JSON.stringify(saved.json.settings));
  const forbidden = await api("GET", `/reports/api/auto-moderation?session_token=${encodeURIComponent(u1Token)}`);
  check("settings are staff-only", forbidden.status === 403, "status=" + forbidden.status);

  // --- profanity -> auto report with context ---
  await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "ну ты и сука, конечно" });
  await page.waitForTimeout(800);
  let autos = await listAutoReports(adminToken);
  const r1 = autos.find(r => r.target_user_id === u1.id);
  check("auto report is created for profanity", !!r1, JSON.stringify(autos[0] || {}).slice(0, 200));
  check("report reason is profanity", !!r1 && r1.reason === "profanity", r1 && r1.reason);
  check("matched words are recorded", !!r1 && /сука/.test(r1.matched_words || ""), r1 && r1.matched_words);
  check("reporter is the auto moderator", !!r1 && r1.reporter_login === "Авто-модерация", r1 && r1.reporter_login);
  check("report carries 3+3 context", !!r1 && /Контекст \(3 до \/ 3 после\)/.test(r1.comment || "") && />> /.test(r1.comment || ""), r1 && (r1.comment || "").slice(0, 200));

  // --- obfuscations ---
  await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "ну и $yka ты" });
  await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "да ты л-о-х" });
  await page.waitForTimeout(900);
  autos = await listAutoReports(adminToken);
  const mine = autos.filter(r => r.target_user_id === u1.id);
  const seenWords = mine.map(r => r.matched_words || "").join(" | ");
  check("homoglyph bypass is caught ($yka)", /сука/.test(seenWords), seenWords.slice(0, 160));
  check("separator bypass is caught (л-о-х)", /лох/.test(seenWords), seenWords.slice(0, 160));

  // --- clean message ---
  const beforeClean = (await listAutoReports(adminToken)).length;
  await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "всем привет, хорошего дня" });
  await page.waitForTimeout(800);
  const afterClean = (await listAutoReports(adminToken)).length;
  check("clean message creates no report", afterClean === beforeClean, beforeClean + " -> " + afterClean);

  // --- edit is scanned ---
  const sent = await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "какая погода" });
  const mid = sent.json.message.message_id;
  await api("PUT", `/chat/api/chats/1/messages/${mid}`, { session_token: u1Token, body_text: "какая погода, блядь" });
  await page.waitForTimeout(800);
  autos = await listAutoReports(adminToken);
  check("edited message is scanned", autos.some(r => r.message_id === mid), JSON.stringify(autos.map(r => r.message_id)).slice(0, 140));

  // --- whitelist silences a word ---
  await setAutomod(adminToken, { whitelist: "блядь" });
  const wlMsg = await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "блядь, опять дождь" });
  const wlMid = wlMsg.json.message.message_id;
  await page.waitForTimeout(800);
  autos = await listAutoReports(adminToken);
  check("whitelisted word is not reported", !autos.some(r => r.message_id === wlMid), JSON.stringify(autos.map(r => r.message_id)).slice(0, 140));

  // --- extra words from settings ---
  await setAutomod(adminToken, { whitelist: "", extra_words: "баклажан" });
  await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "ты баклажан" });
  await page.waitForTimeout(800);
  autos = await listAutoReports(adminToken);
  check("extra admin words are scanned", autos.some(r => /баклажан/.test(r.matched_words || "")), JSON.stringify(autos.slice(0, 1)).slice(0, 160));

  // --- disabled -> nothing ---
  await setAutomod(adminToken, { enabled: false });
  const disabledBefore = (await listAutoReports(adminToken)).length;
  await api("POST", "/chat/api/chats/1/messages", { session_token: u1Token, body_text: "сука и всё тут" });
  await page.waitForTimeout(800);
  const disabledAfter = (await listAutoReports(adminToken)).length;
  check("disabled automod creates no reports", disabledAfter === disabledBefore, disabledBefore + " -> " + disabledAfter);
  await setAutomod(adminToken, { enabled: true, extra_words: "", whitelist: "" });

  // --- resolve with warn ---
  autos = await listAutoReports(adminToken);
  const pending = autos.find(r => r.status === "pending");
  check("pending auto reports exist for the resolve check", !!pending, "pending=" + (autos.filter(r => r.status === "pending").length));
  if (pending) {
    const res = await api("POST", "/reports/api/resolve", { session_token: adminToken, report_id: pending.id, action: "warn" });
    check("auto report can be resolved with warn", res.status === 200, JSON.stringify(res.json).slice(0, 140));
  }

  // --- admin UI ---
  await page.evaluate(() => { window.location.hash = "#/admin"; });
  await page.waitForTimeout(1500);
  await page.click('.tab[data-tab="reports"]');
  await page.waitForTimeout(1200);
  const ui = await page.evaluate(() => ({
    settingsCard: !!document.getElementById("automod-enabled") && !!document.getElementById("automod-save"),
    enabledChecked: document.getElementById("automod-enabled") ? document.getElementById("automod-enabled").checked : null,
    autoBadge: Array.from(document.querySelectorAll("#admin-reports .user-row .badge-type")).some(b => b.textContent === "авто"),
    autoWords: Array.from(document.querySelectorAll("#admin-reports .user-row")).some(row => /Слова:/.test(row.textContent || "")),
    legacyCard: (document.getElementById("admin-reports").textContent || "").includes("старый сканер"),
  }));
  check("settings card is rendered in the admin reports tab", ui.settingsCard, JSON.stringify(ui).slice(0, 200));
  check("settings reflect enabled=true", ui.enabledChecked === true, "checked=" + ui.enabledChecked);
  check("auto reports show the auto badge", ui.autoBadge, JSON.stringify(ui).slice(0, 200));
  check("auto reports show matched words", ui.autoWords, JSON.stringify(ui).slice(0, 200));
  await page.screenshot({ path: SHOTS + "automod-admin.png" });

  check("no page errors", errs.length === 0, errs.join(" | "));

  const code = summary();
  await browser.close();
  process.exit(code);
})();
