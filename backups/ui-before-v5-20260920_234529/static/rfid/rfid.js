// DEPRECATED in RPi-Only architecture (v1.00.00)
const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadAdminDataBtn: document.getElementById("loadAdminDataBtn"),
  statusNote: document.getElementById("statusNote"),
  enrollForm: document.getElementById("enrollForm"),
  cardUid: document.getElementById("cardUid"),
  cardLabel: document.getElementById("cardLabel"),
  cardNote: document.getElementById("cardNote"),
  cardActive: document.getElementById("cardActive"),
  enrollBtn: document.getElementById("enrollBtn"),
  scanUid: document.getElementById("scanUid"),
  scanSource: document.getElementById("scanSource"),
  verifyBtn: document.getElementById("verifyBtn"),
  targetMode: document.getElementById("targetMode"),
  switchModeByCardBtn: document.getElementById("switchModeByCardBtn"),
  cardDecision: document.getElementById("cardDecision"),
  cardsList: document.getElementById("cardsList"),
  eventsList: document.getElementById("eventsList"),
  cardItemTemplate: document.getElementById("cardItemTemplate"),
  eventItemTemplate: document.getElementById("eventItemTemplate"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  cards: [],
  events: [],
};

(function init() {
  if (state.sessionToken && ui.sessionTokenInput) {
    ui.sessionTokenInput.value = state.sessionToken;
    ui.sessionTokenInput.parentElement && (ui.sessionTokenInput.parentElement.style.display = 'none');
  }
})();
};

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

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail?.message || payload?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

function renderCards() {
  ui.cardsList.innerHTML = "";
  if (!state.cards.length) {
    const node = document.createElement("li");
    node.className = "empty";
    node.textContent = "Карты не найдены";
    ui.cardsList.appendChild(node);
    return;
  }

  for (const card of state.cards) {
    const fragment = ui.cardItemTemplate.content.cloneNode(true);
    fragment.querySelector(".card-label").textContent = `${card.card_label} (${card.uid_mask})`;
    fragment.querySelector(".card-meta").textContent = `active:${card.is_active} | last_used:${formatDate(
      card.last_used_at_ms
    )}`;

    const toggleButton = fragment.querySelector(".toggle-card-btn");
    toggleButton.textContent = card.is_active ? "Disable" : "Enable";
    toggleButton.addEventListener("click", async () => {
      try {
        await fetchJSON(`/rfid/api/cards/${card.card_id}/active`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_token: state.sessionToken,
            is_active: !card.is_active,
          }),
        });
        await loadAdminData();
        setStatus("Статус карты обновлен", "ok");
      } catch (error) {
        setStatus(`Ошибка карты: ${error.message}`, "error");
      }
    });

    const deleteButton = fragment.querySelector(".delete-card-btn");
    deleteButton.addEventListener("click", async () => {
      try {
        await fetchJSON(
          `/rfid/api/cards/${card.card_id}?session_token=${encodeURIComponent(state.sessionToken)}`,
          { method: "DELETE" }
        );
        await loadAdminData();
        setStatus("Карта удалена", "ok");
      } catch (error) {
        setStatus(`Ошибка удаления: ${error.message}`, "error");
      }
    });

    ui.cardsList.appendChild(fragment);
  }
}

function renderEvents() {
  ui.eventsList.innerHTML = "";
  if (!state.events.length) {
    const node = document.createElement("li");
    node.className = "empty";
    node.textContent = "События не найдены";
    ui.eventsList.appendChild(node);
    return;
  }

  for (const event of state.events) {
    const fragment = ui.eventItemTemplate.content.cloneNode(true);
    fragment.querySelector(".event-title").textContent = `${event.action} | granted:${event.granted}`;
    fragment.querySelector(".event-meta").textContent = `${event.uid_mask || "-"} | ${formatDate(
      event.created_at_ms
    )} | reason:${event.reason || "-"}`;
    ui.eventsList.appendChild(fragment);
  }
}

async function loadAdminData() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setStatus("Укажите admin session token", "error");
    return;
  }

  const cardsPayload = await fetchJSON(
    `/rfid/api/cards?session_token=${encodeURIComponent(state.sessionToken)}&include_inactive=true&limit=200&offset=0`
  );
  const eventsPayload = await fetchJSON(
    `/rfid/api/events?session_token=${encodeURIComponent(state.sessionToken)}&limit=200&offset=0`
  );

  state.cards = cardsPayload.items || [];
  state.events = eventsPayload.items || [];
  renderCards();
  renderEvents();
  ui.enrollBtn.disabled = false;
  setStatus("RFID данные загружены", "ok");
}

async function enrollCard() {
  await fetchJSON("/rfid/api/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      card_uid: ui.cardUid.value.trim(),
      card_label: ui.cardLabel.value.trim(),
      note: ui.cardNote.value.trim() || null,
      is_active: ui.cardActive.checked,
    }),
  });

  ui.enrollForm.reset();
  ui.cardActive.checked = true;
  await loadAdminData();
}

async function verifyCard() {
  const payload = await fetchJSON("/rfid/api/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      card_uid: ui.scanUid.value.trim(),
      source: ui.scanSource.value.trim() || null,
    }),
  });
  ui.cardDecision.textContent = JSON.stringify(payload.decision, null, 2);
  await loadAdminData();
}

async function switchModeByCard() {
  const payload = await fetchJSON("/rfid/api/mode/switch-by-card", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      card_uid: ui.scanUid.value.trim(),
      target_mode: ui.targetMode.value,
      source: ui.scanSource.value.trim() || null,
    }),
  });
  ui.cardDecision.textContent = JSON.stringify(payload.decision, null, 2);
  await loadAdminData();
}

ui.loadAdminDataBtn.addEventListener("click", async () => {
  try {
    await loadAdminData();
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.enrollForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await enrollCard();
    setStatus("Карта записана", "ok");
  } catch (error) {
    setStatus(`Ошибка записи: ${error.message}`, "error");
  }
});

ui.verifyBtn.addEventListener("click", async () => {
  try {
    await verifyCard();
    setStatus("Проверка карты выполнена", "ok");
  } catch (error) {
    setStatus(`Ошибка проверки: ${error.message}`, "error");
  }
});

ui.switchModeByCardBtn.addEventListener("click", async () => {
  try {
    await switchModeByCard();
    setStatus("Команда mode switch по карте выполнена", "ok");
  } catch (error) {
    setStatus(`Ошибка mode switch: ${error.message}`, "error");
  }
});
