const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadAccountBtn: document.getElementById("loadAccountBtn"),
  statusNote: document.getElementById("statusNote"),
  avatarPreview: document.getElementById("avatarPreview"),
  avatarFileInput: document.getElementById("avatarFile"),
  uploadAvatarBtn: document.getElementById("uploadAvatarBtn"),
  profileForm: document.getElementById("profileForm"),
  displayNameInput: document.getElementById("displayName"),
  profileBioInput: document.getElementById("profileBio"),
  saveProfileBtn: document.getElementById("saveProfileBtn"),
  limitRole: document.getElementById("limitRole"),
  limitMax: document.getElementById("limitMax"),
  limitCurrent: document.getElementById("limitCurrent"),
  limitRemaining: document.getElementById("limitRemaining"),
  limitAllowed: document.getElementById("limitAllowed"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  profile: null,
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
  ui.displayNameInput.disabled = !enabled;
  ui.profileBioInput.disabled = !enabled;
  ui.saveProfileBtn.disabled = !enabled;
  ui.uploadAvatarBtn.disabled = !enabled;
}

function renderProfile(profile) {
  state.profile = profile;
  ui.displayNameInput.value = profile.display_name || "";
  ui.profileBioInput.value = profile.profile_bio || "";

  if (profile.avatar_url) {
    ui.avatarPreview.src = profile.avatar_url;
  } else {
    ui.avatarPreview.removeAttribute("src");
  }
}

function renderLimits(limits) {
  ui.limitRole.textContent = limits.role;
  ui.limitMax.textContent =
    limits.max_custom_chats === null ? "unlimited" : String(limits.max_custom_chats);
  ui.limitCurrent.textContent = String(limits.current_custom_chats);
  ui.limitRemaining.textContent =
    limits.remaining_custom_chats === null ? "unlimited" : String(limits.remaining_custom_chats);
  ui.limitAllowed.textContent = limits.can_create_custom_chats ? "yes" : "no";
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

async function loadAccount() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setStatus("Укажите session token", "error");
    return;
  }

  const profilePayload = await fetchJSON(
    `/account/api/profile?session_token=${encodeURIComponent(state.sessionToken)}`
  );
  const limitsPayload = await fetchJSON(
    `/account/api/limits?session_token=${encodeURIComponent(state.sessionToken)}`
  );

  renderProfile(profilePayload.profile);
  renderLimits(limitsPayload.limits);
  setControlsEnabled(profilePayload.profile.role !== "guest");
  setStatus("Данные аккаунта загружены", "ok");
}

async function saveProfile() {
  const payload = {
    session_token: state.sessionToken,
    display_name: ui.displayNameInput.value.trim() || null,
    profile_bio: ui.profileBioInput.value.trim() || null,
  };

  const result = await fetchJSON("/account/api/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderProfile(result.profile);
  setStatus("Профиль сохранен", "ok");
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}

async function uploadAvatar() {
  const file = ui.avatarFileInput.files && ui.avatarFileInput.files[0];
  if (!file) {
    setStatus("Выберите файл аватара", "error");
    return;
  }

  const dataUrl = await readFileAsDataURL(file);
  const payload = {
    session_token: state.sessionToken,
    image_base64: dataUrl,
    image_mime_type: file.type || null,
  };

  const result = await fetchJSON("/account/api/avatar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  renderProfile(result.profile);
  setStatus("Аватар обновлен", "ok");
}

ui.loadAccountBtn.addEventListener("click", async () => {
  try {
    await loadAccount();
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await saveProfile();
  } catch (error) {
    setStatus(`Ошибка сохранения: ${error.message}`, "error");
  }
});

ui.uploadAvatarBtn.addEventListener("click", async () => {
  try {
    await uploadAvatar();
  } catch (error) {
    setStatus(`Ошибка аватара: ${error.message}`, "error");
  }
});

setControlsEnabled(false);
