const $ = (id) => document.getElementById(id);

const ICON_CLIP =
  '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M8.5 12.5l6-6a2.6 2.6 0 0 1 3.7 3.7l-7.3 7.3a4.3 4.3 0 0 1-6.1-6.1l7-7"/></svg>';

const ui = {
  navUser: $("navUser"),
  refreshBtn: $("refreshBtn"),
  createTicketForm: $("createTicketForm"),
  ticketTitleInput: $("ticketTitle"),
  ticketBodyInput: $("ticketBody"),
  createTicketBtn: $("createTicketBtn"),
  createAttachBtn: $("createAttachBtn"),
  createFiles: $("createFiles"),
  ticketList: $("ticketList"),
  ticketCount: $("ticketCount"),
  tokenCard: $("tokenCard"),
  sessionTokenInput: $("sessionToken"),
  loadTicketsBtn: $("loadTicketsBtn"),
  backBtn: $("backBtn"),
  activeTicketTitle: $("activeTicketTitle"),
  activeTicketMeta: $("activeTicketMeta"),
  threadStatusPill: $("threadStatusPill"),
  messagesViewport: $("messagesViewport"),
  replyForm: $("replyForm"),
  replyBodyInput: $("replyBody"),
  sendReplyBtn: $("sendReplyBtn"),
  replyAttachBtn: $("replyAttachBtn"),
  replyFiles: $("replyFiles"),
  replyHint: $("replyHint"),
  statusSelect: $("statusSelect"),
  updateStatusBtn: $("updateStatusBtn"),
  filePicker: $("filePicker"),
  ticketTemplate: $("ticketTemplate"),
  messageTemplate: $("messageTemplate"),
};

const STATUS = {
  open: { ru: "Открыто", cls: "pill-open" },
  in_progress: { ru: "В работе", cls: "pill-in_progress" },
  resolved: { ru: "Решено", cls: "pill-resolved" },
  closed: { ru: "Закрыто", cls: "pill-closed" },
};

const state = {
  sessionToken: localStorage.getItem("lc_session_token") || "",
  me: null,
  tickets: [],
  activeTicketId: null,
  pending: { create: [], reply: [] },
  pickTarget: "reply",
};

try {
  state.me = JSON.parse(localStorage.getItem("lc_user") || "null");
} catch (error) {
  state.me = null;
}

if (ui.navUser) {
  if (state.me && state.me.login) {
    ui.navUser.textContent = "@" + state.me.login;
    ui.navUser.hidden = false;
  } else {
    ui.navUser.hidden = true;
  }
}
const activeLink = document.querySelector(".nav-links a.active");
if (activeLink && activeLink.scrollIntoView) {
  try {
    activeLink.scrollIntoView({ inline: "center", block: "nearest" });
  } catch (error) {
    /* ignore */
  }
}
if (ui.sessionTokenInput) {
  ui.sessionTokenInput.value = state.sessionToken;
}

function statusInfo(status) {
  return STATUS[status] || { ru: status || "—", cls: "" };
}

function setHint(message, mode = "") {
  if (!ui.replyHint) return;
  ui.replyHint.textContent = message;
  ui.replyHint.classList.remove("error", "ok");
  if (mode) ui.replyHint.classList.add(mode);
}

function setThreadEnabled(enabled) {
  ui.replyBodyInput.disabled = !enabled;
  ui.sendReplyBtn.disabled = !enabled;
  ui.replyAttachBtn.disabled = !enabled;
  ui.statusSelect.disabled = !enabled;
  ui.updateStatusBtn.disabled = !enabled;
  if (!enabled) {
    ui.threadStatusPill.hidden = true;
    setHint("Выберите обращение из списка");
  }
}

function isMobile() {
  return window.matchMedia("(max-width: 860px)").matches;
}

