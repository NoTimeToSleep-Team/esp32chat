const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadCatalogBtn: document.getElementById("loadCatalogBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  statusNote: document.getElementById("statusNote"),
  publishSection: document.getElementById("publishSection"),
  publishForm: document.getElementById("publishForm"),
  deviceSlugInput: document.getElementById("deviceSlug"),
  deviceTitleInput: document.getElementById("deviceTitle"),
  deviceShortDescriptionInput: document.getElementById("deviceShortDescription"),
  deviceFirmwareUrlInput: document.getElementById("deviceFirmwareUrl"),
  deviceInstallGuideInput: document.getElementById("deviceInstallGuide"),
  devicePairingGuideInput: document.getElementById("devicePairingGuide"),
  deviceComboResetGuideInput: document.getElementById("deviceComboResetGuide"),
  publishBtn: document.getElementById("publishBtn"),
  deviceList: document.getElementById("deviceList"),
  activeTitle: document.getElementById("activeTitle"),
  activeMeta: document.getElementById("activeMeta"),
  activeShortDescription: document.getElementById("activeShortDescription"),
  activeFirmwareLink: document.getElementById("activeFirmwareLink"),
  installGuide: document.getElementById("installGuide"),
  pairingGuide: document.getElementById("pairingGuide"),
  comboResetGuide: document.getElementById("comboResetGuide"),
  toggleOwnershipBtn: document.getElementById("toggleOwnershipBtn"),
  ownershipState: document.getElementById("ownershipState"),
  deviceItemTemplate: document.getElementById("deviceItemTemplate"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  role: null,
  devices: [],
};

(function init() {
  if (state.sessionToken && ui.sessionTokenInput) {
    ui.sessionTokenInput.value = state.sessionToken;
    ui.sessionTokenInput.parentElement && (ui.sessionTokenInput.parentElement.style.display = 'none');
  }
})();
  activeDeviceId: null,
};

function setStatus(message, mode = "") {
  ui.statusNote.textContent = message;
  ui.statusNote.classList.remove("ok", "error");
  if (mode) {
    ui.statusNote.classList.add(mode);
  }
}

function setPublishEnabled(enabled) {
  ui.publishBtn.disabled = !enabled;
  ui.publishSection.style.opacity = enabled ? "1" : "0.72";
}

function setOwnershipEnabled(enabled) {
  ui.toggleOwnershipBtn.disabled = !enabled;
}

function currentDevice() {
  return state.devices.find((item) => item.device_id === state.activeDeviceId) || null;
}

function renderCatalog() {
  ui.deviceList.innerHTML = "";

  if (!state.devices.length) {
    const node = document.createElement("li");
    node.className = "empty-note";
    node.textContent = "В каталоге пока нет устройств";
    ui.deviceList.appendChild(node);
    return;
  }

  for (const device of state.devices) {
    const fragment = ui.deviceItemTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".device-btn");
    button.classList.toggle("active", state.activeDeviceId === device.device_id);
    fragment.querySelector(".device-title").textContent = device.title;
    fragment.querySelector(".device-meta").textContent = `${device.slug} | ${
      device.has_device ? "есть устройство" : "не отмечено"
    }`;

    button.addEventListener("click", () => {
      openDevice(device.device_id).catch((error) => {
        setStatus(`Ошибка открытия: ${error.message}`, "error");
      });
    });

    ui.deviceList.appendChild(fragment);
  }
}

