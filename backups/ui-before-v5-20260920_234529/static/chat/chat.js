const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadChatsBtn: document.getElementById("loadChatsBtn"),
  refreshChatsBtn: document.getElementById("refreshChatsBtn"),
  chatList: document.getElementById("chatList"),
  activeChatTitle: document.getElementById("activeChatTitle"),
  activeChatMeta: document.getElementById("activeChatMeta"),
  realtimeState: document.getElementById("realtimeState"),
  messageViewport: document.getElementById("messageViewport"),
  sendForm: document.getElementById("sendMessageForm"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendMessageBtn"),
  composerHint: document.getElementById("composerHint"),
  messageTemplate: document.getElementById("messageTemplate"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  chats: [],
  activeChatId: null,
};

(function init() {
  if (state.sessionToken && ui.sessionTokenInput) {
    ui.sessionTokenInput.value = state.sessionToken;
    ui.sessionTokenInput.parentElement && (ui.sessionTokenInput.parentElement.style.display = 'none');
  }
})();
  ws: null,
};

function setRealtimeState(mode) {
  ui.realtimeState.textContent = mode;
  ui.realtimeState.classList.remove("online", "offline");
  ui.realtimeState.classList.add(mode === "online" ? "online" : "offline");
}

function setComposerEnabled(enabled) {
  ui.messageInput.disabled = !enabled;
  ui.sendBtn.disabled = !enabled;
  ui.composerHint.textContent = enabled
    ? "Enter отправляет сообщение, Shift+Enter — новая строка"
    : "Нужно выбрать чат и загрузить сессию";
}

function renderEmpty(text, isError = false) {
  ui.messageViewport.innerHTML = "";
  const node = document.createElement("div");
  node.className = `empty-state${isError ? " error-note" : ""}`;
  node.textContent = text;
  ui.messageViewport.appendChild(node);
}

function formatTime(ts) {
  if (!ts) {
    return "";
  }
  const dt = new Date(ts);
  return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function messageNode(message) {
  const fragment = ui.messageTemplate.content.cloneNode(true);
  fragment.querySelector(".author").textContent = `user:${message.author_user_id}`;
  fragment.querySelector(".time").textContent = formatTime(message.created_at_ms);
  fragment.querySelector(".body").textContent = message.body_text;
  return fragment;
}

function appendMessage(message) {
  const isAtBottom =
    Math.abs(
      ui.messageViewport.scrollHeight -
        ui.messageViewport.clientHeight -
        ui.messageViewport.scrollTop
    ) < 12;

  ui.messageViewport.appendChild(messageNode(message));

  if (isAtBottom) {
    ui.messageViewport.scrollTop = ui.messageViewport.scrollHeight;
  }
}

function renderMessages(messages) {
  ui.messageViewport.innerHTML = "";
  if (!messages.length) {
    renderEmpty("Пока нет сообщений. Начните диалог первым.");
    return;
  }

  for (const message of messages) {
    ui.messageViewport.appendChild(messageNode(message));
  }
  ui.messageViewport.scrollTop = ui.messageViewport.scrollHeight;
}

function renderChats() {
  ui.chatList.innerHTML = "";
  if (!state.chats.length) {
    const li = document.createElement("li");
    li.className = "empty-state";
    li.textContent = "Доступных чатов не найдено";
    ui.chatList.appendChild(li);
    return;
  }

  for (const chat of state.chats) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.chatId = String(chat.chat_id);
    button.className = state.activeChatId === chat.chat_id ? "active" : "";
    button.innerHTML = `<strong>${chat.title}</strong><br><small>${chat.kind}</small>`;
    button.addEventListener("click", () => openChat(chat.chat_id));
    li.appendChild(button);
    ui.chatList.appendChild(li);
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

async function loadChats() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    renderEmpty("Укажите session token", true);
    return;
  }

  const url = `/chat/api/chats?session_token=${encodeURIComponent(state.sessionToken)}`;
  const payload = await fetchJSON(url);
  state.chats = payload.items || [];
  if (!state.chats.some((chat) => chat.chat_id === state.activeChatId)) {
    state.activeChatId = null;
  }
  renderChats();

  if (state.activeChatId === null && state.chats.length) {
    await openChat(state.chats[0].chat_id);
  }
}

