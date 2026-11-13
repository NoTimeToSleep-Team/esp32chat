const state = {
  token: localStorage.getItem("lc_session_token") || "",
  me: null,
  panel: null,
};

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[ch]));

function fmtTime(ms) {
  if (!ms) return "—";
  return new Date(Number(ms)).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function fmtDate(ms) {
  if (!ms) return "—";
  return new Date(Number(ms)).toLocaleDateString("ru-RU");
}

function localInput(ms) {
  const date = new Date(Number(ms || Date.now()));
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromInput(value) {
  if (!value) return null;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function toast(message, isError = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.classList.remove("hidden");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.add("hidden"), 4500);
}

async function api(path, options = {}) {
  if (!state.token) throw new Error("Нужен токен сессии");
  const url = new URL(path, window.location.origin);
  url.searchParams.set("session_token", state.token);
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
  if (!response.ok) {
    const detail = data.detail || data;
    throw new Error(detail.message || detail.code || `HTTP ${response.status}`);
  }
  return data;
}

function badge(text, mode = "") {
  return `<span class="badge ${mode}">${esc(text)}</span>`;
}

function table(headers, rows, empty = "Нет данных") {
  const body = rows.length
    ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")
    : `<tr><td colspan="${headers.length}">${esc(empty)}</td></tr>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function metrics(items) {
  return `<div class="grid metrics">${items.map(([label, value]) => (
    `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>`
  )).join("")}</div>`;
}

function options(items, valueKey, labelKey, selected = null) {
  return items.map((item) => {
    const value = item[valueKey];
    const isSelected = selected != null && String(selected) === String(value);
    return `<option value="${esc(value)}" ${isSelected ? "selected" : ""}>${esc(item[labelKey])}</option>`;
  }).join("");
}

function role() {
  return String(state.me?.actor?.role || "");
}

function isStaff() {
  return ["counselor", "director", "security", "medic", "it", "kitchen"].includes(role());
}

function navItems() {
  const r = role();
  if (r === "child") return [["day", "Мой день"], ["new-request", "Позвать вожатого"], ["digest", "Мой дневник"]];
  if (r === "parent") return [["children", "Мои дети"], ["digest", "Дневник"], ["consents", "Согласия"]];
  if (r === "counselor") return [["rollcall", "Перекличка"], ["requests", "Заявки"], ["scan", "Сканирование"], ["duty", "Передача смены"], ["digest", "Дневник"]];
  if (r === "director") return [["overview", "Обзор"], ["rollcall", "Перекличка"], ["alerts", "Тревоги"], ["zones", "Зоны"], ["duty", "Смена"], ["gate", "Ворота"], ["dietary", "Питание"], ["digest", "Дневник"], ["report", "Отчёт"], ["consents", "Согласия"], ["kiosk", "Киоск"], ["status", "Статус"]];
  if (r === "security") return [["gate", "Ворота"], ["scan", "Сканирование"], ["alerts", "Тревоги"], ["zones", "Зоны"], ["status", "Статус"]];
  if (r === "medic") return [["alerts", "Тревоги"], ["dietary", "Питание"], ["scan", "Сканирование"], ["status", "Статус"]];
  if (r === "kitchen") return [["dietary", "Питание"]];
  return [["status", "Статус"], ["report", "Отчёт"]];
}

function renderChrome() {
  const actor = state.me.actor;
  $("#roleChip").textContent = actor.role || "camp";
  $("#roleChip").classList.remove("hidden");
  $("#logoutBtn").classList.remove("hidden");
  const current = state.me.current_session;
  $("#sessionLine").textContent = current
    ? `${current.name} · ${current.status} · ${fmtDate(current.starts_at_ms)} — ${fmtDate(current.ends_at_ms)}`
    : "Активная смена не найдена";
  const nav = $("#nav");
  nav.innerHTML = navItems().map(([id, label]) => (
    `<button type="button" data-panel="${esc(id)}" class="${state.panel === id ? "active" : ""}">${esc(label)}</button>`
  )).join("");
  nav.querySelectorAll("[data-panel]").forEach((button) => {
    button.addEventListener("click", () => openPanel(button.dataset.panel));
  });
}

function showLogin(message = "") {
  $("#loginPanel").classList.remove("hidden");
  $("#workspace").classList.add("hidden");
  $("#loginError").textContent = message;
  $("#roleChip").classList.add("hidden");
  $("#logoutBtn").classList.add("hidden");
}

async function connect(token) {
  state.token = token.trim();
  const me = await api("/camp/api/me");
  state.me = me;
  localStorage.setItem("lc_session_token", state.token);
  $("#loginPanel").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  state.panel = navItems()[0]?.[0] || "status";
  renderChrome();
  await openPanel(state.panel);
}

function logout() {
  state.token = "";
  state.me = null;
  state.panel = null;
  localStorage.removeItem("lc_session_token");
  showLogin();
}

async function openPanel(id) {
  state.panel = id;
  renderChrome();
  const panel = $("#panel");
  panel.innerHTML = `<div class="notice">Загрузка…</div>`;
  try {
    const renderers = {
      overview: renderOverview,
      rollcall: renderRollcall,
      requests: renderRequests,
      "new-request": renderNewRequest,
      scan: renderScan,
      alerts: renderAlerts,
      zones: renderZones,
      duty: renderDuty,
      gate: renderGate,
      dietary: renderDietary,
      digest: renderDigest,
      report: renderReport,
      consents: renderConsents,
      kiosk: renderKiosk,
      status: renderStatus,
      day: renderDay,
      children: renderChildren,
    };
    const renderer = renderers[id] || renderOverview;
    await renderer(panel);
  } catch (error) {
    panel.innerHTML = `<section class="card"><h2>Ошибка</h2><p class="error">${esc(error.message)}</p><button class="button" type="button" onclick="location.reload()">Перезагрузить</button></section>`;
  }
}

function header(title, subtitle = "") {
  return `<div class="panel-head"><div><h2>${esc(title)}</h2>${subtitle ? `<p class="muted">${esc(subtitle)}</p>` : ""}</div></div>`;
}

async function people(roleName = "") {
  const query = roleName ? `?role=${encodeURIComponent(roleName)}` : "";
  const data = await api(`/camp/api/people${query}`);
  return data.items || [];
}

async function renderOverview(panel) {
  const data = await api("/camp/api/report");
  const report = data.item;
  const token = state.token;
  panel.innerHTML = `${header("Обзор смены", report.session.name)}
    ${metrics([
      ["Дети", report.people.children],
      ["Staff", report.people.staff],
      ["Открытые заявки", report.requests.open || 0],
      ["Тревоги", report.alerts.open || 0],
      ["Сканы", report.scans.total],
      ["Сейчас вне лагеря", report.movements.currently_out],
    ])}
    <div class="card" style="margin-top:12px">
      <div class="actions" style="margin-bottom:10px">
        <a class="button small" href="/camp/api/report.csv?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">CSV</a>
        <a class="button small" href="/camp/api/report.html?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">HTML print</a>
      </div>
      ${table(["Отряд", "Тип", "Детей"], report.units.map((unit) => [esc(unit.name), esc(unit.kind), esc(unit.child_count)]))}
    </div>`;
}

async function renderDay(panel) {
  const events = (await api("/camp/api/attendance/events?limit=5")).items || [];
  const digests = (await api("/camp/api/digests")).items || [];
  const open = events.find((event) => event.status === "open") || events[0];
  panel.innerHTML = `${header("Мой день", state.me.actor.display_name)}
    <div class="split">
      <section class="card">
        <h3>Перекличка</h3>
        ${open ? `<p>${badge(open.kind)} ${badge(open.status, open.status === "open" ? "warn" : "ok")} ${fmtTime(open.created_at_ms)}</p>
          <p class="muted">${esc(open.unit_name)} · ${open.summary.marked}/${open.summary.total}</p>` : `<p class="muted">Пока нет перекличек.</p>`}
      </section>
      <section class="card">
        <h3>Дневник</h3>
        ${digests.length ? digests.slice(0, 3).map((item) => `<div class="list-item"><strong>${esc(item.date)}</strong><p>${esc(item.text)}</p></div>`).join("") : `<p class="muted">Записей пока нет.</p>`}
      </section>
    </div>`;
}

async function renderNewRequest(panel) {
  panel.innerHTML = `${header("Позвать вожатого", "Сообщение попадёт в очередь staff; свободных личных чатов нет.")}
    <section class="card stack">
      <div class="actions">
        <button class="button primary" data-kind="call_counselor">Нужен вожатый</button>
        <button class="button" data-kind="help">Нужна помощь</button>
        <button class="button" data-kind="parent_question">Вопрос родителям</button>
      </div>
      <label>Короткое пояснение<textarea id="requestNote" maxlength="2000" placeholder="Что случилось?"></textarea></label>
      <p id="requestResult" class="muted"></p>
    </section>`;
  panel.querySelectorAll("[data-kind]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api("/camp/api/requests", { method: "POST", body: { kind: button.dataset.kind, note: $("#requestNote").value } });
        $("#requestResult").textContent = "Вожатый увидит заявку в очереди.";
        toast("Заявка отправлена");
      } catch (error) { toast(error.message, true); }
      finally { button.disabled = false; }
    });
  });
}

async function renderRequests(panel) {
  const items = (await api("/camp/api/requests?limit=100")).items || [];
  const rows = items.map((item) => [
    `<strong>${esc(item.child_name || item.child_id)}</strong>`,
    esc(item.kind),
    badge(item.status, item.status === "open" ? "warn" : item.status === "closed" ? "ok" : ""),
    esc(item.note || ""),
    fmtTime(item.created_at_ms),
    `<div class="actions">${item.status === "open" ? `<button class="button small" data-claim="${item.id}">Взять</button>` : ""}${item.status !== "closed" ? `<button class="button small" data-close="${item.id}">Закрыть</button>` : ""}</div>`,
  ]);
  panel.innerHTML = `${header("Очередь заявок", "Дети не пишут staff напрямую.")}${table(["Ребёнок", "Тип", "Статус", "Заметка", "Создана", ""], rows)}`;
  panel.querySelectorAll("[data-claim]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/requests/${button.dataset.claim}/claim`, { method: "POST" }); toast("Заявка взята"); await openPanel("requests"); }
    catch (error) { toast(error.message, true); }
  }));
  panel.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", async () => {
    const note = window.prompt("Комментарий к закрытию", "Проверено");
    if (note === null) return;
    try { await api(`/camp/api/requests/${button.dataset.close}/close`, { method: "POST", body: { note } }); toast("Заявка закрыта"); await openPanel("requests"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function renderRollcall(panel) {
  const events = (await api("/camp/api/attendance/events?limit=20")).items || [];
  const units = state.me.units || [];
  panel.innerHTML = `${header("Перекличка", "Отметки и all-present guard.")}
    <section class="card" style="margin-bottom:12px">
      <form id="attendanceForm" class="row">
        <label class="grow">Отряд<select id="attendanceUnit">${options(units, "id", "name")}</select></label>
        <label>Тип<select id="attendanceKind"><option value="roll_call">Перекличка</option><option value="lights_out">Отбой</option></select></label>
        <button class="button primary" type="submit">Начать</button>
      </form>
    </section>
    <div class="stack">${events.map((event) => {
      const items = event.items || [];
      const rows = items.map((item) => [
        `<strong>${esc(item.display_name)}</strong>`,
        esc(item.badge_code || ""),
        item.mark_status ? badge(item.mark_status, item.mark_status === "present" ? "ok" : item.mark_status === "absent" ? "danger" : "warn") : badge("не отмечен", "warn"),
        `<div class="actions">
          ${event.status === "open" ? ["present", "absent", "sick", "medic", "parent"].map((status) => `<button class="button small" data-event="${event.id}" data-person="${item.id}" data-status="${status}">${status}</button>`).join("") : ""}
        </div>`,
      ]);
      return `<details ${event.status === "open" ? "open" : ""}><summary>${esc(event.unit_name)} · ${esc(event.kind)} · ${badge(event.status, event.status === "open" ? "warn" : "ok")} · ${event.summary.marked}/${event.summary.total} ${event.overdue ? badge("overdue", "danger") : ""}</summary>
        <div class="actions" style="margin-bottom:8px">
          ${event.status === "open" ? `<button class="button small" data-all="${event.id}">Все присутствуют</button><button class="button small danger" data-close-attendance="${event.id}">Закрыть</button>` : ""}
        </div>
        ${table(["Ребёнок", "Бейдж", "Статус", "Отметить"], rows)}
      </details>`;
    }).join("") || `<div class="notice">Перекличек пока нет.</div>`}</div>`;
  $("#attendanceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/camp/api/attendance/events", { method: "POST", body: { unit_id: Number($("#attendanceUnit").value), kind: $("#attendanceKind").value } });
      toast("Перекличка создана"); await openPanel("rollcall");
    } catch (error) { toast(error.message, true); }
  });
  panel.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", async () => {
    try {
      await api(`/camp/api/attendance/events/${button.dataset.event}/marks`, { method: "POST", body: { person_id: Number(button.dataset.person), status: button.dataset.status } });
      await openPanel("rollcall");
    } catch (error) { toast(error.message, true); }
  }));
  panel.querySelectorAll("[data-all]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/attendance/events/${button.dataset.all}/all-present`, { method: "POST" }); toast("Отмечены присутствующими"); await openPanel("rollcall"); }
    catch (error) { toast(error.message, true); }
  }));
  panel.querySelectorAll("[data-close-attendance]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/attendance/events/${button.dataset.closeAttendance}/close`, { method: "POST", body: { force: false } }); toast("Перекличка закрыта"); await openPanel("rollcall"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function renderScan(panel) {
  const zones = (await api("/camp/api/zones")).items || [];
  panel.innerHTML = `${header("Сканирование", "Ручной или kiosk-скан.")}
    <section class="card stack">
      <form id="scanForm" class="row">
        <label class="grow">Зона<select id="scanZone">${options(zones, "id", "name")}</select></label>
        <label class="grow">Бейдж<input id="scanBadge" placeholder="BADGE-..." required></label>
        <button class="button primary" type="submit">Отметить</button>
      </form>
      <div id="scanResult"></div>
    </section>`;
  $("#scanForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/camp/api/scans", { method: "POST", body: { zone_id: Number($("#scanZone").value), badge_code: $("#scanBadge").value } });
      const item = result.item;
      $("#scanResult").innerHTML = `<div class="notice">${esc(item.person.display_name)} → ${esc(item.zone.name)} · ${fmtTime(item.scan.scanned_at_ms)}</div>`;
      $("#scanBadge").value = "";
    } catch (error) { toast(error.message, true); }
  });
}

