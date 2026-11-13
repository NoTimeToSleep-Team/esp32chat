const state = {
  token: localStorage.getItem("lc_session_token") || "",
  me: null,
  panel: null,
  verified: null,
};

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[ch]));

const LABELS = {
  role: {
    child: "Ребёнок", counselor: "Вожатый", director: "Директор",
    security: "Охрана", medic: "Медик", parent: "Родитель",
    kitchen: "Кухня", it: "Техник",
  },
  unit_kind: { squad: "Отряд", staff: "Персонал", other: "Другое" },
  attendance_status: {
    present: "На месте", absent: "Нет", sick: "Заболел",
    medic: "У медика", parent: "У родителя", left: "Ушёл",
  },
  attendance_event_status: { open: "Идёт", closed: "Закрыта" },
  request_kind: {
    call_counselor: "Нужен вожатый", help: "Нужна помощь",
    parent_question: "Вопрос родителям",
  },
  request_status: { open: "Новая", claimed: "В работе", closed: "Закрыта" },
  alert_status: { open: "Открыта", acknowledged: "Принята", closed: "Закрыта" },
  direction: { out: "Выезд", in: "Возврат" },
  consent: {
    internal_chat: "Фото внутри лагеря", parent_digest: "Фото для родителей",
    promo: "Публикация", none: "Запрещено",
  },
  zone_kind: {
    checkpoint: "Контрольная точка", building: "Корпус",
    gate: "КПП", medical: "Медпункт", other: "Другое",
  },
  kiosk_status: { active: "Активен", stale: "Не на связи", revoked: "Отозван" },
  session_status: {
    planned: "Запланирована", active: "Идёт", closed: "Закрыта", archived: "Архив",
  },
  mode: { offline: "Без интернета", nat: "С интернетом" },
  security: { open: "Открытая", "WPA2-PSK": "Закрытая" },
};

const ERROR_TEXT = {
  attendance_incomplete: "Отметьте всех детей или закройте перекличку с причиной.",
  request_forbidden: "Эту заявку может закрыть только тот, кто её взял.",
  request_closed: "Заявка уже закрыта.",
  request_already_claimed: "Эту заявку уже взял другой вожатый.",
  kiosk_revoked: "Терминал отозван. Выдайте новый код.",
  pickup_not_found: "Код выдачи не найден.",
  person_not_found: "Ребёнок не найден.",
  session_required: "Сначала создайте смену.",
  role_forbidden: "У вас нет доступа к этому действию.",
  guardian_forbidden: "Это чужой ребёнок.",
  attendance_closed: "Перекличка уже закрыта.",
};

function tr(group, value) {
  return LABELS[group]?.[value] ?? (!value ? "—" : String(value));
}

function roleName(value) {
  return tr("role", value);
}

function tone(group, value) {
  if (["present", "closed", "active", "acknowledged"].includes(value)) return "ok";
  if (["absent", "left", "revoked"].includes(value)) return "danger";
  if (["open", "claimed", "sick", "stale", "planned"].includes(value)) return "warn";
  return "";
}

function stateBadge(group, value) {
  return badge(tr(group, value), tone(group, value));
}

function deviceId() {
  let value = localStorage.getItem("camp_device_id");
  if (!value) {
    value = `camp-web-${(crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)}`;
    localStorage.setItem("camp_device_id", value);
  }
  return value;
}

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
  toast.timer = window.setTimeout(() => node.classList.add("hidden"), 5000);
}

function humanError(error) {
  if (error?.code && ERROR_TEXT[error.code]) return ERROR_TEXT[error.code];
  const message = String(error?.message || "");
  if (message.includes("Mark every child")) return ERROR_TEXT.attendance_incomplete;
  if (message.includes("Only the claiming counselor")) return ERROR_TEXT.request_forbidden;
  if (message.includes("already claimed")) return ERROR_TEXT.request_already_claimed;
  return message || "Не получилось. Попробуйте ещё раз.";
}

async function api(path, options = {}) {
  if (!state.token) throw new Error("Нужно войти заново");
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
    const error = new Error(detail.message || detail.code || `Ошибка ${response.status}`);
    error.code = detail.code;
    throw error;
  }
  return data;
}

function badge(text, mode = "") {
  return `<span class="badge ${mode}">${esc(text)}</span>`;
}

function table(headers, rows, empty = "Пока пусто") {
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

function actorId() {
  return Number(state.me?.actor?.user_id || 0);
}

function navItems() {
  const r = role();
  if (r === "child") {
    return [["day", "Сегодня"], ["new-request", "Позвать вожатого"], ["my-requests", "Мои заявки"], ["digest", "Дневник"]];
  }
  if (r === "parent") {
    return [["children", "Дети"], ["digest", "Дневник"], ["consents", "Согласия"]];
  }
  if (r === "counselor") {
    return [["rollcall", "Перекличка"], ["requests", "Заявки"], ["duty", "Передача"], ["digest", "Дневник"], ["scan", "Отметки"]];
  }
  if (r === "director") {
    return [["overview", "Сегодня"], ["rollcall", "Перекличка"], ["alerts", "Тревоги"], ["gate", "Ворота"], ["dietary", "Питание"], ["digest", "Дневник"], ["report", "Отчёт"], ["settings", "Настройки"]];
  }
  if (r === "security") {
    return [["gate", "Ворота"], ["scan", "Отметки"], ["alerts", "Тревоги"], ["zones", "Зоны"]];
  }
  if (r === "medic") {
    return [["alerts", "Тревоги"], ["dietary", "Питание"], ["scan", "Отметки"]];
  }
  if (r === "kitchen") {
    return [["dietary", "Питание"]];
  }
  return [["network", "Сеть"], ["status", "Состояние"]];
}

function renderChrome() {
  const actor = state.me.actor;
  $("#roleChip").textContent = roleName(actor.role);
  $("#roleChip").classList.remove("hidden");
  $("#logoutBtn").classList.remove("hidden");
  const current = state.me.current_session;
  $("#sessionLine").textContent = current
    ? `${current.name} · ${tr("session_status", current.status)} · ${fmtDate(current.starts_at_ms)} — ${fmtDate(current.ends_at_ms)}`
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
  state.me = await api("/camp/api/me");
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
  state.verified = null;
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
      day: renderDay,
      rollcall: renderRollcall,
      requests: renderRequests,
      "my-requests": renderRequests,
      "new-request": renderNewRequest,
      alerts: renderAlerts,
      duty: renderDuty,
      gate: renderGate,
      dietary: renderDietary,
      digest: renderDigest,
      report: renderReport,
      consents: renderConsents,
      settings: renderSettings,
      zones: renderZones,
      scan: renderScan,
      kiosk: renderKiosk,
      network: renderNetwork,
      status: renderStatus,
      children: renderChildren,
    };
    await (renderers[id] || renderOverview)(panel);
  } catch (error) {
    panel.innerHTML = `<section class="card"><h2>Не получилось</h2><p class="error">${esc(humanError(error))}</p><button class="button" type="button" data-open="${esc(id)}">Повторить</button></section>`;
  }
  panel.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => openPanel(button.dataset.open));
  });
}

