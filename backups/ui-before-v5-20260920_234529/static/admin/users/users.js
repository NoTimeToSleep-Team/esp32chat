const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  statusFilter: document.getElementById("statusFilter"),
  loadUsersBtn: document.getElementById("loadUsersBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  statusNote: document.getElementById("statusNote"),
  userList: document.getElementById("userList"),
  userItemTemplate: document.getElementById("userItemTemplate"),
  selectedUserTitle: document.getElementById("selectedUserTitle"),
  selectedUserMeta: document.getElementById("selectedUserMeta"),
  detailRole: document.getElementById("detailRole"),
  detailStatus: document.getElementById("detailStatus"),
  detailPhone: document.getElementById("detailPhone"),
  detailDevice: document.getElementById("detailDevice"),
  detailBlockedUntil: document.getElementById("detailBlockedUntil"),
  detailReason: document.getElementById("detailReason"),
  detailBlacklisted: document.getElementById("detailBlacklisted"),
  actionReasonInput: document.getElementById("actionReason"),
  temporaryMinutesInput: document.getElementById("temporaryMinutes"),
  banBtn: document.getElementById("banBtn"),
  unbanBtn: document.getElementById("unbanBtn"),
  tempBlockBtn: document.getElementById("tempBlockBtn"),
  blacklistDeviceBtn: document.getElementById("blacklistDeviceBtn"),
  unblacklistDeviceBtn: document.getElementById("unblacklistDeviceBtn"),
  deleteUserBtn: document.getElementById("deleteUserBtn"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  users: [],
  selectedUserId: null,
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

function setControlsEnabled(enabled) {
  ui.banBtn.disabled = !enabled;
  ui.unbanBtn.disabled = !enabled;
  ui.tempBlockBtn.disabled = !enabled;
  ui.blacklistDeviceBtn.disabled = !enabled;
  ui.unblacklistDeviceBtn.disabled = !enabled;
  ui.deleteUserBtn.disabled = !enabled;
}

function formatDate(ts) {
  if (!ts) {
    return "-";
  }
  return new Date(ts).toLocaleString();
}

function selectedUser() {
  return state.users.find((item) => item.user_id === state.selectedUserId) || null;
}

function renderUserList() {
  ui.userList.innerHTML = "";

  if (!state.users.length) {
    const node = document.createElement("li");
    node.className = "empty-note";
    node.textContent = "Пользователи не найдены";
    ui.userList.appendChild(node);
    return;
  }

  for (const user of state.users) {
    const fragment = ui.userItemTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".user-btn");
    button.classList.toggle("active", state.selectedUserId === user.user_id);
    fragment.querySelector(".user-login").textContent = user.login;
    fragment.querySelector(".user-meta").textContent = `${user.role} | ${user.status}`;

    button.addEventListener("click", () => {
      openUser(user.user_id).catch((error) => {
        setStatus(`Ошибка открытия: ${error.message}`, "error");
      });
    });

    ui.userList.appendChild(fragment);
  }
}

function renderSelectedUser(user) {
  if (!user) {
    ui.selectedUserTitle.textContent = "Выберите пользователя";
    ui.selectedUserMeta.textContent = "Детали и действия появятся после выбора";
    ui.detailRole.textContent = "-";
    ui.detailStatus.textContent = "-";
    ui.detailPhone.textContent = "-";
    ui.detailDevice.textContent = "-";
    ui.detailBlockedUntil.textContent = "-";
    ui.detailReason.textContent = "-";
    ui.detailBlacklisted.textContent = "-";
    setControlsEnabled(false);
    return;
  }

  ui.selectedUserTitle.textContent = `user:${user.login} (#${user.user_id})`;
  ui.selectedUserMeta.textContent = `created ${formatDate(user.created_at_ms)}`;
  ui.detailRole.textContent = user.role;
  ui.detailStatus.textContent = user.status;
  ui.detailPhone.textContent = user.phone || "-";
  ui.detailDevice.textContent = user.registration_device_id || "-";
  ui.detailBlockedUntil.textContent = formatDate(user.blocked_until_ms);
  ui.detailReason.textContent = user.block_reason || "-";
  ui.detailBlacklisted.textContent = user.device_blacklisted ? "yes" : "no";
  setControlsEnabled(true);
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

async function loadUsers() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setStatus("Укажите admin session token", "error");
    return;
  }

  const statusValue = ui.statusFilter.value;
  const statusPart = statusValue ? `&status=${encodeURIComponent(statusValue)}` : "";
  const payload = await fetchJSON(
    `/admin/users?session_token=${encodeURIComponent(state.sessionToken)}${statusPart}&limit=300&offset=0`
  );
  state.users = payload.items || [];

  if (!state.users.some((item) => item.user_id === state.selectedUserId)) {
    state.selectedUserId = null;
  }

  renderUserList();

  if (state.selectedUserId === null && state.users.length) {
    await openUser(state.users[0].user_id);
  } else {
    renderSelectedUser(selectedUser());
  }

  setStatus("Список пользователей загружен", "ok");
}