async function renderAlerts(panel) {
  const [alertsData, playbooksData] = await Promise.all([
    api("/camp/api/alerts?limit=50"), api("/camp/api/alert-playbooks"),
  ]);
  const alerts = alertsData.items || [];
  const playbooks = playbooksData.items || [];
  panel.innerHTML = `${header("Тревоги и учения", "Плейбуки, подтверждения, after-action.")}
    <section class="card" style="margin-bottom:12px">
      <form id="alertForm" class="row">
        <label class="grow">Плейбук<select id="alertKind">${options(playbooks, "kind", "title")}</select></label>
        <label style="align-self:center"><input id="alertDrill" type="checkbox" style="width:auto;margin-right:6px">Учение</label>
        <button class="button danger" type="submit">Запустить</button>
      </form>
    </section>
    <div class="stack">${alerts.map((alert) => `<details ${alert.status !== "closed" ? "open" : ""}><summary>${esc(alert.title)} · ${badge(alert.status, alert.status === "closed" ? "ok" : "danger")} ${alert.drill ? badge("drill") : ""}</summary>
      <p>${esc(alert.note || "")}</p>
      <ol>${(alert.steps || []).map((step) => `<li>${esc(step.step || step)}</li>`).join("")}</ol>
      <p class="muted">Подтвердили: ${alert.ack_count} · ${(alert.acks || []).map((ack) => esc(ack.display_name)).join(", ") || "никто"}</p>
      <div class="actions">
        ${alert.status !== "closed" ? `<button class="button small" data-ack="${alert.id}">Подтвердить</button>` : ""}
        ${alert.status !== "closed" ? `<button class="button small danger" data-close-alert="${alert.id}">Закрыть</button>` : ""}
      </div>
    </details>`).join("") || `<div class="notice">Тревог нет.</div>`}</div>`;
  $("#alertForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/camp/api/alerts", { method: "POST", body: { kind: $("#alertKind").value, drill: $("#alertDrill").checked } });
      toast("Тревога запущена"); await openPanel("alerts");
    } catch (error) { toast(error.message, true); }
  });
  panel.querySelectorAll("[data-ack]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/alerts/${button.dataset.ack}/ack`, { method: "POST", body: { step_index: 0 } }); toast("Подтверждено"); await openPanel("alerts"); }
    catch (error) { toast(error.message, true); }
  }));
  panel.querySelectorAll("[data-close-alert]").forEach((button) => button.addEventListener("click", async () => {
    const after = window.prompt("After-action заметка", "");
    if (after === null) return;
    try { await api(`/camp/api/alerts/${button.dataset.closeAlert}/close`, { method: "POST", body: { after_action: after } }); toast("Тревога закрыта"); await openPanel("alerts"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function renderZones(panel) {
  const [zonesData, monitorData] = await Promise.all([api("/camp/api/zones"), api("/camp/api/zones/monitor")]);
  const zones = zonesData.items || [];
  const monitor = Object.fromEntries((monitorData.items || []).map((item) => [String(item.id), item]));
  panel.innerHTML = `${header("Зоны и счётчики", "Сканы append-only.")}
    <section class="card" style="margin-bottom:12px">
      <form id="zoneForm" class="row">
        <label class="grow">Название<input id="zoneName" required maxlength="120"></label>
        <label>Тип<select id="zoneKind"><option value="checkpoint">checkpoint</option><option value="building">building</option><option value="gate">gate</option><option value="medical">medical</option><option value="other">other</option></select></label>
        <button class="button primary" type="submit">Создать</button>
      </form>
    </section>
    ${table(["Зона", "Тип", "Сканов", "Людей", "Последний"], zones.map((zone) => {
      const count = monitor[String(zone.id)] || {};
      return [esc(zone.name), esc(zone.kind), esc(count.scan_count ?? 0), esc(count.people_count ?? 0), fmtTime(count.last_scan_ms)];
    }))}`;
  $("#zoneForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/zones", { method: "POST", body: { name: $("#zoneName").value, kind: $("#zoneKind").value } }); toast("Зона создана"); await openPanel("zones"); }
    catch (error) { toast(error.message, true); }
  });
}

async function renderDuty(panel) {
  const [shiftsData, handoversData, staff] = await Promise.all([
    api("/camp/api/duty"), api("/camp/api/handovers?limit=50"), people(),
  ]);
  const shifts = shiftsData.items || [];
  const handovers = handoversData.items || [];
  const canManageShifts = role() === "director";
  const staffWithUser = staff.filter((item) => item.user_id && ["counselor", "director", "security", "medic", "it", "kitchen"].includes(item.role));
  panel.innerHTML = `${header("Смена и передача", "Кто на смене и что открыто.")}
    <div class="split">
      <section class="card"><h3>Смены</h3>
        ${canManageShifts ? `<form id="shiftForm" class="stack">
          <label>Сотрудник<select id="shiftUser">${options(staffWithUser, "user_id", "display_name")}</select></label>
          <div class="row"><label class="grow">Начало<input id="shiftStart" type="datetime-local" value="${localInput()}"></label><label class="grow">Конец<input id="shiftEnd" type="datetime-local" value="${localInput(Date.now() + 8 * 3600_000)}"></label></div>
          <button class="button primary" type="submit">Добавить смену</button>
        </form>` : `<div class="notice">Состав смены ведёт директор.</div>`}
        ${table(["Сотрудник", "Роль", "Начало", "Конец"], shifts.map((shift) => [esc(shift.display_name || shift.user_id), esc(shift.role), fmtTime(shift.starts_at_ms), fmtTime(shift.ends_at_ms)]))}
      </section>
      <section class="card"><h3>Handover</h3>
        <form id="handoverForm" class="stack">
          <label>Кому<select id="handoverUser">${options(staffWithUser, "user_id", "display_name")}</select></label>
          <label>Заметки<textarea id="handoverNotes" required maxlength="4000"></textarea></label>
          <label>Открытые пункты (по одному в строке)<textarea id="handoverItems"></textarea></label>
          <button class="button primary" type="submit">Передать</button>
        </form>
        <div class="list">${handovers.map((item) => `<div class="list-item"><strong>${esc(item.from_display_name || "—")} → ${esc(item.to_display_name || "—")}</strong><p>${esc(item.notes)}</p><p class="muted">${item.acknowledged ? badge("принято", "ok") : badge("ожидает", "warn")} ${fmtTime(item.created_at_ms)}</p>${!item.acknowledged ? `<button class="button small" data-handover="${item.id}">Принять</button>` : ""}</div>`).join("") || `<div class="notice">Handover нет.</div>`}</div>
      </section>
    </div>`;
  if ($("#shiftForm")) $("#shiftForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/camp/api/duty", { method: "POST", body: { user_id: Number($("#shiftUser").value), role: "counselor", starts_at_ms: fromInput($("#shiftStart").value), ends_at_ms: fromInput($("#shiftEnd").value) } });
      toast("Смена добавлена"); await openPanel("duty");
    } catch (error) { toast(error.message, true); }
  });
  $("#handoverForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const openItems = $("#handoverItems").value.split("\n").map((item) => item.trim()).filter(Boolean);
    try {
      await api("/camp/api/handovers", { method: "POST", body: { to_user_id: Number($("#handoverUser").value), notes: $("#handoverNotes").value, open_items: openItems } });
      toast("Handover создан"); await openPanel("duty");
    } catch (error) { toast(error.message, true); }
  });
  panel.querySelectorAll("[data-handover]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/handovers/${button.dataset.handover}/ack`, { method: "POST" }); toast("Принято"); await openPanel("duty"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function renderGate(panel) {
  const [children, authData, logData, zonesData] = await Promise.all([
    people("child"), api("/camp/api/pickup"), api("/camp/api/movements?limit=50"), api("/camp/api/zones"),
  ]);
  const auths = authData.items || [];
  const log = logData.items || [];
  const zones = zonesData.items || [];
  panel.innerHTML = `${header("Ворота и выдача", "QR, ограничения, override reason.")}
    <div class="split">
      <section class="card"><h3>Авторизация</h3>
        <form id="pickupForm" class="stack">
          <label>Ребёнок<select id="pickupChild">${options(children, "id", "display_name")}</select></label>
          <label>Взрослый<input id="pickupAdult" required maxlength="200"></label>
          <label>Кем является<input id="pickupRelation" maxlength="120" placeholder="мама / папа / няня"></label>
          <label>Ограничения<textarea id="pickupRestrictions" maxlength="1000" placeholder="Например: только мама, документ обязателен"></textarea></label>
          <button class="button primary" type="submit">Создать QR</button>
        </form>
        <div id="pickupToken" class="notice" style="margin-top:10px"></div>
        <div class="list" style="margin-top:10px">${auths.slice(0, 8).map((auth) => `<div class="list-item"><strong>${esc(auth.display_name)}</strong> · ${esc(auth.adult_name)}<p class="muted">${esc(auth.relationship || "")} ${esc(auth.restrictions || "")}</p><code>${esc(auth.qr_code)}</code></div>`).join("")}</div>
      </section>
      <section class="card"><h3>Движение</h3>
        <form id="movementForm" class="stack">
          <label>Ребёнок<select id="movementChild">${options(children, "id", "display_name")}</select></label>
          <label>Направление<select id="movementDirection"><option value="out">out</option><option value="in">in</option></select></label>
          <label>QR (если out)<input id="movementQr" maxlength="256"></label>
          <label>Override reason<input id="movementOverride" maxlength="1000"></label>
          <label>Зона<select id="movementZone"><option value="">—</option>${options(zones, "id", "name")}</select></label>
          <button class="button primary" type="submit">Записать</button>
        </form>
      </section>
    </div>
    <section class="card" style="margin-top:12px"><h3>Журнал ворот</h3>${table(["Ребёнок", "Направление", "Время", "Взрослый", "Зона"], log.map((item) => [esc(item.display_name), badge(item.direction, item.direction === "out" ? "warn" : "ok"), fmtTime(item.at_ms), esc(item.adult_name || "—"), esc(item.zone_name || "—")]))}</section>`;
  $("#pickupForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/camp/api/pickup", { method: "POST", body: { person_id: Number($("#pickupChild").value), adult_name: $("#pickupAdult").value, relationship: $("#pickupRelation").value, restrictions: $("#pickupRestrictions").value } });
      $("#pickupToken").textContent = `QR: ${result.item.qr_code}`;
      toast("Авторизация создана");
    } catch (error) { toast(error.message, true); }
  });
  $("#movementForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const zoneId = $("#movementZone").value ? Number($("#movementZone").value) : null;
      await api("/camp/api/movements", { method: "POST", body: { person_id: Number($("#movementChild").value), direction: $("#movementDirection").value, qr_code: $("#movementQr").value || null, override_reason: $("#movementOverride").value || null, zone_id: zoneId } });
      toast("Движение записано"); await openPanel("gate");
    } catch (error) { toast(error.message, true); }
  });
}