function formatDate(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function downloadUrl(attachment) {
  const base = attachment.download_url || "/media/api/attachments/" + attachment.attachment_id + "/download";
  return base + (base.indexOf("?") >= 0 ? "&" : "?") + "session_token=" + encodeURIComponent(state.sessionToken);
}

function emptyMessages(text) {
  ui.messagesViewport.innerHTML = "";
  const node = document.createElement("div");
  node.className = "empty-note";
  node.textContent = text;
  ui.messagesViewport.appendChild(node);
}

function renderMessages(messages, ticket) {
  ui.messagesViewport.innerHTML = "";
  if (!messages.length) {
    emptyMessages("Диалог пока пуст — напишите первое сообщение");
    return;
  }

  const myId = state.me && state.me.id != null ? state.me.id : null;
  const ownerId = ticket ? ticket.user_id : null;

  for (const message of messages) {
    const fragment = ui.messageTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".msg");
    const mine =
      (myId !== null && message.author_user_id === myId) ||
      (ownerId !== null && message.author_user_id === ownerId);
    if (mine) article.classList.add("own");
    fragment.querySelector(".author").textContent = mine ? "Вы" : "Поддержка";
    fragment.querySelector(".time").textContent = formatDate(message.created_at_ms);
    fragment.querySelector(".body").textContent = message.body_text || "";

    const atts = fragment.querySelector(".msg-atts");
    for (const attachment of message.attachments || []) {
      const url = downloadUrl(attachment);
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      if (attachment.media_kind === "image") {
        const img = document.createElement("img");
        img.src = url;
        img.alt = attachment.filename || "вложение";
        img.loading = "lazy";
        link.appendChild(img);
      } else {
        link.innerHTML = ICON_CLIP;
        link.appendChild(document.createTextNode(attachment.filename || "файл"));
      }
      atts.appendChild(link);
    }

    ui.messagesViewport.appendChild(fragment);
  }

  if (isMobile()) {
    const last = ui.messagesViewport.lastElementChild;
    if (last && last.scrollIntoView) last.scrollIntoView({ block: "end" });
  } else {
    ui.messagesViewport.scrollTop = ui.messagesViewport.scrollHeight;
  }
}

function renderTickets() {
  ui.ticketList.innerHTML = "";
  if (ui.ticketCount) {
    ui.ticketCount.hidden = !state.tickets.length;
    ui.ticketCount.textContent = state.tickets.length ? String(state.tickets.length) : "";
  }
  if (!state.tickets.length) {
    const li = document.createElement("li");
    li.className = "empty-note";
    li.textContent = "Обращений пока нет";
    ui.ticketList.appendChild(li);
    return;
  }

  for (const ticket of state.tickets) {
    const fragment = ui.ticketTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".ticket-btn");
    button.dataset.ticketId = String(ticket.ticket_id);
    button.classList.toggle("active", state.activeTicketId === ticket.ticket_id);
    fragment.querySelector(".ticket-title").textContent = ticket.title;
    const info = statusInfo(ticket.status);
    const pill = fragment.querySelector(".status-pill");
    pill.textContent = info.ru;
    if (info.cls) pill.classList.add(info.cls);
    fragment.querySelector(".ticket-time").textContent = formatDate(
      ticket.last_message_at_ms || ticket.updated_at_ms || ticket.created_at_ms
    );
    button.addEventListener("click", () => {
      openTicket(ticket.ticket_id).catch((error) => {
        setHint(`Ошибка открытия: ${error.message}`, "error");
      });
    });
    ui.ticketList.appendChild(fragment);
  }
}

function renderChips(kind) {
  const box = kind === "create" ? ui.createFiles : ui.replyFiles;
  const list = state.pending[kind];
  if (!box) return;
  box.innerHTML = "";
  box.hidden = !list.length;
  list.forEach((item, index) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const name = document.createElement("span");
    name.textContent = item.filename || "файл " + item.attachment_id;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = "Убрать";
    remove.addEventListener("click", () => {
      list.splice(index, 1);
      renderChips(kind);
    });
    chip.append(name, remove);
    box.appendChild(chip);
  });
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && payload.detail;
    const message = (detail && (detail.message || detail.code)) || (payload && payload.message) || `HTTP ${response.status}`;
    if (response.status === 401) {
      throw new Error("сессия истекла — войдите в приложение заново или вставьте новый token");
    }
    throw new Error(message);
  }
  return payload;
}

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(
    "/media/api/attachments?session_token=" + encodeURIComponent(state.sessionToken),
    { method: "POST", body: form }
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload && payload.detail;
    throw new Error((detail && (detail.message || detail.code)) || `Не удалось загрузить файл (${response.status})`);
  }
  return payload.attachment || {};
}