async function openUser(userId) {
  const payload = await fetchJSON(
    `/admin/users/${userId}?session_token=${encodeURIComponent(state.sessionToken)}`
  );
  const loaded = payload.user;

  state.users = state.users.map((item) =>
    item.user_id === loaded.user_id ? loaded : item
  );
  state.selectedUserId = loaded.user_id;

  renderUserList();
  renderSelectedUser(loaded);
}

function selectedUserIdOrThrow() {
  const user = selectedUser();
  if (!user) {
    throw new Error("Сначала выберите пользователя");
  }
  return user.user_id;
}

function normalizedReason() {
  return ui.actionReasonInput.value.trim() || null;
}

async function banSelectedUser() {
  const userId = selectedUserIdOrThrow();
  await fetchJSON(`/admin/users/${userId}/ban`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      reason: normalizedReason(),
    }),
  });
  await loadUsers();
  await openUser(userId);
  setStatus("Пользователь заблокирован (ban)", "ok");
}

async function unbanSelectedUser() {
  const userId = selectedUserIdOrThrow();
  await fetchJSON(`/admin/users/${userId}/unban`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_token: state.sessionToken }),
  });
  await loadUsers();
  await openUser(userId);
  setStatus("Пользователь восстановлен", "ok");
}

async function temporaryBlockSelectedUser() {
  const userId = selectedUserIdOrThrow();
  const durationMinutes = Number.parseInt(ui.temporaryMinutesInput.value, 10);
  if (!Number.isFinite(durationMinutes) || durationMinutes < 1 || durationMinutes > 10080) {
    throw new Error("duration_minutes должен быть в диапазоне 1..10080");
  }

  await fetchJSON(`/admin/users/${userId}/temporary-block`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      duration_minutes: durationMinutes,
      reason: normalizedReason(),
    }),
  });
  await loadUsers();
  await openUser(userId);
  setStatus("Временная блокировка установлена", "ok");
}

async function blacklistDeviceForSelectedUser() {
  const userId = selectedUserIdOrThrow();
  await fetchJSON(`/admin/users/${userId}/blacklist-device`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      reason: normalizedReason(),
    }),
  });
  await loadUsers();
  await openUser(userId);
  setStatus("Устройство добавлено в blacklist", "ok");
}

async function unblacklistDeviceForSelectedUser() {
  const userId = selectedUserIdOrThrow();
  await fetchJSON(`/admin/users/${userId}/unblacklist-device`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
    }),
  });
  await loadUsers();
  await openUser(userId);
  setStatus("Устройство удалено из blacklist", "ok");
}

async function deleteSelectedUser() {
  const userId = selectedUserIdOrThrow();
  await fetchJSON(
    `/admin/users/${userId}?session_token=${encodeURIComponent(state.sessionToken)}`,
    {
      method: "DELETE",
    }
  );

  state.selectedUserId = null;
  await loadUsers();
  setStatus("Пользователь удален", "ok");
}

ui.loadUsersBtn.addEventListener("click", async () => {
  try {
    await loadUsers();
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.refreshBtn.addEventListener("click", async () => {
  try {
    await loadUsers();
  } catch (error) {
    setStatus(`Ошибка обновления: ${error.message}`, "error");
  }
});

ui.banBtn.addEventListener("click", async () => {
  try {
    await banSelectedUser();
  } catch (error) {
    setStatus(`Ошибка ban: ${error.message}`, "error");
  }
});

ui.unbanBtn.addEventListener("click", async () => {
  try {
    await unbanSelectedUser();
  } catch (error) {
    setStatus(`Ошибка unban: ${error.message}`, "error");
  }
});

ui.tempBlockBtn.addEventListener("click", async () => {
  try {
    await temporaryBlockSelectedUser();
  } catch (error) {
    setStatus(`Ошибка temporary block: ${error.message}`, "error");
  }
});

ui.blacklistDeviceBtn.addEventListener("click", async () => {
  try {
    await blacklistDeviceForSelectedUser();
  } catch (error) {
    setStatus(`Ошибка blacklist: ${error.message}`, "error");
  }
});

ui.unblacklistDeviceBtn.addEventListener("click", async () => {
  try {
    await unblacklistDeviceForSelectedUser();
  } catch (error) {
    setStatus(`Ошибка unblacklist: ${error.message}`, "error");
  }
});

ui.deleteUserBtn.addEventListener("click", async () => {
  try {
    await deleteSelectedUser();
  } catch (error) {
    setStatus(`Ошибка delete: ${error.message}`, "error");
  }
});

setControlsEnabled(false);