async function renderDietary(panel) {
  const [itemsData, children] = await Promise.all([api("/camp/api/dietary"), people("child")]);
  const items = itemsData.items || [];
  const token = state.token;
  panel.innerHTML = `${header("Питание", "Список ограничений и печать.")}
    <div class="actions" style="margin-bottom:12px"><a class="button small" href="/camp/api/dietary/print?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Печать</a></div>
    ${["kitchen", "medic", "counselor", "director"].includes(role()) ? `<section class="card" style="margin-bottom:12px"><form id="dietaryForm" class="row"><label class="grow">Ребёнок<select id="dietaryChild">${options(children, "id", "display_name")}</select></label><label class="grow">Ограничение<input id="dietaryRestriction" required maxlength="200"></label><label class="grow">Заметка<input id="dietaryNote" maxlength="1000"></label><button class="button primary" type="submit">Добавить</button></form></section>` : ""}
    ${table(["Отряд", "Ребёнок", "Комната", "Ограничение", "Заметка"], items.map((item) => [esc(item.unit_name || "—"), esc(item.display_name), esc(item.room || "—"), esc(item.restriction), esc(item.note || "")]))}`;
  if ($("#dietaryForm")) $("#dietaryForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/dietary", { method: "POST", body: { person_id: Number($("#dietaryChild").value), restriction: $("#dietaryRestriction").value, note: $("#dietaryNote").value } }); toast("Добавлено"); await openPanel("dietary"); }
    catch (error) { toast(error.message, true); }
  });
}

