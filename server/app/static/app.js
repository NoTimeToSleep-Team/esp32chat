const STATE = {
  token: localStorage.getItem('lc_session_token') || null,
  user: (function(){ try { return JSON.parse(localStorage.getItem('lc_user') || 'null'); } catch(e) { return null; } })(),
  accessMode: null,
  chatCache: {},
  ticketCache: {},
};


// Кэш имён пользователей
var _names = {};
function loadUserNames() {
  if (!STATE.token) return;
  fetch("/admin/users?session_token=" + encodeURIComponent(STATE.token) + "&limit=200")
    .then(function(r) { return r.json(); })
    .then(function(d) {
      (d.items || []).forEach(function(u) {
        _names[u.user_id] = u.display_name || u.login;
      });
    })
    .catch(function(){});
}
function userName(uid) {
  return _names[uid] || ("User #" + uid);
}
// Загружаем имена при старте и каждые 60 сек
setTimeout(loadUserNames, 500);
setInterval(loadUserNames, 60000);

function $(sel, ctx) {return (ctx||document).querySelector(sel)}
function $$(sel, ctx) {return Array.from((ctx||document).querySelectorAll(sel))}
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const [k,v] of Object.entries(attrs)) {
    if (k.startsWith('on')) e[k]=v; else if (k==='style'&&typeof v==='object') Object.assign(e.style,v);
    else if (k==='class') e.className=v; else e.setAttribute(k,v);
  }
  for (const k of kids) if (k!=null&&k!==false) e.append(typeof k==='string'?document.createTextNode(k):k);
  return e;
}

function show(el, cond) {if(cond===false)return;if(typeof el==='string')el=$(el);el&&el.classList.remove('hidden')}
function hide(el, cond) {if(cond===false)return;if(typeof el==='string')el=$(el);el&&el.classList.add('hidden')}

function toast(msg, type='info') {
  const t = el('div',{class:`toast ${type}`});
  t.append(el('span',{},String(msg)));
  const persistent = type === 'error' || type === 'warn';
  if (persistent) {
    const existing = document.querySelectorAll('.toast').length;
    t.style.bottom = (24 + existing * 56) + 'px';
    const ok = el('button',{class:'toast-btn'},'OK');
    ok.onclick = () => t.remove();
    t.append(ok);
    debugReport({stage:'toast', action:'ui-toast', ok:false, stages_done:3, error:String(msg), t3_ms:Date.now()});
  } else {
    setTimeout(()=>{t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(()=>t.remove(),300)},3000);
  }
  document.body.append(t);
}

function fmtTime(ms){const d=new Date(ms);return d.toLocaleString()}
function fmtTimeShort(ms){const d=new Date(ms);const now=new Date();const same=d.toDateString()===now.toDateString()
  ?d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})
  :d.toLocaleDateString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});return same}

function debugReport(payload) {
  try {
    if (STATE && STATE.token) payload.session_token = STATE.token;
    fetch('/debug/api/client-event', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(function(){});
  } catch(e) {}
}
window.lcDebugReport = debugReport;

function newTraceId(prefix) {
  return (prefix || 'tr') + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
}

function apiErrorMessage(d, status) {
  if (d && d.detail) {
    const det = d.detail;
    if (Array.isArray(det) && det.length) {
      const first = det[0] || {};
      const loc = Array.isArray(first.loc) && first.loc.length > 1 ? first.loc[first.loc.length - 1] : '';
      return (loc ? loc + ': ' : '') + (first.msg || 'validation error');
    }
    if (typeof det === 'string') return det;
    return det.message || det.code || `HTTP ${status}`;
  }
  return `HTTP ${status}`;
}

async function api(url, opts={}) {
  const headers={'Content-Type':'application/json'};
  if (opts.sessionHeader) headers['X-Session-Token'] = STATE.token;
  const traceId = newTraceId('tr');
  headers['X-Debug-Trace'] = traceId;
  const controller = new AbortController();
  const timeoutMs = opts.timeoutMs || 10000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const t1 = Date.now();
  try {
    const r = await fetch(url, {...opts, headers, signal: controller.signal});
    const t2 = Date.now();
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const errMsg = apiErrorMessage(d, r.status);
      debugReport({trace_id: traceId, action: url, method: (opts.method||'GET'), ok: false, status: r.status, stages_done: 2, error: errMsg, t1_ms: t1, t2_ms: t2, t3_ms: Date.now()});
      const err = new Error(errMsg);
      err.status = r.status;
      err.code = (d && d.detail && d.detail.code) ? String(d.detail.code) : null;
      throw err;
    }
    debugReport({trace_id: traceId, action: url, method: (opts.method||'GET'), ok: true, status: r.status, stages_done: 3, t1_ms: t1, t2_ms: t2, t3_ms: Date.now()});
    return d;
  } catch(e) {
    if (e.name === 'AbortError') {
      debugReport({trace_id: traceId, action: url, method: (opts.method||'GET'), ok: false, stages_done: 1, error: 'Request timeout', t1_ms: t1, t3_ms: Date.now()});
      throw new Error('Request timeout');
    }
    if (e.name!=='TypeError') throw e;
    debugReport({trace_id: traceId, action: url, method: (opts.method||'GET'), ok: false, stages_done: 1, error: 'Server unreachable', t1_ms: t1, t3_ms: Date.now()});
    throw new Error('Server unreachable');
  } finally {
    clearTimeout(timeoutId);
  }
}

async function uploadAttachment(file) {
  const form = new FormData();
  form.append('file', file);
  const traceId = newTraceId('up');
  const t1 = Date.now();
  try {
    const r = await fetch(`/media/api/attachments?session_token=${encodeURIComponent(STATE.token)}`, {method:'POST', body:form, headers:{'X-Debug-Trace': traceId}});
    const t2 = Date.now();
    const d = await r.json().catch(()=>({}));
    if (!r.ok) {
      const msg = d?.detail?.message || d?.detail?.code || `Upload failed (${r.status})`;
      debugReport({trace_id: traceId, action: '/media/api/attachments', method: 'POST', ok: false, status: r.status, stages_done: 2, error: msg, t1_ms: t1, t2_ms: t2, t3_ms: Date.now()});
      throw new Error(msg);
    }
    debugReport({trace_id: traceId, action: '/media/api/attachments', method: 'POST', ok: true, status: r.status, stages_done: 3, t1_ms: t1, t2_ms: t2, t3_ms: Date.now()});
    return d.attachment;
  } catch(e) {
    if (e.name === 'TypeError') {
      debugReport({trace_id: traceId, action: '/media/api/attachments', method: 'POST', ok: false, stages_done: 1, error: 'Server unreachable', t1_ms: t1, t3_ms: Date.now()});
      throw new Error('Server unreachable');
    }
    throw e;
  }
}

function attachmentUrl(a) {
  const base = a.download_url || `/media/api/attachments/${a.attachment_id}/download`;
  const sep = base.includes('?') ? '&' : '?';
  return `${base}${sep}session_token=${encodeURIComponent(STATE.token)}`;
}

function safeUrl(u) {
  return u.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ===== Minimal inline SVG icon set (replaces emoji glyphs) =====
const ICONS = {
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20.5 20.5L16.7 16.7"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3.5 7.5L12 13l8.5-5.5"/>',
  refresh: '<path d="M20.5 12a8.5 8.5 0 1 1-2.7-6.2"/><path d="M20.5 4.5V10h-5.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  back: '<path d="M19 12H5"/><path d="M11.5 18.5L5 12l6.5-6.5"/>',
  more: '<circle cx="12" cy="5.5" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="12" cy="18.5" r="1.7"/>',
  clip: '<path d="M20.8 11.2l-8.2 8.2a4.7 4.7 0 0 1-6.6-6.6l8.2-8.2a3.2 3.2 0 0 1 4.5 4.5l-8.2 8.2a1.7 1.7 0 0 1-2.4-2.4l7.5-7.5"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0"/><path d="M12 18v3"/>',
  send: '<path d="M21.5 2.5L10.8 13.2"/><path d="M21.5 2.5l-7 19-3.7-8.3-8.3-3.7 19-7z"/>',
  pencil: '<path d="M12.5 20H20"/><path d="M16.2 3.8a2.2 2.2 0 0 1 3.1 3.1L7.4 18.8 3.5 20l1.2-3.9L16.2 3.8z"/>',
  trash: '<path d="M3.5 6.5h17"/><path d="M9 6.5V4.2h6V6.5"/><path d="M6.5 6.5l1 13.3h9l1-13.3"/>',
  check: '<path d="M20 6.5L9.3 17.2 4 11.9"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="M8.2 12.4l2.6 2.6 5-5.2"/>',
  chat: '<path d="M20.5 12a8.5 8.5 0 0 1-8.5 8.5H8.2L3.5 23l1.4-4.9A8.5 8.5 0 1 1 20.5 12z"/>',
  flag: '<path d="M5 21V4"/><path d="M5 5h12.5l-1.6 4 1.6 4H5"/>',
  phone: '<path d="M4.5 3.5h3.7l1.8 4.4-2.3 1.5a12.5 12.5 0 0 0 6 6l1.5-2.3 4.4 1.8v3.7a1.4 1.4 0 0 1-1.5 1.4A16.5 16.5 0 0 1 3.1 5a1.4 1.4 0 0 1 1.4-1.5z"/>',
  fileText: '<path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z"/><path d="M14 3.5V8h4.5"/><path d="M9 13h6M9 16.5h4"/>',
  ticket: '<path d="M4 8.5A2 2 0 0 1 6 6.5h12a2 2 0 0 1 2 2v1a2.5 2.5 0 0 0 0 5v1a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-1a2.5 2.5 0 0 0 0-5z"/><path d="M13 6.5v11" stroke-dasharray="2 2.6"/>',
  warning: '<path d="M12 4.2l8.5 15.3H3.5z"/><path d="M12 10v4.2"/><path d="M12 17h.01"/>',
  bot: '<rect x="4.5" y="8" width="15" height="10.5" rx="3.5"/><path d="M12 4v4"/><path d="M9.5 12.6v1.2M14.5 12.6v1.2"/>',
  user: '<circle cx="12" cy="8.5" r="3.7"/><path d="M5 20.2a7.2 7.2 0 0 1 14 0"/>',
  megaphone: '<path d="M4 10.5v3l11.5 5v-13L4 10.5z"/><path d="M15.5 8.2a3.2 3.2 0 0 1 0 7.6"/><path d="M7 14v4.5"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5"/><path d="M12 16.2h.01"/>',
  messageX: '<path d="M20.5 12a8.5 8.5 0 0 1-8.5 8.5H8.2L3.5 23l1.4-4.9A8.5 8.5 0 1 1 20.5 12z"/><path d="M9.8 9.5l4.4 4.4M14.2 9.5l-4.4 4.4"/>',
  dollar: '<path d="M12 3.5v17"/><path d="M16 7.6c0-1.7-1.8-2.6-4-2.6s-4 .9-4 2.6S10 10.2 12 10.7s4 1.4 4 3.2-1.8 2.9-4 2.9-4-1-4-2.7"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.4c-.7.3-1 .8-1 1.5v.2"/><path d="M12 16.6h.01"/>',
  lock: '<rect x="4.5" y="10" width="15" height="10.5" rx="2.5"/><path d="M8 10V7.8a4 4 0 0 1 8 0V10"/>',
  unlock: '<rect x="4.5" y="10" width="15" height="10.5" rx="2.5"/><path d="M8 10V7.8a4 4 0 0 1 7.2-2.4"/>',
  save: '<path d="M5 3.5h10.5L19 7v13.5H5z"/><path d="M8.5 3.5v5.5h6V3.5"/><path d="M8.5 20.5v-6h7v6"/>',
  download: '<path d="M12 3.5v11"/><path d="M7.5 10.5L12 15l4.5-4.5"/><path d="M5 20.5h14"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  camera: '<path d="M4 8.5h3l1.5-2.5h7L17 8.5h3a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 20 19.5H4A1.5 1.5 0 0 1 2.5 18v-8A1.5 1.5 0 0 1 4 8.5z"/><circle cx="12" cy="13.5" r="3.2"/>'
};
function icon(name, cls) {
  const body = ICONS[name] || '';
  return '<svg class="ic' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true">' + body + '</svg>';
}

// ===== Avatars: photo (avatar_url) with emoji fallback =====
const AVA_URL = {}; // userId -> avatar_url | null (null = no photo / already checked)

function avatarInnerHtml(url, emoji) {
  if (url) return '<img class="ava-img" src="' + safeUrl(url) + '" alt="">';
  return esc(emoji || '');
}

async function ensureAvatarUrl(uid) {
  if (uid === null || uid === undefined) return;
  if (Object.prototype.hasOwnProperty.call(AVA_URL, uid)) return;
  AVA_URL[uid] = null;
  try {
    const d = await api(`/account/api/profile/${uid}?session_token=${encodeURIComponent(STATE.token)}`);
    const url = d && d.profile ? d.profile.avatar_url : null;
    if (!url) return;
    AVA_URL[uid] = url;
    $$('.msg-avatar[data-ava-uid="' + uid + '"]').forEach(el => {
      el.innerHTML = avatarInnerHtml(url, el.dataset.avaEmoji || '');
    });
  } catch (e) { /* ignore, emoji stays */ }
}

function renderAttachments(items) {
  if (!items?.length) return '';
  return `<div class="attachments">${items.map(a => {
    const url = attachmentUrl(a);
    const name = esc(a.filename || `attachment-${a.attachment_id}`);
    const mime = String(a.mime_type || '');
    if ((a.media_kind === 'image' || mime.startsWith('image/'))) {
      return `<a class="attachment image" href="${safeUrl(url)}" data-name="${name}" onclick="openImageLightbox(this.href, this.dataset.name);return false"><img src="${safeUrl(url)}" alt="${name}"><span>${name}</span></a>`;
    }
    if (a.media_kind === 'audio' || mime.startsWith('audio/')) {
      const isVoice = /^voice-/i.test(String(a.filename || ''));
      return `<div class="attachment audio">${isVoice ? '<span class="voice-ico">' + icon('mic') + '</span>' : ''}<audio controls preload="none" src="${safeUrl(url)}"></audio>${isVoice ? '' : `<div class="fname">${name}</div>`}</div>`;
    }
    return `<a class="attachment file" href="${safeUrl(url)}" target="_blank" rel="noopener">${icon('clip')} ${name}</a>`;
  }).join('')}</div>`;
}

let lightboxItems = [];
let lightboxIndex = 0;

function _ensureLightbox() {
  let box = document.getElementById('img-lightbox');
  if (box) return box;
  box = document.createElement('div');
  box.id = 'img-lightbox';
  box.className = 'img-lightbox';
  box.innerHTML = '<button class="img-lightbox-close" title="Close">✕</button>' +
    '<button class="img-lightbox-nav prev" title="Previous">‹</button>' +
    '<img alt="">' +
    '<button class="img-lightbox-nav next" title="Next">›</button>' +
    '<div class="img-lightbox-name"></div><div class="img-lightbox-counter"></div>';
  box.onclick = function(e) {
    if (e.target === box || e.target.classList.contains('img-lightbox-close')) closeImageLightbox();
  };
  box.querySelector('.prev').onclick = function(e) { e.stopPropagation(); lightboxStep(-1); };
  box.querySelector('.next').onclick = function(e) { e.stopPropagation(); lightboxStep(1); };
  let touchX = null;
  box.addEventListener('touchstart', function(e) { touchX = e.changedTouches[0].clientX; }, {passive: true});
  box.addEventListener('touchend', function(e) {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 40) lightboxStep(dx < 0 ? 1 : -1);
  }, {passive: true});
  document.body.appendChild(box);
  document.addEventListener('keydown', function(e) {
    const open = document.getElementById('img-lightbox');
    if (!open || !open.classList.contains('open')) return;
    if (e.key === 'Escape') closeImageLightbox();
    else if (e.key === 'ArrowLeft') lightboxStep(-1);
    else if (e.key === 'ArrowRight') lightboxStep(1);
  });
  return box;
}

function openImageLightbox(url, name) {
  const box = _ensureLightbox();
  lightboxItems = Array.from(document.querySelectorAll('a.attachment.image')).map(el => ({
    url: el.getAttribute('href'), name: el.dataset.name || ''
  }));
  if (!lightboxItems.length) lightboxItems = [{ url: url, name: name || '' }];
  lightboxIndex = lightboxItems.findIndex(x => x.url === url);
  if (lightboxIndex < 0) lightboxIndex = 0;
  showLightboxItem();
  box.classList.add('open');
}

function showLightboxItem() {
  const box = document.getElementById('img-lightbox');
  if (!box) return;
  const item = lightboxItems[lightboxIndex] || { url: '', name: '' };
  box.querySelector('img').src = item.url;
  box.querySelector('.img-lightbox-name').textContent = item.name || '';
  box.querySelector('.img-lightbox-counter').textContent =
    lightboxItems.length > 1 ? (lightboxIndex + 1) + ' / ' + lightboxItems.length : '';
  const multi = lightboxItems.length > 1;
  box.querySelector('.prev').style.display = multi ? '' : 'none';
  box.querySelector('.next').style.display = multi ? '' : 'none';
}

function lightboxStep(delta) {
  if (lightboxItems.length < 2) return;
  lightboxIndex = (lightboxIndex + delta + lightboxItems.length) % lightboxItems.length;
  showLightboxItem();
}

function closeImageLightbox() {
  const box = document.getElementById('img-lightbox');
  if (!box) return;
  box.classList.remove('open');
  const img = box.querySelector('img');
  if (img) img.removeAttribute('src');
}

async function currentMode() {
  try {
    const data = await api('/mode');
    STATE.accessMode = data.access_mode || 'closed';
  } catch(e) {
    STATE.accessMode = 'closed';
  }
  return STATE.accessMode;
}

function requireAuth() {
  if (!STATE.token) {window.location.hash='#/login';return false}
  return true;
}

function setAuth(data) {
  STATE.token = data.session.token;
  STATE.user = data.user;
  localStorage.setItem('lc_session_token', STATE.token);
  localStorage.setItem('lc_user', JSON.stringify(data.user));
  updateNav();
}

function clearAuth() {
  STATE.token = null;
  STATE.user = null;
  localStorage.removeItem('lc_session_token');
  localStorage.removeItem('lc_user');
  STATE.chatCache = {};
  updateNav();
  window.location.hash = '#/login';
}