function header(title, subtitle = "") {
  return `<div class="panel-head"><div><h2>${esc(title)}</h2>${subtitle ? `<p class="muted">${esc(subtitle)}</p>` : ""}</div></div>`;
}

async function people(roleNameFilter = "") {
  const query = roleNameFilter ? `?role=${encodeURIComponent(roleNameFilter)}` : "";
  const data = await api(`/camp/api/people${query}`);
  return data.items || [];
}

async function renderOverview(panel) {
  const report = (await api("/camp/api/report")).item;
  const token = state.token;
  panel.innerHTML = `${header("Сегодня", report.session.name)}
    <section class="card">
      <div class="hero-actions">
        ${["director", "counselor"].includes(role()) ? `<button class="button primary big" type="button" data-open="rollcall">Начать перекличку</button>` : ""}
        <a class="button" href="/camp/api/report.csv?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Скачать таблицу</a>
        <a class="button" href="/camp/api/report.html?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Печать</a>
      </div>
    </section>
    ${metrics([
      ["Дети", report.people.children],
      ["Сотрудники", report.people.staff],
      ["Новые заявки", report.requests.open || 0],
      ["Открытые тревоги", report.alerts.open || 0],
      ["Отметки", report.scans.total],
      ["Сейчас вне лагеря", report.movements.currently_out],
    ])}
    <section class="card" style="margin-top:12px">
      <h3>Отряды</h3>
      ${table(["Отряд", "Тип", "Детей"], report.units.map((unit) => [esc(unit.name), esc(tr("unit_kind", unit.kind)), esc(unit.child_count)]))}
    </section>`;
}

async function renderDay(panel) {
  const requests = (await api("/camp/api/requests?limit=20")).items || [];
  const digests = (await api("/camp/api/digests")).items || [];
  panel.innerHTML = `${header("Сегодня", state.me.actor.display_name)}
    <div class="split">
      <section class="card">
        <h3>Мои заявки</h3>
        ${requests.length ? requests.slice(0, 5).map((item) => `<div class="list-item"><strong>${esc(tr("request_kind", item.kind))}</strong> ${stateBadge("request_status", item.status)}<p class="muted">${fmtTime(item.created_at_ms)}</p></div>`).join("") : `<p class="muted">Пока нет заявок.</p>`}
        <button class="button primary" type="button" data-open="new-request">Позвать вожатого</button>
      </section>
      <section class="card">
        <h3>Дневник</h3>
        ${digests.length ? digests.slice(0, 3).map((item) => `<div class="list-item"><strong>${esc(item.date)}</strong><p>${esc(item.text)}</p></div>`).join("") : `<p class="muted">Записей пока нет.</p>`}
      </section>
    </div>`;
}

async function renderNewRequest(panel) {
  panel.innerHTML = `${header("Позвать вожатого", "Сообщение увидит дежурный вожатый.")}
    <section class="card stack">
      <div class="actions">
        <button class="button primary" data-kind="call_counselor">Нужен вожатый</button>
        <button class="button" data-kind="help">Нужна помощь</button>
      </div>
      <label>Что случилось?<textarea id="requestNote" maxlength="2000" placeholder="Коротко опишите ситуацию"></textarea></label>
      <p id="requestResult" class="muted"></p>
    </section>`;
  panel.querySelectorAll("[data-kind]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api("/camp/api/requests", { method: "POST", body: { kind: button.dataset.kind, note: $("#requestNote").value } });
        toast("Заявка отправлена");
        await openPanel("my-requests");
      } catch (error) { toast(humanError(error), true); }
      finally { button.disabled = false; }
    });
  });
}