async function loadTickets() {
  if (!state.sessionToken) {
    if (ui.tokenCard) ui.tokenCard.open = true;
    setHint("Укажите session token", "error");
    return;
  }

  setHint("Загружаем обращения…");
  const payload = await fetchJSON(
    `/support/api/tickets?session_token=${encodeURIComponent(state.sessionToken)}&limit=100&offset=0`
  );
  state.tickets = payload.items || [];
  if (!state.tickets.some((item) => item.ticket_id === state.activeTicketId)) {
    state.activeTicketId = null;
  }
  renderTickets();

  if (state.activeTicketId === null && state.tickets.length) {
    await openTicket(state.tickets[0].ticket_id, { silent: true });
    setHint("Обращения загружены", "ok");
    return;
  }
  if (!state.tickets.length) {
    setThreadEnabled(false);
    ui.activeTicketTitle.textContent = "Выберите обращение";
    ui.activeTicketMeta.textContent = "Здесь появится переписка";
    emptyMessages("Обращений пока нет — создайте первое");
    setHint("Обращений пока нет", "ok");
    return;
  }
  await loadMessages(state.activeTicketId);
  setHint("Список обновлён", "ok");
}

async function loadMessages(ticketId, ticket) {
  const payload = await fetchJSON(
    `/support/api/tickets/${ticketId}/messages?session_token=${encodeURIComponent(state.sessionToken)}&limit=500&offset=0`
  );
  renderMessages(payload.items || [], ticket || state.tickets.find((item) => item.ticket_id === ticketId));
}

async function openTicket(ticketId, options = {}) {
  const ticket = state.tickets.find((item) => item.ticket_id === ticketId);
  if (!ticket) return;

  state.activeTicketId = ticketId;
  renderTickets();

  ui.activeTicketTitle.textContent = ticket.title;
  ui.activeTicketMeta.textContent = `№${ticket.ticket_id} · обновлено ${formatDate(
    ticket.last_message_at_ms || ticket.updated_at_ms
  )}`;
  const info = statusInfo(ticket.status);
  ui.threadStatusPill.hidden = false;
  ui.threadStatusPill.className = "pill " + (info.cls || "");
  ui.threadStatusPill.textContent = info.ru;
  ui.statusSelect.value = ticket.status;
  setThreadEnabled(true);
  if (isMobile()) document.body.classList.add("thread-open");

  await loadMessages(ticketId, ticket);
  if (!options.silent) setHint("Диалог открыт", "ok");
}

async function createTicket() {
  if (!state.sessionToken) {
    setHint("Сначала укажите session token", "error");
    return;
  }
  const title = ui.ticketTitleInput.value.trim();
  const bodyText = ui.ticketBodyInput.value.trim();
  if (!title || !bodyText) {
    setHint("Нужно заполнить тему и текст", "error");
    return;
  }

  ui.createTicketBtn.disabled = true;
  setHint("Отправляем обращение…");
  try {
    const payload = await fetchJSON("/support/api/tickets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_token: state.sessionToken,
        title,
        body_text: bodyText,
        attachment_ids: state.pending.create.map((item) => item.attachment_id),
      }),
    });

    ui.ticketTitleInput.value = "";
    ui.ticketBodyInput.value = "";
    state.pending.create = [];
    renderChips("create");
    setHint("Обращение создано", "ok");

    await loadTickets();
    if (payload && payload.ticket && payload.ticket.ticket_id) {
      await openTicket(payload.ticket.ticket_id, { silent: true });
    }
  } finally {
    ui.createTicketBtn.disabled = false;
  }
}