function updateNav() {
  const authed = !!STATE.token;
  const isAdmin = STATE.user?.role === 'admin' || STATE.user?.role === 'moderator';
  const nav = document.querySelector('.nav');
  if (authed) {
    if (nav) nav.style.display = '';
    show('#nav-links');
    show('#nav-right');
  } else {
    if (nav) nav.style.display = 'none';
    hide('#nav-links');
    hide('#nav-right');
  }
  $$('.nav-links a').forEach(a => {
    if (!authed && !a.dataset.public) a.style.display = 'none'; else a.style.display = '';
  });
  const adminLink = $('#admin-link');
  if (adminLink) adminLink.style.display = isAdmin ? '' : 'none';
  const netLink = $('#network-link');
  if (netLink) netLink.style.display = isAdmin ? '' : 'none';
  const userEl = $('#nav-user');
  if (userEl) userEl.textContent = STATE.user?.login || '';
  $$('.nav-links a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === window.location.hash);
  });
}

/* ===== PAGES ===== */

async function renderLogin() {
  const c = $('#content');
  const accessMode = await currentMode();
  let mode = 'login';
  function renderForm() {
    const isLogin = mode === 'login';
    const isApplication = mode === 'application';
    const isOpen = accessMode === 'open';
    if (isApplication) {
      c.innerHTML = `
        <div class="login-page">
          <div class="login-card wide">
            <div class="login-title">Access Application</div>
            <div class="login-subtitle">Заявка на доступ / closed mode</div>
            <div id="login-error" class="login-error"></div>
            <div class="form-row"><div class="form-group"><label>First name</label><input class="form-input" id="app-first" autocomplete="given-name"></div><div class="form-group"><label>Last name</label><input class="form-input" id="app-last" autocomplete="family-name"></div></div>
            <div class="form-group"><label>Phone</label><input class="form-input" id="app-phone" type="tel" placeholder="+7..."></div>
            <div class="form-group"><label>Email</label><input class="form-input" id="app-email" type="email" placeholder="name@example.local"></div>
            <div class="form-group"><label>Class / group</label><input class="form-input" id="app-class" placeholder="9A / group"></div>
            <label class="check-row"><input id="app-school" type="checkbox"> <span>Учусь в школе 1575 / school member</span></label>
            <button class="btn btn-primary" id="app-submit" style="width:100%;justify-content:center">Submit application</button>
            <div style="text-align:center;margin-top:16px;font-size:14px;color:var(--text2)"><a href="#" id="login-toggle">Back to login</a></div>
          </div>
        </div>`;
      $('#login-toggle').onclick = (e) => { e.preventDefault(); mode = 'login'; renderForm(); };
      $('#app-submit').onclick = doApplication;
      return;
    }
    c.innerHTML = `
      <div class="login-page">
        <div class="login-card">
          <div class="login-title">Local Chat</div>
          <div class="login-subtitle">${isLogin ? `Sign in · ${accessMode} mode` : 'Create an account'}</div>
          <div id="login-error" class="login-error"></div>
          <div class="form-group">
            <label>Login</label>
            <input class="form-input" id="login-login" type="text" placeholder="Enter login" autocomplete="username">
          </div>
          <div class="form-group">
            <label>Password</label>
            <input class="form-input" id="login-pass" type="password" placeholder="${isLogin ? 'Enter password' : 'Password (min 8 chars)'}" autocomplete="${isLogin ? 'current-password' : 'new-password'}">
          </div>
          ${isLogin ? '' : `<div class="form-group"><label>Phone</label><input class="form-input" id="login-phone" type="text" placeholder="+7..."></div>`}
          <button class="btn btn-primary" id="login-btn" style="width:100%;justify-content:center">${isLogin ? 'Sign In' : 'Create Account'}</button>
          ${isOpen && isLogin ? `<button class="btn btn-outline" id="guest-btn" style="width:100%;justify-content:center;margin-top:10px">Continue as guest</button>` : ''}
          <div style="text-align:center;margin-top:16px;font-size:14px;color:var(--text2)">
            ${isOpen ? (isLogin ? "Don't have an account? <a href='#' id='login-toggle'>Register</a>" : "Already have an account? <a href='#' id='login-toggle'>Sign in</a>") : "No account? <a href='#' id='login-toggle'>Submit application</a>"}
          </div>
        </div>
      </div>`;
    $('#login-toggle').onclick = (e) => { e.preventDefault(); mode = isOpen ? (isLogin ? 'register' : 'login') : 'application'; renderForm(); };
    const btn = $('#login-btn');
    const loginInput = $('#login-login');
    const passInput = $('#login-pass');
    const phoneInput = $('#login-phone');
    btn.onclick = isLogin ? doLogin : doRegister;
    const guestBtn = $('#guest-btn');
    if (guestBtn) guestBtn.onclick = doGuestLogin;
    loginInput.onkeydown = e => {if(e.key==='Enter')btn.click()};
    passInput.onkeydown = e => {if(e.key==='Enter')btn.click()};
  }
  async function doLogin() {
    const login = $('#login-login').value.trim();
    const pass = $('#login-pass').value;
    if (!login || !pass) {show('#login-error');$('#login-error').textContent='Fill in all fields';return}
    hide('#login-error');
    $('#login-btn').disabled = true; $('#login-btn').textContent = 'Signing in...';
    try {
      const data = await api('/auth/login', {method:'POST',body:JSON.stringify({login,password:pass,client_kind:'web'})});
      if (data.status !== 'ok') throw new Error(data.message || 'Auth failed');
      setAuth(data); window.location.hash = '#/chat';
    } catch(e) { show('#login-error'); $('#login-error').textContent = e.message; $('#login-btn').disabled = false; $('#login-btn').textContent = 'Sign In'; }
  }
  async function doRegister() {
    const login = $('#login-login').value.trim();
    const pass = $('#login-pass').value;
    const phoneInputEl = $('#login-phone');
    let phone = (phoneInputEl?.value||'').trim() || 'No Phone';
    if (phone !== 'No Phone') {
      const cleanPhone = phone.replace(/[^0-9+]/g, '');
      if (!/^\+?[0-9]{10,15}$/.test(cleanPhone)) { show('#login-error'); document.getElementById('login-error').textContent = 'Invalid phone. Use +79991234567'; return; }
      phone = cleanPhone;
      if (phoneInputEl) phoneInputEl.value = cleanPhone;
    }
    if (!login || !pass) {show('#login-error');$('#login-error').textContent='Fill in all fields';return}
    $('#login-btn').disabled = true; $('#login-btn').textContent = 'Registering...';
    try {
      const data = await api('/auth/register', {method:'POST',body:JSON.stringify({login,password:pass,phone,device_id:'web-'+Date.now().toString(36),client_kind:'web'})});
      if (data.status !== 'ok') throw new Error(data.message || 'Registration failed');
      setAuth(data); window.location.hash = '#/chat';
    } catch(e) { show('#login-error'); $('#login-error').textContent = e.message; $('#login-btn').disabled = false; $('#login-btn').textContent = 'Create Account'; }
  }
  async function doGuestLogin() {
    hide('#login-error');
    $('#guest-btn').disabled = true; $('#guest-btn').textContent = 'Signing in...';
    try {
      const data = await api('/auth/guest', {method:'POST',body:JSON.stringify({client_kind:'web'})});
      if (data.status !== 'ok') throw new Error(data.message || 'Guest login failed');
      setAuth(data); window.location.hash = '#/chat';
    } catch(e) { show('#login-error'); $('#login-error').textContent = e.message; $('#guest-btn').disabled = false; $('#guest-btn').textContent = 'Continue as guest'; }
  }
  async function doApplication() {
    const payload = {
      first_name: $('#app-first').value.trim(),
      last_name: $('#app-last').value.trim(),
      phone: $('#app-phone').value.trim(),
      email: $('#app-email').value.trim(),
      class_group: $('#app-class').value.trim(),
      is_school_member: $('#app-school').checked,
    };
    if (!payload.first_name || !payload.last_name || !payload.phone || !payload.email || !payload.class_group) {show('#login-error');$('#login-error').textContent='Fill in all application fields';return}
    hide('#login-error'); $('#app-submit').disabled = true; $('#app-submit').textContent = 'Submitting...';
    try {
      await api('/applications', {method:'POST', body:JSON.stringify(payload)});
      toast('Application submitted', 'success');
      mode = 'login'; renderForm();
    } catch(e) { show('#login-error'); $('#login-error').textContent = e.message; $('#app-submit').disabled = false; $('#app-submit').textContent = 'Submit application'; }
  }
  renderForm();
}

async function renderChat() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">${t('chat')}</div><div class="page-subtitle">${t('chat_subtitle')}</div></div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-sm btn-outline" id="dm-chat-btn">+ ${t('dm')}</button>
        <button class="btn btn-success btn-sm" id="create-chat-btn">+ ${t('new_chat')}</button>
      </div>
    </div>
    <div id="create-chat-modal" class="overlay hidden">
      <div class="modal">
        <h3>New Chat</h3>
        <div class="form-group"><label>Title</label><input class="form-input" id="chat-title"></div>
        <div class="form-group"><label>Description</label><textarea class="form-input" id="chat-desc" rows="3"></textarea></div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn btn-outline" id="chat-create-cancel">Cancel</button>
          <button class="btn btn-primary" id="chat-create-submit">Create</button>
        </div>
      </div>
    </div>
    <div id="dm-modal" class="overlay hidden">
      <div class="modal">
        <h3>Новая личка</h3>
        <div class="form-group"><input class="form-input" id="dm-user-search" placeholder="Поиск по логину..."></div>
        <div id="dm-user-list" style="max-height:240px;overflow-y:auto"></div>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
          <button class="btn btn-outline" id="dm-cancel">Cancel</button>
        </div>
      </div>
    </div>
    <div class="chat-layout show-list" id="chat-layout">
      <aside class="chat-side">
        <div class="chat-side-head">
          <div class="chat-side-title only-desktop"><span>${t('chat')}</span><button class="mini" id="chat-refresh" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button></div>
          <div class="chat-top">
            <button class="mini only-mobile" id="chat-menu-btn" title="${t('menu')}" aria-label="${t('menu')}">${icon('menu')}</button>
            <div class="chat-search">${icon('search')}<input id="chat-search-input" placeholder="${t('search_user')}"></div>
            <button class="mini only-mobile mini-pill" id="chat-dm-btn" title="${t('dm')}" aria-label="${t('dm')}"><span class="mi-ico">${icon('mail')}</span><span class="mi-lbl">${t('dm')}</span></button>
            <button class="mini only-mobile" id="chat-refresh-m" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button>
            <button class="mini only-mobile" id="chat-new-btn" title="${t('new_chat')}" aria-label="${t('new_chat')}">${icon('plus')}</button>
          </div>
        </div>
        <div id="chat-list" class="chat-list"><div class="loading"><div class="spinner"></div></div></div>
      </aside>
      <section class="chat-pane">
        <div id="chat-messages" class="chat-messages">
          <div class="empty"><div class="empty-icon">${icon('chat')}</div><div class="empty-text">${t('select_chat')}</div></div>
        </div>
      </section>
    </div>`;
  try {
    const data = await api(`/chat/api/chats?session_token=${encodeURIComponent(STATE.token)}`);
    if (!data.items?.length) {
      $('#chat-list').innerHTML = `<div class="empty"><div class="empty-text">${t('no_chats')}</div></div>`;
      return;
    }
    const list = el('div');
    data.items.forEach(chat => {
      const item = el('div',{class:'chat-item'});
      let displayTitle = chat.title;
      if (displayTitle.includes(' & ')) {
        const parts = displayTitle.split(' & ');
        displayTitle = parts.filter(p => p !== STATE.user?.login).join(' & ') || displayTitle;
      }
      const cav = chatAvaFor(displayTitle, chat.chat_id);
      item.innerHTML = `<div class="chat-ava" style="background:${cav.color}">${esc(cav.initials)}</div>
        <div class="chat-item-main">
          <div class="chat-item-title">${esc(displayTitle)}</div>
          <div class="chat-item-desc">${chat.description ? esc(chat.description) : '#' + chat.chat_id}</div>
        </div>`;
      item.dataset.search = (displayTitle + ' ' + (chat.description || '')).toLowerCase();
      item.onclick = () => loadChatMessages(chat.chat_id, chat.title, item);
      list.append(item);
    });
    $('#chat-list').innerHTML = '';
    $('#chat-list').append(list);
    // auto-select first
    if (data.items.length && list.firstChild) {
      list.firstChild.click();
    }
    $('#chat-layout').classList.add('show-list');
  } catch(e) {
    $('#chat-list').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
  const chatSearchEl = $('#chat-search-input');
  if (chatSearchEl) chatSearchEl.oninput = () => {
    const q = chatSearchEl.value.trim().toLowerCase();
    $$('#chat-list .chat-item').forEach(it => {
      it.style.display = (!q || (it.dataset.search || '').includes(q)) ? '' : 'none';
    });
  };
  const chatRefreshEl = $('#chat-refresh');
  if (chatRefreshEl) chatRefreshEl.onclick = () => renderChat();
  const chatRefreshM = $('#chat-refresh-m');
  if (chatRefreshM) chatRefreshM.onclick = () => renderChat();
  const chatMenuBtn = $('#chat-menu-btn');
  if (chatMenuBtn) chatMenuBtn.onclick = (ev) => {
    ev.stopPropagation();
    document.body.classList.add('menu-open');
    $('#nav-links').classList.add('open');
  };
  const chatDmBtn = $('#chat-dm-btn');
  if (chatDmBtn) chatDmBtn.onclick = () => { const b = $('#dm-chat-btn'); if (b) b.click(); };
  const chatNewBtn = $('#chat-new-btn');
  if (chatNewBtn) chatNewBtn.onclick = () => { const b = $('#create-chat-btn'); if (b) b.click(); };
  $('#create-chat-btn').onclick = () => show('#create-chat-modal');
  $('#chat-create-cancel').onclick = () => { hide('#create-chat-modal'); $('#chat-title').value=''; $('#chat-desc').value=''; };
  $('#chat-create-submit').onclick = async () => { 
    const title = $('#chat-title').value.trim();
    const desc = $('#chat-desc').value.trim();
    if (!title) { toast('Enter a title', 'error'); return; }
    try {
      await api('/chat/api/chats', {
        method:'POST',
        body:JSON.stringify({session_token:STATE.token, title, description:desc||undefined})
      });
      toast('Chat created', 'success');
      hide('#create-chat-modal');
      $('#chat-title').value=''; $('#chat-desc').value='';
      renderChat();
    } catch(e) { toast(e.message, 'error'); }
  };
  // DM modal
  $('#dm-chat-btn').onclick = () => { show('#dm-modal'); $('#dm-user-search').value=''; doDMSearch(); $('#dm-user-search').focus(); };
  $('#dm-cancel').onclick = () => { hide('#dm-modal'); $('#dm-user-search').value=''; };
  let dmSearchTimer = null;
  $('#dm-user-search').oninput = () => {
    clearTimeout(dmSearchTimer);
    dmSearchTimer = setTimeout(doDMSearch, 300);
  };
  async function doDMSearch() {
    const q = $('#dm-user-search').value.trim();
    const list = $('#dm-user-list');
    if (!q) { list.innerHTML = '<div style="color:var(--text2);text-align:center;padding:16px">Введите логин для поиска</div>'; return; }
    list.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
      const data = await api(`/chat/api/users/search?session_token=${encodeURIComponent(STATE.token)}&q=${encodeURIComponent(q)}`);
      if (!data.items?.length) { list.innerHTML = '<div style="color:var(--text2);text-align:center;padding:16px">Пользователи не найдены</div>'; return; }
      list.innerHTML = '';
      data.items.forEach(u => {
        if (u.user_id === STATE.user?.id) return;
        const item = el('div',{class:'dm-user-item',style:'padding:10px;cursor:pointer;border-bottom:1px solid var(--border);border-radius:4px'});
        item.innerHTML = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${u.status==='banned'?'#f85149':u.status==='blocked'?'#d29922':'var(--border)'};margin-right:6px"></span><strong>${esc(u.login)}</strong> <span style="color:var(--text2);font-size:12px">#${u.user_id}</span>`;
        item.onmouseenter = () => item.style.background = 'var(--bg3)';
        item.onmouseleave = () => item.style.background = '';
        item.onclick = async () => { 
          try {
            const dm = await api('/chat/api/dm', {method:'POST',body:JSON.stringify({session_token:STATE.token,target_user_id:u.user_id})});
            toast(`Личка с ${esc(u.login)} открыта`, 'success');
            hide('#dm-modal');
            $('#dm-user-search').value='';
            renderChat();
            setTimeout(() => { const items = $$('#chat-list .chat-item'); if(items.length){ items[0].click(); } }, 500);
          } catch(e) { toast(e.message, 'error'); }
        };
        list.append(item);
      });
    } catch(e) { list.innerHTML = `<div style="color:var(--accent4);text-align:center;padding:16px">${esc(e.message)}</div>`; }
  }
}

let currentChatId = null;
let currentChatTitle = '';
let currentChatDesc = '';
let messagesPollTimer = null;
let pendingFiles = [];
const MAX_ATTACH_FILES = 8;
const MAX_UPLOAD_MB = 10;
const FILE_ACCEPT = "image/*,audio/*,video/mp4,video/webm,video/quicktime,video/x-msvideo,video/x-matroska,video/mpeg,video/3gpp,.flac,.aac,.opus,.mid,.bmp,.tiff,.avif,.ico,.avi,.mkv,.mpeg,.3gp,.pdf,.txt,.md,.zip,.rar,.7z,.gz,.tar,.bz2,.xz,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.rtf,.epub,.csv,.json,.yaml,.toml,.vtt,.srt";

function fmtBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
}

function fileChipsHtml(files) {
  return files.map((f, i) => {
    const isAudio = /^audio\//.test(f.type || '') || /\.(m4a|webm|ogg|opus|mp3|wav|aac|flac)$/i.test(f.name || '');
    if (isAudio) {
      let url = '';
      try { url = URL.createObjectURL(f); } catch (e) { url = ''; }
      return `<span class="attach-chip voice"><audio controls preload="metadata" src="${url}"></audio><span class="attach-size">${fmtBytes(f.size)}</span><button class="attach-remove" data-i="${i}" title="${t('remove')}">${icon('x')}</button></span>`;
    }
    return `<span class="attach-chip"><span class="attach-name">${icon('clip')} ${esc(f.name)}</span><span class="attach-size">${fmtBytes(f.size)}</span><button class="attach-remove" data-i="${i}" title="${t('remove')}">${icon('x')}</button></span>`;
  }).join('');
}

function wireFileChips(box, files, onRemove) {
  if (!box) return;
  box.querySelectorAll('.attach-remove').forEach(b => {
    b.onclick = () => { onRemove(Number(b.dataset.i)); };
  });
}

function addPendingFiles(list) {
  const files = Array.from(list || []);
  for (const f of files) {
    if (pendingFiles.length >= MAX_ATTACH_FILES) { toast(t('too_many_files'), 'error'); break; }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) { toast(`${f.name}: ${t('file_too_large')} (${MAX_UPLOAD_MB} MB)`, 'error'); continue; }
    if (pendingFiles.some(x => x.name === f.name && x.size === f.size)) continue;
    pendingFiles.push(f);
  }
  renderAttachPreview();
}

