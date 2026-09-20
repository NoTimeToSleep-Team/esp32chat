const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadAllBtn: document.getElementById("loadAllBtn"),
  statusNote: document.getElementById("statusNote"),
  applicationsList: document.getElementById("applicationsList"),
  ticketsList: document.getElementById("ticketsList"),
  activeTicketTitle: document.getElementById("activeTicketTitle"),
  activeTicketMeta: document.getElementById("activeTicketMeta"),
  messagesView: document.getElementById("messagesView"),
  replyText: document.getElementById("replyText"),
  sendReplyBtn: document.getElementById("sendReplyBtn"),
  ticketStatusSelect: document.getElementById("ticketStatusSelect"),
  updateTicketStatusBtn: document.getElementById("updateTicketStatusBtn"),
  publishPostForm: document.getElementById("publishPostForm"),
  postTitle: document.getElementById("postTitle"),
  postBody: document.getElementById("postBody"),
  publishPostBtn: document.getElementById("publishPostBtn"),
  postsList: document.getElementById("postsList"),
  applicationItemTemplate: document.getElementById("applicationItemTemplate"),
  ticketItemTemplate: document.getElementById("ticketItemTemplate"),
  messageItemTemplate: document.getElementById("messageItemTemplate"),
  postItemTemplate: document.getElementById("postItemTemplate"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  applications: [],
  tickets: [],
  selectedTicketId: null,
  posts: [],
};

(function init() {
  if (state.sessionToken && ui.sessionTokenInput) {
    ui.sessionTokenInput.value = state.sessionToken;
    ui.sessionTokenInput.parentElement && (ui.sessionTokenInput.parentElement.style.display = 'none');
  }
})();

function setStatus(message, mode = "") {
  ui.statusNote.textContent = message;
  ui.statusNote.classList.remove("ok", "error");
  if (mode) {
    ui.statusNote.classList.add(mode);
  }
}

function formatDate(ms) {
  if (!ms) {
    return "-";
  }
  return new Date(ms).toLocaleString();
}