async function sendReply() {
  const ticketId = state.activeTicketId;
  const bodyText = ui.replyBodyInput.value.trim();
  const attachmentIds = state.pending.reply.map((item) => item.attachment_id);
  if (!ticketId) return;
  if (!bodyText && !attachmentIds.length) {
    setHint("Введите текст или приложите файл", "error");
    return;
  }

  ui.sendReplyBtn.disabled = true;
  setHint("Отправляем…");
  try {
    await fetchJSON(`/support/api/tickets/${ticketId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_token: state.sessionToken,
        body_text: bodyText,
        attachment_ids: attachmentIds,
      }),
    });

    ui.replyBodyInput.value = "";
    state.pending.reply = [];
    renderChips("reply");
    setHint("Сообщение отправлено", "ok");
    await loadTickets();
    await loadMessages(ticketId);
  } finally {
    ui.sendReplyBtn.disabled = false;
  }
}

async function updateStatus() {
  const ticketId = state.activeTicketId;
  if (!ticketId) return;
  ui.updateStatusBtn.disabled = true;
  try {
    await fetchJSON(`/support/api/tickets/${ticketId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_token: state.sessionToken,
        status: ui.statusSelect.value,
      }),
    });
    await loadTickets();
    await openTicket(ticketId, { silent: true });
    setHint("Статус обновлён", "ok");
  } finally {
    ui.updateStatusBtn.disabled = false;
  }
}

function pickFiles(target) {
  state.pickTarget = target;
  if (!state.sessionToken) {
    setHint("Сначала укажите session token", "error");
    return;
  }
  ui.filePicker.click();
}

ui.replyAttachBtn.addEventListener("click", () => pickFiles("reply"));
ui.createAttachBtn.addEventListener("click", () => pickFiles("create"));

ui.filePicker.addEventListener("change", async () => {
  const kind = state.pickTarget;
  const files = Array.from(ui.filePicker.files || []);
  ui.filePicker.value = "";
  if (!files.length) return;

  for (const file of files) {
    try {
      setHint(`Загружаем ${file.name}…`);
      const attachment = await uploadFile(file);
      if (attachment.attachment_id) {
        state.pending[kind].push({
          attachment_id: attachment.attachment_id,
          filename: attachment.filename || attachment.original_filename || file.name,
        });
        renderChips(kind);
      }
    } catch (error) {
      setHint(`Ошибка вложения: ${error.message}`, "error");
      return;
    }
  }
  setHint("Файл прикреплён", "ok");
});

ui.backBtn.addEventListener("click", () => {
  document.body.classList.remove("thread-open");
});

ui.refreshBtn.addEventListener("click", async () => {
  ui.refreshBtn.disabled = true;
  try {
    await loadTickets();
  } catch (error) {
    setHint(`Ошибка загрузки: ${error.message}`, "error");
  } finally {
    ui.refreshBtn.disabled = false;
  }
});

ui.loadTicketsBtn.addEventListener("click", async () => {
  const value = ui.sessionTokenInput.value.trim();
  if (value) {
    state.sessionToken = value;
    try {
      localStorage.setItem("lc_session_token", value);
    } catch (error) {
      /* ignore storage errors */
    }
  }
  try {
    await loadTickets();
  } catch (error) {
    setHint(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.createTicketForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await createTicket();
  } catch (error) {
    setHint(`Ошибка создания: ${error.message}`, "error");
  }
});

ui.replyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await sendReply();
  } catch (error) {
    setHint(`Ошибка отправки: ${error.message}`, "error");
  }
});

ui.updateStatusBtn.addEventListener("click", async () => {
  try {
    await updateStatus();
  } catch (error) {
    setHint(`Ошибка статуса: ${error.message}`, "error");
  }
});

setThreadEnabled(false);
emptyMessages("Загружаем обращения…");
if (state.sessionToken) {
  loadTickets().catch((error) => {
    if (ui.tokenCard) ui.tokenCard.open = true;
    setHint(`Ошибка загрузки: ${error.message}`, "error");
    emptyMessages("Не удалось загрузить обращения");
  });
} else {
  if (ui.tokenCard) ui.tokenCard.open = true;
  setHint("Укажите session token, чтобы загрузить обращения", "error");
  emptyMessages("Нет активной сессии");
}