// ===== Voice messages (MediaRecorder) =====
// getUserMedia needs a secure context (https or localhost). On the plain-http
// portal the mic button explains this and suggests attaching an audio file.
const VOICE_MAX_SEC = 300;
let voiceRec = null;
let voiceChunks = [];
let voiceStream = null;
let voiceTimer = null;
let voiceStartMs = 0;

function voiceSupported() {
  return !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.isSecureContext);
}

function voicePickMime() {
  const candidates = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
  for (const c of candidates) {
    try { if (MediaRecorder.isTypeSupported(c)) return c; } catch (e) {}
  }
  return '';
}

function voiceExt(mime) {
  if (/mp4|m4a|aac/.test(mime)) return 'm4a';
  if (/ogg|opus/.test(mime)) return 'ogg';
  if (/wav/.test(mime)) return 'wav';
  return 'webm';
}

function voiceTick() {
  const timer = $('#voice-timer');
  const sec = Math.floor((Date.now() - voiceStartMs) / 1000);
  if (timer) timer.textContent = Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
  if (sec >= VOICE_MAX_SEC) voiceStop();
}

function voiceCleanup() {
  if (voiceTimer) { clearInterval(voiceTimer); voiceTimer = null; }
  if (voiceStream) { voiceStream.getTracks().forEach(tr => tr.stop()); voiceStream = null; }
  voiceRec = null;
  const rec = $('#voice-rec');
  const mic = $('#mic-btn');
  if (rec) rec.classList.add('hidden');
  if (mic) mic.classList.remove('recording');
}

async function voiceStart() {
  if (!voiceSupported()) { toast(t('voice_need_https'), 'error'); return; }
  if (voiceRec) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch (e) {
    toast(t('voice_no_mic'), 'error');
    return;
  }
  voiceStream = stream;
  voiceChunks = [];
  const mime = voicePickMime();
  try {
    voiceRec = mime ? new MediaRecorder(stream, {mimeType: mime}) : new MediaRecorder(stream);
  } catch (e) {
    voiceRec = new MediaRecorder(stream);
  }
  const actualMime = voiceRec.mimeType || mime || 'audio/webm';
  voiceRec.ondataavailable = (e) => { if (e.data && e.data.size) voiceChunks.push(e.data); };
  voiceRec.onstop = () => {
    const blob = new Blob(voiceChunks, {type: actualMime});
    voiceChunks = [];
    voiceCleanup();
    if (blob.size > 0) voiceAttach(blob, actualMime);
  };
  voiceStartMs = Date.now();
  try { voiceRec.start(250); } catch (e) { voiceCleanup(); toast(t('voice_no_mic'), 'error'); return; }
  const rec = $('#voice-rec');
  const mic = $('#mic-btn');
  const timer = $('#voice-timer');
  if (rec) rec.classList.remove('hidden');
  if (mic) mic.classList.add('recording');
  if (timer) timer.textContent = '0:00';
  voiceTimer = setInterval(voiceTick, 250);
}

function voiceStop() {
  if (voiceRec && voiceRec.state !== 'inactive') {
    try { voiceRec.stop(); return; } catch (e) {}
  }
  voiceCleanup();
}

function voiceCancel() {
  if (voiceRec && voiceRec.state !== 'inactive') {
    voiceRec.onstop = null;
    try { voiceRec.stop(); } catch (e) {}
  }
  voiceChunks = [];
  voiceCleanup();
}

function voiceAttach(blob, mime) {
  if (blob.size > MAX_UPLOAD_MB * 1024 * 1024) { toast(t('file_too_large'), 'error'); return; }
  if (pendingFiles.length >= MAX_ATTACH_FILES) { toast(t('too_many_files'), 'error'); return; }
  const file = new File([blob], 'voice-' + Date.now() + '.' + voiceExt(mime), {type: mime});
  pendingFiles.push(file);
  renderAttachPreview();
}

function renderAttachPreview() {
  const box = $('#attach-preview');
  if (!box) return;
  if (!pendingFiles.length) { box.innerHTML = ''; return; }
  box.innerHTML = fileChipsHtml(pendingFiles);
  wireFileChips(box, pendingFiles, (i) => { pendingFiles.splice(i, 1); renderAttachPreview(); });
}

async function loadChatMessages(chatId, title, itemEl) {
  $$('.chat-item.active').forEach(e => e.classList.remove('active'));
  if (itemEl) itemEl.classList.add('active');
  currentChatId = chatId;
  currentChatTitle = title;
  currentChatDesc = itemEl ? ((itemEl.querySelector('.chat-item-desc') || {}).textContent || '') : '';
  const lay = $('#chat-layout');
  if (lay) lay.classList.remove('show-list');
  const cm = $('#chat-messages');
  if (cm) { cm.classList.remove('fade-switch'); void cm.offsetWidth; cm.classList.add('fade-switch'); }
  msgLoadOffset = 0;
  if (messagesPollTimer) clearInterval(messagesPollTimer);
  await doLoadMessages({force:true});
  // messagesPollTimer = setInterval(doLoadMessages, 10000); // отключено — только при отправке
}

let msgLoadOffset = 0;

function buildMessageEl(m) {
  const isMe = m.author_user_id === STATE.user?.id;
  var emojis = ['🐱','🐶','🐼','🦊','🐸','🐵','🦁','🐮','🐷','🐭','🐹','🐰','🐻','🐨','🐯','🐙','🦄','🐳','🐧','🐤'];
  var uemoji = emojis[(m.author_user_id||0) % emojis.length];
  var initial = m.author_avatar_emoji || uemoji;
  const div = el('div',{class:'msg' + (isMe ? ' out' : '')});
  div.dataset.mid = m.message_id;
  div.dataset.day = fmtDayKey(m.created_at_ms);
  const authorName = isMe ? esc(STATE.user?.login||'You') : esc(m.author_login || userName(m.author_user_id));
  const avaUrl = AVA_URL[m.author_user_id];
  if (!avaUrl) ensureAvatarUrl(m.author_user_id);
  div.innerHTML = `
    <div class="msg-avatar" data-ava-uid="${m.author_user_id}" data-ava-emoji="${esc(initial)}" style="cursor:pointer" onclick="viewUserProfile(${m.author_user_id})" title="View profile">${avatarInnerHtml(avaUrl, initial)}</div>
    <div class="msg-body">
      ${isMe ? '' : `<div class="msg-header"><span class="msg-author">${authorName}</span></div>`}
      <div class="msg-text">${esc(m.body_text || '')}${m.edited_at_ms ? ' <span class="edited">(edited)</span>' : ''}</div>
      ${renderAttachments(m.attachments)}
      <div class="msg-meta">
        <span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span>
        ${isMe ? '<span class="msg-tick" title="отправлено">' + icon('check') + '</span>' : ''}
        ${isMe ? '<span class="msg-actions"><button title="Edit" onclick="editMsg(' + m.message_id + ',this)">' + icon('pencil') + '</button><button title="Delete" onclick="confirmDel(' + m.message_id + ')">' + icon('trash') + '</button></span>' : ''}
      </div>
    </div>`;
  return div;
}

async function doLoadMessages(opts) {
  opts = opts || {};
  if (!currentChatId) return;
  const container = $('#chat-messages');
  // Не перерисовывать если пользователь печатает или ушёл вверх (кроме force/older)
  var oldInput2 = document.getElementById('msg-input');
  if (!opts.force && oldInput2 && oldInput2.value.trim()) return;
  var msgList2 = document.getElementById('msg-list');
  if (!opts.force && !opts.older && msgList2 && (msgList2.scrollHeight - msgList2.scrollTop - msgList2.clientHeight > 100)) return;
  const limit = 50;
  try {
    if (opts.older) {
      const list = $('#msg-list');
      if (!list || list._olderLoading) return;
      list._olderLoading = true;
      try {
        const data = await api(`/chat/api/chats/${currentChatId}/messages?session_token=${encodeURIComponent(STATE.token)}&limit=${limit}&offset=${msgLoadOffset}`);
        const older = data.items || [];
        if (!older.length) return;
        const prevHeight = list.scrollHeight;
        const prevTop = list.scrollTop;
        const anchor = list.querySelector('.load-older');
        const fragment = document.createDocumentFragment();
        let lastDay = null;
        older.forEach(m => {
          const day = fmtDayKey(m.created_at_ms);
          if (day !== lastDay) { fragment.append(daySepEl(m.created_at_ms)); lastDay = day; }
          fragment.append(buildMessageEl(m));
        });
        const nextEl = anchor ? anchor.nextSibling : list.firstChild;
        const nextDay = nextEl && nextEl.dataset ? nextEl.dataset.day : null;
        list.insertBefore(fragment, nextEl);
        if (nextDay && lastDay && nextDay !== lastDay) list.insertBefore(daySepEl(older[older.length - 1].created_at_ms), nextEl);
        msgLoadOffset += older.length;
        if (older.length < limit && anchor) anchor.remove();
        list.scrollTop = prevTop + (list.scrollHeight - prevHeight);
      } finally {
        list._olderLoading = false;
      }
      return;
    }
    const data = await api(`/chat/api/chats/${currentChatId}/messages?session_token=${encodeURIComponent(STATE.token)}&limit=${limit}`);
    const msgs = data.items || [];
    var oldList = document.getElementById("msg-list");
    var wasAtBottom = !oldList || (oldList.scrollHeight - oldList.scrollTop - oldList.clientHeight < 50);
    var oldScrollTop = oldList ? oldList.scrollTop : 0;
    const cav = chatAvaFor(currentChatTitle, currentChatId);
    container.innerHTML = `
      <div class="chead">
        <button class="chat-back" id="chat-back" title="${t('back_login')}" aria-label="${t('back_login')}">${icon('back')}</button>
        <div class="chat-ava" style="background:${cav.color}">${esc(cav.initials)}</div>
        <div class="chead-info">
          <div class="t1">${esc(currentChatTitle)}</div>
          <div class="t2">${esc(currentChatDesc || '#' + currentChatId)}</div>
        </div>
        <span class="spacer"></span>
        <button class="icon-btn" id="chat-reload" title="${t('refresh')}" aria-label="${t('refresh')}">${icon('refresh')}</button>
        <button class="icon-btn" id="chat-more" title="${t('description')}" aria-label="${t('description')}">${icon('more', 'fill')}</button>
      </div>
      <div id="msg-list" class="msg-list"></div>
      <div class="comp">
        <div id="attach-preview" class="attach-preview"></div>
        <div id="voice-rec" class="voice-rec hidden">
          <span class="rec-dot"></span>
          <span id="voice-timer" class="rec-time">0:00</span>
          <span class="spacer"></span>
          <button class="btn btn-sm btn-outline" id="voice-cancel">${t('cancel')}</button>
          <button class="btn btn-sm btn-primary" id="voice-stop">${t('voice_stop')}</button>
        </div>
        <div class="comp-field">
          <input id="msg-file" type="file" multiple style="display:none" accept="${FILE_ACCEPT}">
          <button class="comp-btn" id="attach-btn" title="${t('attach')}" aria-label="${t('attach')}">${icon('clip')}</button>
          <button class="comp-btn" id="mic-btn" title="${t('voice_msg')}" aria-label="${t('voice_msg')}">${icon('mic')}</button>
          <textarea id="msg-input" placeholder="${t('type_msg')}" rows="1"></textarea>
          <button class="comp-btn send" id="send-btn" title="${t('send')}" aria-label="${t('send')}">${icon('send')}</button>
        </div>
      </div>`;
    const list = $('#msg-list');
    if (msgs.length >= limit) {
      const olderBtn = el('button',{class:'btn btn-sm btn-outline load-older'},t('load_older'));
      olderBtn.onclick = () => doLoadMessages({older:true});
      list.append(olderBtn);
    }
    let firstDay = null;
    msgs.forEach(m => {
      const day = fmtDayKey(m.created_at_ms);
      if (day !== firstDay) { list.append(daySepEl(m.created_at_ms)); firstDay = day; }
      list.append(buildMessageEl(m));
    });
    msgLoadOffset = msgs.length;
    if (opts.newMid) {
      const newEl = list.querySelector('.msg[data-mid="' + opts.newMid + '"]');
      if (newEl) newEl.classList.add('new');
    }
    if (opts.force || wasAtBottom) {
      requestAnimationFrame(function() {
        if (!list) return;
        if (opts.smooth) list.scrollTo({top: list.scrollHeight, behavior: 'smooth'});
        else list.scrollTop = list.scrollHeight;
      });
    } else { list.scrollTop = oldScrollTop; }
    list._stickBottom = opts.force || wasAtBottom;
    list.querySelectorAll('img').forEach(im => {
      im.onload = () => { if (list._stickBottom) list.scrollTop = list.scrollHeight; };
    });
    list.onscroll = function() {
      list._stickBottom = (list.scrollHeight - list.scrollTop - list.clientHeight < 60);
      if (list.scrollTop < 40 && list.querySelector('.load-older')) doLoadMessages({older:true});
    };
    const backEl = $('#chat-back');
    if (backEl) backEl.onclick = () => { const lay = $('#chat-layout'); if (lay) lay.classList.add('show-list'); };
    const reloadEl = $('#chat-reload');
    if (reloadEl) reloadEl.onclick = () => doLoadMessages({force:true});
    const moreEl = $('#chat-more');
    if (moreEl) moreEl.onclick = showChatInfo;
    $('#send-btn').onclick = sendMessage;
    const msgFile = $('#msg-file');
    if ($('#attach-btn')) $('#attach-btn').onclick = () => msgFile && msgFile.click();
    if (msgFile) msgFile.onchange = () => { addPendingFiles(msgFile.files); msgFile.value = ''; };
    const micBtn = $('#mic-btn');
    if (micBtn) micBtn.onclick = () => { if (voiceRec) voiceStop(); else voiceStart(); };
    const voiceStopBtn = $('#voice-stop');
    if (voiceStopBtn) voiceStopBtn.onclick = voiceStop;
    const voiceCancelBtn = $('#voice-cancel');
    if (voiceCancelBtn) voiceCancelBtn.onclick = voiceCancel;
    renderAttachPreview();
    const miEl = $('#msg-input');
    miEl.onkeydown = e => {if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}};
    miEl.oninput = () => { miEl.style.height = 'auto'; miEl.style.height = Math.min(miEl.scrollHeight, 120) + 'px'; };
    miEl.onfocus = () => {
      list._stickBottom = true;
      setTimeout(function(){ if (list) list.scrollTop = list.scrollHeight; }, 300);
    };
  } catch(e) {
    if (container) container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function sendMessage() {
  const input = $('#msg-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text && !pendingFiles.length) return;
  const files = pendingFiles.slice();
  const sendBtn = $('#send-btn');
  const attachBtn = $('#attach-btn');
  if (sendBtn) { sendBtn.disabled = true; sendBtn.classList.add('busy'); }
  if (attachBtn) attachBtn.disabled = true;
  if (files.length) toast(t('uploading'), 'info');
  try {
    const ids = [];
    for (const f of files) {
      const a = await uploadAttachment(f);
      ids.push(a.attachment_id);
      const idx = pendingFiles.indexOf(f);
      if (idx >= 0) pendingFiles.splice(idx, 1);
    }
    const sent = await api(`/chat/api/chats/${currentChatId}/messages`, {
      method:'POST',
      body:JSON.stringify({session_token:STATE.token, body_text:text, attachment_ids:ids})
    });
    input.value = '';
    const newMid = sent && sent.message ? sent.message.message_id : null;
    await doLoadMessages({force:true, newMid: newMid, smooth:true});
  } catch(e) {
    toast(e.message, 'error');
  } finally {
    if (sendBtn) { sendBtn.disabled = false; sendBtn.classList.remove('busy'); }
    if (attachBtn) attachBtn.disabled = false;
    renderAttachPreview();
  }
}

const AVA_COLORS = ["#e17076","#7bc862","#e5ca77","#a695e7","#6ec9cb","#ee7aae","#65aadd"];
function chatAvaFor(title, id) {
  const src = (title || '') + '#' + (id || 0);
  let h = 0;
  for (let i = 0; i < src.length; i++) h = (h * 31 + src.charCodeAt(i)) >>> 0;
  const words = (title || '').trim().split(/\s+/).filter(Boolean);
  const initials = words.length ? words.map(w => w[0]).slice(0, 2).join('').toUpperCase() : 'Ч';
  return { color: AVA_COLORS[h % AVA_COLORS.length], initials };
}

function fmtDayKey(ms) {
  const d = new Date(ms || Date.now());
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function dayLabel(ms) {
  const d = new Date(ms || Date.now());
  const today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  if (fmtDayKey(ms) === fmtDayKey(today.getTime())) return 'Сегодня';
  if (fmtDayKey(ms) === fmtDayKey(yest.getTime())) return 'Вчера';
  const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  return d.getDate() + ' ' + months[d.getMonth()] + (d.getFullYear() !== today.getFullYear() ? ' ' + d.getFullYear() : '');
}
function daySepEl(ms) {
  return el('div',{class:'day-sep'}, dayLabel(ms));
}

function showChatInfo() {
  const old = document.getElementById('chat-info-modal');
  if (old) old.remove();
  const ov = el('div',{class:'overlay',id:'chat-info-modal'});
  ov.innerHTML = `<div class="modal">
    <h3>${esc(currentChatTitle || t('chat'))}</h3>
    <div class="chat-info-row"><span class="k">ID</span><span>#${esc(String(currentChatId || ''))}</span></div>
    <div class="chat-info-row"><span class="k">${t('description')}</span><span>${esc(currentChatDesc || '—')}</span></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
      <button class="btn btn-outline" id="chat-info-close">${t('close')}</button>
      <button class="btn btn-primary" id="chat-info-reload">${t('refresh')}</button>
    </div>
  </div>`;
  document.body.append(ov);
  const close = () => ov.remove();
  ov.onclick = (e) => { if (e.target === ov) close(); };
  ov.querySelector('#chat-info-close').onclick = close;
  ov.querySelector('#chat-info-reload').onclick = () => { close(); doLoadMessages({force:true}); };
}

// ===== Devices =====
function pairErrorText(e) {
  var map = {
    code_not_found: t('pair_err_not_found'),
    code_expired: t('pair_err_expired'),
    already_paired: t('pair_err_already'),
    guest_blocked: t('pair_err_guest')
  };
  var code = e && e.code;
  if (code && map[code]) return map[code];
  if (e && e.status === 404 && !code) return t('pair_err_unavailable');
  return (e && e.message) || 'Error';
}

async function renderDevices() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">${t('devices')}</div><div class="page-subtitle">${t('devices_subtitle')}</div></div>
    </div>
    <div class="card">
      <div class="card-title">${t('pair_by_code')}</div>
      <div class="card-subtitle">${t('pair_hint')}</div>
      <div class="pair-row">
        <input id="pair-code" class="form-input pair-code-input" type="text" inputmode="numeric" pattern="[0-9]*" maxlength="6" autocomplete="one-time-code" placeholder="000000" aria-label="${t('pair_by_code')}">
        <button id="pair-claim-btn" class="btn btn-primary" disabled>${t('pair_btn')}</button>
      </div>
      <div id="pair-msg" class="pair-msg"></div>
    </div>
    <div class="card">
      <div class="card-title">${t('my_devices')}</div>
      <div id="paired-list"><div class="loading"><div class="spinner"></div></div></div>
    </div>
    <div class="card-title" style="margin-bottom:12px">${t('catalog')}</div>
    <div id="device-grid" class="grid-3"><div class="loading"><div class="spinner"></div></div></div>`;

  const codeInput = $('#pair-code');
  const claimBtn = $('#pair-claim-btn');
  const msgBox = $('#pair-msg');
  const setMsg = (text, kind) => { msgBox.className = 'pair-msg' + (kind ? ' ' + kind : ''); msgBox.textContent = text || ''; };
  const syncBtn = () => { claimBtn.disabled = codeInput.value.length !== 6; };

  async function claim() {
    const code = codeInput.value.trim();
    if (code.length !== 6) { setMsg(t('pair_err_not_found'), 'err'); return; }
    claimBtn.disabled = true;
    claimBtn.textContent = t('pairing');
    setMsg('');
    try {
      const res = await api('/devices/api/pair/claim', {method:'POST', body:JSON.stringify({session_token:STATE.token, code})});
      const dev = (res && res.device) || {};
      const label = dev.name || dev.device_type || dev.device_id || '';
      codeInput.value = '';
      setMsg(label ? t('device_paired_ok') + ': ' + label : t('device_paired_ok'), 'ok');
      toast(t('device_paired_ok'), 'success');
      loadPaired();
    } catch(e) {
      setMsg(pairErrorText(e), 'err');
    } finally {
      claimBtn.textContent = t('pair_btn');
      syncBtn();
    }
  }

  codeInput.oninput = () => {
    codeInput.value = codeInput.value.replace(/\D/g, '').slice(0, 6);
    setMsg('');
    syncBtn();
  };
  codeInput.onkeydown = (e) => { if (e.key === 'Enter' && codeInput.value.length === 6) claim(); };
  claimBtn.onclick = claim;
  syncBtn();

  async function loadPaired() {
    const box = $('#paired-list');
    if (!box) return;
    try {
      const data = await api(`/devices/api/pair/list?session_token=${encodeURIComponent(STATE.token)}`);
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = `<div class="empty"><div class="empty-text">${t('no_devices')}</div></div>`;
        return;
      }
      box.innerHTML = '';
      items.forEach(p => {
        const row = el('div', {class:'paired-row'});
        const when = p.paired_at_ms ? new Date(p.paired_at_ms).toLocaleString() : '';
        const meta = [p.device_type, when].filter(Boolean).join(' · ');
        row.innerHTML = `<div class="paired-main">
            <div class="paired-id">${esc(p.device_id)}</div>
            <div class="paired-meta">${esc(meta)}</div>
          </div>
          <button class="btn btn-sm btn-outline">${t('unpair')}</button>`;
        const btn = row.querySelector('button');
        btn.onclick = async () => {
          btn.disabled = true;
          try {
            await api('/devices/api/unpair', {method:'POST', body:JSON.stringify({session_token:STATE.token, device_id:p.device_id})});
            loadPaired();
          } catch(e) { toast(e.message, 'error'); btn.disabled = false; }
        };
        box.append(row);
      });
    } catch(e) {
      box.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
    }
  }

  async function loadCatalog() {
    const grid = $('#device-grid');
    if (!grid) return;
    try {
      const data = await api(`/devices/api/catalog?session_token=${encodeURIComponent(STATE.token)}`);
      grid.innerHTML = '';
      if (!data.items || !data.items.length) {
        grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><div class="empty-text">No devices found</div></div>';
        return;
      }
      data.items.forEach(d => {
        const card = el('div',{class:'device-card'});
        const tags = [];
        if (d.is_published) tags.push('<span class="device-tag published">Published</span>');
        if (d.has_device) tags.push('<span class="device-tag owned">Owned</span>');
        card.innerHTML = `
          <h3>${esc(d.title)}</h3>
          <p>${esc(d.short_description||'No description')}</p>
          <div style="margin-bottom:8px">${tags.join(' ')}</div>
          ${d.firmware_archive_url ? `<a href="${esc(d.firmware_archive_url)}" target="_blank" rel="noopener" class="btn btn-sm btn-outline" style="margin-bottom:8px;width:100%;display:flex;justify-content:center;text-decoration:none">Download Firmware</a>` : ''}
          <details><summary style="cursor:pointer;font-size:13px;color:var(--accent)">Guides</summary>
            <div style="font-size:13px;color:var(--text2);margin-top:8px">
              <p><strong>Install:</strong> ${esc(d.install_guide||'N/A')}</p>
              <p><strong>Pairing:</strong> ${esc(d.pairing_guide||'N/A')}</p>
              <p><strong>Reset:</strong> ${esc(d.combo_reset_guide||'N/A')}</p>
            </div>
          </details>
          <button class="btn btn-sm ${d.has_device?'btn-danger':'btn-success'}" style="margin-top:8px;width:100%;justify-content:center">
            ${d.has_device?'Release':'Claim'}
          </button>`;
        card.querySelector('button').onclick = async () => {
          const owned = !!d.has_device;
          try {
            await api(`/devices/api/catalog/${d.device_id}/ownership`, {
              method:'POST',
              body:JSON.stringify({session_token:STATE.token, has_device:!owned})
            });
            toast(owned?'Device released':'Device claimed!', 'success');
            loadCatalog();
          } catch(e) { toast(e.message, 'error'); }
        };
        grid.append(card);
      });
    } catch(e) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="empty-text">${esc(e.message)}</div></div>`;
    }
  }

  loadPaired();
  loadCatalog();
}