async function loadHistory(chatId) {
  const url = `/chat/api/chats/${chatId}/messages?session_token=${encodeURIComponent(
    state.sessionToken
  )}&limit=200&offset=0`;
  const payload = await fetchJSON(url);
  renderMessages(payload.items || []);
}

function closeSocket() {
  if (!state.ws) {
    return;
  }
  try {
    state.ws.close();
  } catch (_) {
    // ignore close errors
  }
  state.ws = null;
  setRealtimeState("offline");
}

function wsURL(chatId, sessionToken) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/realtime/chat/${chatId}?session_token=${encodeURIComponent(
    sessionToken
  )}`;
}

function connectRealtime(chatId) {
  closeSocket();
  const socket = new WebSocket(wsURL(chatId, state.sessionToken));
  state.ws = socket;

  socket.addEventListener("open", () => {
    setRealtimeState("online");
  });

  socket.addEventListener("close", () => {
    if (state.ws === socket) {
      setRealtimeState("offline");
    }
  });

  socket.addEventListener("message", (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch (_) {
      return;
    }

    if (payload.type === "chat.message" && payload.message?.chat_id === state.activeChatId) {
      appendMessage(payload.message);
      return;
    }

    if (payload.type === "chat.history") {
      renderMessages(payload.items || []);
      return;
    }

    if (payload.type === "error") {
      renderEmpty(payload.error?.message || "Ошибка realtime", true);
    }
  });
}

async function openChat(chatId) {
  const chat = state.chats.find((item) => item.chat_id === chatId);
  if (!chat) {
    return;
  }

  state.activeChatId = chatId;
  renderChats();

  ui.activeChatTitle.textContent = chat.title;
  ui.activeChatMeta.textContent = `${chat.kind} chat`;
  setComposerEnabled(true);

  try {
    await loadHistory(chatId);
    connectRealtime(chatId);
  } catch (error) {
    renderEmpty(`Не удалось открыть чат: ${error.message}`, true);
    setComposerEnabled(false);
  }
}

function randomClientMessageId() {
  return `web-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

async function sendCurrentMessage() {
  const chatId = state.activeChatId;
  const bodyText = ui.messageInput.value.trim();
  if (!chatId || !bodyText) {
    return;
  }

  const clientMessageId = randomClientMessageId();

  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(
      JSON.stringify({
        type: "chat.send",
        body_text: bodyText,
        client_message_id: clientMessageId,
      })
    );
  } else {
    const payload = {
      session_token: state.sessionToken,
      body_text: bodyText,
      client_message_id: clientMessageId,
    };
    const response = await fetchJSON(`/chat/api/chats/${chatId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (response.message) {
      appendMessage(response.message);
    }
  }

  ui.messageInput.value = "";
  ui.messageInput.focus();
}

ui.loadChatsBtn.addEventListener("click", async () => {
  try {
    await loadChats();
  } catch (error) {
    renderEmpty(`Ошибка загрузки чатов: ${error.message}`, true);
  }
});

ui.refreshChatsBtn.addEventListener("click", async () => {
  try {
    await loadChats();
  } catch (error) {
    renderEmpty(`Ошибка обновления: ${error.message}`, true);
  }
});

ui.sendForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await sendCurrentMessage();
  } catch (error) {
    renderEmpty(`Ошибка отправки: ${error.message}`, true);
  }
});

ui.messageInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    try {
      await sendCurrentMessage();
    } catch (error) {
      renderEmpty(`Ошибка отправки: ${error.message}`, true);
    }
  }
});

setRealtimeState("offline");
setComposerEnabled(false);
renderEmpty("Введите session token и загрузите чаты.");