async function renderDigest(panel) {
  const [digestsData, children] = await Promise.all([api("/camp/api/digests"), people("child")]);
  const digests = digestsData.items || [];
  const canWrite = ["counselor", "director"].includes(role());
  panel.innerHTML = `${header("Дневник", "Родитель видит только своих детей.")}
    ${canWrite ? `<section class="card" style="margin-bottom:12px"><form id="digestForm" class="stack"><label>Ребёнок<select id="digestChild">${options(children, "id", "display_name")}</select></label><label>Дата<input id="digestDate" type="date" value="${new Date().toISOString().slice(0, 10)}"></label><label>Текст<textarea id="digestText" required maxlength="4000"></textarea></label><button class="button primary" type="submit">Сохранить</button></form></section>` : ""}
    ${table(["Дата", "Ребёнок", "Текст", "Отправлено"], digests.map((item) => [esc(item.date), esc(item.display_name), esc(item.text), item.sent_at_ms ? badge("sent", "ok") : badge("не отправлено", "warn")]))}`;
  if ($("#digestForm")) $("#digestForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/digests", { method: "POST", body: { person_id: Number($("#digestChild").value), date: $("#digestDate").value, text: $("#digestText").value } }); toast("Дневник сохранён"); await openPanel("digest"); }
    catch (error) { toast(error.message, true); }
  });
}