async function renderAccount() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">${t('account')}</div><div class="page-subtitle">${t('account_subtitle')}</div></div>
    </div>
    <div id="account-card"><div class="loading"><div class="spinner"></div></div>
        </div>`;
  try {
    const data = await api(`/account/api/profile?session_token=${encodeURIComponent(STATE.token)}`);
    const p = data.profile;
    $('#account-card').innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
          <div class="account-avatar" id="acct-avatar">${avatarInnerHtml(p.avatar_url, p.avatar_emoji || localStorage.getItem('lc_my_emoji') || '🐱')}</div>
          <div style="min-width:0">
            <div style="font-size:18px;font-weight:600">${esc(p.display_name||p.login)}</div>
            <div style="font-size:13px;color:var(--text2)">@${esc(p.login)} · <span class="badge badge-${p.role}">${p.role}</span></div>
            <div class="ava-actions">
              <input id="avatar-file" type="file" accept="image/png,image/jpeg,image/webp" style="display:none">
              <button class="btn btn-sm btn-outline" id="avatar-upload">${icon('camera')} ${t('upload_photo')}</button>
            </div>
            <div class="ava-hint">${t('avatar_hint')}</div>
          </div>
        </div>
        
        <div class="form-group">
          <label>${t('display_name')}</label>
          <input class="form-input" id="acct-name" value="${esc(p.display_name||'')}">
        </div>
        <div class="form-group">
          <label>${t('phone')}</label>
          <input class="form-input" id="acct-phone" value="${esc(p.phone||'')}">
        </div>
        <div class="form-group">
          <label>${t('bio')}</label>
          <textarea class="form-input" id="acct-bio" rows="3">${esc(p.profile_bio||'')}</textarea>
        </div>
        <button class="btn btn-success" id="acct-save">${t('save_changes')}</button>
        <div class="card" style="margin-top:12px;text-align:center">
          <div style="font-size:36px;margin-bottom:4px" id="my-emoji-display"></div>
          <div style="color:var(--text2);font-size:11px;margin-bottom:6px">${t('avatar_emoji')}</div>
          <div id="emoji-grid" style="display:flex;flex-wrap:wrap;gap:4px;justify-content:center;max-width:280px;margin:0 auto"></div>
        </div>
        
      </div>`;

    // Photo avatar upload (server keeps png/jpeg/webp up to 2 MB)
    var avaFile = document.getElementById("avatar-file");
    var avaBtn = document.getElementById("avatar-upload");
    if (avaBtn && avaFile) {
      avaBtn.onclick = function() { avaFile.click(); };
      avaFile.onchange = function() {
        var f = avaFile.files && avaFile.files[0];
        avaFile.value = "";
        if (!f) return;
        if (!/^image\/(png|jpeg|webp)$/i.test(f.type)) { toast(t('avatar_bad_type'), 'error'); return; }
        if (f.size > 2 * 1024 * 1024) { toast(t('avatar_too_big'), 'error'); return; }
        var reader = new FileReader();
        reader.onload = async function() {
          try {
            var res = await api('/account/api/avatar', {method:'POST', body:JSON.stringify({session_token: STATE.token, image_base64: String(reader.result), image_mime_type: f.type})});
            var url = (res && (res.avatar_url || (res.profile && res.profile.avatar_url))) || null;
            var box = document.getElementById('acct-avatar');
            var emoji = (STATE.user && STATE.user.avatar_emoji) || localStorage.getItem('lc_my_emoji') || '🐱';
            if (box) box.innerHTML = avatarInnerHtml(url, emoji);
            if (STATE.user) STATE.user.avatar_url = url;
            if (url) AVA_URL[STATE.user ? STATE.user.id : -1] = url;
            toast(t('avatar_photo_ok'), 'success');
          } catch(err) { toast(err.message, 'error'); }
        };
        reader.readAsDataURL(f);
      };
    }

    // Emoji avatar picker (stored on the server, mirrored locally)
    var myEmoji = p.avatar_emoji || localStorage.getItem("lc_my_emoji") || "🐱";
    var ed = document.getElementById("my-emoji-display");
    if (ed) ed.textContent = myEmoji;
    var eg = document.getElementById("emoji-grid");
    if (eg) {
      var emojis = ["🐱","🐶","🐼","🦊","🐸","🐵","🦁","🐮","🐷","🐭","🐹","🐰","🐻","🐨","🐯","🐙","🦄","🐳","🐧","🐤","👻","🤖","👽","🐲","🦋","🐞","🐝","🦉","🐺","🐴"];
      emojis.forEach(function(e) {
        var d = document.createElement("div");
        d.textContent = e;
        if (e === myEmoji) d.classList.add('sel');
        d.onclick = async function() {
          localStorage.setItem("lc_my_emoji", e);
          document.getElementById("my-emoji-display").textContent = e;
          document.querySelectorAll("#emoji-grid div").forEach(function(x) { x.classList.remove("sel"); });
          d.classList.add("sel");
          try {
            await api('/account/api/profile', {method:'POST', body:JSON.stringify({session_token: STATE.token, avatar_emoji: e})});
            if (STATE.user) STATE.user.avatar_emoji = e;
            toast('Avatar updated', 'success');
          } catch(err) { toast(err.message, 'error'); }
        };
        eg.appendChild(d);
      });
    }
    $('#acct-save').onclick = async () => { 
      try {
        const r = await api('/account/api/profile', {
          method:'POST',
          body:JSON.stringify({
            session_token: STATE.token,
            display_name: $('#acct-name').value.trim(),
            phone: $('#acct-phone').value.trim(),
            profile_bio: $('#acct-bio').value.trim(),
          })
        });
        if (r.status==='ok') toast('Profile updated', 'success');
      } catch(e) { toast(e.message, 'error'); }
    };
    
  } catch(e) {
    $('#account-card').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function renderBlog() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">${t('blog')}</div><div class="page-subtitle">${t('blog_subtitle')}</div></div>
    </div>
    <div id="blog-list"><div class="loading"><div class="spinner"></div></div></div>`;
  try {
    const data = await api(`/blog/api/posts?session_token=${encodeURIComponent(STATE.token)}`);
    const list = $('#blog-list');
    list.innerHTML = '';
    if (!data.items?.length) {
      list.innerHTML = `<div class="empty"><div class="empty-text">${t('no_posts')}</div></div>`;
      return;
    }
    data.items.forEach(post => {
      const div = el('div',{class:'blog-card'});
      div.innerHTML = `
        <h3>${esc(post.title)}</h3>
        <div class="blog-meta">By User #${post.author_user_id} · ${fmtTime(post.published_at_ms)}</div>
        <div class="blog-body">${esc(post.body_text)}</div>
        ${renderAttachments(post.attachments)}`;
      list.append(div);
    });
  } catch(e) {
    $('#blog-list').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

function renderAbout() {
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">О проекте</div><div class="page-subtitle">Local Chat — демо версия</div></div>
    </div>
    <div class="card" style="line-height:1.7;font-size:14px">
      <h3>О проекте</h3>
      <p>Привет, мы команда <strong>no time to sleep</strong>, и вы находитесь на нашем проекте <strong>local-chat</strong>.</p>
      <p>Это <strong>ДЕМО версия</strong> проекта, в будущем он будет и дальше развиваться и обновляться.</p>
      <p>Также у нас есть и другие проекты, но это уже совсем другая история, заглядывайте на наш
      <a href="https://github.com/No-time-to-sleep" target="_blank" rel="noopener">Github</a></p>
    </div>
    <div class="card" style="line-height:1.7;font-size:14px;margin-top:16px">
      <h3>Первоначальная идея</h3>
      <p>Идея была создать очень сложную, отказоустойчивую mesh систему, которая будет работать в любых условиях и не нуждаться во вмешательстве. На основе Raspberry Pi 5, и ещё около 6-7 дополнительных модулей и процессоров для увеличения мощности и функционала. В частности много устройств от компании M5Stack. Но пока есть только RPi 5, так как это только демо.</p>
    </div>
    <div class="card" style="line-height:1.7;font-size:14px;margin-top:16px">
      <h3>История</h3>
      <p>Проект начался ещё более года назад, нам просто было скучно и мы решили попробовать программировать с помощью ИИ, но попытки не увенчались успехом. Но мы всё равно понемногу работали, работали, работали и ещё раз работали. И вот спустя сотни часов работы мы представляем первое демо, хоть в нём только половина от того что мы хотели (в лучшем случае), но мы будем и дальше продолжать этот проект.</p>
      <p>За этот проект мы изучили: построение mesh сетей, сетевые протоколы, логические цепи, Arduino, hardware, и много чего ещё. Мы прошли путь в ИИ от «сделай мне всё за 5 мин» до сложных систем разработки и работы через API.</p>
    </div>
    <div class="card" style="line-height:1.7;font-size:14px;margin-top:16px">
      <h3>Об авторах</h3>
      <p>Авторы — это 2 мальчика, которые помимо этого проекта ещё приняли ключевое участие в создании мультика <strong>A Default Day Of A Default Cat</strong> — <a href="https://no-time-to-sleep.github.io/paper-mult-site/" target="_blank" rel="noopener">сайт мультфильма</a>, который сильно нас изменил.</p>
      <p>Кроме этого, мы разрабатывали очень большое количество разных систем для ИИ, продвинулись в компьютерной безопасности и в Linux в частности. Также мы делаем и игры, но пока даже демо нет.</p>
      <p>И как же без D&D — один из разработчиков мастер, а второй игрок. Мы очень весёлые и хорошие ребята, и готовы стараться на благо нашего проекта.</p>
    </div>`;
}

let currentTicketId = null;

async function renderSupport() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">${t('support')}</div><div class="page-subtitle">${t('support_subtitle')}</div></div>
      <button class="btn btn-success btn-sm" id="new-ticket-btn" style="${STATE.user?.role === 'guest' ? 'display:none' : ''}">+ ${t('new_ticket')}</button>
    </div>
    <div id="new-ticket-modal" class="overlay hidden">
      <div class="modal">
        <h3>New Ticket</h3>
        <div class="form-group"><label>${t('title')}</label><input class="form-input" id="ticket-title"></div>
        <div class="form-group"><label>${t('description')}</label><textarea class="form-input" id="ticket-body" rows="4"></textarea></div>
        <div class="form-group"><label>${t('attachments')}</label><input class="form-input" id="ticket-file" type="file" multiple accept="${FILE_ACCEPT}"></div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn btn-outline" id="ticket-cancel">${t('cancel')}</button>
          <button class="btn btn-primary" id="ticket-submit">${t('submit')}</button>
        </div>
      </div>
    </div>
    <div class="grid-2" id="support-layout">
      <div id="ticket-list"><div class="loading"><div class="spinner"></div></div></div>
      <div id="ticket-detail">
        <div class="card" style="text-align:center;color:var(--text2);padding:40px">
          <div class="empty-icon">${icon('ticket')}</div>
          <div>${t('select_ticket')}</div>
        </div>
      </div>
    </div>`;
  try {
    const data = await api(`/support/api/tickets?session_token=${encodeURIComponent(STATE.token)}`);
    const list = $('#ticket-list');
    list.innerHTML = '';
    if (data.items?.length) {
    const _admIsMe = function(m) { return m.author_user_id === STATE.user?.id; };
    data.items.forEach(t => {
        const item = el('div',{class:'ticket-item'});
        item.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <strong>${esc(t.title)}</strong>
            <span class="ticket-status ${t.status}">${t.status.replace('_',' ')}</span>
          </div>
          <div style="font-size:12px;color:var(--text2)">${t.kind === 'report' ? icon('flag') + ' report · ' : ''}${fmtTime(t.created_at_ms)}</div>`;
        item.onclick = () => loadTicketDetail(t.ticket_id, t.title, item);
        list.append(item);
      });
      if (data.items.length && list.firstChild) list.firstChild.click();
    } else {
      list.innerHTML = `<div class="empty"><div class="empty-text">${t('no_tickets')}</div></div>`;
    }
  } catch(e) {
    $('#ticket-list').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
  // support-only ticket modal handlers
  const newTicketBtn = $('#new-ticket-btn');
  if (newTicketBtn) newTicketBtn.onclick = () => { show('#new-ticket-modal'); };
  $('#ticket-cancel').onclick = () => { hide('#new-ticket-modal'); $('#ticket-title').value=''; $('#ticket-body').value=''; if ($('#ticket-file')) $('#ticket-file').value=''; };
  $('#ticket-submit').onclick = async () => { 
    const title = $('#ticket-title').value.trim();
    const body = $('#ticket-body').value.trim();
    const files = Array.from($('#ticket-file')?.files || []);
    if (!title || !body) { toast('Fill in title and message', 'error'); return; }
    const submitBtn = $('#ticket-submit');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = t('sending'); }
    try {
      const attachmentIds = [];
      for (const file of files) { const a = await uploadAttachment(file); attachmentIds.push(a.attachment_id); }
      await api('/support/api/tickets', {
        method:'POST',
        body:JSON.stringify({
          session_token:STATE.token, title, body_text:body, attachment_ids:attachmentIds,
          kind: 'support',
        })
      });
      toast('Ticket created', 'success');
      hide('#new-ticket-modal');
      $('#ticket-title').value=''; $('#ticket-body').value=''; if ($('#ticket-file')) $('#ticket-file').value='';
      renderSupport();
    } catch(e) { toast(e.message, 'error'); }
    finally { if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = t('submit'); } }
  };
}

