const CampApp = (() => {
  const state = { token: localStorage.getItem("lc_session_token") || "", me: null, chats: [], links: [], activeChatId: null, activeLink: null, messages: [], userNames: {}, ws: null, sheetAction: null, rollcallEvent: null };
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const T = {
    role: { child: "Ребёнок", counselor: "Вожатый", director: "Директор", security: "Охрана", medic: "Медик", parent: "Родитель", kitchen: "Кухня", it: "Техник" },
    request: { call_counselor: "Нужен вожатый", help: "Нужна помощь", parent_question: "Вопрос родителям" },
    attendance: { present: "На месте", absent: "Нет", sick: "Заболел", medic: "У медика", parent: "У родителя", left: "Ушёл" },
  };
  const ERR = { role_forbidden: "Нет доступа к действию.", unit_forbidden: "Это чужой отряд.", attendance_incomplete: "Отметьте всех или закройте с причиной.", request_forbidden: "Закрыть может только тот, кто взял.", alert_forbidden: "Тревогу запускает директор или охрана." };
  const tr = (g, v) => T[g]?.[v] ?? (v || "—");
  const roleName = (v) => tr("role", v);
  const humanError = (e) => (e?.code && ERR[e.code]) || e?.message || "Не получилось. Попробуйте ещё раз.";
  const fmtTime = (ms) => ms ? new Date(Number(ms)).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "";
  const fmtDay = (ms) => ms ? new Date(Number(ms)).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }) : "";
  const dayKey = (ms) => new Date(Number(ms)).toDateString();
  const initials = (t) => String(t || "?").replace(/[^0-9A-Za-zА-Яа-яЁё]/g, "").slice(0, 1).toUpperCase() || "#";

  function toast(message, isError = false) {
    const n = $("#campToast"); n.textContent = message; n.classList.toggle("error", isError); n.classList.remove("hidden");
    clearTimeout(toast.timer); toast.timer = setTimeout(() => n.classList.add("hidden"), 4500);
  }
  async function api(path, options = {}) {
    const url = new URL(path, location.origin);
    if (!url.pathname.startsWith("/auth/")) url.searchParams.set("session_token", state.token);
    const r = await fetch(url, { method: options.method || "GET", headers: options.body ? { "Content-Type": "application/json" } : undefined, body: options.body ? JSON.stringify(options.body) : undefined });
    const text = await r.text(); let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
    if (!r.ok) { const d = data.detail || data; const e = new Error(d.message || d.code || `Ошибка ${r.status}`); e.code = d.code || d.detail?.code; throw e; }
    return data;
  }
  function showApp() { $("#campLogin").classList.add("hidden"); $("#campApp").classList.remove("hidden"); }
  function showLogin(message = "") { $("#campLogin").classList.remove("hidden"); $("#campApp").classList.add("hidden"); $("#campLoginError").textContent = message; $("#campSide")?.classList.remove("open"); }

  async function connect(token) {
    state.token = token.trim();
    state.me = await api("/camp/api/me");
    localStorage.setItem("lc_session_token", state.token);
    showApp();
    $("#campUserLine").innerHTML = `<strong>${esc(state.me.actor.display_name)}</strong>${esc(roleName(state.me.actor.role))}`;
    $("#campSessionName").textContent = state.me.current_session?.name || "Смена не выбрана";
    await loadPeople();
    if (state.me.actor.role === "director") { try { await api("/camp/api/chats/bootstrap", { method: "POST" }); } catch (e) { console.warn(e); } }
    await loadChats();
    await loadContext();
    renderActionButton();
  }
  async function loadPeople() {
    try {
      const d = await api("/camp/api/people?limit=500"); state.userNames = {};
      (d.items || []).forEach((p) => { if (p.user_id) state.userNames[String(p.user_id)] = p.display_name; });
      if (state.me?.actor?.user_id) state.userNames[String(state.me.actor.user_id)] = state.me.actor.display_name;
    } catch (e) { console.warn(e); }
  }
  async function loadChats() {
    let links = [];
    try { links = (await api("/camp/api/chats")).items || []; } catch (e) { console.warn(e); }
    state.links = links;
    let all = [];
    try { all = (await api(`/chat/api/chats?session_token=${encodeURIComponent(state.token)}`)).items || []; } catch (e) { console.warn(e); }
    const byId = new Map(all.map((c) => [Number(c.chat_id), c]));
    if (links.length) {
      state.chats = links.map((l) => ({ ...(byId.get(Number(l.chat_id)) || {}), chat_id: Number(l.chat_id), title: l.title || byId.get(Number(l.chat_id))?.title || "Чат", scope: l.scope, unit_id: l.unit_id }));
    } else if (["director", "counselor", "security", "medic", "it", "kitchen"].includes(state.me?.actor?.role)) {
      state.chats = all.map((c) => ({ ...c, scope: "general" }));
    } else state.chats = [];
    if (state.activeChatId && !state.chats.some((c) => Number(c.chat_id) === Number(state.activeChatId))) state.activeChatId = null;
    renderChatList();
    if (!state.activeChatId && state.chats.length) await openChat(state.chats[0].chat_id);
    if (!state.chats.length) renderEmptyChat("Нет доступных чатов", "Директор ещё не создал каналы отряда и персонала.");
  }
  function renderChatList() {
    const node = $("#campChatList");
    node.innerHTML = state.chats.map((c) => `<button class="chat-item ${Number(c.chat_id) === Number(state.activeChatId) ? "active" : ""}" type="button" data-chat="${c.chat_id}"><div class="camp-chat-ava">${esc(initials(c.title))}</div><div class="chat-item-main"><div class="chat-item-title">${esc(c.title || "Чат")}</div><div class="chat-item-desc">${esc(c.scope === "staff" ? "Персонал" : c.scope === "unit" ? "Отряд" : "Общий чат")}</div></div>${c.unread_count ? `<span class="camp-badge">${esc(c.unread_count)}</span>` : ""}</button>`).join("");
    node.querySelectorAll("[data-chat]").forEach((b) => b.addEventListener("click", () => openChat(Number(b.dataset.chat))));
  }
  function renderEmptyChat(title, text) { $("#campMessages").innerHTML = `<div class="camp-empty"><strong>${esc(title)}</strong><span>${esc(text)}</span></div>`; }
  async function openChat(chatId) {
    const chat = state.chats.find((c) => Number(c.chat_id) === Number(chatId)); if (!chat) return;
    state.activeChatId = Number(chatId); state.activeLink = state.links.find((l) => Number(l.chat_id) === Number(chatId)) || null;
    closeSocket(); renderChatList();
    $("#campChatTitle").textContent = chat.title || "Чат";
    $("#campChatSubtitle").textContent = chat.scope === "staff" ? "Канал персонала" : chat.scope === "unit" ? "Канал отряда" : "Общий чат";
    $("#campChatAvatar").textContent = initials(chat.title);
    $("#campSide").classList.remove("open"); renderActionButton();
    $("#campMessages").innerHTML = `<div class="camp-empty"><strong>Загрузка…</strong></div>`;
    try {
      state.messages = (await api(`/chat/api/chats/${chatId}/messages?limit=100&session_token=${encodeURIComponent(state.token)}`)).items || [];
      state.rollcallEvent = null;
      if (state.activeLink?.scope === "unit" && ["counselor", "director"].includes(state.me?.actor?.role)) {
        try {
          const events = (await api(`/camp/api/attendance/events?limit=20&session_id=${encodeURIComponent(state.me.current_session?.id || "")}`)).items || [];
          state.rollcallEvent = events.find((event) => Number(event.unit_id) === Number(state.activeLink.unit_id) && event.status === "open") || null;
        } catch (_) {}
      }
      renderMessages(); connectSocket(chatId); markRead();
    } catch (e) { renderEmptyChat("Чат не открылся", humanError(e)); }
    await loadContext();
  }
  function renderMessages() {
    const list = $("#campMessages");
    const card = rollcallCard();
    if (!state.messages.length) {
      list.innerHTML = `${card}<div class="camp-empty"><strong>Пока тихо</strong><span>Напишите первое сообщение в этот чат.</span></div>`;
      bindRollcall(list);
      return;
    }
    let day = ""; const parts = [];
    for (const m of state.messages) {
      if (dayKey(m.created_at_ms) !== day) { day = dayKey(m.created_at_ms); parts.push(`<div class="day-sep">${esc(fmtDay(m.created_at_ms))}</div>`); }
      const mine = Number(m.author_user_id) === Number(state.me?.actor?.user_id);
      const author = mine ? "Вы" : (state.userNames[String(m.author_user_id)] || `Участник #${m.author_user_id}`);
      parts.push(`<div class="msg ${mine ? "out" : ""}" data-mid="${m.message_id}"><div class="msg-avatar">${esc(initials(author))}</div><div class="msg-body"><div class="msg-header"><span class="msg-author">${esc(author)}</span><span class="msg-time">${esc(fmtTime(m.created_at_ms))}</span></div><div class="msg-text">${esc(m.body_text || "")}</div></div></div>`);
    }
    list.innerHTML = card + parts.join(""); bindRollcall(list); list.scrollTop = list.scrollHeight;
  }
  function appendMessage(m) {
    if (!m || Number(m.chat_id) !== Number(state.activeChatId) || document.querySelector(`.msg[data-mid="${m.message_id}"]`)) return;
    state.messages.push(m); const list = $("#campMessages"); const bottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
    const mine = Number(m.author_user_id) === Number(state.me?.actor?.user_id);
    const author = mine ? "Вы" : (state.userNames[String(m.author_user_id)] || `Участник #${m.author_user_id}`);
    if (list.querySelector(".camp-empty")) list.innerHTML = "";
    list.insertAdjacentHTML("beforeend", `<div class="msg ${mine ? "out" : ""}" data-mid="${m.message_id}"><div class="msg-avatar">${esc(initials(author))}</div><div class="msg-body"><div class="msg-header"><span class="msg-author">${esc(author)}</span><span class="msg-time">${esc(fmtTime(m.created_at_ms))}</span></div><div class="msg-text">${esc(m.body_text || "")}</div></div></div>`);
    if (bottom || mine) list.scrollTop = list.scrollHeight;
  }
  function closeSocket() { if (state.ws) { try { state.ws.close(); } catch (_) {} } state.ws = null; }
  function connectSocket(chatId) {
    try {
      const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/realtime/chat/${chatId}?session_token=${encodeURIComponent(state.token)}`);
      state.ws = ws;
      ws.addEventListener("message", (e) => { try { const p = JSON.parse(e.data); if (p.type === "chat.message" && p.message) appendMessage(p.message); if (p.type === "chat.history" && Array.isArray(p.items)) { state.messages = p.items; renderMessages(); } } catch (_) {} });
    } catch (_) {}
  }
  async function sendMessage() {
    const input = $("#campInput"); const text = input.value.trim();
    if (!text || !state.activeChatId) return;
    input.value = ""; input.style.height = ""; $("#campSend").disabled = true;
    try {
      const r = await api(`/chat/api/chats/${state.activeChatId}/messages`, { method: "POST", body: { session_token: state.token, body_text: text, client_message_id: `web-${Date.now()}-${Math.random().toString(16).slice(2, 8)}` } });
      if (r.message) appendMessage(r.message); else await openChat(state.activeChatId);
    } catch (e) { toast(humanError(e), true); input.value = text; }
    finally { $("#campSend").disabled = false; input.focus(); }
  }
  async function markRead() {
    if (!state.activeChatId || !state.messages.length) return;
    try { await api(`/chat/api/chats/${state.activeChatId}/read`, { method: "POST", body: { session_token: state.token, message_id: state.messages[state.messages.length - 1].message_id } }); } catch (_) {}
  }
  function renderActionButton() {
    const b = $("#campChatAction"); const l = state.activeLink;
    if (!l) { b.classList.add("hidden"); return; }
    let action = "requests", label = "Заявки";
    if (l.scope === "unit") { action = "rollcall"; label = "Перекличка"; }
    if (state.me?.actor?.role === "security") { action = "gate"; label = "Ворота"; }
    if (state.me?.actor?.role === "medic") { action = "alerts"; label = "Тревоги"; }
    b.dataset.action = action; b.textContent = label; b.classList.remove("hidden");
  }
  function openSheet(title, html, onMount) { $("#campSheetTitle").textContent = title; $("#campSheetBody").innerHTML = html; $("#campSheet").classList.remove("hidden"); if (onMount) onMount($("#campSheetBody")); }
  function closeSheet() { $("#campSheet").classList.add("hidden"); $("#campSheetBody").innerHTML = ""; state.sheetAction = null; }
  function openAction(action) {
    if (window.CampActions && window.CampActions[action]) { state.sheetAction = action; window.CampActions[action]({ api, toast, esc, tr, humanError, fmtTime, fmtDay, openSheet, closeSheet, state, loadContext, loadChats, openChat }); return; }
    openSheet("Действие", `<div class="notice">Это действие появится в следующем обновлении.</div>`);
  }
  async function loadContext() {
    const title = $("#campContextTitle"), body = $("#campContextBody"), actions = $("#campContextActions");
    if (!state.me) return;
    const role = state.me.actor.role;
    title.textContent = role === "child" ? "Мой день" : role === "parent" ? "Мой ребёнок" : "Сегодня";
    body.innerHTML = `<div class="camp-context-card"><h3>${esc(state.me.current_session?.name || "Смена")}</h3><p>${esc(roleName(role))} · ${esc(state.me.actor.display_name)}</p></div>`;
    actions.innerHTML = "";
    try {
      if (role === "child") {
        const [requests, digests] = await Promise.all([api("/camp/api/requests?limit=5"), api("/camp/api/digests")]);
        const items = requests.items || [], last = (digests.items || [])[0];
        body.innerHTML += `<div class="camp-stat"><div class="label">Мои заявки</div><div class="value">${items.length}</div><div class="hint">${items[0] ? esc(tr("request", items[0].kind)) : "Нет активных"}</div></div>`;
        if (last) body.innerHTML += `<div class="camp-context-card"><h3>Дневник · ${esc(last.date)}</h3><p>${esc(last.text)}</p></div>`;
        actions.innerHTML = `<button class="btn btn-primary" data-action="new-request">Позвать вожатого</button><button class="btn btn-outline" data-action="digest">Мой дневник</button>`;
      } else if (role === "parent") {
        const digests = await api("/camp/api/digests");
        body.innerHTML += `<div class="camp-stat"><div class="label">Записи дневника</div><div class="value">${(digests.items || []).length}</div></div>`;
        actions.innerHTML = `<button class="btn btn-primary" data-action="digest">Дневник</button><button class="btn btn-outline" data-action="consents">Согласия</button>`;
      } else if (["director", "counselor", "security"].includes(role)) {
        const [requests, alerts, events] = await Promise.all([api("/camp/api/requests?limit=50"), api("/camp/api/alerts?limit=50"), api("/camp/api/attendance/events?limit=10")]);
        const openRequests = (requests.items || []).filter((i) => i.status !== "closed");
        const openAlerts = (alerts.items || []).filter((i) => i.status !== "closed");
        const openEvents = (events.items || []).filter((i) => i.status === "open");
        body.innerHTML += `<div class="camp-stat"><div class="label">Заявки</div><div class="value">${openRequests.length}</div><div class="hint">${openRequests[0] ? esc(tr("request", openRequests[0].kind)) : "Очередь пуста"}</div></div>`;
        body.innerHTML += `<div class="camp-stat"><div class="label">Тревоги</div><div class="value">${openAlerts.length}</div><div class="hint">${openAlerts[0] ? esc(openAlerts[0].title) : "Спокойно"}</div></div>`;
        body.innerHTML += `<div class="camp-stat"><div class="label">Переклички</div><div class="value">${openEvents.length}</div><div class="hint">${openEvents.length ? "Есть незакрытая" : "Всё закрыто"}</div></div>`;
        actions.innerHTML = `${["director", "counselor"].includes(role) ? `<button class="btn btn-primary" data-action="rollcall">Перекличка</button>` : ""}<button class="btn btn-outline" data-action="requests">Заявки</button><button class="btn btn-outline" data-action="alerts">Тревоги</button>${role === "director" ? `<button class="btn btn-outline" data-action="import">Импорт</button>` : ""}`;
      } else if (role === "medic") {
        const alerts = await api("/camp/api/alerts?limit=20");
        body.innerHTML += `<div class="camp-stat"><div class="label">Тревоги</div><div class="value">${(alerts.items || []).filter((i) => i.status !== "closed").length}</div></div>`;
        actions.innerHTML = `<button class="btn btn-primary" data-action="alerts">Тревоги</button><button class="btn btn-outline" data-action="dietary">Питание</button>`;
      } else if (role === "kitchen") {
        actions.innerHTML = `<button class="btn btn-primary" data-action="dietary">Питание</button>`;
      } else {
        actions.innerHTML = `<button class="btn btn-outline" data-action="import">Импорт</button>`;
      }
    } catch (e) { body.innerHTML += `<div class="notice">${esc(humanError(e))}</div>`; }
    actions.querySelectorAll("[data-action]").forEach((b) => b.addEventListener("click", () => openAction(b.dataset.action)));
    updateBadges();
  }
  async function updateBadges() {
    try {
      const [requests, alerts] = await Promise.all([api("/camp/api/requests?limit=100"), api("/camp/api/alerts?limit=100")]);
      const r = (requests.items || []).filter((i) => i.status !== "closed").length;
      const a = (alerts.items || []).filter((i) => i.status !== "closed").length;
      const rb = $("#campRequestBadge"), ab = $("#campAlertBadge");
      rb.textContent = r; rb.classList.toggle("hidden", !r); ab.textContent = a; ab.classList.toggle("hidden", !a);
    } catch (_) {}
  }
  function bindUi() {
    $("#campLoginForm").addEventListener("submit", async (event) => {
      event.preventDefault(); $("#campLoginError").textContent = "";
      try {
        const response = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ login: $("#campLoginName").value.trim(), password: $("#campLoginPassword").value, client_kind: "web", device_id: localStorage.getItem("camp_device_id") || `camp-web-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}` }) });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { const e = new Error(data.detail?.message || data.detail?.code || `Ошибка ${response.status}`); e.code = data.detail?.code; throw e; }
        if (!data.session?.token) throw new Error("Сервер не вернул сессию");
        await connect(data.session.token);
      } catch (e) { showLogin(humanError(e)); }
    });
    $("#campLogout").addEventListener("click", () => { localStorage.removeItem("lc_session_token"); state.token = ""; state.me = null; state.chats = []; state.links = []; closeSocket(); showLogin(); });
    $("#campComposer").addEventListener("submit", (e) => { e.preventDefault(); sendMessage(); });
    $("#campInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    $("#campInput").addEventListener("input", () => { const i = $("#campInput"); i.style.height = "auto"; i.style.height = Math.min(i.scrollHeight, 120) + "px"; });
    $("#campRefreshChats").addEventListener("click", loadChats);
    document.querySelectorAll(".camp-action-pill[data-action]").forEach((button) => {
      button.addEventListener("click", () => openAction(button.dataset.action));
    });
    $("#campMenuBtn").addEventListener("click", () => $("#campSide").classList.add("open"));
    $("#campSideClose").addEventListener("click", () => $("#campSide").classList.remove("open"));
    $("#campContextBtn").addEventListener("click", () => $("#campContext").classList.toggle("open"));
    $("#campContextClose").addEventListener("click", () => $("#campContext").classList.remove("open"));
    $("#campChatAction").addEventListener("click", (e) => openAction(e.currentTarget.dataset.action));
    $("#campQuickBtn").addEventListener("click", () => {
      const role = state.me?.actor?.role;
      const actions = {
        director: [["rollcall", "Перекличка"], ["requests", "Заявки"], ["alerts", "Тревога"], ["import", "Импорт"], ["digest", "Дневник"]],
        counselor: [["rollcall", "Перекличка"], ["requests", "Заявки"], ["digest", "Дневник"]],
        security: [["gate", "Ворота"], ["alerts", "Тревоги"]],
        medic: [["alerts", "Тревоги"], ["dietary", "Питание"]],
        child: [["new-request", "Позвать вожатого"], ["digest", "Дневник"]],
        parent: [["digest", "Дневник"], ["consents", "Согласия"]],
        kitchen: [["dietary", "Питание"]],
      }[role] || [];
      openSheet("Действия", actions.map(([id, label]) => `<button class="btn btn-outline" data-sheet-action="${id}">${esc(label)}</button>`).join("") || `<div class="notice">Нет доступных действий.</div>`, (root) => {
        root.querySelectorAll("[data-sheet-action]").forEach((b) => b.addEventListener("click", () => { closeSheet(); openAction(b.dataset.sheetAction); }));
      });
    });
    $("#campSheetClose").addEventListener("click", closeSheet);
    $("#campSheet").addEventListener("click", (e) => { if (e.target.dataset.sheetClose) closeSheet(); });
  }
  async function boot() {
    bindUi();
    if (!state.token) { showLogin(); return; }
    try { await connect(state.token); } catch (e) { showLogin(humanError(e)); }
  }
  return { state, api, esc, tr, roleName, humanError, fmtTime, fmtDay, toast, openSheet, closeSheet, openChat, loadChats, loadContext, loadPeople, renderMessages, renderChatList, renderActionButton, updateBadges, sendMessage, boot };
})();
window.CampApp = CampApp;
document.addEventListener("DOMContentLoaded", () => CampApp.boot());
  function rollcallCard() {
    if (state.activeLink?.scope !== "unit" || !["counselor", "director"].includes(state.me?.actor?.role)) return "";
    const event = state.rollcallEvent;
    if (!event) {
      return `<div class="camp-card"><div class="camp-card-head"><strong>Перекличка</strong><span class="camp-mini">${esc(state.activeLink.title || "Отряд")}</span></div><div class="camp-card-body"><div class="camp-mini">Открытой переклички нет. Начните её в чате отряда.</div></div><div class="camp-card-actions"><button class="btn btn-sm btn-primary" data-start-rollcall="1">Начать перекличку</button></div></div>`;
    }
    const items = event.items || [];
    return `<div class="camp-card"><div class="camp-card-head"><strong>Перекличка · ${esc(event.unit_name || "Отряд")}</strong><span class="camp-mini">${event.summary.marked}/${event.summary.total}</span></div><div class="camp-card-body"><div class="camp-progress"><span style="width:${event.summary.total ? Math.round(event.summary.marked * 100 / event.summary.total) : 0}%"></span></div>${items.map((item) => `<div class="camp-card-row"><span>${esc(item.display_name)}</span><select data-mark="${event.id}" data-person="${item.id}"><option value="">Не отмечен</option>${["present", "absent", "sick", "medic", "parent", "left"].map((status) => `<option value="${status}" ${item.mark_status === status ? "selected" : ""}>${esc(tr("attendance", status))}</option>`).join("")}</select></div>`).join("")}</div><div class="camp-card-actions"><button class="btn btn-sm btn-primary" data-all-present="${event.id}">Все на месте</button><button class="btn btn-sm btn-outline" data-close-roll="${event.id}">Закрыть</button><button class="btn btn-sm btn-outline" data-force-roll="${event.id}">Закрыть с причиной</button></div></div>`;
  }
  async function refreshRollcall() {
    try {
      const events = (await api(`/camp/api/attendance/events?limit=20&session_id=${encodeURIComponent(state.me.current_session?.id || "")}`)).items || [];
      state.rollcallEvent = events.find((event) => Number(event.unit_id) === Number(state.activeLink?.unit_id) && event.status === "open") || null;
      renderMessages();
    } catch (e) { toast(humanError(e), true); }
  }
  function bindRollcall(root) {
    root.querySelector("[data-start-rollcall]")?.addEventListener("click", async () => {
      try { await api("/camp/api/attendance/events", { method: "POST", body: { unit_id: Number(state.activeLink.unit_id), kind: "roll_call" } }); toast("Перекличка начата"); await refreshRollcall(); } catch (e) { toast(humanError(e), true); }
    });
    root.querySelectorAll("[data-mark]").forEach((select) => select.addEventListener("change", async () => {
      if (!select.value) return;
      try { await api(`/camp/api/attendance/events/${select.dataset.mark}/marks`, { method: "POST", body: { person_id: Number(select.dataset.person), status: select.value } }); await refreshRollcall(); } catch (e) { toast(humanError(e), true); }
    }));
    root.querySelectorAll("[data-all-present]").forEach((b) => b.addEventListener("click", async () => {
      try { await api(`/camp/api/attendance/events/${b.dataset.allPresent}/all-present`, { method: "POST" }); toast("Все отмечены"); await refreshRollcall(); } catch (e) { toast(humanError(e), true); }
    }));
    root.querySelectorAll("[data-close-roll]").forEach((b) => b.addEventListener("click", async () => {
      try { await api(`/camp/api/attendance/events/${b.dataset.closeRoll}/close`, { method: "POST", body: { force: false } }); toast("Перекличка закрыта"); await refreshRollcall(); }
      catch (e) { toast(humanError(e), true); if (e.code === "attendance_incomplete") { const note = prompt("Кто не отмечен и почему закрываем?"); if (note) { try { await api(`/camp/api/attendance/events/${b.dataset.closeRoll}/close`, { method: "POST", body: { force: true, note } }); toast("Закрыто с причиной"); await refreshRollcall(); } catch (x) { toast(humanError(x), true); } } } }
    }));
    root.querySelectorAll("[data-force-roll]").forEach((b) => b.addEventListener("click", async () => {
      const note = prompt("Причина закрытия без всех отметок"); if (!note) return;
      try { await api(`/camp/api/attendance/events/${b.dataset.forceRoll}/close`, { method: "POST", body: { force: true, note } }); toast("Закрыто с причиной"); await refreshRollcall(); } catch (e) { toast(humanError(e), true); }
    }));
  }