async function renderRequests(panel) {
  const items = (await api("/camp/api/requests?limit=100")).items || [];
  const child = role() === "child";
  const rows = items.map((item) => {
    const canClose = !child && item.status === "claimed" && (role() === "director" || Number(item.claimed_by) === actorId());
    const actions = child ? "" : `<div class="actions">
      ${item.status === "open" ? `<button class="button small" data-claim="${item.id}">Взять</button>` : ""}
      ${canClose ? `<button class="button small" data-close="${item.id}">Закрыть</button>` : ""}
    </div>`;
    return [
      child ? esc(tr("request_kind", item.kind)) : `<strong>${esc(item.child_name || item.child_id)}</strong>`,
      child ? "" : esc(item.unit_name || "—"),
      stateBadge("request_status", item.status),
      esc(item.note || ""),
      fmtTime(item.created_at_ms),
      actions,
    ];
  });
  const headers = child ? ["Тема", "", "Статус", "Комментарий", "Создана", ""] : ["Ребёнок", "Отряд", "Статус", "Комментарий", "Создана", ""];
  panel.innerHTML = `${header(child ? "Мои заявки" : "Заявки", child ? "Здесь видно, что происходит с вашей заявкой." : "Сначала возьмите заявку, потом закрывайте.")}
    ${table(headers, rows, child ? "Заявок пока нет." : "Очередь пуста.")}`;
  panel.querySelectorAll("[data-claim]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/requests/${button.dataset.claim}/claim`, { method: "POST" }); toast("Заявка взята"); await openPanel("requests"); }
    catch (error) { toast(humanError(error), true); }
  }));
  panel.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", async () => {
    const note = window.prompt("Что сделали?", "Проверено");
    if (note === null) return;
    try { await api(`/camp/api/requests/${button.dataset.close}/close`, { method: "POST", body: { note } }); toast("Заявка закрыта"); await openPanel("requests"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function renderRollcall(panel) {
  const events = (await api("/camp/api/attendance/events?limit=20")).items || [];
  const units = state.me.units || [];
  const ownUnit = Number(state.me.actor.unit_id || 0);
  const visibleEvents = role() === "counselor" && ownUnit
    ? events.filter((event) => Number(event.unit_id) === ownUnit)
    : events;
  panel.innerHTML = `${header("Перекличка", "Отметьте детей. Если всё хорошо — одна кнопка «Все на месте».")}
    <section class="card" style="margin-bottom:12px">
      <form id="attendanceForm" class="row">
        <label class="grow">Отряд
          <select id="attendanceUnit" required>
            <option value="">Выберите отряд</option>
            ${options(units, "id", "name")}
          </select>
        </label>
        <label>Что отмечаем
          <select id="attendanceKind"><option value="roll_call">Перекличка</option><option value="lights_out">Отбой</option></select>
        </label>
        <button class="button primary" type="submit">Начать</button>
      </form>
    </section>
    <div class="stack">${visibleEvents.map((event) => {
      const items = event.items || [];
      const rows = items.map((item) => [
        `<strong>${esc(item.display_name)}</strong>`,
        esc(item.badge_code || "—"),
        `<select data-event="${event.id}" data-person="${item.id}" class="mark-select">
          <option value="">Не отмечен</option>
          ${["present", "absent", "sick", "medic", "parent", "left"].map((value) => `<option value="${value}" ${item.mark_status === value ? "selected" : ""}>${esc(tr("attendance_status", value))}</option>`).join("")}
        </select>`,
      ]);
      return `<details ${event.status === "open" ? "open" : ""}><summary>${esc(event.unit_name)} · ${esc(event.kind === "lights_out" ? "Отбой" : "Перекличка")} · ${stateBadge("attendance_event_status", event.status)} · ${event.summary.marked}/${event.summary.total}${event.overdue ? ` · ${badge("Просрочено", "danger")}` : ""}</summary>
        <div class="actions" style="margin:8px 0">
          ${event.status === "open" ? `<button class="button primary" data-all="${event.id}">Все на месте</button><button class="button" data-close-attendance="${event.id}">Закрыть</button><button class="button" data-force-close="${event.id}">Закрыть с причиной</button>` : ""}
        </div>
        ${table(["Ребёнок", "Бейдж", "Отметка"], rows)}
      </details>`;
    }).join("") || `<div class="notice">Перекличка ещё не начата. Выберите отряд и нажмите «Начать».</div>`}</div>`;
  $("#attendanceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const unitId = Number($("#attendanceUnit").value);
    if (!unitId) { toast("Выберите отряд", true); return; }
    try {
      await api("/camp/api/attendance/events", { method: "POST", body: { unit_id: unitId, kind: $("#attendanceKind").value } });
      toast("Перекличка начата");
      await openPanel("rollcall");
    } catch (error) { toast(humanError(error), true); }
  });
  panel.querySelectorAll(".mark-select").forEach((select) => select.addEventListener("change", async () => {
    if (!select.value) return;
    try {
      await api(`/camp/api/attendance/events/${select.dataset.event}/marks`, { method: "POST", body: { person_id: Number(select.dataset.person), status: select.value } });
      await openPanel("rollcall");
    } catch (error) { toast(humanError(error), true); }
  }));
  panel.querySelectorAll("[data-all]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/attendance/events/${button.dataset.all}/all-present`, { method: "POST" }); toast("Отмечены все"); await openPanel("rollcall"); }
    catch (error) { toast(humanError(error), true); }
  }));
  panel.querySelectorAll("[data-close-attendance]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/attendance/events/${button.dataset.closeAttendance}/close`, { method: "POST", body: { force: false } }); toast("Перекличка закрыта"); await openPanel("rollcall"); }
    catch (error) {
      toast(humanError(error), true);
      if (error.code === "attendance_incomplete") {
        const reason = window.prompt("Кто не отмечен и почему закрываем?", "");
        if (reason) {
          try { await api(`/camp/api/attendance/events/${button.dataset.closeAttendance}/close`, { method: "POST", body: { force: true, note: reason } }); toast("Закрыто с причиной"); await openPanel("rollcall"); }
          catch (inner) { toast(humanError(inner), true); }
        }
      }
    }
  }));
  panel.querySelectorAll("[data-force-close]").forEach((button) => button.addEventListener("click", async () => {
    const reason = window.prompt("Причина закрытия без всех отметок", "");
    if (!reason) return;
    try { await api(`/camp/api/attendance/events/${button.dataset.forceClose}/close`, { method: "POST", body: { force: true, note: reason } }); toast("Закрыто с причиной"); await openPanel("rollcall"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function startAlert(kind, drill) {
  if (!kind) return;
  if (!window.confirm(`Запустить «${kind}»?`)) return;
  if (!drill && !window.confirm("Это реальная тревога, а не учение. Запустить?")) return;
  await api("/camp/api/alerts", { method: "POST", body: { kind, drill } });
  toast(drill ? "Учение запущено" : "Тревога запущена");
  await openPanel("alerts");
}

async function renderAlerts(panel) {
  const [alertsData, playbooksData] = await Promise.all([
    api("/camp/api/alerts?limit=50"), api("/camp/api/alert-playbooks"),
  ]);
  const alerts = alertsData.items || [];
  const playbooks = playbooksData.items || [];
  const canStart = ["director", "security"].includes(role());
  const medicalOnly = role() === "medic";
  panel.innerHTML = `${header("Тревоги", "Сначала подтвердите, что видите тревогу. Закрывает директор или охрана.")}
    ${canStart ? `<section class="card" style="margin-bottom:12px"><form id="alertForm" class="row">
      <label class="grow">Что случилось<select id="alertKind">${options(playbooks, "kind", "title")}</select></label>
      <label class="check"><input id="alertDrill" type="checkbox"> Учение</label>
      <button class="button danger" type="submit">Запустить</button>
    </form></section>` : ""}
    ${medicalOnly ? `<section class="card" style="margin-bottom:12px"><button class="button danger" id="medicalAlert">Медицинская тревога</button></section>` : ""}
    <div class="stack">${alerts.map((alert) => {
      const mine = new Set((alert.acks || []).filter((ack) => Number(ack.user_id) === actorId()).map((ack) => Number(ack.step_index)));
      let nextStep = (alert.steps || []).findIndex((_, index) => !mine.has(index));
      if (nextStep < 0) nextStep = 0;
      const canClose = ["director", "security"].includes(role()) || alert.created_by === actorId();
      return `<details ${alert.status !== "closed" ? "open" : ""}><summary>${esc(alert.title)} · ${stateBadge("alert_status", alert.status)} ${alert.drill ? badge("Учение") : ""}</summary>
        <p class="muted">Запустил: ${esc(alert.created_by_login || "—")} · ${fmtTime(alert.created_at_ms)}</p>
        <ol>${(alert.steps || []).map((step) => `<li>${esc(step.step || step)}</li>`).join("")}</ol>
        <p class="muted">Подтвердили: ${alert.ack_count || 0} · ${(alert.acks || []).map((ack) => esc(ack.display_name)).join(", ") || "никто"}</p>
        <div class="actions">
          ${alert.status !== "closed" ? `<button class="button primary" data-ack="${alert.id}" data-step="${nextStep}">Подтвердить шаг ${nextStep + 1}</button>` : ""}
          ${alert.status !== "closed" && canClose ? `<button class="button danger" data-close-alert="${alert.id}">Закрыть тревогу</button>` : ""}
        </div>
      </details>`;
    }).join("") || `<div class="notice">Тревог нет.</div>`}</div>`;
  if ($("#alertForm")) $("#alertForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await startAlert($("#alertKind").value, $("#alertDrill").checked); }
    catch (error) { toast(humanError(error), true); }
  });
  if ($("#medicalAlert")) $("#medicalAlert").addEventListener("click", async () => {
    try { await startAlert("medical", false); } catch (error) { toast(humanError(error), true); }
  });
  panel.querySelectorAll("[data-ack]").forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/camp/api/alerts/${button.dataset.ack}/ack`, { method: "POST", body: { step_index: Number(button.dataset.step) } }); toast("Шаг подтверждён"); await openPanel("alerts"); }
    catch (error) { toast(humanError(error), true); }
  }));
  panel.querySelectorAll("[data-close-alert]").forEach((button) => button.addEventListener("click", async () => {
    const after = window.prompt("Что сделали и что учесть на будущее?", "");
    if (after === null) return;
    try { await api(`/camp/api/alerts/${button.dataset.closeAlert}/close`, { method: "POST", body: { after_action: after } }); toast("Тревога закрыта"); await openPanel("alerts"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function renderDuty(panel) {
  const [shiftsData, handoversData, staff] = await Promise.all([
    api("/camp/api/duty"), api("/camp/api/handovers?limit=50"), people(),
  ]);
  const shifts = shiftsData.items || [];
  const handovers = handoversData.items || [];
  const canManageShifts = role() === "director";
  const staffWithUser = staff.filter((item) => item.user_id && ["counselor", "director", "security", "medic", "it", "kitchen"].includes(item.role));
  const staffById = Object.fromEntries(staffWithUser.map((item) => [String(item.user_id), item]));
  const now = Date.now();
  const current = shifts.filter((shift) => Number(shift.starts_at_ms) <= now && Number(shift.ends_at_ms) >= now);
  panel.innerHTML = `${header("Передача смены", "Кто сейчас на смене и что нужно передать.")}
    <div class="split">
      <section class="card"><h3>Сейчас на смене</h3>
        ${current.length ? current.map((shift) => `<div class="list-item"><strong>${esc(shift.display_name || shift.user_id)}</strong> · ${esc(roleName(shift.role))}<p class="muted">до ${fmtTime(shift.ends_at_ms)}</p></div>`).join("") : `<p class="muted">Сейчас никто не отмечен.</p>`}
        ${canManageShifts ? `<form id="shiftForm" class="stack" style="margin-top:12px">
          <label>Сотрудник<select id="shiftUser">${options(staffWithUser, "user_id", "display_name")}</select></label>
          <div class="row"><label class="grow">Начало<input id="shiftStart" type="datetime-local" value="${localInput()}"></label><label class="grow">Конец<input id="shiftEnd" type="datetime-local" value="${localInput(Date.now() + 8 * 3600_000)}"></label></div>
          <button class="button primary" type="submit">Добавить смену</button>
        </form>` : `<div class="notice" style="margin-top:12px">Состав смены ведёт директор.</div>`}
        ${table(["Сотрудник", "Роль", "Начало", "Конец"], shifts.map((shift) => [esc(shift.display_name || shift.user_id), esc(roleName(shift.role)), fmtTime(shift.starts_at_ms), fmtTime(shift.ends_at_ms)]))}
      </section>
      <section class="card"><h3>Передать смену</h3>
        <form id="handoverForm" class="stack">
          <label>Кому<select id="handoverUser">${options(staffWithUser, "user_id", "display_name")}</select></label>
          <label>Что важно знать<textarea id="handoverNotes" required maxlength="4000"></textarea></label>
          <label>Открытые вопросы, по одному в строке<textarea id="handoverItems"></textarea></label>
          <button class="button primary" type="submit">Передать</button>
        </form>
        <div class="list" style="margin-top:12px">${handovers.map((item) => `<div class="list-item"><strong>${esc(item.from_display_name || "—")} → ${esc(item.to_display_name || "—")}</strong><p>${esc(item.notes)}</p><p class="muted">${item.acknowledged ? badge("Принято", "ok") : badge("Ожидает", "warn")} · ${fmtTime(item.created_at_ms)}</p>${!item.acknowledged ? `<button class="button small" data-handover="${item.id}">Принять</button>` : ""}</div>`).join("") || `<div class="notice">Передач пока нет.</div>`}</div>
      </section>
    </div>`;
  if ($("#shiftForm")) $("#shiftForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const userId = Number($("#shiftUser").value);
    const person = staffById[String(userId)];
    try {
      await api("/camp/api/duty", { method: "POST", body: { user_id: userId, role: person?.role || "counselor", starts_at_ms: fromInput($("#shiftStart").value), ends_at_ms: fromInput($("#shiftEnd").value) } });
      toast("Смена добавлена"); await openPanel("duty");
    } catch (error) { toast(humanError(error), true); }
  });
  $("#handoverForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const openItems = $("#handoverItems").value.split("\n").map((item) => item.trim()).filter(Boolean);
    try {
      await api("/camp/api/handovers", { method: "POST", body: { to_user_id: Number($("#handoverUser").value), notes: $("#handoverNotes").value, open_items: openItems } });
      toast("Передача создана"); await openPanel("duty");
    } catch (error) { toast(humanError(error), true); }
  });
  panel.querySelectorAll("[data-handover]").forEach((button) => button.addEventListener("click", async () => {
    const item = handovers.find((row) => String(row.id) === button.dataset.handover);
    const openItems = item?.open_items || [];
    if (openItems.length && !window.confirm(`Открытые вопросы:\n- ${openItems.join("\n- ")}\n\nПринять смену?`)) return;
    try { await api(`/camp/api/handovers/${button.dataset.handover}/ack`, { method: "POST" }); toast("Смена принята"); await openPanel("duty"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function renderGate(panel) {
  state.verified = null;
  const [children, authData, logData, zonesData] = await Promise.all([
    people("child"), api("/camp/api/pickup"), api("/camp/api/movements?limit=50"), api("/camp/api/zones"),
  ]);
  const auths = authData.items || [];
  const log = logData.items || [];
  const zones = zonesData.items || [];
  panel.innerHTML = `${header("Ворота", "Проверьте код, посмотрите ограничения, только потом выпускайте.")}
    <div class="split">
      <section class="card"><h3>Проверить код</h3>
        <form id="verifyForm" class="row">
          <label class="grow">Код из пропуска<input id="verifyCode" required maxlength="256" placeholder="Вставьте код"></label>
          <button class="button primary" type="submit">Проверить</button>
        </form>
        <div id="verifyResult"></div>
        <h3 style="margin-top:16px">Выдать пропуск</h3>
        <form id="pickupForm" class="stack">
          <label>Ребёнок<select id="pickupChild">${options(children, "id", "display_name")}</select></label>
          <label>Взрослый<input id="pickupAdult" required maxlength="200"></label>
          <label>Кем является<input id="pickupRelation" maxlength="120" placeholder="мама, папа, няня"></label>
          <label>Ограничения<textarea id="pickupRestrictions" maxlength="1000" placeholder="Только этот взрослый; нужен документ"></textarea></label>
          <button class="button primary" type="submit">Создать пропуск</button>
        </form>
        <div id="pickupToken" class="notice" style="margin-top:10px"></div>
        <div class="list" style="margin-top:10px">${auths.slice(0, 8).map((auth) => `<div class="list-item"><strong>${esc(auth.display_name)}</strong> · ${esc(auth.adult_name)}<p class="muted">${esc(auth.relationship || "")} ${esc(auth.restrictions || "")}</p><code>${esc(auth.qr_code)}</code></div>`).join("")}</div>
      </section>
      <section class="card"><h3>Ручная запись</h3>
        <form id="movementForm" class="stack">
          <label>Ребёнок<select id="movementChild">${options(children, "id", "display_name")}</select></label>
          <label>Направление<select id="movementDirection"><option value="out">Выезд</option><option value="in">Возврат</option></select></label>
          <label>Зона<select id="movementZone"><option value="">—</option>${options(zones, "id", "name")}</select></label>
          <details><summary>Без кода / ограничение</summary><label>Причина<input id="movementOverride" maxlength="1000" placeholder="Почему выпускаем без кода"></label></details>
          <button class="button" type="submit">Записать вручную</button>
        </form>
        <h3 style="margin-top:16px">Журнал ворот</h3>
        ${table(["Ребёнок", "Куда", "Время", "Взрослый"], log.map((item) => [esc(item.display_name), stateBadge("direction", item.direction), fmtTime(item.at_ms), esc(item.adult_name || "—")]))}
      </section>
    </div>`;
  $("#verifyForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api(`/camp/api/pickup/verify?qr_code=${encodeURIComponent($("#verifyCode").value)}`);
      state.verified = result.item;
      $("#verifyResult").innerHTML = `<div class="notice" style="margin-top:10px"><strong>${esc(result.item.display_name)}</strong> · ${esc(result.item.unit_name || "—")}<br>Взрослый: ${esc(result.item.adult_name)}<br>Ограничения: ${esc(result.item.restrictions || "нет")}<div class="actions" style="margin-top:8px"><button class="button primary" id="releaseOut">Выпустить</button><button class="button" id="releaseIn">Вернуть</button></div></div>`;
      $("#releaseOut").addEventListener("click", () => recordVerifiedMovement("out"));
      $("#releaseIn").addEventListener("click", () => recordVerifiedMovement("in"));
    } catch (error) { toast(humanError(error), true); }
  });
  $("#pickupForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/camp/api/pickup", { method: "POST", body: { person_id: Number($("#pickupChild").value), adult_name: $("#pickupAdult").value, relationship: $("#pickupRelation").value, restrictions: $("#pickupRestrictions").value } });
      $("#pickupToken").textContent = `Код: ${result.item.qr_code}`;
      toast("Пропуск создан");
    } catch (error) { toast(humanError(error), true); }
  });
  $("#movementForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/camp/api/movements", { method: "POST", body: { person_id: Number($("#movementChild").value), direction: $("#movementDirection").value, zone_id: $("#movementZone").value ? Number($("#movementZone").value) : null, override_reason: $("#movementOverride").value || null } });
      toast("Запись добавлена"); await openPanel("gate");
    } catch (error) { toast(humanError(error), true); }
  });
  async function recordVerifiedMovement(direction) {
    if (!state.verified) return;
    try {
      await api("/camp/api/movements", { method: "POST", body: { person_id: Number(state.verified.person_id), direction, qr_code: state.verified.qr_code } });
      toast(direction === "out" ? "Ребёнок выпущен" : "Ребёнок возвращён");
      await openPanel("gate");
    } catch (error) { toast(humanError(error), true); }
  }
}

async function renderDietary(panel) {
  const [itemsData, children] = await Promise.all([api("/camp/api/dietary"), people("child")]);
  const items = itemsData.items || [];
  const token = state.token;
  panel.innerHTML = `${header("Питание", "Ограничения для кухни и медпункта.")}
    <div class="actions" style="margin-bottom:12px"><a class="button small" href="/camp/api/dietary/print?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Печать для кухни</a></div>
    ${["kitchen", "medic", "counselor", "director"].includes(role()) ? `<section class="card" style="margin-bottom:12px"><form id="dietaryForm" class="row"><label class="grow">Ребёнок<select id="dietaryChild">${options(children, "id", "display_name")}</select></label><label class="grow">Ограничение<input id="dietaryRestriction" required maxlength="200" placeholder="Без орехов"></label><label class="grow">Заметка<input id="dietaryNote" maxlength="1000"></label><button class="button primary" type="submit">Добавить</button></form></section>` : ""}
    ${table(["Отряд", "Ребёнок", "Комната", "Ограничение", "Заметка", ""], items.map((item) => [esc(item.unit_name || "—"), esc(item.display_name), esc(item.room || "—"), esc(item.restriction), esc(item.note || ""), `<button class="button small danger" data-dietary="${esc(item.person_id)}" data-restriction="${esc(item.restriction)}">Удалить</button>`]))}`;
  if ($("#dietaryForm")) $("#dietaryForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/dietary", { method: "POST", body: { person_id: Number($("#dietaryChild").value), restriction: $("#dietaryRestriction").value, note: $("#dietaryNote").value } }); toast("Ограничение добавлено"); await openPanel("dietary"); }
    catch (error) { toast(humanError(error), true); }
  });
  panel.querySelectorAll("[data-dietary]").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm("Удалить ограничение? Ребёнку оно больше не нужно?")) return;
    try { await api(`/camp/api/dietary?person_id=${button.dataset.dietary}&restriction=${encodeURIComponent(button.dataset.restriction)}`, { method: "DELETE" }); toast("Удалено"); await openPanel("dietary"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function renderDigest(panel) {
  const [digestsData, children] = await Promise.all([api("/camp/api/digests"), people("child")]);
  const all = digestsData.items || [];
  const digests = role() === "parent" ? all.filter((item) => item.sent_at_ms) : all;
  const canWrite = ["counselor", "director"].includes(role());
  panel.innerHTML = `${header("Дневник", role() === "parent" ? "Записи, которые лагерь отправил вам." : "Короткая запись о дне ребёнка.")}
    ${canWrite ? `<section class="card" style="margin-bottom:12px"><form id="digestForm" class="stack"><label>Ребёнок<select id="digestChild">${options(children, "id", "display_name")}</select></label><label>Дата<input id="digestDate" type="date" value="${new Date().toISOString().slice(0, 10)}"></label><label>Текст<textarea id="digestText" required maxlength="4000"></textarea></label><button class="button primary" type="submit">Сохранить</button></form></section>` : ""}
    ${table(["Дата", "Ребёнок", "Текст", "Отправлено", ""], digests.map((item) => [esc(item.date), esc(item.display_name), esc(item.text), item.sent_at_ms ? badge("Отправлено", "ok") : badge("Не отправлено", "warn"), canWrite && !item.sent_at_ms ? `<button class="button small" data-sent="${esc(item.person_id)}" data-date="${esc(item.date)}">Отметить отправленным</button>` : ""]))}`;
  if ($("#digestForm")) $("#digestForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/digests", { method: "POST", body: { person_id: Number($("#digestChild").value), date: $("#digestDate").value, text: $("#digestText").value } }); toast("Запись сохранена"); await openPanel("digest"); }
    catch (error) { toast(humanError(error), true); }
  });
  panel.querySelectorAll("[data-sent]").forEach((button) => button.addEventListener("click", async () => {
    try { await api("/camp/api/digests/sent", { method: "POST", body: { person_id: Number(button.dataset.sent), date: button.dataset.date } }); toast("Отмечено отправленным"); await openPanel("digest"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function renderReport(panel) {
  const report = (await api("/camp/api/report")).item;
  const token = state.token;
  panel.innerHTML = `${header("Отчёт смены", "Для печати и передачи директору.")}
    <div class="actions" style="margin-bottom:12px">
      <a class="button" href="/camp/api/report.csv?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Скачать таблицу</a>
      <a class="button" href="/camp/api/report.html?session_token=${encodeURIComponent(token)}" target="_blank" rel="noopener">Печать</a>
    </div>
    ${metrics([["Дети", report.people.children], ["Сотрудники", report.people.staff], ["Отметки", report.scans.total], ["Тревоги", report.alerts.total], ["Питание", report.dietary.records], ["Дневник", report.digests.total]])}
    <section class="card" style="margin-top:12px"><h3>Отряды</h3>${table(["Отряд", "Тип", "Детей"], report.units.map((unit) => [esc(unit.name), esc(tr("unit_kind", unit.kind)), esc(unit.child_count)]))}</section>`;
}

async function renderConsents(panel) {
  if (role() === "parent") {
    const children = await people("child");
    panel.innerHTML = `${header("Согласия", "Только для ваших детей.")}
      <section class="card"><form id="consentForm" class="stack">
        <label>Ребёнок<select id="consentChild">${options(children, "id", "display_name")}</select></label>
        <label>Что разрешаем<select id="consentKind">${Object.entries(LABELS.consent).map(([value, label]) => `<option value="${value}">${esc(label)}</option>`).join("")}</select></label>
        <label class="check"><input id="consentGranted" type="checkbox"> Разрешено</label>
        <button class="button primary" type="submit">Сохранить</button>
      </form><div id="consentStatus" class="muted" style="margin-top:10px"></div></section>`;
    const load = async () => {
      try {
        const data = await api(`/camp/api/consents?person_id=${encodeURIComponent($("#consentChild").value)}`);
        const consents = data.item.consents || {};
        $("#consentStatus").textContent = Object.entries(LABELS.consent).map(([kind, label]) => `${label}: ${consents[kind]?.granted ? "да" : "нет"}`).join(" · ");
      } catch (error) { $("#consentStatus").textContent = humanError(error); }
    };
    $("#consentChild").addEventListener("change", load);
    await load();
    $("#consentForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try { await api("/camp/api/consents", { method: "POST", body: { person_id: Number($("#consentChild").value), kind: $("#consentKind").value, granted: $("#consentGranted").checked } }); toast("Согласие сохранено"); await load(); }
      catch (error) { toast(humanError(error), true); }
    });
    return;
  }
  const [matrixData, children] = await Promise.all([api("/camp/api/consents/matrix"), people("child")]);
  const matrix = matrixData.items || [];
  panel.innerHTML = `${header("Согласия", "Кто разрешил фото и дневник.")}
    <section class="card" style="margin-bottom:12px"><form id="consentForm" class="row">
      <label class="grow">Ребёнок<select id="consentChild">${options(children, "id", "display_name")}</select></label>
      <label>Что разрешаем<select id="consentKind">${Object.entries(LABELS.consent).map(([value, label]) => `<option value="${value}">${esc(label)}</option>`).join("")}</select></label>
      <label class="check"><input id="consentGranted" type="checkbox"> Разрешено</label>
      <button class="button primary" type="submit">Сохранить</button>
    </form></section>
    ${table(["Ребёнок", "Отряд", "Внутри лагеря", "Родителям", "Публикация"], matrix.map((child) => [esc(child.display_name), esc(child.unit_name || "—"), child.consents.internal_chat ? badge("Да", "ok") : badge("Нет"), child.consents.parent_digest ? badge("Да", "ok") : badge("Нет"), child.consents.promo ? badge("Да", "ok") : badge("Нет")]))}`;
  $("#consentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/consents", { method: "POST", body: { person_id: Number($("#consentChild").value), kind: $("#consentKind").value, granted: $("#consentGranted").checked } }); toast("Согласие сохранено"); await openPanel("consents"); }
    catch (error) { toast(humanError(error), true); }
  });
}

async function renderSettings(panel) {
  panel.innerHTML = `${header("Настройки", "Здесь только то, что нужно директору и технику.")}
    <div class="grid settings-grid">
      <button class="card settings-card" type="button" data-open="zones"><strong>Зоны</strong><span>КПП, корпуса, медпункт</span></button>
      <button class="card settings-card" type="button" data-open="consents"><strong>Согласия</strong><span>Фото и дневник</span></button>
      <button class="card settings-card" type="button" data-open="kiosk"><strong>Терминалы</strong><span>Выдача и отзыв кодов</span></button>
      <button class="card settings-card" type="button" data-open="network"><strong>Сеть</strong><span>Wi-Fi и страница входа</span></button>
      <button class="card settings-card" type="button" data-open="status"><strong>Состояние</strong><span>База, диск, часы</span></button>
    </div>`;
}

async function renderZones(panel) {
  const [zonesData, monitorData] = await Promise.all([api("/camp/api/zones"), api("/camp/api/zones/monitor")]);
  const zones = zonesData.items || [];
  const monitor = Object.fromEntries((monitorData.items || []).map((item) => [String(item.id), item]));
  panel.innerHTML = `${header("Зоны", "Где ребёнка видели в последний раз.")}
    <section class="card" style="margin-bottom:12px"><form id="zoneForm" class="row">
      <label class="grow">Название<input id="zoneName" required maxlength="120" placeholder="КПП, столовая"></label>
      <label>Тип<select id="zoneKind">${Object.entries(LABELS.zone_kind).map(([value, label]) => `<option value="${value}">${esc(label)}</option>`).join("")}</select></label>
      <button class="button primary" type="submit">Добавить</button>
    </form></section>
    ${table(["Зона", "Тип", "Отметок", "Детей", "Последняя"], zones.map((zone) => {
      const count = monitor[String(zone.id)] || {};
      return [esc(zone.name), esc(tr("zone_kind", zone.kind)), esc(count.scan_count ?? 0), esc(count.people_count ?? 0), fmtTime(count.last_scan_ms)];
    }))}`;
  $("#zoneForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/camp/api/zones", { method: "POST", body: { name: $("#zoneName").value, kind: $("#zoneKind").value } }); toast("Зона добавлена"); await openPanel("zones"); }
    catch (error) { toast(humanError(error), true); }
  });
}

async function renderScan(panel) {
  const zones = (await api("/camp/api/zones")).items || [];
  panel.innerHTML = `${header("Отметки", "Отметьте ребёнка в зоне.")}
    <section class="card stack">
      <form id="scanForm" class="row">
        <label class="grow">Зона<select id="scanZone">${options(zones, "id", "name")}</select></label>
        <label class="grow">Бейдж<input id="scanBadge" placeholder="Номер бейджа" required></label>
        <button class="button primary" type="submit">Отметить</button>
      </form>
      <div id="scanResult"></div>
    </section>`;
  $("#scanForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/camp/api/scans", { method: "POST", body: { zone_id: Number($("#scanZone").value), badge_code: $("#scanBadge").value } });
      $("#scanResult").innerHTML = `<div class="notice">${esc(result.item.person.display_name)} → ${esc(result.item.zone.name)} · ${fmtTime(result.item.scan.scanned_at_ms)}</div>`;
      $("#scanBadge").value = "";
    } catch (error) { toast(humanError(error), true); }
  });
}

async function renderKiosk(panel) {
  const [kiosksData, zonesData] = await Promise.all([api("/camp/api/kiosks"), api("/camp/api/zones")]);
  const kiosks = kiosksData.items || [];
  const zones = zonesData.items || [];
  panel.innerHTML = `${header("Терминалы", "Код показывается один раз. Потерянный терминал сразу отзывайте.")}
    <section class="card" style="margin-bottom:12px"><form id="kioskForm" class="row">
      <label class="grow">Название<input id="kioskDevice" required maxlength="128" placeholder="КПП-1"></label>
      <label class="grow">Зона<select id="kioskZone">${options(zones, "id", "name")}</select></label>
      <button class="button primary" type="submit">Выдать код</button>
    </form><div id="kioskToken" class="notice" style="margin-top:10px"></div></section>
    ${table(["Терминал", "Зона", "Статус", "Последняя отметка", ""], kiosks.map((item) => [esc(item.device_id), esc(item.zone_name || item.zone_id), item.active ? (item.stale ? badge("Не на связи", "warn") : badge("Активен", "ok")) : badge("Отозван", "danger"), fmtTime(item.last_seen_ms), item.active ? `<button class="button small danger" data-revoke="${item.id}">Отозвать</button>` : ""]))}`;
  $("#kioskForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await api("/camp/api/kiosks", { method: "POST", body: { device_id: $("#kioskDevice").value, zone_id: Number($("#kioskZone").value), scopes: "scan" } });
      toast("Терминал создан"); await openPanel("kiosk");
      $("#kioskToken").textContent = `Код для терминала: ${result.token}`;
    } catch (error) { toast(humanError(error), true); }
  });
  panel.querySelectorAll("[data-revoke]").forEach((button) => button.addEventListener("click", async () => {
    if (!window.confirm("Отозвать терминал? Он больше не сможет отмечать детей.")) return;
    try { await api(`/camp/api/kiosks/${button.dataset.revoke}/revoke`, { method: "POST" }); toast("Терминал отозван"); await openPanel("kiosk"); }
    catch (error) { toast(humanError(error), true); }
  }));
}

async function renderNetwork(panel) {
  const status = await fetch("/camp/status", { headers: { Accept: "application/json" } }).then((response) => response.json());
  const net = status.network || {};
  panel.innerHTML = `${header("Сеть", "Wi-Fi для лагеря.")}
    ${metrics([["Сеть", net.ssid || "—"], ["Доступ", net.open === false ? "Закрытая" : "Открытая"], ["Страница входа", net.captive_portal === false ? "Выключена" : "Включена"], ["Интернет", net.internet ? "Есть" : "Нет"]])}
    <section class="card" style="margin-top:12px"><h3>Как подключиться</h3><p>Подключите телефон к Wi-Fi <strong>${esc(net.ssid || "лагерь")}</strong>. Должно открыться окно входа; если нет — откройте <code>${esc(net.captive_url || "http://192.168.4.1")}</code>.</p><p class="muted">Настройка точки доступа выполняется на Raspberry Pi администратором.</p></section>`;
}

async function renderStatus(panel) {
  const status = await fetch("/camp/status", { headers: { Accept: "application/json" } }).then((response) => response.json());
  panel.innerHTML = `${header("Состояние", "Проверка базы и диска.")}
    ${metrics([["Состояние", status.status === "ok" ? "В норме" : "Есть проблемы"], ["База", status.checks.db_read ? "Читается" : "Ошибка"], ["Запись", status.checks.db_write ? "Работает" : "Ошибка"], ["Диск, МБ", status.checks.disk_free_mb], ["Часы, мс", status.checks.clock_skew_ms], ["Терминалы", status.kiosks.stale]])}
    <section class="card" style="margin-top:12px"><h3>Резервная копия</h3><p class="muted">Сделайте копию базы перед сменой и храните её отдельно от планшета.</p><p class="muted">Проверка базы: ${esc(status.checks.db_quick_check)} · Смен: ${esc(status.sessions.active)}</p></section>`;
}

async function renderChildren(panel) {
  const children = await people("child");
  panel.innerHTML = `${header("Дети")}${table(["Ребёнок", "Отряд", "Комната", "Бейдж"], children.map((child) => [esc(child.display_name), esc(child.unit_name || "—"), esc(child.room || "—"), esc(child.badge_code || "—")]))}`;
}

$("#passwordForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#loginError").textContent = "";
  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        login: $("#loginName").value.trim(),
        password: $("#loginPassword").value,
        client_kind: "web",
        device_id: deviceId(),
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail || data;
      const error = new Error(detail.message || detail.code || `Ошибка ${response.status}`);
      error.code = detail.code;
      throw error;
    }
    const token = data.session?.token;
    if (!token) throw new Error("Сервер не вернул сессию");
    await connect(token);
  } catch (error) {
    showLogin(humanError(error));
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
    showLogin(humanError(error));
  }
})();
