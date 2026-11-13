(function () {
  const A = {};
  const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${headers.length}">Пока пусто</td></tr>`}</tbody></table></div>`;
  const options = (items, value, label) => items.map((item) => `<option value="${item[value]}">${item[label]}</option>`).join("");
  const styleCard = (title, body, actions = "") => `<div class="camp-card"><div class="camp-card-head"><strong>${title}</strong></div><div class="camp-card-body">${body}</div>${actions ? `<div class="camp-card-actions">${actions}</div>` : ""}</div>`;
  async function refresh(ctx, action) { ctx.closeSheet(); await ctx[action](); }

  A.rollcall = async (ctx) => {
    const { api, openSheet, esc, tr, humanError, toast } = ctx;
    const [eventsData, unitsData] = await Promise.all([api("/camp/api/attendance/events?limit=20"), api("/camp/api/units")]);
    const events = eventsData.items || [], units = unitsData.items || [];
    const openEvents = events.filter((e) => e.status === "open");
    const unitOptions = options(units, "id", "name");
    const eventHtml = openEvents.map((e) => styleCard(
      `${esc(e.unit_name)} · ${e.kind === "lights_out" ? "Отбой" : "Перекличка"}`,
      `<div class="camp-mini">${e.summary.marked}/${e.summary.total} отмечено</div><div class="camp-progress"><span style="width:${e.summary.total ? Math.round(e.summary.marked * 100 / e.summary.total) : 0}%"></span></div>${(e.items || []).map((i) => `<div class="camp-card-row"><span>${esc(i.display_name)}</span><select data-mark="${e.id}" data-person="${i.id}"><option value="">Не отмечен</option>${["present", "absent", "sick", "medic", "parent", "left"].map((s) => `<option value="${s}" ${i.mark_status === s ? "selected" : ""}>${esc(tr("attendance", s))}</option>`).join("")}</select></div>`).join("")}`,
      `<button class="btn btn-sm btn-primary" data-all="${e.id}">Все на месте</button><button class="btn btn-sm btn-outline" data-close="${e.id}">Закрыть</button><button class="btn btn-sm btn-outline" data-force="${e.id}">Закрыть с причиной</button>`
    )).join("");
    openSheet("Перекличка", `<div class="notice">${units.length ? "Выберите отряд и начните перекличку." : "Нет отрядов. Директор создаёт их в подготовке."}</div>
      ${units.length ? `<div class="row"><label class="grow">Отряд<select id="campRollUnit">${unitOptions}</select></label><label>Тип<select id="campRollKind"><option value="roll_call">Перекличка</option><option value="lights_out">Отбой</option></select></label><button class="btn btn-primary" id="campRollStart">Начать</button></div>` : ""}
      <div class="stack">${eventHtml || `<div class="notice">Открытых перекличке нет.</div>`}</div>`, (root) => {
      root.querySelector("#campRollStart")?.addEventListener("click", async () => {
        try { await api("/camp/api/attendance/events", { method: "POST", body: { unit_id: Number(root.querySelector("#campRollUnit").value), kind: root.querySelector("#campRollKind").value } }); toast("Перекличка начата"); A.rollcall(ctx); } catch (e) { toast(humanError(e), true); }
      });
      root.querySelectorAll("[data-mark]").forEach((select) => select.addEventListener("change", async () => {
        if (!select.value) return;
        try { await api(`/camp/api/attendance/events/${select.dataset.mark}/marks`, { method: "POST", body: { person_id: Number(select.dataset.person), status: select.value } }); A.rollcall(ctx); } catch (e) { toast(humanError(e), true); select.value = ""; }
      }));
      root.querySelectorAll("[data-all]").forEach((b) => b.addEventListener("click", async () => {
        try { await api(`/camp/api/attendance/events/${b.dataset.all}/all-present`, { method: "POST" }); toast("Все отмечены"); A.rollcall(ctx); } catch (e) { toast(humanError(e), true); }
      }));
      root.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", async () => {
        try { await api(`/camp/api/attendance/events/${b.dataset.close}/close`, { method: "POST", body: { force: false } }); toast("Перекличка закрыта"); A.rollcall(ctx); }
        catch (e) { toast(humanError(e), true); if (e.code === "attendance_incomplete") { const note = prompt("Кто не отмечен и почему закрываем?"); if (note) { try { await api(`/camp/api/attendance/events/${b.dataset.close}/close`, { method: "POST", body: { force: true, note } }); toast("Закрыто с причиной"); A.rollcall(ctx); } catch (x) { toast(humanError(x), true); } } } }
      }));
      root.querySelectorAll("[data-force]").forEach((b) => b.addEventListener("click", async () => {
        const note = prompt("Причина закрытия без всех отметок"); if (!note) return;
        try { await api(`/camp/api/attendance/events/${b.dataset.force}/close`, { method: "POST", body: { force: true, note } }); toast("Закрыто с причиной"); A.rollcall(ctx); } catch (e) { toast(humanError(e), true); }
      }));
    });
  };

  A.requests = async (ctx) => {
    const { api, openSheet, esc, tr, humanError, toast, state } = ctx;
    const items = (await api("/camp/api/requests?limit=100")).items || [];
    const child = state.me.actor.role === "child";
    const rows = items.map((item) => {
      const canClose = !child && item.status === "claimed" && (state.me.actor.role === "director" || Number(item.claimed_by) === Number(state.me.actor.user_id));
      return [child ? esc(tr("request", item.kind)) : `<strong>${esc(item.child_name || item.child_id)}</strong>`, esc(item.unit_name || "—"), `<span class="camp-mini">${esc(item.status === "open" ? "Новая" : item.status === "claimed" ? "В работе" : "Закрыта")}</span>`, esc(item.note || ""), child ? "" : `${item.status === "open" ? `<button class="btn btn-sm btn-primary" data-claim="${item.id}">Взять</button>` : ""}${canClose ? `<button class="btn btn-sm btn-outline" data-close="${item.id}">Закрыть</button>` : ""}`];
    });
    openSheet(child ? "Мои заявки" : "Заявки", `${child ? `<div class="notice">Вожатый увидит заявку в своей очереди.</div><div class="row"><button class="btn btn-primary" data-new="call_counselor">Позвать вожатого</button><button class="btn btn-outline" data-new="help">Нужна помощь</button></div>` : ""}${table(child ? ["Тема", "Отряд", "Статус", "Комментарий", ""] : ["Ребёнок", "Отряд", "Статус", "Комментарий", ""], rows)}`, (root) => {
      root.querySelectorAll("[data-new]").forEach((b) => b.addEventListener("click", async () => {
        const note = prompt("Что случилось?"); if (note === null) return;
        try { await api("/camp/api/requests", { method: "POST", body: { kind: b.dataset.new, note } }); toast("Заявка отправлена"); A.requests(ctx); } catch (e) { toast(humanError(e), true); }
      }));
      root.querySelectorAll("[data-claim]").forEach((b) => b.addEventListener("click", async () => {
        try { await api(`/camp/api/requests/${b.dataset.claim}/claim`, { method: "POST" }); toast("Заявка взята"); A.requests(ctx); } catch (e) { toast(humanError(e), true); }
      }));
      root.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", async () => {
        const note = prompt("Что сделали?", "Проверено"); if (note === null) return;
        try { await api(`/camp/api/requests/${b.dataset.close}/close`, { method: "POST", body: { note } }); toast("Заявка закрыта"); A.requests(ctx); } catch (e) { toast(humanError(e), true); }
      }));
    });
  };
  A.alerts = async (ctx) => {
    const { api, openSheet, esc, tr, humanError, toast, state } = ctx;
    const [alertsData, playbooksData] = await Promise.all([api("/camp/api/alerts?limit=50"), api("/camp/api/alert-playbooks")]);
    const alerts = alertsData.items || [], playbooks = playbooksData.items || [];
    const canStart = ["director", "security"].includes(state.me.actor.role) || state.me.actor.role === "medic";
    const alertTitle = (kind, title) => ({ missing_child: "Пропал ребёнок", evacuation: "Эвакуация", medical: "Медицинская тревога", intruder: "Посторонний", lockdown: "Полная изоляция" }[kind] || title || kind);
    const cards = alerts.map((a) => {
      const acked = new Set((a.acks || []).filter((x) => Number(x.user_id) === Number(state.me.actor.user_id)).map((x) => Number(x.step_index)));
      let next = (a.steps || []).findIndex((_, i) => !acked.has(i)); if (next < 0) next = 0;
      const canClose = ["director", "security"].includes(state.me.actor.role) || Number(a.created_by) === Number(state.me.actor.user_id);
      return styleCard(`${esc(alertTitle(a.kind, a.title))} · ${esc(a.status === "open" ? "Открыта" : a.status === "closed" ? "Закрыта" : "Принята")}${a.drill ? " · Учение" : ""}`, `<p class="camp-mini">Запустил: ${esc(a.created_by_login || "—")} · ${esc(ctx.fmtTime(a.created_at_ms))}</p><ol>${(a.steps || []).map((s) => `<li>${esc(s.step || s)}</li>`).join("")}</ol>`, `${a.status !== "closed" ? `<button class="btn btn-sm btn-primary" data-ack="${a.id}" data-step="${next}">Подтвердить шаг ${next + 1}</button>` : ""}${a.status !== "closed" && canClose ? `<button class="btn btn-sm btn-outline" data-close-alert="${a.id}">Закрыть</button>` : ""}`);
    }).join("");
    const availablePlaybooks = state.me.actor.role === "medic" ? playbooks.filter((p) => p.kind === "medical") : playbooks;
    openSheet("Тревоги", `${canStart ? `<div class="row"><label class="grow">Что случилось<select id="campAlertKind">${availablePlaybooks.map((p) => `<option value="${p.kind}">${esc(alertTitle(p.kind, p.title))}</option>`).join("")}</select></label><label class="check"><input id="campAlertDrill" type="checkbox"> Учение</label><button class="btn btn-danger" id="campAlertStart">Запустить</button></div>` : ""}<div class="stack">${cards || `<div class="notice">Тревог нет.</div>`}</div>`, (root) => {
      root.querySelector("#campAlertStart")?.addEventListener("click", async () => {
        const kind = root.querySelector("#campAlertKind").value, drill = root.querySelector("#campAlertDrill").checked;
        if (!confirm("Запустить тревогу?")) return;
        if (!drill && !confirm("Это реальная тревога, а не учение. Запустить?")) return;
        try { await api("/camp/api/alerts", { method: "POST", body: { kind, drill } }); toast("Тревога запущена"); A.alerts(ctx); } catch (e) { toast(humanError(e), true); }
      });
      root.querySelectorAll("[data-ack]").forEach((b) => b.addEventListener("click", async () => {
        try { await api(`/camp/api/alerts/${b.dataset.ack}/ack`, { method: "POST", body: { step_index: Number(b.dataset.step) } }); toast("Шаг подтверждён"); A.alerts(ctx); } catch (e) { toast(humanError(e), true); }
      }));
      root.querySelectorAll("[data-close-alert]").forEach((b) => b.addEventListener("click", async () => {
        const after = prompt("Что сделали и что учесть?"); if (after === null) return;
        try { await api(`/camp/api/alerts/${b.dataset.closeAlert}/close`, { method: "POST", body: { after_action: after } }); toast("Тревога закрыта"); A.alerts(ctx); } catch (e) { toast(humanError(e), true); }
      }));
    });
  };

  A.digest = async (ctx) => {
    const { api, openSheet, esc, humanError, toast, state } = ctx;
    const [digestsData, peopleData] = await Promise.all([api("/camp/api/digests"), api("/camp/api/people?role=child&limit=500")]);
    const items = digestsData.items || [], children = peopleData.items || [];
    const canWrite = ["counselor", "director"].includes(state.me.actor.role);
    const rows = items.map((d) => [esc(d.date), esc(d.display_name), esc(d.text), d.sent_at_ms ? "Отправлено" : "Не отправлено", canWrite && !d.sent_at_ms ? `<button class="btn btn-sm btn-outline" data-sent="${d.person_id}" data-date="${d.date}">Отправить</button>` : ""]);
    openSheet("Дневник", `${canWrite ? `<div class="stack"><label>Ребёнок<select id="campDigestChild">${options(children, "id", "display_name")}</select></label><label>Дата<input id="campDigestDate" type="date" value="${new Date().toISOString().slice(0, 10)}"></label><label>Текст<textarea id="campDigestText" maxlength="4000"></textarea></label><button class="btn btn-primary" id="campDigestSave">Сохранить</button></div>` : `<div class="notice">Здесь только отправленные записи.</div>`}${table(["Дата", "Ребёнок", "Текст", "Статус", ""], rows)}`, (root) => {
      root.querySelector("#campDigestSave")?.addEventListener("click", async () => {
        try { await api("/camp/api/digests", { method: "POST", body: { person_id: Number(root.querySelector("#campDigestChild").value), date: root.querySelector("#campDigestDate").value, text: root.querySelector("#campDigestText").value } }); toast("Запись сохранена"); A.digest(ctx); } catch (e) { toast(humanError(e), true); }
      });
      root.querySelectorAll("[data-sent]").forEach((b) => b.addEventListener("click", async () => {
        try { await api("/camp/api/digests/sent", { method: "POST", body: { person_id: Number(b.dataset.sent), date: b.dataset.date } }); toast("Отмечено отправленным"); A.digest(ctx); } catch (e) { toast(humanError(e), true); }
      }));
    });
  };
  function parseCsv(text) {
    const lines = String(text || "").trim().split(/\r?\n/).filter((l) => l.trim());
    if (!lines.length) return [];
    const headers = lines.shift().split(",").map((v) => v.trim());
    const aliases = { "ребёнок": "child", "ребенок": "child", "вожатый": "counselor", "директор": "director", "охрана": "security", "медик": "medic", "родитель": "parent", "кухня": "kitchen" };
    return lines.map((line) => {
      const values = line.split(",").map((v) => v.trim());
      const row = Object.fromEntries(headers.map((h, i) => [h, values[i] || ""]));
      if (row.role) row.role = aliases[row.role.toLowerCase()] || row.role;
      return row;
    }).filter((r) => r.display_name);
  }

  A.import = async (ctx) => {
    const { api, openSheet, esc, humanError, toast, state } = ctx;
    const current = state.me.current_session;
    if (!current) { openSheet("Импорт", `<div class="notice">Сначала создайте смену в старом экране подготовки или через API.</div>`); return; }
    openSheet("Импорт из Excel/CSV", `<div class="notice">Колонки: display_name, role, birth_date, unit_name, badge_code, room. Роль можно писать по-русски: ребёнок, вожатый, родитель.</div>
      <textarea id="campImportText" style="min-height:130px">display_name,role,birth_date,unit_name,badge_code,room
Аня,ребёнок,2014-05-12,Отряд 1,CAMP-001,101</textarea>
      <div class="row"><button class="btn btn-primary" id="campImportPreview">Проверить</button><button class="btn btn-outline" id="campImportCommit" disabled>Импортировать</button><button class="btn btn-outline" id="campImportUndo" ${state.importBatch ? "" : "disabled"}>Отменить</button></div>
      <div id="campImportResult"></div>`, (root) => {
      root.querySelector("#campImportPreview").addEventListener("click", async () => {
        try {
          const rows = parseCsv(root.querySelector("#campImportText").value);
          if (!rows.length) { toast("Добавьте хотя бы одну строку", true); return; }
          const preview = await api("/camp/api/import/preview", { method: "POST", body: { session_id: current.id, rows } });
          state.importPreview = preview;
          const errors = preview.errors || [];
          root.querySelector("#campImportResult").innerHTML = `<div class="notice">Строк: ${preview.summary?.rows ?? rows.length}; ошибок: ${preview.summary?.errors ?? errors.length}; дублей: ${preview.summary?.duplicates ?? 0}</div>${errors.length ? `<ul>${errors.slice(0, 8).map((e) => `<li>Строка ${e.row}: ${esc(e.code)}</li>`).join("")}</ul>` : ""}`;
          root.querySelector("#campImportCommit").disabled = Boolean(errors.length);
        } catch (e) { toast(humanError(e), true); }
      });
      root.querySelector("#campImportCommit").addEventListener("click", async () => {
        if (!state.importPreview) return;
        try {
          const result = await api("/camp/api/import/commit", { method: "POST", body: { session_id: current.id, rows: state.importPreview.rows || [] } });
          state.importBatch = result.batch_id;
          toast(`Импортировано: ${result.count}`);
          try { await api("/camp/api/chats/bootstrap", { method: "POST" }); } catch (_) {}
          await ctx.loadChats();
          A.import(ctx);
        } catch (e) { toast(humanError(e), true); }
      });
      root.querySelector("#campImportUndo").addEventListener("click", async () => {
        if (!state.importBatch) return;
        if (!confirm("Отменить последний импорт?")) return;
        try { await api(`/camp/api/import/${state.importBatch}/undo`, { method: "POST" }); state.importBatch = null; toast("Импорт отменён"); A.import(ctx); } catch (e) { toast(humanError(e), true); }
      });
    });
  };

  A["new-request"] = async (ctx) => { await A.requests(ctx); };

  A.gate = async (ctx) => {
    const { api, openSheet, esc, humanError, toast } = ctx;
    openSheet("Ворота", `<label>Код из пропуска<input id="campGateCode" placeholder="Вставьте код"></label><button class="btn btn-primary" id="campGateVerify">Проверить</button><div id="campGateResult"></div>`, (root) => {
      root.querySelector("#campGateVerify").addEventListener("click", async () => {
        try {
          const result = await api(`/camp/api/pickup/verify?qr_code=${encodeURIComponent(root.querySelector("#campGateCode").value)}`);
          const p = result.item, out = Boolean(p.currently_out);
          root.querySelector("#campGateResult").innerHTML = `<div class="notice"><strong>${esc(p.display_name)}</strong><br>Взрослый: ${esc(p.adult_name)}<br>Ограничения: ${esc(p.restrictions || "нет")}<br>Сейчас: <strong>${out ? "вне лагеря" : "в лагере"}</strong><div class="actions" style="margin-top:8px"><button class="btn btn-primary" id="campGateMove">${out ? "Вернуть" : "Выпустить"}</button></div></div>`;
          root.querySelector("#campGateMove").addEventListener("click", async () => {
            try { await api("/camp/api/movements", { method: "POST", body: { person_id: Number(p.person_id), direction: out ? "in" : "out", qr_code: p.qr_code } }); toast(out ? "Ребёнок возвращён" : "Ребёнок выпущен"); A.gate(ctx); } catch (e) { toast(humanError(e), true); }
          });
        } catch (e) { toast(humanError(e), true); }
      });
    });
  };

  A.dietary = async (ctx) => {
    const { api, openSheet, esc, humanError, state } = ctx;
    try {
      const items = (await api("/camp/api/dietary")).items || [];
      const rows = items.map((i) => [esc(i.unit_name || "—"), esc(i.display_name), esc(i.room || "—"), esc(i.restriction), esc(i.note || "")]);
      openSheet("Питание", `${state.token ? `<a class="btn btn-sm btn-outline" href="/camp/api/dietary/print?session_token=${encodeURIComponent(state.token)}" target="_blank" rel="noopener">Печать для кухни</a>` : ""}${table(["Отряд", "Ребёнок", "Комната", "Ограничение", "Заметка"], rows)}`);
    } catch (e) { openSheet("Питание", `<div class="notice">${esc(humanError(e))}</div>`); }
  };

  A.consents = async (ctx) => {
    const { api, openSheet, esc, humanError } = ctx;
    try {
      const children = (await api("/camp/api/people?role=child&limit=100")).items || [];
      if (!children.length) { openSheet("Согласия", `<div class="notice">Нет привязанных детей.</div>`); return; }
      openSheet("Согласия", `<label>Ребёнок<select id="campConsentChild">${options(children, "id", "display_name")}</select></label><div id="campConsentResult" class="notice">Загрузка…</div>`, async (root) => {
        const load = async () => {
          try { const data = await api(`/camp/api/consents?person_id=${encodeURIComponent(root.querySelector("#campConsentChild").value)}`); root.querySelector("#campConsentResult").textContent = JSON.stringify(data.item?.consents || data.item || {}); }
          catch (e) { root.querySelector("#campConsentResult").textContent = humanError(e); }
        };
        root.querySelector("#campConsentChild").addEventListener("change", load); await load();
      });
    } catch (e) { openSheet("Согласия", `<div class="notice">${esc(humanError(e))}</div>`); }
  };

  A.today = () => {};
  window.CampActions = A;
})();
