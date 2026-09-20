const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadTicketsBtn: document.getElementById("loadTicketsBtn"),
  createTicketForm: document.getElementById("createTicketForm"),
  ticketTitleInput: document.getElementById("ticketTitle"),
  ticketBodyInput: document.getElementById("ticketBody"),
  ticketList: document.getElementById("ticketList"),
  activeTicketTitle: document.getElementById("activeTicketTitle"),
  activeTicketMeta: document.getElementById("activeTicketMeta"),
  messagesViewport: document.getElementById("messagesViewport"),
  replyForm: document.getElementById("replyForm"),
  replyBodyInput: document.getElementById("replyBody"),
  sendReplyBtn: document.getElementById("sendReplyBtn"),
  replyHint: document.getElementById("replyHint"),
  statusSelect: document.getElementById("statusSelect"),
  updateStatusBtn: document.getElementById("updateStatusBtn"),
  ticketTemplate: document.getElementById("ticketTemplate"),
  messageTemplate: document.getElementById("messageTemplate"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  tickets: [],
  activeTicketId: null,
};

// Auto-hide manual token input if token is in localStorage
(function init() {
  if (state.sessionToken && ui.sessionTokenInput) {
    ui.sessionTokenInput.value = state.sessionToken;
    ui.sessionTokenInput.parentElement && (ui.sessionTokenInput.parentElement.style.display = 'none');
  }
})();

function setHint(message, mode = "") {
  ui.replyHint.textContent = message;
  ui.replyHint.classList.remove("error", "ok");
  if (mode) {
    ui.replyHint.classList.add(mode);
  }
}

function setThreadEnabled(enabled) {
  ui.replyBodyInput.disabled = !enabled;
  ui.sendReplyBtn.disabled = !enabled;
  ui.statusSelect.disabled = !enabled;
  ui.updateStatusBtn.disabled = !enabled;
  if (!enabled) {
    setHint("Загрузите обращения и выберите диалог");
  }
}

function formatDate(ts) {
  if (!ts) {
    return "";
  }
  return new Date(ts).toLocaleString();
}

function emptyMessages(text) {
  ui.messagesViewport.innerHTML = "";
  const node = document.createElement("div");
  node.className = "empty-note";
  node.textContent = text;
  ui.messagesViewport.appendChild(node);
}

function renderMessages(messages) {
  ui.messagesViewport.innerHTML = "";
  if (!messages.length) {
    emptyMessages("Диалог пока пуст");
    return;
  }

  for (const message of messages) {
    const fragment = ui.messageTemplate.content.cloneNode(true);
    fragment.querySelector(".author").textContent = `user:${message.author_user_id}`;
    fragment.querySelector(".time").textContent = formatDate(message.created_at_ms);
    fragment.querySelector(".body").textContent = message.body_text;
    ui.messagesViewport.appendChild(fragment);
  }
  ui.messagesViewport.scrollTop = ui.messagesViewport.scrollHeight;
}

function renderTickets() {
  ui.ticketList.innerHTML = "";
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
    fragment.querySelector(".ticket-meta").textContent = `${ticket.status} | ${formatDate(
      ticket.updated_at_ms
    )}`;
    button.addEventListener("click", () => {
      openTicket(ticket.ticket_id).catch((error) => {
        setHint(`Ошибка открытия: ${error.message}`, "error");
      });
    });
    ui.ticketList.appendChild(fragment);
  }
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail?.message || payload?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function loadTickets() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setHint("Укажите session token", "error");
    return;
  }

  const payload = await fetchJSON(
    `/support/api/tickets?session_token=${encodeURIComponent(state.sessionToken)}&limit=100&offset=0`
  );
  state.tickets = payload.items || [];
  if (!state.tickets.some((item) => item.ticket_id === state.activeTicketId)) {
    state.activeTicketId = null;
  }
  renderTickets();

  if (state.activeTicketId === null && state.tickets.length) {
    await openTicket(state.tickets[0].ticket_id);
  }
  if (!state.tickets.length) {
    setThreadEnabled(false);
    ui.activeTicketTitle.textContent = "Выберите обращение";
    ui.activeTicketMeta.textContent = "Здесь появится переписка";
    emptyMessages("Нет данных");
  }
}

async function loadMessages(ticketId) {
  const payload = await fetchJSON(
    `/support/api/tickets/${ticketId}/messages?session_token=${encodeURIComponent(
      state.sessionToken
    )}&limit=500&offset=0`
  );
  renderMessages(payload.items || []);
}

async function openTicket(ticketId) {
  const ticket = state.tickets.find((item) => item.ticket_id === ticketId);
  if (!ticket) {
    return;
  }

  state.activeTicketId = ticketId;
  renderTickets();

  ui.activeTicketTitle.textContent = ticket.title;
  ui.activeTicketMeta.textContent = `status: ${ticket.status} | owner:${ticket.user_id}`;
  ui.statusSelect.value = ticket.status;
  setThreadEnabled(true);

  await loadMessages(ticketId);
  setHint("Диалог открыт", "ok");
}

async function createTicket() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
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

  const payload = await fetchJSON("/support/api/tickets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      title,
      body_text: bodyText,
    }),
  });

  ui.ticketTitleInput.value = "";
  ui.ticketBodyInput.value = "";
  setHint("Обращение создано", "ok");

  await loadTickets();
  if (payload.ticket?.ticket_id) {
    await openTicket(payload.ticket.ticket_id);
  }
}

async function sendReply() {
  const ticketId = state.activeTicketId;
  const bodyText = ui.replyBodyInput.value.trim();
  if (!ticketId || !bodyText) {
    return;
  }

  await fetchJSON(`/support/api/tickets/${ticketId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      body_text: bodyText,
    }),
  });

  ui.replyBodyInput.value = "";
  setHint("Сообщение отправлено", "ok");
  await loadTickets();
  await loadMessages(ticketId);
}

async function updateStatus() {
  const ticketId = state.activeTicketId;
  if (!ticketId) {
    return;
  }

  await fetchJSON(`/support/api/tickets/${ticketId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      status: ui.statusSelect.value,
    }),
  });

  await loadTickets();
  await openTicket(ticketId);
  setHint("Статус обновлен", "ok");
}

ui.loadTicketsBtn.addEventListener("click", async () => {
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
emptyMessages("Загрузите обращения");