async function renderReport(panel) {
  const data = await api("/camp/api/report");
  const report = data.item;
  const token = state.token;
  panel.innerHTML = `${header("Отчёт смены", "JSON, CSV и печатный HTML.")}
    <div class="actions" style="margin-bottom:12px">
      <a class="button small" href="/camp/api/report.csv?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Скачать CSV</a>
      <a class="button small" href="/camp/api/report.html?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Открыть HTML</a>
    </div>
    ${metrics([["Дети", report.people.children], ["Staff", report.people.staff], ["Сканы", report.scans.total], ["Alert-события", report.alerts.total], ["Dietary", report.dietary.records], ["Digest", report.digests.total]])}
    <section class="card" style="margin-top:12px"><h3>JSON</h3><pre style="white-space:pre-wrap;color:var(--muted)">${esc(JSON.stringify(report, null, 2))}</pre></section>`;
}

async function renderConsents(panel) {
  if (role() === "parent") {
    const children = await people("child");
    panel.innerHTML = `${header("Согласия", "Только для своих детей.")}
      <section class="card"><form id="consentForm" class="stack">
        <label>Ребёнок<select id="consentChild">${options(children, "id", "display_name")}</select></label>
        <label>Тип<select id="consentKind"><option value="internal_chat">internal_chat</option><option value="parent_digest">parent_digest</option><option value="promo">promo</option><option value="none">none</option></select></label>
        <label><input id="consentGranted" type="checkbox" style="width:auto;margin-right:6px">Разрешено</label>
        <button class="button primary" type="submit">Сохранить</button>
      </form></section>`;
    $("#consentForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try { await api("/camp/api/consents", { method: "POST", body: { person_id: Number($("#consentChild").value), kind: $("#consentKind").value, granted: $("#consentGranted").checked } }); toast("Согласие сохранено"); }
      catch (error) { toast(error.message, true); }
    });
    return;
  }
  const [matrixData, children] = await Promise.all([api("/camp/api/consents/matrix"), people("child")]);
  const matrix = matrixData.items || [];
  panel.innerHTML = `${header("Матрица согласий", "Кто разрешил фото и дневник.")}
    <section class="card" style="margin-bottom:12px"><form id="consentForm" class="row">
      <label class="grow">Ребёнок<select id="consentChild">${options(children, "id", "display_name")}</select></label>
      <label>Тип<select id="consentKind"><option value="internal_chat">internal_chat</option><option value="parent_digest">parent_digest</option><option value="promo">promo</option><option value="none">none</option></select></label>
      <label style="align-self:center"><input id="consentGranted" type="checkbox" style="width:auto;margin-right:6px">Разрешено</label>
      <button class="button primary" type="submit">Сохранить</button>
    </form></section>
    ${table(["Ребёнок", "Отряд", "internal", "digest", "promo"], matrix.map((child) => [esc(child.display_name), esc(child.unit_name || "—"), child.consents.internal_chat ? badge("да", "ok") : badge("нет"), child.consents.parent_digest ? badge("да", "ok") : badge("нет"), child.consents.promo ? badge("да", "ok") : badge("нет")]))}`;
  $("#consentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/consents", { method: "POST", body: { person_id: Number($("#consentChild").value), kind: $("#consentKind").value, granted: $("#consentGranted").checked } }); toast("Согласие сохранено"); await openPanel("consents"); }
    catch (error) { toast(error.message, true); }
  });
}

