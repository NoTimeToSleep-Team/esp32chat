// P2 features: polls, user blocks, online indicator.
// Run: node tests/ui/chat_p2_check.js
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
  const password = "uip2-pass-123";
  const res = await api("POST", "/auth/register", {
    login,
    password,
    phone: "+7000" + String(Math.floor(Math.random() * 900000) + 100000),
    device_id: "uip2-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6),
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
  const u1 = await register("uip2a");
  const u2 = await register("uip2b");
  check("two test users registered", !!u1.id && !!u2.id, JSON.stringify([u1.id, u2.id]));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("dialog", d => d.accept());
  await login(page, "admin");
  await page.waitForTimeout(600);
  const adminToken = await page.evaluate(() => STATE.token);
  const adminId = await page.evaluate(() => STATE.user.id);

  const grpTitle = "P2 " + Math.random().toString(36).slice(2, 6);
  const created = await api("POST", "/chat/api/chats", {
    session_token: adminToken, title: grpTitle, member_ids: [u1.id], chat_type: "group",
  });
  const chatId = created.json.chat.chat_id;
  check("group created for the P2 tests", !!chatId, JSON.stringify(created.json).slice(0, 160));

  // --- polls (API) ---
  const poll = await api("POST", `/chat/api/chats/${chatId}/polls`, {
    session_token: adminToken, question: "Куда идём?", options: ["В кино", "Домой", "В парк"],
  });
  const pollId = poll.json && poll.json.message && poll.json.message.poll ? poll.json.message.poll.poll_id : null;
  check("poll is created with options", poll.status === 200 && poll.json.message.poll.options.length === 3, JSON.stringify(poll.json).slice(0, 220));
  check("poll options start empty", poll.json.message.poll.total_votes === 0, JSON.stringify(poll.json.message.poll).slice(0, 160));

  const u1Token = await tokenFor(u1.login, u1.password);
  const vote = await api("POST", `/chat/api/chats/${chatId}/polls/${pollId}/vote`, { session_token: u1Token, option_index: 1 });
  check("vote is counted", vote.status === 200 && vote.json.message.poll.options[1].votes === 1 && vote.json.message.poll.options[1].mine,
    JSON.stringify(vote.json.message.poll).slice(0, 220));
  const switchVote = await api("POST", `/chat/api/chats/${chatId}/polls/${pollId}/vote`, { session_token: u1Token, option_index: 0 });
  check("single-choice poll keeps one vote",
    switchVote.status === 200 && switchVote.json.message.poll.options[0].votes === 1 && switchVote.json.message.poll.options[1].votes === 0,
    JSON.stringify(switchVote.json.message.poll).slice(0, 220));

  // --- polls (UI) ---
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
  const pollUi = await page.evaluate(() => ({
    card: !!document.querySelector(".poll-card"),
    options: document.querySelectorAll(".poll-card .poll-opt").length,
    bars: document.querySelectorAll(".poll-card .poll-bar").length,
    meta: document.querySelector(".poll-card .poll-meta")?.textContent || "",
  }));
  check("poll card is rendered in the feed", pollUi.card && pollUi.options === 3 && pollUi.bars === 3, JSON.stringify(pollUi));
  check("poll shows the vote counter", /голосов/.test(pollUi.meta), JSON.stringify(pollUi));
  await page.screenshot({ path: SHOTS + "chat-p2-poll.png" });

  // vote through the UI (second option)
  await page.evaluate(() => {
    const opts = document.querySelectorAll(".poll-card .poll-opt");
    if (opts[2]) opts[2].click();
  });
  await page.waitForTimeout(1500);
  const afterVote = await page.evaluate(() => ({
    mine: document.querySelectorAll(".poll-card .poll-opt.mine").length,
    meta: document.querySelector(".poll-card .poll-meta")?.textContent || "",
  }));
  check("UI vote marks the option as mine", afterVote.mine === 1, JSON.stringify(afterVote));

  // --- poll creation through the UI ---
  await page.click("#poll-btn");
  await page.waitForTimeout(500);
  const pollModal = await page.evaluate(() => ({
    visible: !!document.querySelector("#poll-modal"),
    optionInputs: document.querySelectorAll("#poll-options input").length,
  }));
  check("poll creation modal opens with two options", pollModal.visible && pollModal.optionInputs === 2, JSON.stringify(pollModal));
  await page.fill("#poll-question", "Какой чай?");
  const inputs = await page.$$("#poll-options input");
  await inputs[0].fill("Чёрный");
  await inputs[1].fill("Зелёный");
  await page.click("#poll-submit");
  await page.waitForTimeout(2500);
  const createdUi = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll(".poll-card .poll-question")).map(e => e.textContent);
    return { cards };
  });
  check("poll created through the UI appears in the feed", createdUi.cards.includes("Какой чай?"), JSON.stringify(createdUi));

  // --- blocks ---
  const block = await api("POST", `/chat/api/blocks/${u2.id}`, { session_token: adminToken });
  check("user can be blocked", block.status === 200, JSON.stringify(block.json).slice(0, 140));
  const blocks = await api("GET", "/chat/api/blocks?session_token=" + encodeURIComponent(adminToken));
  check("blocked list contains the user", (blocks.json.user_ids || []).includes(u2.id), JSON.stringify(blocks.json).slice(0, 140));

  const u2Token = await tokenFor(u2.login, u2.password);
  const dmBlocked = await api("POST", "/chat/api/dm", { session_token: adminToken, target_user_id: u2.id });
  check("DM with a blocked user is refused", dmBlocked.status === 403 && dmBlocked.json.detail.code === "blocked",
    dmBlocked.status + " " + JSON.stringify(dmBlocked.json).slice(0, 160));
  const dmBlockedOther = await api("POST", "/chat/api/dm", { session_token: u2Token, target_user_id: adminId });
  check("blocked user cannot open a DM either", dmBlockedOther.status === 403, dmBlockedOther.status + " " + JSON.stringify(dmBlockedOther.json).slice(0, 160));

  const searchAfterBlock = await api("GET", `/chat/api/users/search?session_token=${encodeURIComponent(adminToken)}&q=${encodeURIComponent(u2.login.slice(0, 10))}`);
  check("blocked user is hidden from search", !((searchAfterBlock.json.items || []).some(i => i.user_id === u2.id)),
    JSON.stringify(searchAfterBlock.json).slice(0, 160));

  const unblock = await api("DELETE", `/chat/api/blocks/${u2.id}`, { session_token: adminToken });
  check("user can be unblocked", unblock.status === 200, JSON.stringify(unblock.json).slice(0, 140));
  const dmAfter = await api("POST", "/chat/api/dm", { session_token: adminToken, target_user_id: u2.id });
  check("DM works again after unblock", dmAfter.status === 200, dmAfter.status + " " + JSON.stringify(dmAfter.json).slice(0, 160));

  // block button in the profile modal (real flow: open the author profile from the feed)
  await api("POST", `/chat/api/chats/${chatId}/messages`, { session_token: u1Token, body_text: "P2 profile check " + Date.now() });
  await page.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, grpTitle);
  await page.waitForTimeout(2000);
  const avatarClicked = await page.evaluate((uid) => {
    const ava = document.querySelector(`#msg-list .msg-avatar[data-ava-uid="${uid}"]`);
    if (!ava) return false;
    ava.click();
    return true;
  }, u1.id);
  await page.waitForTimeout(1500);
  const blockBtn = await page.evaluate(() => {
    const btn = document.querySelector("#profile-modal #pm-block");
    return btn ? { text: btn.textContent.trim(), hasIcon: !!btn.querySelector("svg") } : null;
  });
  check("profile modal has the block button", avatarClicked && !!blockBtn && /Заблокировать/.test(blockBtn.text) && blockBtn.hasIcon,
    JSON.stringify({ avatarClicked, blockBtn }));
  await page.evaluate(() => { const b = document.querySelector("#profile-modal #pm-block"); if (b) b.click(); });
  await page.waitForTimeout(1500);
  const blocksAfterUi = await api("GET", "/chat/api/blocks?session_token=" + encodeURIComponent(adminToken));
  check("block button in the profile blocks the user", (blocksAfterUi.json.user_ids || []).includes(u1.id),
    JSON.stringify(blocksAfterUi.json).slice(0, 140));
  await api("DELETE", `/chat/api/blocks/${u1.id}`, { session_token: adminToken });

  // --- online indicator ---
  const ping = await api("POST", "/chat/api/presence/ping", { session_token: u1Token });
  const onlineApi = await api("GET", `/chat/api/chats/${chatId}/online?session_token=${encodeURIComponent(u1Token)}`);
  check("presence ping and chat online list work",
    ping.status === 200 && onlineApi.status === 200 && (onlineApi.json.user_ids || []).includes(u1.id),
    ping.status + " " + JSON.stringify(onlineApi.json).slice(0, 160));
  const ctx1 = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page1 = await ctx1.newPage();
  page1.on("dialog", d => d.accept());
  await login(page1, u1.login, u1.password);
  await page1.waitForTimeout(2500);
  await page1.evaluate((title) => {
    const items = Array.from(document.querySelectorAll("#chat-list .chat-item"));
    const item = items.find(i => (i.querySelector(".chat-item-title") || {}).textContent.includes(title));
    if (item) item.click();
  }, grpTitle);
  await page1.waitForTimeout(2500);
  const onlineUi = await page1.evaluate(() => document.querySelector(".chead .t2")?.textContent || "");
  check("chat header shows who is online", /в сети/.test(onlineUi), onlineUi);
  await ctx1.close();

  // --- mobile: poll card fits ---
  const { browser: mBrowser, page: mPage } = await launchMobile();
  mPage.on("dialog", d => d.accept());
  await login(mPage, "admin");
  await mPage.waitForTimeout(2500);
  await mPage.click("#chat-list .chat-item");
  await mPage.waitForTimeout(1500);
  await mPage.click("#chat-more");
  await mPage.waitForTimeout(1500);
  const mobile = await mPage.evaluate(() => ({
    overflowX: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth,
  }));
  check("no horizontal overflow on mobile with the new features", mobile.overflowX <= 1, JSON.stringify(mobile));
  await mPage.screenshot({ path: SHOTS + "chat-p2-mobile.png" });
  await mBrowser.close();

  check("no page errors", errs.length === 0, errs.join(" | "));

  const code = summary();
  await browser.close();
  process.exit(code);
})();