async function loadTicketDetail(ticketId, title, itemEl) {
  $$('.ticket-item.selected')?.forEach(e => e.style.background='');
  if(itemEl) itemEl.style.background='var(--bg3)';
  currentTicketId = ticketId;
  const container = $('#ticket-detail');
  container.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
  try {
    const data = await api(`/support/api/tickets/${ticketId}/messages?session_token=${encodeURIComponent(STATE.token)}`);
    const msgs = data.items || [];
    container.innerHTML = `
      <div class="card" style="padding:16px">
        <div class="card-title" style="font-size:16px">${esc(title)}</div>
        <div style="margin-bottom:12px"><button class="btn btn-sm btn-outline" id="close-ticket-btn">${t('close_ticket')}</button></div>
        <div style="max-height:40vh;overflow-y:auto;margin-bottom:12px">
          ${msgs.length ? msgs.map(m => `
            <div class="msg" style="margin-bottom:8px">
              <div class="msg-avatar" style="width:28px;height:28px;font-size:11px">${m.author_user_id===STATE.user?.id?'Y':'U'}</div>
              <div class="msg-body">
                <div class="msg-header">
                  <span class="msg-author">${m.author_user_id===STATE.user?.id?esc(STATE.user?.login||'You'):(m.author_login||((m.author_user_id===STATE.user?.id) ? (STATE.user?.login||'You') : (userName(m.author_user_id))))}</span>
                  <span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span>
                </div>
                  <div class="msg-text">${esc(m.body_text || '')}</div>
                ${renderAttachments(m.attachments)}
              </div>
            </div>`).join('') : `<div style="color:var(--text2);text-align:center;padding:16px">${t('no_messages')}</div>`}
        </div>
        <div class="send-area">
          <textarea id="support-input" placeholder="Reply..." rows="1"></textarea>
          
          <input id="support-file" type="file" multiple accept="${FILE_ACCEPT}" style="max-width:180px">
          <button class="btn btn-primary btn-sm" id="support-send">Send</button>
        </div>
        
      </div>`;
    $('#close-ticket-btn').onclick = async () => { try { await api('/support/api/tickets/' + currentTicketId + '/status', {method:'POST',body:JSON.stringify({session_token:STATE.token,status:'closed'})}); toast('Ticket closed','success'); loadTicketDetail(currentTicketId, title, null); } catch(e) { toast(e.message,'error'); } };
    $('#support-send').onclick = async () => { 
      const inp = $('#support-input');
      const files = Array.from(document.getElementById('support-file')?.files || []);
      const text = (inp?.value || '').trim();
      if (!text && !files.length) return;
      $('#support-send').disabled = true;
      try {
        const attachments = [];
        for (const file of files) attachments.push(await uploadAttachment(file));
        await api(`/support/api/tickets/${currentTicketId}/messages`, {
          method:'POST',
          body:JSON.stringify({session_token:STATE.token, body_text:text, attachment_ids:attachments.map(a=>a.attachment_id)})
        });
        if (inp) inp.value = '';
        await loadTicketDetail(currentTicketId, title, null);
      } catch(e) { toast(e.message, 'error'); }
      finally { if ($('#support-send')) $('#support-send').disabled = false; }
    };
    $('#support-input').onkeydown = e => {if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#support-send')?.click()}};
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function renderAdmin() {
  if (!requireAuth()) return;
  if (STATE.user?.role !== 'admin' && STATE.user?.role !== 'moderator') { window.location.hash = '#/chat'; return; }
  const c = $('#content');
  const adminOnlyStyle = STATE.user?.role === 'admin' ? '' : 'display:none';
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Admin Panel</div><div class="page-subtitle">System management</div></div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="users">Users</button>
      <button class="tab" data-tab="blog" style="${adminOnlyStyle}">Blog</button>
      <button class="tab" data-tab="support" style="${adminOnlyStyle}">Support</button>
      <button class="tab" data-tab="mode" style="${adminOnlyStyle}">Mode</button>
      <button class="tab" data-tab="cleanup" style="${adminOnlyStyle}">Cleanup</button>
      <button class="tab" data-tab="passwords" style="${adminOnlyStyle}">Passwords</button>
      <button class="tab" data-tab="system" style="${adminOnlyStyle}">System</button>
      <button class="tab" data-tab="activity" style="${adminOnlyStyle}">Activity</button>
      <button class="tab" data-tab="reports">Reports</button>
    </div>
    <div id="admin-users"></div>
    <div id="admin-support" class="hidden"></div>
    <div id="admin-blog" class="hidden"></div>
    <div id="admin-mode" class="hidden"></div>
    <div id="admin-cleanup" class="hidden"></div>
    <div id="admin-passwords" class="hidden"></div>
    <div id="admin-system" class="hidden"></div>
    <div id="admin-activity" class="hidden"></div>
    <div id="admin-reports" class="hidden"></div>`;
  $$('.tab').forEach(t => t.onclick = () => {
    $$('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    ['users','support','blog','mode','cleanup','passwords','system','activity','reports'].forEach(id => hide('#admin-' + id));
    show('#admin-' + t.dataset.tab);
    const tab = t.dataset.tab;
    if (tab === 'users') renderAdminUsers();
    else if (tab === 'support') renderAdminSupport();
    else if (tab === 'blog') renderAdminBlog();
    else if (tab === 'mode') renderAdminMode();
    else if (tab === 'cleanup') renderAdminCleanup();
    else if (tab === 'passwords') renderAdminPasswords();
    else if (tab === 'system') renderAdminSystem();
    else if (tab === 'activity') renderAdminActivity();
    else if (tab === 'reports') renderAdminReports();
  });
  await renderAdminUsers();
  await renderAdminSupport();
  await renderAdminBlog();
  await renderAdminMode();
  renderAdminCleanup();
  try { renderAdminPasswords(); } catch(e) {}
  try { renderAdminSystem(); } catch(e) {}
  renderAdminActivity();
  renderAdminReports();
}

async function renderAdminReports() {
  const container = $('#admin-reports');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  let userData = { reports: [], pending_count: 0 };
  let autoData = { reports: [], pending_count: 0 };
  let userErr = null, autoErr = null;
  try { userData = await api(`/reports/api/list?session_token=${encodeURIComponent(STATE.token)}&limit=100`); } catch(e) { userErr = e.message; }
  try { autoData = await api(`/moderation/api/admin/reports?session_token=${encodeURIComponent(STATE.token)}&limit=100`); } catch(e) { autoErr = e.message; }

  let html = `<div class="admin-card"><h3>${icon('flag')} ${t('admin_user_reports')} <span style="color:var(--accent4)">(${userData.pending_count||0})</span></h3>`;
  if (userErr) html += `<div class="empty"><div class="empty-text">${esc(userErr)}</div></div>`;
  else if (!userData.reports?.length) html += `<div class="empty"><div class="empty-text">${t('no_reports')}</div></div>`;
  else {
    html += userData.reports.map(r => `
      <div class="user-row" style="display:block;border-left:3px solid ${r.status==='pending'?'var(--accent4)':'var(--border)'};padding-left:12px">
        <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px">
          <span><strong>${esc(r.reporter_login)}</strong> → <strong>${esc(r.target_login||('User #'+r.target_user_id))}</strong></span>
          <span style="font-size:11px;color:var(--text2)">#${r.id} · ${esc(r.status)}</span>
        </div>
        <div style="margin:4px 0"><span class="report-reason-badge">${esc(reportReasonLabel(r.reason))}</span> <span style="font-size:11px;color:var(--text2)">${fmtTime(r.created_at_ms)}${r.target_reports_count > 1 ? ' · ' + t('reports_against') + ': ' + r.target_reports_count : ''}</span></div>
        ${r.comment ? `<div style="font-size:12px;background:var(--bg);padding:6px;border-radius:4px;margin:4px 0;white-space:pre-wrap">${esc(r.comment)}</div>` : ''}
        ${(r.attachments||[]).length ? renderAttachments(r.attachments) : ''}
        ${r.status === 'pending' ? `<div style="margin-top:6px">
            <button class="btn btn-sm btn-danger" data-urep="${r.id}" data-uraction="ban">Ban</button>
            <button class="btn btn-sm btn-outline" data-urep="${r.id}" data-uraction="warn">Warn (${r.target_warn_count||0}/3)</button>
            <button class="btn btn-sm btn-outline" data-urep="${r.id}" data-uraction="dismiss">Dismiss</button>
            <button class="btn btn-sm btn-outline" data-uevidence="${r.id}" data-utarget="${r.target_user_id}">${icon('fileText')} ${t('show_messages')}</button>
          </div>` : `<div style="font-size:11px;color:var(--text2)">${esc(r.action||'?')} · ${esc(r.resolved_by||'?')} · ${fmtTime(r.resolved_at_ms)}</div>`}
        <div id="uevidence-${r.id}" class="hidden" style="margin-top:8px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px"></div>
      </div>`).join('');
  }
  html += '</div>';

  html += `<div class="admin-card"><h3>${icon('bot')} ${t('admin_auto_reports')} <span style="color:var(--accent4)">(${autoData.pending_count||0})</span></h3>`;
  if (autoErr) html += `<div class="empty"><div class="empty-text">${esc(autoErr)}</div></div>`;
  else if (!autoData.reports?.length) html += `<div class="empty"><div class="empty-text">${t('no_reports')}</div></div>`;
  else {
    html += (autoData.reports||[]).map(r => `
      <div class="user-row" style="display:block;border-left:3px solid ${r.status==='pending'?'var(--accent3)':'var(--border)'};padding-left:12px">
        <div style="display:flex;justify-content:space-between">
          <strong>${esc(r.user_login||('User #'+r.user_id))}</strong>
          <span style="font-size:11px;color:var(--text2)">#${r.id} ${esc(r.status)}</span>
        </div>
        <div style="font-size:12px;color:var(--accent4);margin:4px 0">Words: ${esc(r.found_words||'')}</div>
        <div style="font-size:12px;background:var(--bg);padding:6px;border-radius:4px;margin:4px 0;max-height:80px;overflow-y:auto">${esc(r.message_text||'')}</div>
        ${r.status === 'pending' ? `<div style="margin-top:6px">
            <button class="btn btn-sm btn-danger" data-rrep="${r.id}" data-raction="ban">Ban</button>
            <button class="btn btn-sm btn-outline" data-rrep="${r.id}" data-raction="warn">Warn (${r.user_warn_count||0}/3)</button>
            <button class="btn btn-sm btn-outline" data-rrep="${r.id}" data-raction="dismiss">Dismiss</button>
          </div>` : `<div style="font-size:11px;color:var(--text2)">Resolved: ${esc(r.action||'?')} by ${esc(r.resolved_by||'?')}</div>`}
      </div>`).join('');
  }
  html += '</div>';
  container.innerHTML = html;

  container.querySelectorAll('[data-urep]').forEach(btn => {
    btn.onclick = async () => {
      if (btn.dataset.uraction === 'ban' && !confirm(t('report_ban_confirm'))) return;
      try {
        const d = await api('/reports/api/resolve', {method:'POST', body:JSON.stringify({session_token:STATE.token, report_id: parseInt(btn.dataset.urep), action: btn.dataset.uraction})});
        if (btn.dataset.uraction === 'warn' && d.warn) {
          if (d.warn.banned) toast(t('warn_banned').replace('{max}', d.warn.max_warns), 'error');
          else toast(t('warn_given').replace('{n}', d.warn.warn_count).replace('{max}', d.warn.max_warns), 'warn');
        } else {
          toast(`Report ${btn.dataset.uraction}`, 'success');
        }
        renderAdminReports();
      } catch(e) { toast(e.message, 'error'); }
    };
  });
  container.querySelectorAll('[data-uevidence]').forEach(btn => {
    btn.onclick = async () => {
      const box = document.getElementById('uevidence-' + btn.dataset.uevidence);
      if (!box) return;
      if (!box.classList.contains('hidden') && box.innerHTML) { box.classList.add('hidden'); return; }
      box.classList.remove('hidden');
      box.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
      try {
        const d = await api(`/reports/api/target-messages?session_token=${encodeURIComponent(STATE.token)}&target_user_id=${btn.dataset.utarget}&limit=10`);
        const items = d.items || [];
        box.innerHTML = items.length
          ? items.map(m => `<div style="font-size:12px;margin-bottom:6px;border-bottom:1px solid var(--border);padding-bottom:4px"><span style="color:var(--text2)">${esc(m.chat_title||('Chat #'+m.chat_id))} · ${fmtTime(m.created_at_ms)}</span><div style="white-space:pre-wrap">${esc(m.body_text||'')}</div></div>`).join('')
          : `<div style="font-size:12px;color:var(--text2)">${t('no_messages')}</div>`;
      } catch(e) { box.innerHTML = `<div style="font-size:12px;color:var(--accent4)">${esc(e.message)}</div>`; }
    };
  });
  container.querySelectorAll('[data-rrep]').forEach(btn => {
    btn.onclick = async () => {
      if (btn.dataset.raction === 'ban' && !confirm('Ban the author of this report?')) return;
      try {
        await api('/moderation/api/admin/reports/resolve', {method:'POST', body:JSON.stringify({session_token:STATE.token, report_id: parseInt(btn.dataset.rrep), action: btn.dataset.raction})});
        toast(`Report ${btn.dataset.raction}`, 'success');
        renderAdminReports();
      } catch(e) { toast(e.message, 'error'); }
    };
  });
}

async function renderAdminUsers() {
  const container = $('#admin-users');
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const data = await api(`/admin/users?session_token=${encodeURIComponent(STATE.token)}&_=${Date.now()}`);
    var onlineIds = [];
    try { var od = await api('/realtime/online', {method:'POST',body:JSON.stringify({session_token:STATE.token})}); onlineIds = od.online_user_ids || []; } catch(e) {}
    const items = data.items || [];
    const isFullAdmin = STATE.user?.role === 'admin';
    container.innerHTML = `<div class="admin-card">
      <h3>Users (${items.length})</h3>
      ${items.map(u => `
        <div class="user-row">
          <div style="flex:1">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${u.status==='banned'?'#f85149':u.status==='blocked'?'#d29922':onlineIds.includes(u.user_id)?'#4fb286':'var(--border)'};margin-right:6px"></span><strong>${esc(u.login)}</strong>
            <span class="user-role ${u.role}">${u.role}</span>
            <span class="user-status ${u.status}" style="margin-left:8px">${u.status}</span>${u.blocked_until_ms ? ' <span class="blocked-until" data-until="' + u.blocked_until_ms + '" style="font-size:11px;color:var(--accent3);margin-left:6px">(unblocks in ...)</span>' : ''}
            ${u.device_blacklisted ? '<span class="device-tag owned" style="font-size:10px">blacklisted</span>' : ''}
          </div>
          <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">
            ${u.user_id === STATE.user?.id ? '<span style="font-size:12px;color:var(--text2)">you</span>' : `
              ${u.status === 'active' ? `${isFullAdmin || u.role !== 'admin' ? `<button class="btn btn-sm btn-outline" data-action="setrole" data-uid="${u.user_id}" data-role="${u.role==='moderator'?'user':'moderator'}">${u.role==='moderator'?'Demote':'Promote'}</button>` : ''}
              <button class="btn btn-sm btn-danger" data-action="ban" data-uid="${u.user_id}">Ban</button>
              <input class="tb-dur" data-uid="${u.user_id}" type="number" min="1" max="10080" value="60" style="width:50px;padding:4px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:12px;text-align:center" title="Minutes"><button class="btn btn-sm btn-outline" data-action="tempblock" data-uid="${u.user_id}">min</button>
              ${isFullAdmin ? (u.device_blacklisted ? `<button class="btn btn-sm btn-outline" data-action="unblacklist" data-uid="${u.user_id}">Unblacklist Dev</button>` : `<button class="btn btn-sm btn-outline" data-action="blacklist" data-uid="${u.user_id}">Blacklist Dev</button>`) : ''}
              ${isFullAdmin ? `<button class="btn btn-sm btn-danger" data-action="delete" data-uid="${u.user_id}" data-login="${esc(u.login)}">Delete</button>` : ''}` : `
              <button class="btn btn-sm btn-success" data-action="unban" data-uid="${u.user_id}">Unban</button>`}
            `}
          </div>
          <div style="font-size:12px;color:var(--text2);min-width:30px;text-align:right">ID ${u.user_id}</div>
        </div>`).join('')}
    </div>`;
    if (window._blockTimer) clearInterval(window._blockTimer);
    function updateBlocks() {
      document.querySelectorAll('.blocked-until').forEach(function(el){
        var ms = parseInt(el.dataset.until); if (!ms) return;
        var left = Math.max(0, ms - Date.now());
        if (left <= 0) { el.textContent = '(expired)'; return; }
        var m = Math.floor(left / 60000);
        if (m < 1) { var s = Math.floor(left / 1000); el.textContent = '(unblocks in ' + s + 's)'; }
        else if (m < 60) el.textContent = '(unblocks in ' + m + 'm)';
        else { var h = Math.floor(m / 60); el.textContent = '(unblocks in ' + h + 'h ' + (m % 60) + 'm)'; }
      });
    }
    updateBlocks();
    window._blockTimer = setInterval(updateBlocks, 5000);
    container.querySelectorAll('[data-action]').forEach(btn => {
      btn.onclick = async () => { 
        const uid = btn.dataset.uid;
        const action = btn.dataset.action;
        if (action === 'delete') {
          if (!confirm(`Delete user "${btn.dataset.login}" (ID ${uid})?`)) return;
          try {
            await api(`/admin/users/${uid}?session_token=${encodeURIComponent(STATE.token)}`, {method:'DELETE'});
            toast('User ' + btn.dataset.login + ' deleted', 'success');
            await renderAdminUsers();
          } catch(e) { toast(e.message, 'error'); }
          return;
        }
        if (action === 'setrole') {
          const newRole = btn.dataset.role;
          if (!confirm(`Set role to "${newRole}" for user ID ${uid}?`)) return;
          try {
            await api(`/admin/users/${uid}/set-role`, {
              method:'POST',
              body:JSON.stringify({session_token:STATE.token, role:newRole})
            });
            toast(`Role set to ${newRole}`, 'success');
            renderAdminUsers();
          } catch(e) { toast(e.message, 'error'); }
          return;
        }
        if (action === 'tempblock') {
          const inp = btn.previousElementSibling; const dur = parseInt(inp?.value || '60');
          if (isNaN(dur) || dur < 1 || dur > 10080) { toast('Invalid duration (1-10080)', 'error'); return; }
          if (!confirm(`Temporarily block user ID ${uid} for ${dur} min?`)) return;
          try {
            await api(`/admin/users/${uid}/temporary-block`, {
              method:'POST',
              body:JSON.stringify({session_token:STATE.token, duration_minutes:dur})
            });
            toast('User temporarily blocked', 'success');
            renderAdminUsers();
          } catch(e) { toast(e.message, 'error'); }
          return;
        }
        if (action === 'blacklist') {
          const devId = prompt('Device ID (optional):', '');
          try {
            await api(`/admin/users/${uid}/blacklist-device`, {
              method:'POST',
              body:JSON.stringify({session_token:STATE.token, device_id: devId || null})
            });
            toast('Device blacklisted', 'success');
            renderAdminUsers();
          } catch(e) { toast(e.message, 'error'); }
          return;
        }
        if (action === 'unblacklist') {
          try {
            await api(`/admin/users/${uid}/unblacklist-device`, {
              method:'POST',
              body:JSON.stringify({session_token:STATE.token})
            });
            toast('Device unblacklisted', 'success');
            renderAdminUsers();
          } catch(e) { toast(e.message, 'error'); }
          return;
        }
        if (action === 'ban' && !confirm(`Ban user ID ${uid}?`)) return;
        if (action === 'unban' && !confirm(`Unban user ID ${uid}?`)) return;
        try {
          await api(`/admin/users/${uid}/${action}`, {
            method:'POST',
            body:JSON.stringify({session_token:STATE.token})
          });
          toast(`User ${action}ned`, 'success');
          renderAdminUsers();
        } catch(e) { toast(e.message, 'error'); }
      };
    });
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

// Admin Support
async function renderAdminSupport() {
  const container = $('#admin-support');
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const data = await api(`/admin/content/support/tickets?session_token=${encodeURIComponent(STATE.token)}`);
    container.innerHTML = `<div class="admin-card"><h3>Support Tickets (${data.count||0})</h3></div>`;
    if (!data.items?.length) { container.innerHTML += '<div class="empty"><div class="empty-text">No tickets</div></div>'; return; }
    const _admIsMe = function(m) { return m.author_user_id === STATE.user?.id; };
    const _attachTitle = t('attach');
    data.items.forEach(t => {
      const card = el('div',{class:'ticket-item',style:'margin-bottom:8px'});
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${esc(t.title)}</strong>
          <select class="ats" data-tid="${t.ticket_id}" style="padding:4px 8px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:12px"><option value="open" ${t.status==="open"?"selected":""}>open</option><option value="in_progress" ${t.status==="in_progress"?"selected":""}>in progress</option><option value="resolved" ${t.status==="resolved"?"selected":""}>resolved</option><option value="closed" ${t.status==="closed"?"selected":""}>closed</option></select><button class="btn btn-sm btn-outline aus" data-tid="${t.ticket_id}">Update</button>
        </div>
        <div style="font-size:12px;color:var(--text2)">${t.kind === 'report' ? icon('flag') + ' report · ' : ''}User #${t.user_id} · ${fmtTime(t.created_at_ms)}</div>
        <div id="admin-ticket-${t.ticket_id}-msgs" style="display:none;margin-top:8px;border-top:1px solid var(--border);padding-top:8px"></div>
        <div id="admin-ticket-${t.ticket_id}-reply" style="display:none;margin-top:8px" class="send-area">
          <input id="admin-ticket-${t.ticket_id}-file" type="file" multiple style="display:none" accept="${FILE_ACCEPT}">
          <button class="btn btn-sm btn-outline att-btn" data-tid="${t.ticket_id}" title="${_attachTitle}">${icon('clip')}</button>
          <textarea id="admin-ticket-${t.ticket_id}-input" placeholder="Reply as admin..." rows="1"></textarea>
          <button class="btn btn-primary btn-sm" data-tid="${t.ticket_id}">Send</button>
        </div>`;
      card.onclick = async (e) => {
        if (e.target.closest('.send-area')) return;
        const msgsDiv = $(`#admin-ticket-${t.ticket_id}-msgs`);
        const replyDiv = $(`#admin-ticket-${t.ticket_id}-reply`);
        const isOpen = msgsDiv.style.display === 'block';
        msgsDiv.style.display = isOpen ? 'none' : 'block';
        replyDiv.style.display = isOpen ? 'none' : 'flex';
        if (!isOpen && !msgsDiv.hasChildNodes()) {
          try {
            const msgsData = await api(`/admin/content/support/tickets/${t.ticket_id}/messages?session_token=${encodeURIComponent(STATE.token)}`);
            msgsDiv.innerHTML = (msgsData.items||[]).map(m => `
              <div class="msg" style="margin-bottom:6px">
                <div class="msg-avatar" style="width:24px;height:24px;font-size:10px">${m.author_user_id===STATE.user?.id?'A':'U'}</div>
                <div class="msg-body">
                  <div class="msg-header"><span class="msg-author">${m.author_user_id===STATE.user?.id?'Admin':(m.author_login||((m.author_user_id===STATE.user?.id) ? (STATE.user?.login||'You') : (userName(m.author_user_id))))}</span><span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span></div>
                <div class="msg-text">${esc(m.body_text || '')}</div>
                  ${renderAttachments(m.attachments)}
                </div>
              </div>`).join('') || '<div style="color:var(--text2);text-align:center">No messages</div>';
          } catch(e) { msgsDiv.innerHTML = `<div style="color:var(--accent4)">${esc(e.message)}</div>`; }
        }
      };
      container.append(card);
    });
    container.querySelectorAll('.aus').forEach(btn => { btn.onclick = async (e) => { e.stopPropagation(); var tid = btn.dataset.tid; var sel = document.querySelector('.ats[data-tid="' + tid + '"]'); if (!sel) return; try { await api('/admin/content/support/tickets/' + tid + '/status', {method:'POST',body:JSON.stringify({session_token:STATE.token,status:sel.value})}); toast('Status: '+sel.value,'success'); } catch(e) { toast(e.message,'error'); } }; });
    container.querySelectorAll('[data-tid]').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const tid = btn.dataset.tid;
        if (btn.classList.contains("aus")) return;
        if (btn.classList.contains("att-btn")) { const fi = $(`#admin-ticket-${tid}-file`); if (fi) fi.click(); return; }
        const inp = $(`#admin-ticket-${tid}-input`);
        const files = Array.from($(`#admin-ticket-${tid}-file`)?.files || []);
        const text = (inp?.value || '').trim();
        if (!text && !files.length) { toast("Reply cannot be empty", "error"); return; }
        btn.disabled = true;
        try {
          const ids = [];
          for (const f of files) { const a = await uploadAttachment(f); ids.push(a.attachment_id); }
          await api(`/admin/content/support/tickets/${tid}/reply`, {
            method:'POST',
            body:JSON.stringify({session_token:STATE.token, body_text:text, attachment_ids:ids})
          });
          toast('Reply sent', 'success');
          if (inp) inp.value = '';
          const msgsDiv = $(`#admin-ticket-${tid}-msgs`);
          if (msgsDiv) msgsDiv.innerHTML = '';
        } catch(e) { toast(e.message, 'error'); }
        finally { btn.disabled = false; }
      };
    });
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