async function renderKiosk(panel) {
  const [kiosksData, zonesData] = await Promise.all([api("/camp/api/kiosks"), api("/camp/api/zones")]);
  const kiosks = kiosksData.items || [];
  const zones = zonesData.items || [];
  panel.innerHTML = `${header("Kiosk", "Токен показывается один раз; на сервере только hash.")}
    <section class="card" style="margin-bottom:12px"><form id="kioskForm" class="row">
      <label class="grow">Device ID<input id="kioskDevice" required maxlength="128" placeholder="gate-pi-1"></label>
      <label class="grow">Зона<select id="kioskZone">${options(zones, "id", "name")}</select></label>
      <button class="button primary" type="submit">Выдать токен</button>
    </form><div id="kioskToken" class="notice" style="margin-top:10px"></div></section>
    ${table(["Device", "Зона", "Статус", "Последний scan", ""], kiosks.map((item) => [esc(item.device_id), esc(item.zone_name || item.zone_id), item.active ? (item.stale ? badge("stale", "warn") : badge("active", "ok")) : badge("revoked", "danger"), fmtTime(item.last_seen_ms), item.active ? `<button class="button small danger" data-revoke="${item.id}">Отозвать</button>` : ""]))}`;
  $("#kioskForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/camp/api/kiosks", { method: "POST", body: { device_id: $("#kioskDevice").value, zone_id: Number($("#kioskZone").value), scopes: "scan" } });
      toast("Kiosk создан"); await openPanel("kiosk");
      $("#kioskToken").textContent = `Токен (сохраните сейчас): ${result.token}`;
    } catch (error) { toast(error.message, true); }
  });
  panel.querySelectorAll("[data-revoke]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/kiosks/${button.dataset.revoke}/revoke`, { method: "POST" }); toast("Kiosk отозван"); await openPanel("kiosk"); }
    catch (error) { toast(error.message, true); }
  }));
}