function renderDevice(device) {
  if (!device) {
    ui.activeTitle.textContent = "Выберите устройство";
    ui.activeMeta.textContent = "Подробности появятся после выбора";
    ui.activeShortDescription.textContent = "";
    ui.activeFirmwareLink.textContent = "";
    ui.installGuide.textContent = "";
    ui.pairingGuide.textContent = "";
    ui.comboResetGuide.textContent = "";
    ui.ownershipState.textContent = "Статус владения не задан";
    ui.toggleOwnershipBtn.textContent = "Отметить «у меня есть устройство»";
    setOwnershipEnabled(false);
    return;
  }

  ui.activeTitle.textContent = device.title;
  ui.activeMeta.textContent = `${device.slug} | ${
    device.is_published ? "published" : "draft"
  }`;
  ui.activeShortDescription.textContent = device.short_description;

  if (device.firmware_archive_url) {
    ui.activeFirmwareLink.innerHTML = `Архив/прошивка: <a href="${device.firmware_archive_url}" target="_blank" rel="noreferrer">${device.firmware_archive_url}</a>`;
  } else {
    ui.activeFirmwareLink.textContent = "Архив/прошивка не указан";
  }

  ui.installGuide.textContent = device.install_guide;
  ui.pairingGuide.textContent = device.pairing_guide;
  ui.comboResetGuide.textContent = device.combo_reset_guide;

  if (state.role === "guest") {
    ui.ownershipState.textContent = "Гостевой аккаунт не может отметить владение";
    ui.toggleOwnershipBtn.textContent = "Недоступно в guest";
    setOwnershipEnabled(false);
  } else {
    ui.ownershipState.textContent = device.has_device
      ? "Вы отметили: устройство есть"
      : "Вы не отметили владение";
    ui.toggleOwnershipBtn.textContent = device.has_device
      ? "Снять отметку «у меня есть устройство»"
      : "Отметить «у меня есть устройство»";
    setOwnershipEnabled(true);
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

async function loadCatalog() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setStatus("Укажите session token", "error");
    return;
  }

  const profilePayload = await fetchJSON(
    `/account/api/profile?session_token=${encodeURIComponent(state.sessionToken)}`
  );
  state.role = profilePayload.profile.role;

  const catalogPayload = await fetchJSON(
    `/devices/api/catalog?session_token=${encodeURIComponent(state.sessionToken)}&limit=200&offset=0`
  );

  state.devices = catalogPayload.items || [];
  if (!state.devices.some((item) => item.device_id === state.activeDeviceId)) {
    state.activeDeviceId = null;
  }

  setPublishEnabled(state.role === "admin");
  renderCatalog();

  if (state.activeDeviceId === null && state.devices.length) {
    await openDevice(state.devices[0].device_id);
  } else {
    renderDevice(currentDevice());
  }

  setStatus("Каталог загружен", "ok");
}

async function openDevice(deviceId) {
  const payload = await fetchJSON(
    `/devices/api/catalog/${deviceId}?session_token=${encodeURIComponent(state.sessionToken)}`
  );
  const loaded = payload.device;

  state.devices = state.devices.map((item) =>
    item.device_id === loaded.device_id ? loaded : item
  );
  state.activeDeviceId = loaded.device_id;

  renderCatalog();
  renderDevice(loaded);
}

async function publishProfile() {
  const payload = {
    session_token: state.sessionToken,
    slug: ui.deviceSlugInput.value.trim().toLowerCase(),
    title: ui.deviceTitleInput.value.trim(),
    short_description: ui.deviceShortDescriptionInput.value.trim(),
    firmware_archive_url: ui.deviceFirmwareUrlInput.value.trim() || null,
    install_guide: ui.deviceInstallGuideInput.value.trim(),
    pairing_guide: ui.devicePairingGuideInput.value.trim(),
    combo_reset_guide: ui.deviceComboResetGuideInput.value.trim(),
    is_published: true,
  };

  await fetchJSON("/devices/api/catalog", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  ui.publishForm.reset();
  setStatus("Профиль устройства опубликован", "ok");
  await loadCatalog();
}

async function toggleOwnership() {
  const device = currentDevice();
  if (!device) {
    return;
  }

  await fetchJSON(`/devices/api/catalog/${device.device_id}/ownership`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      has_device: !device.has_device,
    }),
  });

  await openDevice(device.device_id);
  setStatus("Флаг владения обновлен", "ok");
}

ui.loadCatalogBtn.addEventListener("click", async () => {
  try {
    await loadCatalog();
  } catch (error) {
    setStatus(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.refreshBtn.addEventListener("click", async () => {
  try {
    await loadCatalog();
  } catch (error) {
    setStatus(`Ошибка обновления: ${error.message}`, "error");
  }
});

ui.publishForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await publishProfile();
  } catch (error) {
    setStatus(`Ошибка публикации: ${error.message}`, "error");
  }
});

ui.toggleOwnershipBtn.addEventListener("click", async () => {
  try {
    await toggleOwnership();
  } catch (error) {
    setStatus(`Ошибка владения: ${error.message}`, "error");
  }
});

setPublishEnabled(false);
renderDevice(null);
