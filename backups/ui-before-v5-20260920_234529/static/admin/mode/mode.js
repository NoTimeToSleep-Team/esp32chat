const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadModeStateBtn: document.getElementById("loadModeStateBtn"),
  statusNote: document.getElementById("statusNote"),
  currentMode: document.getElementById("currentMode"),
  safeSequence: document.getElementById("safeSequence"),
  targetMode: document.getElementById("targetMode"),
  holdSeconds: document.getElementById("holdSeconds"),
  applyModeBtn: document.getElementById("applyModeBtn"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  requiredHoldSeconds: 5,
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

function renderSafeSequence(items) {
  ui.safeSequence.innerHTML = "";
  for (const step of items || []) {
    const li = document.createElement("li");
    li.textContent = step;
    ui.safeSequence.appendChild(li);
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

async function loadModeState() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setStatus("Укажите admin session token", "error");
    return;
  }

  const payload = await fetchJSON(
    `/admin/mode/state?session_token=${encodeURIComponent(state.sessionToken)}`
  );
  ui.currentMode.textContent = payload.access_mode;
  ui.targetMode.value = payload.access_mode;
  state.requiredHoldSeconds = payload.required_hold_seconds || 5;
  ui.holdSeconds.value = String(state.requiredHoldSeconds);
  renderSafeSequence(payload.safe_sequence || []);
  ui.applyModeBtn.disabled = false;
  setStatus("Mode state загружен", "ok");
}

async function applyMode() {
  const targetMode = ui.targetMode.value;
  const holdSeconds = Number.parseInt(ui.holdSeconds.value, 10);
  if (!Number.isFinite(holdSeconds)) {
    throw new Error("hold_seconds должен быть числом");
  }

  const payload = await fetchJSON("/admin/mode/set", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      access_mode: targetMode,
      hold_seconds: holdSeconds,
    }),
  });

  ui.currentMode.textContent = payload.access_mode;
  renderSafeSequence(payload.safe_sequence || []);
  state.requiredHoldSeconds = payload.required_hold_seconds || state.requiredHoldSeconds;
  setStatus(`Режим переключен на ${payload.access_mode}`, "ok");
}

ui.loadModeStateBtn.addEventListener("click", async () => {
  try {
    await loadModeState();
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.applyModeBtn.addEventListener("click", async () => {
  try {
    await applyMode();
  } catch (error) {
    setStatus(`Ошибка переключения: ${error.message}`, "error");
  }
});