async function renderStatus(panel) {
  const response = await fetch("/camp/status", { headers: { Accept: "application/json" } });
  const status = await response.json();
  panel.innerHTML = `${header("Статус", "DB read/write, quick_check, диск, часы.")}
    ${metrics([["Состояние", status.status], ["DB", status.checks.db_read ? "read ok" : "fail"], ["Запись", status.checks.db_write ? "ok" : "fail"], ["Диск, MB", status.checks.disk_free_mb], ["Clock skew, ms", status.checks.clock_skew_ms], ["Kiosk stale", status.kiosks.stale]])}
    <section class="card" style="margin-top:12px"><h3>Backup hint</h3><p class="muted">${esc(status.backup_hint)}</p><p class="muted">Quick check: ${esc(status.checks.db_quick_check)} · Sessions active: ${esc(status.sessions.active)}</p></section>`;
}

async function renderChildren(panel) {
  const children = await people("child");
  panel.innerHTML = `${header("Мои дети")}${table(["Ребёнок", "Отряд", "Комната", "Бейдж"], children.map((child) => [esc(child.display_name), esc(child.unit_name || "—"), esc(child.room || "—"), esc(child.badge_code || "—")]))}`;
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#loginError").textContent = "";
  try {
    await connect($("#tokenInput").value);
  } catch (error) {
    showLogin(error.message);
  }
});

$("#logoutBtn").addEventListener("click", logout);

(async function boot() {
  const params = new URLSearchParams(window.location.search);
  const queryToken = params.get("token");
  if (queryToken) {
    state.token = queryToken;
    history.replaceState({}, "", "/camp/");
  }
  if (!state.token) {
    showLogin();
    return;
  }
  try {
    await connect(state.token);
  } catch (error) {
    showLogin(error.message);
  }
})();