function setSupportControlsEnabled(enabled) {
  ui.replyText.disabled = !enabled;
  ui.sendReplyBtn.disabled = !enabled;
  ui.ticketStatusSelect.disabled = !enabled;
  ui.updateTicketStatusBtn.disabled = !enabled;
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

function selectedTicket() {
  return state.tickets.find((item) => item.ticket_id === state.selectedTicketId) || null;
}

function renderApplications() {
  ui.applicationsList.innerHTML = "";
  if (!state.applications.length) {
    const node = document.createElement("li");
    node.className = "empty";
    node.textContent = "Очередь заявок пуста";
    ui.applicationsList.appendChild(node);
    return;
  }

  for (const app of state.applications) {
    const fragment = ui.applicationItemTemplate.content.cloneNode(true);
    fragment.querySelector(".app-title").textContent = `${app.last_name} ${app.first_name} (${app.class_group})`;
    fragment.querySelector(".app-meta").textContent = `${app.email} | ${app.phone} | ${app.status}`;

    const statusSelect = fragment.querySelector(".app-status");
    const noteInput = fragment.querySelector(".app-note");
    const applyButton = fragment.querySelector(".apply-status");
    statusSelect.value = app.status;
    noteInput.value = app.review_note || "";

    applyButton.addEventListener("click", async () => {
      try {
        await fetchJSON(`/admin/content/applications/${app.application_id}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_token: state.sessionToken,
            status: statusSelect.value,
            review_note: noteInput.value.trim() || null,
          }),
        });
        setStatus("Статус заявки обновлен", "ok");
        await loadApplications();
      } catch (error) {
        setStatus(`Ошибка заявки: ${error.message}`, "error");
      }
    });

    ui.applicationsList.appendChild(fragment);
  }
}

function renderTickets() {
  ui.ticketsList.innerHTML = "";
  if (!state.tickets.length) {
    const node = document.createElement("li");
    node.className = "empty";
    node.textContent = "Очередь support пуста";
    ui.ticketsList.appendChild(node);
    return;
  }

  for (const ticket of state.tickets) {
    const fragment = ui.ticketItemTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".ticket-btn");
    button.classList.toggle("active", state.selectedTicketId === ticket.ticket_id);
    fragment.querySelector(".ticket-title").textContent = ticket.title;
    fragment.querySelector(".ticket-meta").textContent = `#${ticket.ticket_id} | ${ticket.status}`;
    button.addEventListener("click", () => {
      openTicket(ticket.ticket_id).catch((error) => {
        setStatus(`Ошибка обращения: ${error.message}`, "error");
      });
    });
    ui.ticketsList.appendChild(fragment);
  }
}

function renderMessages(messages) {
  ui.messagesView.innerHTML = "";
  if (!messages.length) {
    const node = document.createElement("div");
    node.className = "empty";
    node.textContent = "Сообщений пока нет";
    ui.messagesView.appendChild(node);
    return;
  }

  for (const message of messages) {
    const fragment = ui.messageItemTemplate.content.cloneNode(true);
    fragment.querySelector(".message-author").textContent = `user:${message.author_user_id}`;
    fragment.querySelector(".message-time").textContent = formatDate(message.created_at_ms);
    fragment.querySelector(".message-body").textContent = message.body_text;
    ui.messagesView.appendChild(fragment);
  }
  ui.messagesView.scrollTop = ui.messagesView.scrollHeight;
}

function renderPosts() {
  ui.postsList.innerHTML = "";
  if (!state.posts.length) {
    const node = document.createElement("li");
    node.className = "empty";
    node.textContent = "Постов пока нет";
    ui.postsList.appendChild(node);
    return;
  }

  for (const post of state.posts) {
    const fragment = ui.postItemTemplate.content.cloneNode(true);
    fragment.querySelector(".post-title").textContent = post.title;
    fragment.querySelector(".post-meta").textContent = `#${post.post_id} | ${formatDate(
      post.published_at_ms
    )}`;
    ui.postsList.appendChild(fragment);
  }
}

async function loadApplications() {
  const payload = await fetchJSON(
    `/admin/content/applications?session_token=${encodeURIComponent(state.sessionToken)}&limit=200&offset=0`
  );
  state.applications = payload.items || [];
  renderApplications();
}

async function loadTickets() {
  const payload = await fetchJSON(
    `/admin/content/support/tickets?session_token=${encodeURIComponent(state.sessionToken)}&limit=200&offset=0`
  );
  state.tickets = payload.items || [];

  if (!state.tickets.some((item) => item.ticket_id === state.selectedTicketId)) {
    state.selectedTicketId = null;
  }
  renderTickets();

  if (state.selectedTicketId === null && state.tickets.length) {
    await openTicket(state.tickets[0].ticket_id);
  }
}

async function loadPosts() {
  const payload = await fetchJSON(
    `/admin/content/blog/posts?session_token=${encodeURIComponent(state.sessionToken)}&limit=100&offset=0`
  );
  state.posts = payload.items || [];
  renderPosts();
}

async function openTicket(ticketId) {
  state.selectedTicketId = ticketId;
  renderTickets();

  const ticket = selectedTicket();
  if (!ticket) {
    return;
  }

  ui.activeTicketTitle.textContent = `${ticket.title} (#${ticket.ticket_id})`;
  ui.activeTicketMeta.textContent = `owner:${ticket.user_id} | ${ticket.status}`;
  ui.ticketStatusSelect.value = ticket.status;
  setSupportControlsEnabled(true);

  const payload = await fetchJSON(
    `/admin/content/support/tickets/${ticketId}/messages?session_token=${encodeURIComponent(
      state.sessionToken
    )}&limit=500&offset=0`
  );
  renderMessages(payload.items || []);
}

async function sendTicketReply() {
  const ticket = selectedTicket();
  if (!ticket) {
    throw new Error("Сначала выберите обращение");
  }

  const bodyText = ui.replyText.value.trim();
  if (!bodyText) {
    throw new Error("Текст ответа не должен быть пустым");
  }

  await fetchJSON(`/admin/content/support/tickets/${ticket.ticket_id}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      body_text: bodyText,
    }),
  });
  ui.replyText.value = "";
  await loadTickets();
  await openTicket(ticket.ticket_id);
}

async function updateTicketStatus() {
  const ticket = selectedTicket();
  if (!ticket) {
    throw new Error("Сначала выберите обращение");
  }

  await fetchJSON(`/admin/content/support/tickets/${ticket.ticket_id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      status: ui.ticketStatusSelect.value,
    }),
  });
  await loadTickets();
  await openTicket(ticket.ticket_id);
}

async function publishBlogPost() {
  const title = ui.postTitle.value.trim();
  const bodyText = ui.postBody.value.trim();
  if (!title || !bodyText) {
    throw new Error("Заполните заголовок и текст поста");
  }

  await fetchJSON("/admin/content/blog/posts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      title,
      body_text: bodyText,
    }),
  });

  ui.publishPostForm.reset();
  await loadPosts();
}

async function loadAll() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setStatus("Укажите admin session token", "error");
    return;
  }

  ui.publishPostBtn.disabled = false;

  await loadApplications();
  await loadTickets();
  await loadPosts();
  setStatus("Данные админ-панели контента загружены", "ok");
}

ui.loadAllBtn.addEventListener("click", async () => {
  try {
    await loadAll();
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.sendReplyBtn.addEventListener("click", async () => {
  try {
    await sendTicketReply();
    setStatus("Ответ отправлен", "ok");
  } catch (error) {
    setStatus(`Ошибка reply: ${error.message}`, "error");
  }
});

ui.updateTicketStatusBtn.addEventListener("click", async () => {
  try {
    await updateTicketStatus();
    setStatus("Статус обращения обновлен", "ok");
  } catch (error) {
    setStatus(`Ошибка статуса: ${error.message}`, "error");
  }
});

ui.publishPostForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await publishBlogPost();
    setStatus("Пост опубликован", "ok");
  } catch (error) {
    setStatus(`Ошибка публикации: ${error.message}`, "error");
  }
});

setSupportControlsEnabled(false);
ui.publishPostBtn.disabled = true;