// Admin Blog
async function renderAdminBlog() {
  const container = $('#admin-blog');
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  let blogFiles = [];
  try {
    const data = await api(`/admin/content/blog/posts?session_token=${encodeURIComponent(STATE.token)}`);
    container.innerHTML = `
      <div class="admin-card">
        <h3>Publish Post</h3>
        <div class="form-group"><label>Title</label><input class="form-input" id="blog-post-title"></div>
        <div class="form-group"><label>Body</label><textarea class="form-input" id="blog-post-body" rows="6"></textarea></div>
        <div class="form-group"><label>${t('attachments')}</label>
          <input id="blog-post-file" type="file" multiple style="display:none" accept="${FILE_ACCEPT}">
          <button type="button" class="btn btn-sm btn-outline" id="blog-post-attach">${icon('clip')} ${t('attach')}</button>
          <div id="blog-post-preview" class="attach-preview" style="margin-top:8px"></div>
        </div>
        <button class="btn btn-success" id="blog-post-publish">Publish</button>
      </div>
      <div class="admin-card"><h3>Published Posts (${data.count||0})</h3></div>`;
    const blogPreview = $('#blog-post-preview');
    function renderBlogChips() {
      blogPreview.innerHTML = blogFiles.length ? fileChipsHtml(blogFiles) : '';
      wireFileChips(blogPreview, blogFiles, (i) => { blogFiles.splice(i, 1); renderBlogChips(); });
    }
    $('#blog-post-attach').onclick = () => $('#blog-post-file').click();
    $('#blog-post-file').onchange = function() {
      for (const f of Array.from(this.files || [])) {
        if (blogFiles.length >= MAX_ATTACH_FILES) { toast(t('too_many_files'), 'error'); break; }
        if (f.size > MAX_UPLOAD_MB * 1024 * 1024) { toast(`${f.name}: ${t('file_too_large')} (${MAX_UPLOAD_MB} MB)`, 'error'); continue; }
        blogFiles.push(f);
      }
      this.value = '';
      renderBlogChips();
    };
    $('#blog-post-publish').onclick = async () => { 
      const title = $('#blog-post-title').value.trim();
      const body = $('#blog-post-body').value.trim();
      if (!title || !body) { toast('Fill in all fields', 'error'); return; }
      const btn = $('#blog-post-publish');
      btn.disabled = true;
      if (blogFiles.length) btn.textContent = t('uploading');
      try {
        const ids = [];
        for (const f of blogFiles) { const a = await uploadAttachment(f); ids.push(a.attachment_id); }
        await api('/admin/content/blog/posts', {
          method:'POST',
          body:JSON.stringify({session_token:STATE.token, title, body_text:body, attachment_ids:ids})
        });
        toast('Post published', 'success');
        $('#blog-post-title').value=''; $('#blog-post-body').value='';
        renderAdminBlog();
      } catch(e) { toast(e.message, 'error'); btn.disabled = false; btn.textContent = 'Publish'; }
    };
    if (data.items?.length) {
      data.items.forEach(post => {
        const div = el('div',{class:'blog-card',style:'margin-bottom:8px'});
        div.innerHTML = `<h3>${esc(post.title)}</h3>
          <div class="blog-meta">Published ${fmtTime(post.published_at_ms)}</div>
          <div class="blog-body">${esc(post.body_text)}</div>
          ${renderAttachments(post.attachments)}`;
        container.append(div);
      });
    } else {
      container.innerHTML += '<div class="empty"><div class="empty-text">No posts yet</div></div>';
    }
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

// Admin Mode toggle (simple click with confirm)
async function renderAdminMode() {
  const container = $('#admin-mode');
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const data = await api(`/admin/mode/state?session_token=${encodeURIComponent(STATE.token)}`);
    const mode = data.access_mode;
    container.innerHTML = `<div class="admin-card">
      <h3>Access Mode</h3>
      <p style="color:var(--text2);margin-bottom:16px">Current mode: <strong style="color:${mode==='open'?'var(--accent2)':'var(--accent3)'}">${mode}</strong></p>
      <button class="btn ${mode==='open'?'btn-danger':'btn-success'}" id="mode-toggle" style="width:100%;justify-content:center">
        Switch to ${mode==='open'?'closed':'open'}
      </button>
    </div>`;
    $('#mode-toggle').onclick = async () => { 
      const newMode = mode === 'open' ? 'closed' : 'open';
      if (!confirm(`Switch mode to "${newMode}"?`)) return;
      try {
        const r = await api('/admin/mode/set', {
          method:'POST',
          body:JSON.stringify({session_token:STATE.token, access_mode:newMode, hold_seconds:5})
        });
        if (r.status === 'ok') {
          toast(`Mode changed to ${r.access_mode}`, 'success');
          renderAdminMode();
        }
      } catch(e) { toast(e.message, 'error'); }
    };
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function renderAdminCleanup() {
  const c = $('#admin-cleanup');
  c.innerHTML = `
    <div class="admin-card">
      <h3>Clear Chat Messages</h3>
      <div class="form-group"><label>Chat ID</label><input class="form-input" id="cleanup-chat-id" type="number" placeholder="Chat ID"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-danger btn-sm" id="clear-all-msgs">Clear All Messages</button>
        <button class="btn btn-danger btn-sm" id="delete-chat-btn">Delete Entire Chat</button>
      </div>
    </div>
    <div class="admin-card">
      <h3>Clear Messages by Date Range</h3>
      <div class="form-row">
        <div class="form-group"><label>Chat ID</label><input class="form-input" id="range-chat-id" type="number" placeholder="Chat ID"></div>
        <div class="form-group"><label>From</label><input class="form-input" id="range-from" type="date"></div>
        <div class="form-group"><label>To</label><input class="form-input" id="range-to" type="date"></div>
      </div>
      <button class="btn btn-danger btn-sm" id="clear-range-btn">Clear Range</button>
    </div>
    <div class="admin-card">
      <h3>Bulk Operations</h3>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-outline btn-sm" id="clear-global-btn">Clear Global Chat</button>
        <button class="btn btn-outline btn-sm" id="clear-blog-btn">Clear All Blog Posts</button>
        <button class="btn btn-outline btn-sm" id="clear-support-btn">Clear All Tickets</button>
        <button class="btn btn-danger btn-sm" id="delete-all-chats-btn">Delete All Chats</button>
        <button class="btn btn-danger btn-sm" id="delete-all-users-btn">Delete All Users</button>
      </div>
    </div>
    <div class="admin-card" style="border-color:var(--accent4)">
      <h3 style="color:var(--accent4)">Full System Reset</h3>
      <p style="color:var(--text2);font-size:13px;margin-bottom:12px">Deletes ALL chats, ALL messages, ALL users except admin. This cannot be undone.</p>
      <button class="btn btn-danger" id="full-reset-btn">FULL RESET</button>
    </div>
    <div id="cleanup-msg" style="margin-top:8px;font-size:13px"></div>`;

  const msg = (t) => { $('#cleanup-msg').textContent = t; };

  $('#clear-all-msgs').onclick = async () => { 
    const cid = parseInt($('#cleanup-chat-id').value);
    if (!cid) { msg('Enter Chat ID'); return; }
    if (!confirm('Delete ALL messages in chat ' + cid + '?')) return;
    try {
      const r = await api('/chat/api/admin/chats/' + cid + '/messages', {method:'DELETE',body:JSON.stringify({session_token:STATE.token})});
      msg('Deleted: ' + r.deleted_count + ' messages');
    } catch(e) { msg(e.message); }
  };

  $('#delete-chat-btn').onclick = async () => { 
    const cid = parseInt($('#cleanup-chat-id').value);
    if (!cid) { msg('Enter Chat ID'); return; }
    if (!confirm('DELETE chat ' + cid + ' completely?')) return;
    try {
      await api('/chat/api/admin/chats/' + cid, {method:'DELETE',body:JSON.stringify({session_token:STATE.token})});
      msg('Chat ' + cid + ' deleted');
    } catch(e) { msg(e.message); }
  };

  $('#clear-range-btn').onclick = async () => { 
    const cid = parseInt($('#range-chat-id').value);
    const from = $('#range-from').value;
    const to = $('#range-to').value;
    if (!cid || !from || !to) { msg('Fill all fields'); return; }
    if (!confirm('Delete messages in chat ' + cid + ' from ' + from + ' to ' + to + '?')) return;
    try {
      const r = await api('/chat/api/admin/chats/' + cid + '/messages/range', {method:'POST',body:JSON.stringify({session_token:STATE.token,from_date:from,to_date:to})});
      msg('Deleted: ' + r.deleted_count + ' messages');
    } catch(e) { msg(e.message); }
  };

  $('#clear-global-btn').onclick = async () => { 
    if (!confirm('Clear ALL messages in the global/common chat?')) return;
    try {
      const r = await api('/chat/api/admin/clear-global', {method:'POST',body:JSON.stringify({session_token:STATE.token})});
      msg('Global chat cleared: ' + r.deleted_count + ' messages');
    } catch(e) { msg(e.message); }
  };

  $('#delete-all-chats-btn').onclick = async () => { 
    if (!confirm('Delete ALL chats? This removes everything except the default common chat.')) return;
    try {
      const r = await api('/chat/api/admin/delete-all-chats', {method:'POST',body:JSON.stringify({session_token:STATE.token})});
      msg('Deleted: ' + r.deleted_count + ' chats');
    } catch(e) { msg(e.message); }
  };

  $('#delete-all-users-btn').onclick = async () => { 
    if (!confirm('Delete ALL users? Admin will be kept. This cannot be undone.')) return;
    try {
      const r = await api('/chat/api/admin/delete-all-users', {method:'POST',body:JSON.stringify({session_token:STATE.token})});
      msg('Deleted: ' + r.deleted_count + ' users');
    } catch(e) { msg(e.message); }
  };

  $('#clear-blog-btn').onclick = async () => { 
    if (!confirm('Delete ALL blog posts?')) return;
    try {
      const r = await api('/chat/api/admin/clear-blog', {method:'POST',body:JSON.stringify({session_token:STATE.token})});
      msg('Deleted: ' + r.deleted_count + ' blog posts');
    } catch(e) { msg(e.message); }
  };

  $('#clear-support-btn').onclick = async () => { 
    if (!confirm('Delete ALL support tickets and messages?')) return;
    try {
      const r = await api('/chat/api/admin/clear-support', {method:'POST',body:JSON.stringify({session_token:STATE.token})});
      msg('Deleted: ' + r.deleted_count + ' items');
    } catch(e) { msg(e.message); }
  };

  $('#full-reset-btn').onclick = async () => { 
    if (!confirm('FULL RESET? This will delete ALL chats and ALL users except admin. Are you SURE?')) return;
    if (!confirm('SECOND CONFIRMATION: This cannot be undone. Proceed?')) return;
    try {
      const r = await api('/chat/api/admin/full-reset', {method:'POST',body:JSON.stringify({session_token:STATE.token,confirm:true})});
      msg('Reset done. Users deleted: ' + r.users_deleted);
    } catch(e) { msg(e.message); }
  };
}

async function renderAdminActivity() {
  const c = $('#admin-activity');
  c.innerHTML = '<div class="card"><div style="display:flex;gap:24px;flex-wrap:wrap" id="activity-stats"></div></div><div class="card"><h3>Activity Log (last 100)</h3><div id="activity-log"><div class="loading"><div class="spinner"></div></div></div></div>';
  try {
    const r = await api('/chat/api/admin/activity?session_token=' + encodeURIComponent(STATE.token) + '&limit=100');
    const s = r.stats;
    $('#activity-stats').innerHTML = '<div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent2)">' + s.messages_30d + '</div><div style="font-size:12px;color:var(--text2)">Messages (30 days)</div></div><div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">' + s.users_30d + '</div><div style="font-size:12px;color:var(--text2)">New users (30 days)</div></div><div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--text2)">' + s.total_events + '</div><div style="font-size:12px;color:var(--text2)">Total events</div></div>';
    const items = r.items || [];
    $('#activity-log').innerHTML = items.length ? items.map(function(e) {
      var dt = new Date(e.time).toLocaleString();
      var icon = e.event === 'login' ? 'login' : e.event === 'register' ? 'register' : e.event === 'guest_login' ? 'guest' : e.event === 'message_sent' ? 'msg' : e.event === 'device_session' ? 'device' : '--';
      return '<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:13px"><strong>' + esc(e.event) + '</strong> <span style="color:var(--text2)">' + esc(e.user_login||'') + '</span> <span style="color:var(--text2);font-size:11px">' + dt + '</span> ' + (e.details ? '<span style="color:var(--text2);font-size:11px">' + esc(e.details) + '</span>' : '') + '</div>';
    }).join('') : '<div style="color:var(--text2);text-align:center;padding:16px">No activity yet</div>';
  } catch(e) {
    c.innerHTML = '<div class="empty"><div class="empty-text">' + esc(e.message) + '</div></div>';
  }
}

/* ===== ROUTER ===== */
function esc(s) {const d=document.createElement('div');d.textContent=s;return d.innerHTML}

let warnChecked = false;
async function checkWarnings() {
  if (warnChecked || !STATE.token) return;
  if (STATE.user?.role === 'guest') return;
  warnChecked = true;
  try {
    const d = await api(`/reports/api/my-status?session_token=${encodeURIComponent(STATE.token)}`);
    if (d.warn_count > 0) {
      const key = 'lc_warn_seen_' + d.warn_count;
      if (sessionStorage.getItem(key) !== '1') {
        sessionStorage.setItem(key, '1');
        toast(t('warn_banner').replace('{n}', d.warn_count).replace('{max}', d.max_warns), 'warn');
      }
    }
  } catch(e) {}
}

async function handleRoute() {
  const hash = window.location.hash || '#/login';
  if (hash === '#/login' && STATE.token) {window.location.hash = '#/chat'; return}
  const publicRoutes = ['#/login', '#/about'];
  if (!publicRoutes.includes(hash.split('?')[0]) && !STATE.token) {window.location.hash = '#/login'; return}
  updateNav();
  checkWarnings();
  const contentEl = document.getElementById('content');
  const isChat = hash.split('?')[0] === '#/chat';
  if (contentEl) contentEl.classList.toggle('chat-wide', isChat);
  document.body.classList.toggle('chat-mode', isChat);
  try {
    switch(hash.split('?')[0]) {
      case '#/login': await renderLogin(); break;
      case '#/chat': await renderChat(); break;
      case '#/devices': await renderDevices(); break;
      case '#/account': await renderAccount(); break;
      case '#/blog': await renderBlog(); break;
      case '#/support': await renderSupport(); break;
      case '#/admin': await renderAdmin(); break;
      case '#/about': renderAbout(); break;
      default: window.location.hash = '#/chat';
    }
  } catch(e) {
    console.error('Route render error:', e);
    const c = $('#content');
    if (c) c.innerHTML = `<div class="empty"><div class="empty-text">Error: ${esc(e.message||e)}</div></div>`;
  }
}

window.onhashchange = handleRoute;

// Entry point for the static login form in templates/index.html
window.lcStaticLoginComplete = function() {
  try {
    STATE.token = localStorage.getItem('lc_session_token') || null;
    STATE.user = (function(){ try { return JSON.parse(localStorage.getItem('lc_user') || 'null'); } catch(e) { return null; } })();
  } catch(e) {}
  updateNav();
  handleRoute();
};
window.onload = async () => {
  // Auto-login from ?token= in URL (captive portal login)
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('token');
  if (urlToken && !STATE.token) {
    try {
      const session = await api(`/auth/session/${encodeURIComponent(urlToken)}`);
      if (session.user && session.session) {
        setAuth(session);
        window.history.replaceState({}, '', window.location.pathname + window.location.hash);
      }
    } catch(e) { /* token invalid, proceed normally */ }
  }
  if (messagesPollTimer) clearInterval(messagesPollTimer);
  handleRoute();
  // hamburger
  const closeNav = () => { const nl = $('#nav-links'); if (nl) nl.classList.remove('open'); document.body.classList.remove('menu-open'); };
  $('#hamburger').onclick = (ev) => {
    ev.stopPropagation();
    const open = $('#nav-links').classList.toggle('open');
    document.body.classList.toggle('menu-open', open);
  };
  // close nav on link click (mobile)
  $$('.nav-links a').forEach(a => a.onclick = closeNav);
  document.addEventListener('click', (ev) => {
    if (!ev.target.closest('.nav') && !ev.target.closest('#chat-menu-btn') && !ev.target.closest('#hamburger')) closeNav();
  });
  $('#logout-btn').onclick = async () => { 
    if (STATE.token) {
      try { await api('/auth/logout', {method:'POST',body:JSON.stringify({session_token:STATE.token})}) } catch(e) {}
    }
    clearAuth();
  };
};

// iOS-safe app viewport: keep the app glued to the real visible area
// (visualViewport), so on iPhone the page cannot drift and the keyboard
// does not push the composer/input off-screen.
function setAppHeight() {
  var vv = window.visualViewport;
  var root = document.documentElement;
  if (vv) {
    root.style.setProperty('--app-h', Math.round(vv.height) + 'px');
    root.style.setProperty('--app-top', Math.round(vv.offsetTop) + 'px');
  } else {
    root.style.setProperty('--app-h', Math.round(window.innerHeight) + 'px');
    root.style.setProperty('--app-top', '0px');
  }
  var l = document.getElementById('msg-list');
  if (l && l._stickBottom) l.scrollTop = l.scrollHeight;
}
setAppHeight();
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', setAppHeight);
  window.visualViewport.addEventListener('scroll', setAppHeight);
}
window.addEventListener('resize', setAppHeight);
window.addEventListener('orientationchange', function(){ setTimeout(setAppHeight, 250); });





async function renderAdminPasswords() {
  var container = document.getElementById("admin-passwords");
  if (!container) return;
  container.innerHTML = "<div class=loading>Loading...</div>";
  try {
    var data = await api("/admin/users?session_token=" + encodeURIComponent(STATE.token) + "&limit=200");
    var html = "<div class=admin-card><h3>Password Reset</h3><p style=color:var(--text2);margin-bottom:12px>Enter new password (min 8 chars) and click Reset</p></div>";
    for (var i = 0; i < (data.items||[]).length; i++) {
      var u = data.items[i];
      html += "<div style=display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)>";
      html += "<span style=flex:1><strong>" + esc(u.login) + "</strong> <span style=color:var(--text2);font-size:12px>" + u.role + "</span></span>";
      html += "<input id=pw" + u.user_id + " type=text placeholder=New_password style=width:140px;padding:4px 8px;font-size:12px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text)>";
      html += "<button data-uid=" + u.user_id + " class=btn btn-sm style=font-size:11px>Reset</button>";
      html += "<span id=pwmsg" + u.user_id + " style=font-size:11px;margin-left:8px></span></div>";
    }
    container.innerHTML = html;
    var buttons = container.querySelectorAll("button[data-uid]");
    for (var j = 0; j < buttons.length; j++) {
      buttons[j].onclick = async function() {
        var uid = this.dataset.uid;
        var inp = document.getElementById("pw" + uid);
        var msg = document.getElementById("pwmsg" + uid);
        var pw = inp.value.trim();
        if (pw.length < 8) { msg.textContent = "Min 8 chars"; return; }
        try {
          await api("/admin/users/" + uid + "/reset-password", {method:"POST",body:JSON.stringify({session_token:STATE.token,new_password:pw})});
          msg.textContent = "OK"; msg.style.color = "var(--accent2)";
        } catch(e) { msg.textContent = e.message; msg.style.color = "var(--accent4)"; }
      };
    }
  } catch(e) { container.innerHTML = "<div class=empty>Error: " + esc(e.message||e) + "</div>"; }
}

async function renderAdminSystem() {
  var container = document.getElementById("admin-system");
  if (!container) return;
  container.innerHTML = "<div class=loading>Loading...</div>";
  try {
    var h = await api("/ops/api/system-health?session_token=" + encodeURIComponent(STATE.token));
    var s = await api("/ops/api/services?session_token=" + encodeURIComponent(STATE.token));
    var media = null;
    try { media = await api("/media/api/stats?session_token=" + encodeURIComponent(STATE.token)); } catch(e) {}
    var health = h.health || {};
    var svcs = s.services || [];
    var html = "<div class=admin-card><h3>RPi System</h3>";
    html += "<div style=display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px>";
    html += "<div style=background:var(--bg);padding:12px;border-radius:8px;text-align:center><div style=font-size:24px;font-weight:700;color:var(--accent2)>" + (health.cpu_temp||"?") + "</div><div style=font-size:11px;color:var(--text2)>CPU</div></div>";
    html += "<div style=background:var(--bg);padding:12px;border-radius:8px;text-align:center><div style=font-size:24px;font-weight:700>" + (health.ram_used||"?") + "</div><div style=font-size:11px;color:var(--text2)>RAM / " + (health.ram_total||"?") + "</div></div>";
    html += "<div style=background:var(--bg);padding:12px;border-radius:8px;text-align:center><div style=font-size:24px;font-weight:700>" + (health.disk_used||"?") + "</div><div style=font-size:11px;color:var(--text2)>Disk " + (health.disk_pct||"?") + "</div></div>";
    html += "</div>";
    if (media && media.count !== undefined) {
      var freeGb = media.free_bytes != null ? (media.free_bytes / 1073741824).toFixed(2) + " GB" : "?";
      var usedMb = (media.total_bytes / 1048576).toFixed(1) + " MB";
      var lowFree = media.free_bytes != null && media.free_bytes < 1024 * 1024 * 1024;
      html += "<h4 style=margin:12px 0 8px>Media storage</h4>";
      html += "<div style=font-size:13px;background:var(--bg);padding:10px;border-radius:8px>";
      html += "Files: <strong>" + media.count + "</strong> \u00b7 Used: <strong>" + usedMb + "</strong> \u00b7 Free on disk: <strong style=color:" + (lowFree ? "var(--accent4)" : "var(--accent2)") + ">" + freeGb + "</strong>";
      if (lowFree) html += "<div style=color:var(--accent4);font-size:12px;margin-top:6px>\u26a0 Free space is low. Uploads are disabled automatically when free space drops below " + Math.round((media.min_free_bytes||0)/1048576) + " MB.</div>";
      html += "</div>";
    }
    html += "<h4 style=margin:12px 0 8px>Services</h4>";
    for (var i = 0; i < svcs.length; i++) {
      var svc = svcs[i];
      var color = svc.active === "active" ? "var(--accent2)" : "var(--accent4)";
      html += "<div style=display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px>";
      html += "<span><span style=color:" + color + ";margin-right:6px>●</span>" + svc.name + " <span style=color:var(--text2);font-size:11px>" + (svc.substate||svc.active) + "</span></span>";
      html += "</div>";
    }
    html += "</div>";
    // Restart buttons
    html += "<div style=display:flex;gap:6px;flex-wrap:wrap;margin-top:8px>";
    var svcNames = ["local-chat-server","local-chat-proxy","hostapd","dnsmasq","ssh","wpa_supplicant","cron","bluetooth","NetworkManager"];
    for (var k = 0; k < svcNames.length; k++) {
      var sn = svcNames[k];
      html += "<button class='btn btn-sm btn-outline sys-rst' data-svc='" + sn + "' style=font-size:11px>Restart " + sn.split("-").pop() + "</button>";
    }
    html += "<button class='btn btn-sm btn-danger sys-rst' data-svc='reboot' style=font-size:11px>Reboot RPi</button>";
    html += "<span id=sys-rst-msg style=font-size:11px;margin-left:8px></span></div>";
    container.innerHTML = html;
    // Attach handlers
    var rstBtns = container.querySelectorAll(".sys-rst");
    for (var r = 0; r < rstBtns.length; r++) {
      rstBtns[r].onclick = async function() {
        var svc = this.dataset.svc;
        var msg = document.getElementById("sys-rst-msg");
        if (svc === "reboot") {
          if (!confirm("Reboot Raspberry Pi? All users will be disconnected.")) return;
          msg.textContent = "Rebooting...";
          try { await api("/ops/api/reboot", {method:"POST",body:JSON.stringify({session_token:STATE.token,confirm:true})}); } catch(e) { msg.textContent = e.message; }
          return;
        }
        this.disabled = true;
        this.textContent = "...";
        msg.textContent = "Restarting " + svc + "...";
        try {
          await api("/ops/api/restart-service", {method:"POST",body:JSON.stringify({session_token:STATE.token,service:svc})});
          msg.textContent = svc + " restarted";
          setTimeout(function() { msg.textContent = ""; }, 3000);
        } catch(e) { msg.textContent = "Error: " + e.message; }
        this.disabled = false;
        this.textContent = "Restart " + svc.split("-").pop();
      };
    }
    if (window._sysTimer) clearInterval(window._sysTimer);
    window._sysTimer = setInterval(function() {
      var el = document.getElementById("admin-system");
      if (el && !el.classList.contains("hidden")) renderAdminSystem();
    }, 15000);
  } catch(e) { container.innerHTML = "<div class=empty>Error: " + esc(e.message||e) + "</div>"; }
}


setTimeout(function() {
  var c = document.getElementById('content');
  if (typeof handleRoute === "function" && (!c || !c.innerHTML.trim())) handleRoute();
}, 100);

// ===== TRANSLATION SYSTEM =====
var LANG = localStorage.getItem("lc_lang") || "rus";

var T = {
"sign_in":{rus:"Войти",eng:"Sign In"},"create_account":{rus:"Создать аккаунт",eng:"Create Account"},
"auth_tagline":{rus:"Локальный чат в вашей сети",eng:"Local chat inside your network"},
"auth_point1":{rus:"Работает без интернета",eng:"Works without internet"},
"auth_point2":{rus:"Телефон, ноутбук, устройства",eng:"Phone, laptop, devices"},
"auth_point3":{rus:"Сообщения и файлы остаются внутри сети",eng:"Messages and files stay inside the network"},
"field_login":{rus:"Логин",eng:"Login"},
"field_pass":{rus:"Пароль",eng:"Password"},
"field_phone":{rus:"Телефон",eng:"Phone"},
"enter_login_pass":{rus:"Введите логин и пароль",eng:"Enter login and password"},
"min_8_chars":{rus:"Минимум 8 символов",eng:"Min 8 characters"},
"continue_guest":{rus:"Продолжить как гость",eng:"Continue as guest"},
"submit_app":{rus:"Подать заявку",eng:"Submit application"},
"back_login":{rus:"Назад",eng:"Back"},
"chat":{rus:"Чат",eng:"Chat"},"devices":{rus:"Устройства",eng:"Devices"},
"account":{rus:"Аккаунт",eng:"Account"},"blog":{rus:"Блог",eng:"Blog"},
"support":{rus:"Поддержка",eng:"Support"},"admin":{rus:"Админ",eng:"Admin"},
"network":{rus:"Сеть",eng:"Network"},"about":{rus:"О проекте",eng:"About"},
"logout":{rus:"Выйти",eng:"Logout"},"send":{rus:"Отправить",eng:"Send"},
"type_msg":{rus:"Введите сообщение...",eng:"Type a message..."},
"new_chat":{rus:"Новый чат",eng:"New Chat"},"dm":{rus:"Личка",eng:"DM"},
"menu":{rus:"Меню",eng:"Menu"},
"edit_msg":{rus:"Редактировать сообщение",eng:"Edit message"},
"voice_msg":{rus:"Голосовое сообщение",eng:"Voice message"},
"voice_stop":{rus:"Готово",eng:"Done"},
"voice_need_https":{rus:"Запись с микрофона работает только по HTTPS (или на localhost). Можно приложить готовый аудиофайл.",eng:"Microphone recording needs HTTPS (or localhost). You can attach an audio file instead."},
"voice_no_mic":{rus:"Не удалось получить доступ к микрофону. Проверьте разрешение браузера.",eng:"Could not access the microphone. Check the browser permission."},
"upload_photo":{rus:"Загрузить фото",eng:"Upload photo"},
"avatar_hint":{rus:"PNG, JPEG или WEBP · до 2 МБ. Фото заменяет эмодзи-аватар.",eng:"PNG, JPEG or WEBP · up to 2 MB. The photo replaces the emoji avatar."},
"avatar_photo_ok":{rus:"Фото-аватар обновлён",eng:"Photo avatar updated"},
"avatar_bad_type":{rus:"Только PNG, JPEG или WEBP",eng:"PNG, JPEG or WEBP only"},
"avatar_too_big":{rus:"Файл больше 2 МБ",eng:"File is larger than 2 MB"},
"devices_subtitle":{rus:"Сопряжение и управление устройствами",eng:"Pair and manage devices"},
"pair_by_code":{rus:"Сопряжение по коду",eng:"Pair by code"},
"pair_hint":{rus:"Включите устройство и введите 6-значный код с его экрана. Код действует 5 минут и срабатывает один раз.",eng:"Turn on the device and enter the 6-digit code from its screen. The code is valid for 5 minutes and works once."},
"pair_btn":{rus:"Сопрячь",eng:"Pair"},
"pairing":{rus:"Сопряжение...",eng:"Pairing..."},
"my_devices":{rus:"Мои устройства",eng:"My devices"},
"no_devices":{rus:"Нет сопряжённых устройств",eng:"No paired devices"},
"unpair":{rus:"Отвязать",eng:"Unpair"},
"catalog":{rus:"Каталог устройств",eng:"Device catalog"},
"device_paired_ok":{rus:"Устройство сопряжено",eng:"Device paired"},
"pair_err_not_found":{rus:"Код не найден — проверьте цифры",eng:"Code not found — check the digits"},
"pair_err_expired":{rus:"Код истёк — запросите новый на устройстве",eng:"Code expired — get a new one on the device"},
"pair_err_already":{rus:"Это устройство уже сопряжено",eng:"This device is already paired"},
"pair_err_guest":{rus:"Гостям сопряжение недоступно",eng:"Guest accounts cannot pair devices"},
"pair_err_unavailable":{rus:"Сопряжение по коду пока недоступно на сервере",eng:"Pairing by code is not available on the server yet"},
"no_chats":{rus:"Нет чатов",eng:"No chats"},
"select_chat":{rus:"Выберите чат",eng:"Select a chat"},
"search_user":{rus:"Поиск по логину...",eng:"Search by login..."},
"no_users":{rus:"Не найдены",eng:"Not found"},
"create":{rus:"Создать",eng:"Create"},"cancel":{rus:"Отмена",eng:"Cancel"},
"title":{rus:"Название",eng:"Title"},"description":{rus:"Описание",eng:"Description"},
"display_name":{rus:"Имя",eng:"Display Name"},"phone":{rus:"Телефон",eng:"Phone"},
"bio":{rus:"О себе",eng:"Bio"},"save":{rus:"Сохранить",eng:"Save"},
"profile_updated":{rus:"Профиль обновлён",eng:"Profile updated"},
"avatar_emoji":{rus:"Аватар",eng:"Avatar emoji"},
"click_change":{rus:"Нажми чтобы сменить",eng:"Click to change"},
"delete":{rus:"Удалить",eng:"Delete"},"ban":{rus:"Бан",eng:"Ban"},
"unban":{rus:"Разбан",eng:"Unban"},"promote":{rus:"Повысить",eng:"Promote"},
"demote":{rus:"Понизить",eng:"Demote"},
"make_admin":{rus:"Админ",eng:"Make Admin"},
"remove_admin":{rus:"Не админ",eng:"Remove Admin"},
"clear_global":{rus:"Очистить общий чат",eng:"Clear Global Chat"},
"clear_blog_btn":{rus:"Очистить блог",eng:"Clear Blog"},
"clear_support_btn":{rus:"Очистить поддержку",eng:"Clear Support"},
"delete_all_chats":{rus:"Удалить все чаты",eng:"Delete All Chats"},
"delete_all_users":{rus:"Удалить всех",eng:"Delete All Users"},
"full_reset":{rus:"ПОЛНЫЙ СБРОС",eng:"FULL RESET"},
"restart":{rus:"Перезапуск",eng:"Restart"},
"reboot":{rus:"Перезагрузить RPi",eng:"Reboot RPi"},
"reply":{rus:"Ответить",eng:"Reply"},"close":{rus:"Закрыть",eng:"Close"},
"refresh":{rus:"Обновить",eng:"Refresh"},
"view":{rus:"Смотреть",eng:"View"},"login_btn":{rus:"Войти",eng:"Login"},
"about_text":{rus:"Local Chat — локальный чат-сервер на Raspberry Pi 5. Автономная система без интернета. Чат, блог, тикеты, админ-панель.",eng:"Local Chat — self-hosted chat on Raspberry Pi 5. Works offline. Chat, blog, tickets, admin panel."},
"sign_in_portal":{rus:"Войдите для доступа",eng:"Sign in to access internet"},
"enter_login":{rus:"Введите логин",eng:"Enter login"},
"lang_label":{rus:"🇷🇺 RUS",eng:"🇬🇧 ENG"},"enter_pass":{rus:"Введите пароль",eng:"Enter password"},
"chat_subtitle":{rus:"Сообщения",eng:"Workspace messages"},
"support_subtitle":{rus:"Тикеты помощи",eng:"Help desk tickets"},
"account_subtitle":{rus:"Ваш профиль",eng:"Your profile"},
"blog_subtitle":{rus:"Последние посты",eng:"Latest posts"},
"load_older":{rus:"↑ Загрузить старые",eng:"↑ Load older messages"},
"new_ticket":{rus:"Новый тикет",eng:"New Ticket"},
"submit":{rus:"Отправить",eng:"Submit"},
"save_changes":{rus:"Сохранить изменения",eng:"Save Changes"},
"no_tickets":{rus:"Нет тикетов",eng:"No tickets"},
"no_messages":{rus:"Нет сообщений",eng:"No messages"},
"no_posts":{rus:"Пока нет постов",eng:"No posts yet"},
"type_label":{rus:"Тип",eng:"Type"},
"support_kind":{rus:"Запрос в поддержку",eng:"Support request"},
"report_kind":{rus:"Жалоба на пользователя",eng:"Report a user"},
"report_user_label":{rus:"На кого жалоба",eng:"User to report"},
"report_title":{rus:"Пожаловаться на пользователя",eng:"Report user"},
"report_reason_label":{rus:"Причина",eng:"Reason"},
"report_comment_label":{rus:"Комментарий",eng:"Comment"},
"report_comment_ph":{rus:"Опишите проблему (необязательно)",eng:"Describe the issue (optional)"},
"report_send":{rus:"Отправить жалобу",eng:"Send report"},
"report_sent_title":{rus:"Жалоба отправлена",eng:"Report sent"},
"report_sent_text":{rus:"Модераторы рассмотрят её в ближайшее время. Спасибо!",eng:"Moderators will review it soon. Thank you!"},
"report_ban_confirm":{rus:"Забанить пользователя из этой жалобы?",eng:"Ban the user from this report?"},
"reason_spam":{rus:"Спам",eng:"Spam"},
"reason_abuse":{rus:"Оскорбления",eng:"Abuse"},
"reason_profanity":{rus:"Мат",eng:"Profanity"},
"reason_ads":{rus:"Реклама",eng:"Ads"},
"reason_scam":{rus:"Мошенничество",eng:"Scam"},
"reason_other":{rus:"Другое",eng:"Other"},
"admin_user_reports":{rus:"Жалобы пользователей",eng:"User reports"},
"admin_auto_reports":{rus:"Авто-модерация",eng:"Auto-moderation"},
"no_reports":{rus:"Жалоб нет",eng:"No reports"},
"warn_banner":{rus:"У вас предупреждений: {n}/{max}. При {max} — бан на 3 дня.",eng:"You have {n}/{max} warnings. At {max} — a 3-day ban."},
"warn_given":{rus:"Предупреждение {n}/{max} выдано",eng:"Warning {n}/{max} issued"},
"warn_banned":{rus:"{max}/{max} предупреждений — пользователь забанен на 3 дня",eng:"{max}/{max} warnings — user banned for 3 days"},
"show_messages":{rus:"Сообщения",eng:"Messages"},
"no_messages":{rus:"Сообщений нет",eng:"No messages"},
"reports_against":{rus:"жалоб на него",eng:"reports against"},
"attachments":{rus:"Вложения",eng:"Attachments"},
"optional":{rus:"необязательно",eng:"optional"},
"attach":{rus:"Прикрепить файл",eng:"Attach file"},
"uploading":{rus:"Загрузка...",eng:"Uploading..."},
"too_many_files":{rus:"Максимум 8 файлов на сообщение",eng:"Up to 8 files per message"},
"file_too_large":{rus:"Файл слишком большой",eng:"File is too large"},
"remove":{rus:"Убрать",eng:"Remove"},
"close_ticket":{rus:"Закрыть тикет",eng:"Close Ticket"},
"sending":{rus:"Отправка...",eng:"Sending..."},
"access_application":{rus:"Заявка на доступ",eng:"Access Application"},
"select_ticket":{rus:"Выберите тикет для просмотра",eng:"Select a ticket to view"},
"register_link":{rus:"Нет аккаунта? Зарегистрироваться",eng:"No account? Register"},
"login_link":{rus:"Уже есть аккаунт? Войти",eng:"Already have an account? Sign in"},
};
function t(key) { var e = T[key]; return e ? (e[LANG] || e["rus"] || key) : key; }


// Profile viewer — click avatar in chat
function showProfileModal(html) {
  var m = document.getElementById("profile-modal");
  if (!m) {
    m = document.createElement("div");
    m.id = "profile-modal";
    m.className = "overlay";
    m.onclick = function(e) { if (e.target === m) { m.style.animation="fadeOut .15s"; setTimeout(function(){m.remove()},140); } };
    document.body.appendChild(m);
  }
  m.innerHTML = html;
}
async function viewUserProfile(uid) {
  if (uid === STATE.user?.id) { window.location.hash = "#/account"; return; }
  try {
    var d = await api("/account/api/profile/" + uid + "?session_token=" + encodeURIComponent(STATE.token));
    var p = d.profile;
    var emojis = ["🐱","🐶","🐼","🦊","🐸","🐵","🦁","🐮","🐷","🐭","🐹","🐰","🐻","🐨","🐯"];
    var emoji = p.avatar_emoji || emojis[uid % emojis.length];
    var isGuest = STATE.user?.role === 'guest';
    var h = "<div class='modal profile-modal'>";
    h += "<button class='pm-close' onclick=\"document.getElementById('profile-modal').remove()\">&times;</button>";
    h += "<div class='pm-avatar'>" + (p.avatar_url ? "<img class='ava-img' src='" + safeUrl(p.avatar_url) + "' alt=''>" : esc(emoji)) + "</div>";
    h += "<h2 class='pm-name'>" + esc(p.display_name || p.login) + "</h2>";
    h += "<div class='pm-login'>@" + esc(p.login) + "</div>";
    h += "<div class='pm-role'>" + esc(p.role) + "</div>";
    if (p.phone) h += "<div class='pm-phone'>" + icon('phone') + " " + esc(p.phone) + "</div>";
    if (p.profile_bio) h += "<div class='pm-bio'>" + esc(p.profile_bio) + "</div>";
    h += "<div class='pm-actions'>";
    h += "<button id='pm-dm' class='btn btn-success'>" + icon('mail') + " DM</button>";
    if (!isGuest) h += "<button id='pm-report' class='btn btn-danger'>" + icon('flag') + " Report</button>";
    h += "</div></div>";
    showProfileModal(h);
    var dmBtn = document.getElementById("pm-dm");
    if (dmBtn) dmBtn.onclick = async function() {
      try {
        await api('/chat/api/dm', {method:'POST', body:JSON.stringify({session_token:STATE.token, target_user_id: uid})});
        var modal = document.getElementById("profile-modal"); if (modal) modal.remove();
        window.location.hash = '#/chat';
        setTimeout(function(){ renderChat(); }, 150);
      } catch(e) { toast(e.message, 'error'); }
    };
    var repBtn = document.getElementById("pm-report");
    if (repBtn) repBtn.onclick = function() {
      var modal = document.getElementById("profile-modal"); if (modal) modal.remove();
      openReportModal(uid, p.display_name || p.login, emoji);
    };
  } catch(e) { toast(e.message, "error"); }
}

// ===== User reports (dedicated flow, not support tickets) =====
function reportReasonLabel(reason) {
  var map = {
    spam: t('reason_spam'), abuse: t('reason_abuse'), profanity: t('reason_profanity'),
    ads: t('reason_ads'), scam: t('reason_scam'), other: t('reason_other'),
  };
  return map[reason] || reason;
}
function openReportModal(uid, name, emoji) {
  var existing = document.getElementById('report-modal');
  if (existing) existing.remove();
  var overlay = document.createElement('div');
  overlay.id = 'report-modal';
  overlay.className = 'overlay';
  overlay.innerHTML = `
    <div class="modal report-modal">
      <h3>${icon('flag')} ${t('report_title')}</h3>
      <div class="report-target">
        <span class="report-target-avatar">${emoji ? esc(emoji) : icon('user')}</span>
        <div>
          <div class="report-target-name">${esc(name || ('User #' + uid))}</div>
          <div class="report-target-sub">ID #${uid}</div>
        </div>
      </div>
      <div class="form-group"><label>${t('report_reason_label')}</label>
        <div class="report-reasons" id="report-reasons"></div>
      </div>
      <div class="form-group"><label>${t('report_comment_label')}</label>
        <textarea class="form-input" id="report-comment" rows="3" maxlength="1000" placeholder="${t('report_comment_ph')}"></textarea>
      </div>
      <div class="form-group"><label>${t('attachments')} (${t('optional')})</label>
        <input id="report-file" type="file" multiple style="display:none" accept="${FILE_ACCEPT}">
        <button type="button" class="btn btn-sm btn-outline" id="report-attach">${icon('clip')} ${t('attach')}</button>
        <div id="report-preview" class="attach-preview" style="margin-top:8px"></div>
      </div>
      <div id="report-error" class="login-error"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn btn-outline" id="report-cancel">${t('cancel')}</button>
        <button class="btn btn-danger" id="report-send">${t('report_send')}</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
  var selected = 'spam';
  var reasonsBox = document.getElementById('report-reasons');
  [['spam','megaphone'],['abuse','alert'],['profanity','messageX'],['ads','megaphone'],['scam','dollar'],['other','help']].forEach(function(pair) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'report-reason' + (pair[0] === selected ? ' active' : '');
    b.dataset.reason = pair[0];
    b.innerHTML = icon(pair[1]) + ' ' + reportReasonLabel(pair[0]);
    b.onclick = function() {
      selected = pair[0];
      reasonsBox.querySelectorAll('.report-reason').forEach(function(x) { x.classList.remove('active'); });
      b.classList.add('active');
    };
    reasonsBox.appendChild(b);
  });
  document.getElementById('report-cancel').onclick = function() { overlay.remove(); };
  var reportFiles = [];
  var reportPreview = document.getElementById('report-preview');
  var reportFileInput = document.getElementById('report-file');
  function renderReportChips() {
    if (!reportPreview) return;
    reportPreview.innerHTML = reportFiles.length ? fileChipsHtml(reportFiles) : '';
    wireFileChips(reportPreview, reportFiles, function(i) { reportFiles.splice(i, 1); renderReportChips(); });
  }
  document.getElementById('report-attach').onclick = function() { reportFileInput.click(); };
  reportFileInput.onchange = function() {
    for (const f of Array.from(reportFileInput.files || [])) {
      if (reportFiles.length >= MAX_ATTACH_FILES) { toast(t('too_many_files'), 'error'); break; }
      if (f.size > MAX_UPLOAD_MB * 1024 * 1024) { toast(`${f.name}: ${t('file_too_large')} (${MAX_UPLOAD_MB} MB)`, 'error'); continue; }
      reportFiles.push(f);
    }
    reportFileInput.value = '';
    renderReportChips();
  };
  document.getElementById('report-send').onclick = async function() {
    var btn = document.getElementById('report-send');
    var errBox = document.getElementById('report-error');
    errBox.textContent = ''; errBox.style.display = 'none';
    btn.disabled = true; btn.textContent = reportFiles.length ? t('uploading') : t('sending');
    try {
      var ids = [];
      for (const f of reportFiles) {
        const a = await uploadAttachment(f);
        ids.push(a.attachment_id);
      }
      await api('/reports/api/create', {method:'POST', body:JSON.stringify({
        session_token: STATE.token, target_user_id: uid, reason: selected,
        comment: document.getElementById('report-comment').value.trim(),
        attachment_ids: ids,
      })});
      var card = overlay.querySelector('.modal');
      card.innerHTML = `
        <div class="report-success">
          <div class="report-success-icon">${icon('checkCircle')}</div>
          <h3>${t('report_sent_title')}</h3>
          <p>${t('report_sent_text')}</p>
          <button class="btn btn-primary" id="report-close">${t('close')}</button>
        </div>`;
      document.getElementById('report-close').onclick = function() { overlay.remove(); };
    } catch(e) {
      errBox.textContent = e.message; errBox.style.display = 'block';
      btn.disabled = false; btn.textContent = t('report_send');
    }
  };
}

// ===== Language switcher =====
function applyLang() {
  document.documentElement.lang = LANG === 'eng' ? 'en' : 'ru';
  $$('[data-t]').forEach(function(node) {
    var key = node.getAttribute('data-t');
    var value = T[key];
    if (value) node.textContent = value[LANG] || value.rus || key;
  });
  $$('[data-t-placeholder]').forEach(function(node) {
    var key = node.getAttribute('data-t-placeholder');
    var value = T[key];
    if (value) node.setAttribute('placeholder', value[LANG] || value.rus || key);
  });
  $$('.lang-btn').forEach(function(btn) {
    btn.textContent = LANG === 'eng' ? '🇷🇺 RUS' : '🇬🇧 ENG';
  });
}
function switchLang() {
  LANG = LANG === 'eng' ? 'rus' : 'eng';
  localStorage.setItem('lc_lang', LANG);
  applyLang();
  if (typeof handleRoute === 'function') { handleRoute(); }
}
document.addEventListener('click', function(e) {
  var t = e.target;
  if (t && t.classList && t.classList.contains('lang-btn')) {
    e.preventDefault();
    switchLang();
  }
});
setTimeout(function() { applyLang(); }, 50);

// Edit/Delete messages
async function editMsg(mid, btn) {
  var current = "";
  if (btn) {
    var body = btn.closest('.msg-body');
    var textEl = body ? body.querySelector('.msg-text') : null;
    current = textEl ? textEl.textContent.replace(/\s*\(edited\)\s*$/,'') : "";
  }
  // native prompt() does not work in iOS captive portal / in-app browsers
  var overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `<div class="modal edit-modal">
    <h3>${t('edit_msg')}</h3>
    <textarea class="form-input" id="edit-text" rows="4"></textarea>
    <div class="confirm-actions">
      <button class="btn btn-primary" id="edit-save">${t('save')}</button>
      <button class="btn btn-outline" id="edit-cancel">${t('cancel')}</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  var ta = overlay.querySelector('#edit-text');
  ta.value = current;
  var close = function() { overlay.remove(); };
  overlay.querySelector('#edit-cancel').onclick = close;
  overlay.querySelector('#edit-save').onclick = async function() {
    var newText = ta.value.trim();
    if (!newText || newText === current) { close(); return; }
    try {
      await api("/chat/api/chats/" + currentChatId + "/messages/" + mid, {method:"PUT", body:JSON.stringify({session_token:STATE.token, body_text:newText})});
      close();
      doLoadMessages({force:true});
    } catch(e) { toast(e.message, "error"); }
  };
  setTimeout(function(){ ta.focus(); }, 60);
}

function confirmDel(mid) {
  var overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal confirm-modal">
    <div class="confirm-icon">${icon('trash')}</div>
    <h3>Delete this message?</h3>
    <div class="confirm-actions">
      <button id="cfm-yes" class="btn btn-danger">Yes, delete</button>
      <button id="cfm-no" class="btn btn-outline">No, keep it</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  document.getElementById("cfm-yes").onclick = function() { overlay.remove(); delMsg(mid); };
  document.getElementById("cfm-no").onclick = function() { overlay.remove(); };
}

async function delMsg(mid) {
  try {
    await api("/chat/api/chats/" + currentChatId + "/messages/" + mid, {method:"DELETE", body:JSON.stringify({session_token:STATE.token})});
    doLoadMessages({force:true});
  } catch(e) { toast(e.message, "error"); }
}
