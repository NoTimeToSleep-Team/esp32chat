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
  const t = el('div',{class:`toast ${type}`},msg);
  document.body.append(t);
  setTimeout(()=>{t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(()=>t.remove(),300)},3000);
}

function fmtTime(ms){const d=new Date(ms);return d.toLocaleString()}
function fmtTimeShort(ms){const d=new Date(ms);const now=new Date();const same=d.toDateString()===now.toDateString()
  ?d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})
  :d.toLocaleDateString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});return same}

async function api(url, opts={}) {
  const headers={'Content-Type':'application/json'};
  if (opts.sessionHeader) headers['X-Session-Token'] = STATE.token;
  const controller = new AbortController();
  const timeoutMs = opts.timeoutMs || 10000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(url, {...opts, headers, signal: controller.signal});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d?.detail?.message || d?.detail?.code || `HTTP ${r.status}`);
    return d;
  } catch(e) {
    if (e.name === 'AbortError') throw new Error('Request timeout');
    if (e.name!=='TypeError') throw e;
    throw new Error('Server unreachable');
  } finally {
    clearTimeout(timeoutId);
  }
}

async function uploadAttachment(file) {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`/media/api/attachments?session_token=${encodeURIComponent(STATE.token)}`, {method:'POST', body:form});
  const d = await r.json().catch(()=>({}));
  if (!r.ok) throw new Error(d?.detail?.message || d?.detail?.code || `Upload failed (${r.status})`);
  return d.attachment;
}

function attachmentUrl(a) {
  const base = a.download_url || `/media/api/attachments/${a.attachment_id}/download`;
  const sep = base.includes('?') ? '&' : '?';
  return `${base}${sep}session_token=${encodeURIComponent(STATE.token)}`;
}

function safeUrl(u) {
  return u.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderAttachments(items) {
  if (!items?.length) return '';
  return `<div class="attachments">${items.map(a => {
    const url = attachmentUrl(a);
    const name = esc(a.filename || `attachment-${a.attachment_id}`);
    const mime = String(a.mime_type || '');
    if ((a.media_kind === 'image' || mime.startsWith('image/'))) {
      return `<a class="attachment image" href="${safeUrl(url)}" target="_blank" rel="noopener"><img src="${safeUrl(url)}" alt="${name}" loading="lazy"><span>${name}</span></a>`;
    }
    if (a.media_kind === 'audio' || mime.startsWith('audio/')) {
      return `<div class="attachment audio"><div>${name}</div><audio controls preload="none" src="${safeUrl(url)}"></audio></div>`;
    }
    return `<a class="attachment file" href="${safeUrl(url)}" target="_blank" rel="noopener">📎 ${name}</a>`;
  }).join('')}</div>`;
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
      <div><div class="page-title">Chat</div><div class="page-subtitle">Workspace messages</div></div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-sm btn-outline" id="dm-chat-btn">+ Личка</button>
        <button class="btn btn-success btn-sm" id="create-chat-btn">+ New Chat</button>
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
    <div class="grid-2" id="chat-layout">
      <div id="chat-list"><div class="loading"><div class="spinner"></div></div></div>
      <div id="chat-messages">
        <div class="card" style="text-align:center;color:var(--text2);padding:40px">
          <div style="font-size:40px;margin-bottom:8px">💬</div>
          <div>Select a chat to view messages</div>
        </div>
      </div>
    </div>`;
  try {
    const data = await api(`/chat/api/chats?session_token=${encodeURIComponent(STATE.token)}`);
    if (!data.items?.length) {
      $('#chat-list').innerHTML = '<div class="empty"><div class="empty-text">No chats found</div></div>';
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
      item.innerHTML = `<div class="chat-item-title">${esc(displayTitle)} <span style="color:var(--text2);font-size:11px">#${chat.chat_id}</span></div>
        <div class="chat-item-desc">${chat.description ? esc(chat.description) : 'No description'}</div>`;
      item.onclick = () => loadChatMessages(chat.chat_id, chat.title, item);
      list.append(item);
    });
    $('#chat-list').innerHTML = '';
    $('#chat-list').append(list);
    // auto-select first
    if (data.items.length && list.firstChild) {
      list.firstChild.click();
    }
  } catch(e) {
    $('#chat-list').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
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
        item.innerHTML = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${u.status==='banned'?'#f85149':u.status==='blocked'?'#d29922':'#30363d'};margin-right:6px"></span><strong>${esc(u.login)}</strong> <span style="color:var(--text2);font-size:12px">#${u.user_id}</span>`;
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
let messagesPollTimer = null;

async function loadChatMessages(chatId, title, itemEl) {
  $$('.chat-item.active').forEach(e => e.classList.remove('active'));
  if (itemEl) itemEl.classList.add('active');
  currentChatId = chatId;
  currentChatTitle = title;
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
  const div = el('div',{class:'msg',style:{flexDirection:isMe?'row-reverse':undefined}});
  const authorName = isMe ? esc(STATE.user?.login||'You') : esc(m.author_login || userName(m.author_user_id));
  div.innerHTML = `
    <div class="msg-avatar" style="cursor:pointer;${isMe?'background:var(--accent2)':''}" onclick="viewUserProfile(${m.author_user_id})" title="View profile">${esc(initial)}</div>
    <div class="msg-body" style="text-align:${isMe?'right':'left'}">
      <div class="msg-header" style="justify-content:${isMe?'flex-end':'flex-start'}">
        <span class="msg-author">${authorName}</span>
        <span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span>
      </div>
      <div class="msg-text">${esc(m.body_text || '')}${m.edited_at_ms ? ' <span style=font-size:10px;color:var(--text2)>(edited)</span>' : ''}</div>${isMe ? '<div class=msg-actions style=text-align:right;margin-top:4px;opacity:0.6><button class=btn-sm style=background:transparent;border:none;cursor:pointer;font-size:14px;padding:2px 6px title="Edit" onclick="editMsg(' + m.message_id + ',this)">✏️</button> <button class=btn-sm style=background:transparent;border:none;cursor:pointer;font-size:14px;padding:2px 6px title="Delete" onclick="confirmDel(' + m.message_id + ')">🗑️</button></div>' : ''}
    ${renderAttachments(m.attachments)}
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
        older.forEach(m => fragment.append(buildMessageEl(m)));
        list.insertBefore(fragment, anchor ? anchor.nextSibling : list.firstChild);
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
    container.innerHTML = `
      <div class="card" style="padding:16px">
        <div class="card-title" style="font-size:16px">${esc(currentChatTitle)}</div>
        <div id="msg-list" style="max-height:60vh;overflow-y:auto;margin-bottom:12px"></div>
        <div class="send-area">
          <textarea id="msg-input" placeholder="Type a message..." rows="1"></textarea>
          <button class="btn btn-primary btn-sm" id="send-btn">Send</button>
        </div>
      </div>`;
    const list = $('#msg-list');
    if (msgs.length >= limit) {
      const olderBtn = el('button',{class:'btn btn-sm btn-outline load-older',style:'width:100%;margin-bottom:8px'},'↑ Load older messages');
      olderBtn.onclick = () => doLoadMessages({older:true});
      list.append(olderBtn);
    }
    msgs.forEach(m => list.append(buildMessageEl(m)));
    msgLoadOffset = msgs.length;
    if (opts.force || wasAtBottom) { requestAnimationFrame(function() { if (list) list.scrollTop = list.scrollHeight; }); } else { list.scrollTop = oldScrollTop; }
    list.onscroll = function() {
      if (list.scrollTop < 40 && list.querySelector('.load-older')) doLoadMessages({older:true});
    };
    $('#send-btn').onclick = sendMessage;
    $('#msg-input').onkeydown = e => {if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}};
  } catch(e) {
    if (container) container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function sendMessage() {
  const input = $('#msg-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  const sendBtn = $('#send-btn');
  if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Sending...'; }
  try {
    await api(`/chat/api/chats/${currentChatId}/messages`, {
      method:'POST',
      body:JSON.stringify({session_token:STATE.token, body_text:text, attachment_ids:[]})
    });
    await doLoadMessages({force:true});
  } catch(e) {
    toast(e.message, 'error');
  } finally {
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Send'; }
  }
}

async function renderDevices() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Devices</div><div class="page-subtitle">Supported hardware catalog</div></div>
    </div>
    <div id="device-grid" class="grid-3"><div class="loading"><div class="spinner"></div></div></div>`;
  try {
    const data = await api(`/devices/api/catalog?session_token=${encodeURIComponent(STATE.token)}`);
    const grid = $('#device-grid');
    grid.innerHTML = '';
    if (!data.items?.length) {
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
        ${d.firmware_archive_url ? `<a href="${esc(d.firmware_archive_url)}" target="_blank" class="btn btn-sm btn-outline" style="margin-bottom:8px;width:100%;display:block;text-align:center;text-decoration:none">Download Firmware</a>` : ''}
        <details><summary style="cursor:pointer;font-size:13px;color:var(--accent)">Guides</summary>
          <div style="font-size:13px;color:var(--text2);margin-top:8px">
            <p><strong>Install:</strong> ${esc(d.install_guide||'N/A')}</p>
            <p><strong>Pairing:</strong> ${esc(d.pairing_guide||'N/A')}</p>
            <p><strong>Reset:</strong> ${esc(d.combo_reset_guide||'N/A')}</p>
          </div>
        </details>
        <button class="btn btn-sm ${d.has_device?'btn-danger':'btn-success'}" data-device-id="${d.device_id}" style="margin-top:8px;width:100%">
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
          renderDevices();
        } catch(e) { toast(e.message, 'error'); }
      };
      grid.append(card);
    });
  } catch(e) {
    $('#device-grid').innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="empty-text">${esc(e.message)}</div></div>`;
  }

  // Pair device section
  try {
    const pairings = await api(`/devices/api/pair/list?session_token=${encodeURIComponent(STATE.token)}`);
    const pairDiv = el('div',{style:'margin-top:24px;padding:16px;background:var(--bg2);border-radius:8px;border:1px solid var(--border)'});
    pairDiv.innerHTML = `
      <h3 style="margin:0 0 12px">Pair New Device</h3>
      <p style="color:var(--text2);font-size:13px;margin-bottom:12px">Enter the Device ID shown on your device screen</p>
      <div style="display:flex;gap:8px">
        <input id="pair-device-id" placeholder="Device ID (e.g. m5stickc-...)" style="flex:1;padding:8px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px">
        <button id="pair-btn" class="btn btn-success" style="white-space:nowrap">Pair Device</button>
      </div>
      <div id="pair-msg" style="margin-top:8px;font-size:13px"></div>
      ${pairings.items?.length ? `<div style="margin-top:16px"><h4 style="margin:0 0 8px;font-size:14px">Paired Devices</h4>${pairings.items.map(p=>`<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)"><span>${esc(p.device_id)}</span><button class="btn btn-sm btn-danger" data-id="${esc(p.device_id)}">Unpair</button></div>`).join('')}</div>` : ''}
    `;
    c.append(pairDiv);

    $('#pair-btn').onclick = async () => { 
      const did = $('#pair-device-id').value.trim();
      if(!did) return;
      $('#pair-btn').disabled = true; $('#pair-btn').textContent = 'Pairing...';
      try {
        await api('/devices/api/pair', {method:'POST',body:JSON.stringify({session_token:STATE.token,device_id:did})});
        $('#pair-msg').innerHTML = '<span style="color:var(--success)">Device paired! It will connect automatically.</span>';
        $('#pair-device-id').value = '';
      } catch(e) { $('#pair-msg').innerHTML = `<span style="color:var(--danger)">${esc(e.message)}</span>`; }
      $('#pair-btn').disabled = false; $('#pair-btn').textContent = 'Pair Device';
    };

    // Unpair buttons
    pairDiv.querySelectorAll('[data-id]').forEach(btn => {
      btn.onclick = async () => { 
        try {
          await api('/devices/api/unpair', {method:'POST',body:JSON.stringify({session_token:STATE.token,device_id:btn.dataset.id})});
          renderDevices();
        } catch(e) { toast(e.message,'error'); }
      };
    });
  } catch(e) { /* pair list may not be available */ }
}

async function renderAccount() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Account</div><div class="page-subtitle">Your profile</div></div>
    </div>
    <div id="account-card"><div class="loading"><div class="spinner"></div></div>
        </div>`;
  try {
    const data = await api(`/account/api/profile?session_token=${encodeURIComponent(STATE.token)}`);
    const p = data.profile;
    $('#account-card').innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
          <div class="account-avatar">${esc(p.avatar_emoji || localStorage.getItem('lc_my_emoji') || '🐱')}</div>
          <div>
            <div style="font-size:18px;font-weight:600">${esc(p.display_name||p.login)}</div>
            <div style="font-size:13px;color:var(--text2)">@${esc(p.login)} · <span class="badge badge-${p.role}">${p.role}</span></div>
          </div>
        </div>
        
        <div class="form-group">
          <label>Display Name</label>
          <input class="form-input" id="acct-name" value="${esc(p.display_name||'')}">
        </div>
        <div class="form-group">
          <label>Phone</label>
          <input class="form-input" id="acct-phone" value="${esc(p.phone||'')}">
        </div>
        <div class="form-group">
          <label>Bio</label>
          <textarea class="form-input" id="acct-bio" rows="3">${esc(p.profile_bio||'')}</textarea>
        </div>
        <button class="btn btn-success" id="acct-save">Save Changes</button>
        <div class="card" style="margin-top:12px;text-align:center">
          <div style="font-size:36px;margin-bottom:4px" id="my-emoji-display"></div>
          <div style="color:#8b949e;font-size:11px;margin-bottom:6px">Avatar emoji</div>
          <div id="emoji-grid" style="display:flex;flex-wrap:wrap;gap:4px;justify-content:center;max-width:280px;margin:0 auto"></div>
        </div>
        
      </div>`;

    // Emoji avatar picker (stored on the server, mirrored locally)
    var myEmoji = p.avatar_emoji || localStorage.getItem("lc_my_emoji") || "🐱";
    var ed = document.getElementById("my-emoji-display");
    if (ed) ed.textContent = myEmoji;
    var eg = document.getElementById("emoji-grid");
    if (eg) {
      var emojis = ["🐱","🐶","🐼","🦊","🐸","🐵","🦁","🐮","🐷","🐭","🐹","🐰","🐻","🐨","🐯","🐙","🦄","🐳","🐧","🐤","👻","🤖","👽","🐲","🦋","🐞","🐝","🦉","🐺","🐴"];
      emojis.forEach(function(e) {
        var d = document.createElement("div");
        d.textContent = e; d.style.cssText = "font-size:24px;cursor:pointer;padding:2px;border-radius:4px;width:36px;text-align:center";
        if (e === myEmoji) d.style.background = "#238636";
        d.onclick = async function() {
          localStorage.setItem("lc_my_emoji", e);
          document.getElementById("my-emoji-display").textContent = e;
          document.querySelectorAll("#emoji-grid div").forEach(function(x) { x.style.background = ""; });
          d.style.background = "#238636";
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
      <div><div class="page-title">Blog</div><div class="page-subtitle">Latest posts</div></div>
    </div>
    <div id="blog-list"><div class="loading"><div class="spinner"></div></div></div>`;
  try {
    const data = await api(`/blog/api/posts?session_token=${encodeURIComponent(STATE.token)}`);
    const list = $('#blog-list');
    list.innerHTML = '';
    if (!data.items?.length) {
      list.innerHTML = '<div class="empty"><div class="empty-text">No posts yet</div></div>';
      return;
    }
    data.items.forEach(post => {
      const div = el('div',{class:'blog-card'});
      div.innerHTML = `
        <h3>${esc(post.title)}</h3>
        <div class="blog-meta">By User #${post.author_user_id} · ${fmtTime(post.published_at_ms)}</div>
        <div class="blog-body">${esc(post.body_text)}</div>`;
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
      <div><div class="page-title">Support</div><div class="page-subtitle">Help desk tickets</div></div>
      <button class="btn btn-success btn-sm" id="new-ticket-btn" style="${STATE.user?.role === 'guest' ? 'display:none' : ''}">+ New Ticket</button>
    </div>
    <div id="new-ticket-modal" class="overlay hidden">
      <div class="modal">
        <h3>New Ticket</h3>
        <div class="form-group"><label>Type</label>
          <select class="form-input" id="ticket-kind">
            <option value="support">Support request</option>
            <option value="report">Report a user</option>
          </select>
        </div>
        <div class="form-group" id="report-user-group" style="display:none">
          <label>User to report</label>
          <input class="form-input" id="report-user-search" placeholder="Search by login...">
          <div id="report-user-results" style="max-height:140px;overflow-y:auto;margin-top:6px"></div>
        </div>
        <div class="form-group"><label>Title</label><input class="form-input" id="ticket-title"></div>
        <div class="form-group"><label>Description</label><textarea class="form-input" id="ticket-body" rows="4"></textarea></div>
        <div class="form-group"><label>Attachments</label><input class="form-input" id="ticket-file" type="file" multiple></div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn btn-outline" id="ticket-cancel">Cancel</button>
          <button class="btn btn-primary" id="ticket-submit">Submit</button>
        </div>
      </div>
    </div>
    <div class="grid-2" id="support-layout">
      <div id="ticket-list"><div class="loading"><div class="spinner"></div></div></div>
      <div id="ticket-detail">
        <div class="card" style="text-align:center;color:var(--text2);padding:40px">
          <div style="font-size:40px;margin-bottom:8px">🎫</div>
          <div>Select a ticket to view</div>
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
          <div style="font-size:12px;color:var(--text2)">${t.kind === 'report' ? '🚩 report · ' : ''}${fmtTime(t.created_at_ms)}</div>`;
        item.onclick = () => loadTicketDetail(t.ticket_id, t.title, item);
        list.append(item);
      });
      if (data.items.length && list.firstChild) list.firstChild.click();
    } else {
      list.innerHTML = '<div class="empty"><div class="empty-text">No tickets</div></div>';
    }
  } catch(e) {
    $('#ticket-list').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
  // always attach modal handlers regardless of API result
  const reportTarget = { user_id: null };
  function onKindChange() {
    const kindSel = $('#ticket-kind');
    const group = $('#report-user-group');
    if (group) group.style.display = kindSel && kindSel.value === 'report' ? '' : 'none';
  }
  async function prefillReportUser(uid) {
    const results = $('#report-user-results');
    if (!results) return;
    try {
      const d = await api(`/account/api/profile/${uid}?session_token=${encodeURIComponent(STATE.token)}`);
      const p = d.profile;
      results.innerHTML = `<div class="ticket-item" style="padding:8px;border-radius:6px;background:var(--bg3)">✔ ${esc(p.display_name||p.login)} (#${p.user_id})</div>`;
    } catch(e) { results.innerHTML = `<div style="padding:6px;color:var(--text2)">User #${uid}</div>`; }
  }
  const newTicketBtn = $('#new-ticket-btn');
  if (newTicketBtn) newTicketBtn.onclick = () => {
    show('#new-ticket-modal');
    if (window.STATE_REPORT_TARGET) {
      const kindSel = $('#ticket-kind');
      if (kindSel && STATE.user?.role !== 'guest') kindSel.value = 'report';
      reportTarget.user_id = window.STATE_REPORT_TARGET;
      window.STATE_REPORT_TARGET = null;
      onKindChange();
      prefillReportUser(reportTarget.user_id);
    } else {
      onKindChange();
    }
  };
  $('#ticket-cancel').onclick = () => { hide('#new-ticket-modal'); $('#ticket-title').value=''; $('#ticket-body').value=''; if ($('#ticket-file')) $('#ticket-file').value=''; };
  const kindSelEl = $('#ticket-kind');
  if (kindSelEl) kindSelEl.onchange = onKindChange;
  const reportSearchEl = $('#report-user-search');
  if (reportSearchEl) {
    let reportTimer = null;
    reportSearchEl.oninput = () => {
      clearTimeout(reportTimer);
      reportTimer = setTimeout(async () => {
        const q = reportSearchEl.value.trim();
        const results = $('#report-user-results');
        if (!results) return;
        if (!q) { results.innerHTML = ''; return; }
        try {
          const d = await api(`/chat/api/users/search?session_token=${encodeURIComponent(STATE.token)}&q=${encodeURIComponent(q)}`);
          results.innerHTML = '';
          (d.items||[]).forEach(u => {
            if (u.user_id === STATE.user?.id) return;
            const item = el('div',{class:'ticket-item',style:'padding:8px;cursor:pointer;border-radius:6px'},`${u.login} (#${u.user_id})`);
            item.onclick = () => {
              reportTarget.user_id = u.user_id;
              results.querySelectorAll('.ticket-item').forEach(x => x.style.background='');
              item.style.background = 'var(--bg3)';
            };
            results.append(item);
          });
          if (!results.children.length) results.innerHTML = '<div style="padding:6px;color:var(--text2)">Not found</div>';
        } catch(e) { results.innerHTML = `<div style="padding:6px;color:var(--accent4)">${esc(e.message)}</div>`; }
      }, 300);
    };
  }
  $('#ticket-submit').onclick = async () => { 
    const title = $('#ticket-title').value.trim();
    const body = $('#ticket-body').value.trim();
    const kindValue = ($('#ticket-kind')?.value) || 'support';
    const files = Array.from($('#ticket-file')?.files || []);
    if (!title || !body) { toast('Fill in title and message', 'error'); return; }
    if (kindValue === 'report' && !reportTarget.user_id) { toast('Select the user to report', 'error'); return; }
    const submitBtn = $('#ticket-submit');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Submitting...'; }
    try {
      const attachmentIds = [];
      for (const file of files) { const a = await uploadAttachment(file); attachmentIds.push(a.attachment_id); }
      await api('/support/api/tickets', {
        method:'POST',
        body:JSON.stringify({
          session_token:STATE.token, title, body_text:body, attachment_ids:attachmentIds,
          kind: kindValue,
          target_user_id: kindValue === 'report' ? reportTarget.user_id : undefined,
        })
      });
      toast('Ticket created', 'success');
      hide('#new-ticket-modal');
      $('#ticket-title').value=''; $('#ticket-body').value=''; if ($('#ticket-file')) $('#ticket-file').value='';
      reportTarget.user_id = null;
      renderSupport();
    } catch(e) { toast(e.message, 'error'); }
    finally { if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Submit'; } }
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
        <div style="margin-bottom:12px"><button class="btn btn-sm btn-outline" id="close-ticket-btn">Close Ticket</button></div>
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
            </div>`).join('') : '<div style="color:var(--text2);text-align:center;padding:16px">No messages</div>'}
        </div>
        <div class="send-area">
          <textarea id="support-input" placeholder="Reply..." rows="1"></textarea>
          
          <input id="support-file" type="file" multiple style="max-width:180px">
          <button class="btn btn-primary btn-sm" id="support-send">Send</button>
        </div>
        
      </div>`;
    $('#close-ticket-btn').onclick = async () => { try { await api('/support/api/tickets/' + currentTicketId + '/status', {method:'POST',body:JSON.stringify({session_token:STATE.token,status:'closed'})}); toast('Ticket closed','success'); loadTicketDetail(currentTicketId, title, null); } catch(e) { toast(e.message,'error'); } };
    $('#support-send').onclick = async () => { 
      const inp = $('#support-input');
      if (!inp?.value.trim()) return;
      const text = inp.value.trim();
      inp.value = '';
      $('#support-send').disabled = true;
      try {
        const attachments = [];
        var files = Array.from(document.getElementById('support-file')?.files || []);
        for (const file of files) attachments.push(await uploadAttachment(file));
        await api(`/support/api/tickets/${currentTicketId}/messages`, {
          method:'POST',
          body:JSON.stringify({session_token:STATE.token, body_text:text, attachment_ids:attachments.map(a=>a.attachment_id)})
        });
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
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Admin Panel</div><div class="page-subtitle">System management</div></div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="users">Users</button>
      <button class="tab" data-tab="blog">Blog</button>
      <button class="tab" data-tab="support">Support</button>
      <button class="tab" data-tab="mode">Mode</button>
      <button class="tab" data-tab="cleanup">Cleanup</button>
      <button class="tab" data-tab="passwords">Passwords</button>
      <button class="tab" data-tab="system">System</button>
      <button class="tab" data-tab="activity">Activity</button>
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
  try {
    const data = await api(`/moderation/api/admin/reports?session_token=${encodeURIComponent(STATE.token)}&limit=100`);
    let html = `<div class="admin-card"><h3>Moderation Reports <span style="color:var(--accent4)">(${data.pending_count||0} pending)</span></h3>`;
    if (!data.reports?.length) html += '<div class="empty"><div class="empty-text">No reports</div></div>';
    html += (data.reports||[]).map(r => `
      <div class="user-row" style="display:block">
        <div style="display:flex;justify-content:space-between">
          <strong>${esc(r.user_login||('User #'+r.user_id))}</strong>
          <span style="font-size:11px;color:var(--text2)">#${r.id} ${esc(r.status)}</span>
        </div>
        <div style="font-size:12px;color:var(--accent4);margin:4px 0">Words: ${esc(r.found_words||'')}</div>
        <div style="font-size:12px;background:var(--bg);padding:6px;border-radius:4px;margin:4px 0;max-height:80px;overflow-y:auto">${esc(r.message_text||'')}</div>
        ${r.status === 'pending' ? `<div style="margin-top:6px">
            <button class="btn btn-sm btn-danger" data-rrep="${r.id}" data-raction="ban">Ban</button>
            <button class="btn btn-sm btn-outline" data-rrep="${r.id}" data-raction="warn">Warn</button>
            <button class="btn btn-sm btn-outline" data-rrep="${r.id}" data-raction="dismiss">Dismiss</button>
          </div>` : `<div style="font-size:11px;color:var(--text2)">Resolved: ${esc(r.action||'?')} by ${esc(r.resolved_by||'?')}</div>`}
      </div>`).join('');
    html += '</div>';
    container.innerHTML = html;
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
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function renderAdminUsers() {
  const container = $('#admin-users');
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const data = await api(`/admin/users?session_token=${encodeURIComponent(STATE.token)}&_=${Date.now()}`);
    var onlineIds = [];
    try { var od = await api('/realtime/online', {method:'POST',body:JSON.stringify({session_token:STATE.token})}); onlineIds = od.online_user_ids || []; } catch(e) {}
    const items = data.items || [];
    container.innerHTML = `<div class="admin-card">
      <h3>Users (${items.length})</h3>
      ${items.map(u => `
        <div class="user-row">
          <div style="flex:1">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${u.status==='banned'?'#f85149':u.status==='blocked'?'#d29922':onlineIds.includes(u.user_id)?'#238636':'#30363d'};margin-right:6px"></span><strong>${esc(u.login)}</strong>
            <span class="user-role ${u.role}">${u.role}</span>
            <span class="user-status ${u.status}" style="margin-left:8px">${u.status}</span>${u.blocked_until_ms ? ' <span class="blocked-until" data-until="' + u.blocked_until_ms + '" style="font-size:11px;color:var(--accent3);margin-left:6px">(unblocks in ...)</span>' : ''}
            ${u.device_blacklisted ? '<span class="device-tag owned" style="font-size:10px">blacklisted</span>' : ''}
          </div>
          <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">
            ${u.user_id === STATE.user?.id ? '<span style="font-size:12px;color:var(--text2)">you</span>' : `
              ${u.status === 'active' ? `<button class="btn btn-sm btn-outline" data-action="setrole" data-uid="${u.user_id}" data-role="${u.role==='moderator'?'user':'moderator'}">${u.role==='moderator'?'Demote':'Promote'}</button>
              <button class="btn btn-sm btn-danger" data-action="ban" data-uid="${u.user_id}">Ban</button>
              <input class="tb-dur" data-uid="${u.user_id}" type="number" min="1" max="10080" value="60" style="width:50px;padding:4px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:12px;text-align:center" title="Minutes"><button class="btn btn-sm btn-outline" data-action="tempblock" data-uid="${u.user_id}">min</button>
              ${u.device_blacklisted ? `<button class="btn btn-sm btn-outline" data-action="unblacklist" data-uid="${u.user_id}">Unblacklist Dev</button>` : `<button class="btn btn-sm btn-outline" data-action="blacklist" data-uid="${u.user_id}">Blacklist Dev</button>`}
              <button class="btn btn-sm btn-danger" data-action="delete" data-uid="${u.user_id}" data-login="${esc(u.login)}">Delete</button>` : `
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
    data.items.forEach(t => {
      const card = el('div',{class:'ticket-item',style:'margin-bottom:8px'});
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${esc(t.title)}</strong>
          <select class="ats" data-tid="${t.ticket_id}" style="padding:4px 8px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:12px"><option value="open" ${t.status==="open"?"selected":""}>open</option><option value="in_progress" ${t.status==="in_progress"?"selected":""}>in progress</option><option value="resolved" ${t.status==="resolved"?"selected":""}>resolved</option><option value="closed" ${t.status==="closed"?"selected":""}>closed</option></select><button class="btn btn-sm btn-outline aus" data-tid="${t.ticket_id}">Update</button>
        </div>
        <div style="font-size:12px;color:var(--text2)">${t.kind === 'report' ? '🚩 report · ' : ''}User #${t.user_id} · ${fmtTime(t.created_at_ms)}</div>
        <div id="admin-ticket-${t.ticket_id}-msgs" style="display:none;margin-top:8px;border-top:1px solid var(--border);padding-top:8px"></div>
        <div id="admin-ticket-${t.ticket_id}-reply" style="display:none;margin-top:8px" class="send-area">
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
        const inp = $(`#admin-ticket-${tid}-input`);
        if (!inp?.value.trim()) { toast("Reply cannot be empty", "error"); return; }
        const text = inp.value.trim(); inp.value = '';
        try {
          await api(`/admin/content/support/tickets/${tid}/reply`, {
            method:'POST',
            body:JSON.stringify({session_token:STATE.token, body_text:text})
          });
          toast('Reply sent', 'success');
        } catch(e) { toast(e.message, 'error'); }
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
  try {
    const data = await api(`/admin/content/blog/posts?session_token=${encodeURIComponent(STATE.token)}`);
    container.innerHTML = `
      <div class="admin-card">
        <h3>Publish Post</h3>
        <div class="form-group"><label>Title</label><input class="form-input" id="blog-post-title"></div>
        <div class="form-group"><label>Body</label><textarea class="form-input" id="blog-post-body" rows="6"></textarea></div>
        <button class="btn btn-success" id="blog-post-publish">Publish</button>
      </div>
      <div class="admin-card"><h3>Published Posts (${data.count||0})</h3></div>`;
    $('#blog-post-publish').onclick = async () => { 
      const title = $('#blog-post-title').value.trim();
      const body = $('#blog-post-body').value.trim();
      if (!title || !body) { toast('Fill in all fields', 'error'); return; }
      try {
        await api('/admin/content/blog/posts', {
          method:'POST',
          body:JSON.stringify({session_token:STATE.token, title, body_text:body})
        });
        toast('Post published', 'success');
        $('#blog-post-title').value=''; $('#blog-post-body').value='';
        renderAdminBlog();
      } catch(e) { toast(e.message, 'error'); }
    };
    if (data.items?.length) {
      data.items.forEach(post => {
        const div = el('div',{class:'blog-card',style:'margin-bottom:8px'});
        div.innerHTML = `<h3>${esc(post.title)}</h3>
          <div class="blog-meta">Published ${fmtTime(post.published_at_ms)}</div>
          <div class="blog-body">${esc(post.body_text)}</div>`;
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

async function handleRoute() {
  const hash = window.location.hash || '#/login';
  if (hash === '#/login' && STATE.token) {window.location.hash = '#/chat'; return}
  const publicRoutes = ['#/login', '#/about'];
  if (!publicRoutes.includes(hash.split('?')[0]) && !STATE.token) {window.location.hash = '#/login'; return}
  updateNav();
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
  $('#hamburger').onclick = () => $('#nav-links').classList.toggle('open');
  // close nav on link click (mobile)
  $$('.nav-links a').forEach(a => a.onclick = () => $('#nav-links').classList.remove('open'));
  $('#logout-btn').onclick = async () => { 
    if (STATE.token) {
      try { await api('/auth/logout', {method:'POST',body:JSON.stringify({session_token:STATE.token})}) } catch(e) {}
    }
    clearAuth();
  };
};





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
    var health = h.health || {};
    var svcs = s.services || [];
    var html = "<div class=admin-card><h3>RPi System</h3>";
    html += "<div style=display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px>";
    html += "<div style=background:var(--bg);padding:12px;border-radius:8px;text-align:center><div style=font-size:24px;font-weight:700;color:var(--accent2)>" + (health.cpu_temp||"?") + "</div><div style=font-size:11px;color:var(--text2)>CPU</div></div>";
    html += "<div style=background:var(--bg);padding:12px;border-radius:8px;text-align:center><div style=font-size:24px;font-weight:700>" + (health.ram_used||"?") + "</div><div style=font-size:11px;color:var(--text2)>RAM / " + (health.ram_total||"?") + "</div></div>";
    html += "<div style=background:var(--bg);padding:12px;border-radius:8px;text-align:center><div style=font-size:24px;font-weight:700>" + (health.disk_used||"?") + "</div><div style=font-size:11px;color:var(--text2)>Disk " + (health.disk_pct||"?") + "</div></div>";
    html += "</div><h4 style=margin:12px 0 8px>Services</h4>";
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
"view":{rus:"Смотреть",eng:"View"},"login_btn":{rus:"Войти",eng:"Login"},
"about_text":{rus:"Local Chat — локальный чат-сервер на Raspberry Pi 5. Автономная система без интернета. Чат, блог, тикеты, админ-панель.",eng:"Local Chat — self-hosted chat on Raspberry Pi 5. Works offline. Chat, blog, tickets, admin panel."},
"sign_in_portal":{rus:"Войдите для доступа",eng:"Sign in to access internet"},
"enter_login":{rus:"Введите логин",eng:"Enter login"},
"lang_label":{rus:"🇷🇺 RUS",eng:"🇬🇧 ENG"},"enter_pass":{rus:"Введите пароль",eng:"Enter password"},
};
function t(key) { var e = T[key]; return e ? (e[LANG] || e["rus"] || key) : key; }


// Profile viewer — click avatar in chat
function showProfileModal(html) {
  var m = document.getElementById("profile-modal");
  if (!m) {
    m = document.createElement("div");
    m.id = "profile-modal";
    m.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px";
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
    var h = "<div style=background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;max-width:340px;width:100%;position:relative>";
    h += "<button onclick=document.getElementById(\"profile-modal\").remove() style=position:absolute;top:8px;right:8px;background:none;border:none;color:#8b949e;font-size:20px;cursor:pointer>&times;</button>";
    h += "<div style=text-align:center;font-size:48px;margin-bottom:8px>" + esc(emoji) + "</div>";
    h += "<h2 style=color:#58a6ff;text-align:center;margin:8px 0;font-size:18px>" + esc(p.display_name || p.login) + "</h2>";
    h += "<div style=text-align:center;color:#8b949e;font-size:13px>@" + esc(p.login) + "</div>";
    h += "<div style=text-align:center;color:#8b949e;font-size:12px;margin-bottom:12px>" + esc(p.role) + "</div>";
    if (p.phone) h += "<div style=margin:6px 0;font-size:13px>📞 " + esc(p.phone) + "</div>";
    if (p.profile_bio) h += "<div style=margin-top:8px;font-size:13px;white-space:pre-wrap;background:#0d1117;padding:10px;border-radius:6px;line-height:1.4>" + esc(p.profile_bio) + "</div>";
    h += "<div style='display:flex;gap:8px;margin-top:14px;justify-content:center'>";
    h += "<button id=pm-dm style=background:#238636;color:#fff;border:none;padding:8px 14px;border-radius:6px;cursor:pointer>✉ DM</button>";
    if (!isGuest) h += "<button id=pm-report style=background:#da3633;color:#fff;border:none;padding:8px 14px;border-radius:6px;cursor:pointer>🚩 Report</button>";
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
      window.STATE_REPORT_TARGET = uid;
      var modal = document.getElementById("profile-modal"); if (modal) modal.remove();
      window.location.hash = '#/support';
    };
  } catch(e) { toast(e.message, "error"); }
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
  var newText = prompt("Edit message:", current);
  if (newText === null) return;
  newText = newText.trim();
  if (!newText || newText === current) return;
  try {
    await api("/chat/api/chats/" + currentChatId + "/messages/" + mid, {method:"PUT", body:JSON.stringify({session_token:STATE.token, body_text:newText})});
    doLoadMessages({force:true});
  } catch(e) { toast(e.message, "error"); }
}

function confirmDel(mid) {
  var overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);z-index:99999;display:flex;align-items:center;justify-content:center";
  overlay.innerHTML = "<div style=background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;max-width:320px;text-align:center><div style=font-size:40px;margin-bottom:8px>🗑️</div><h3 style=color:#e6edf3;margin:0 0 16px>Delete this message?</h3><div style=display:flex;gap:8px;justify-content:center><button id=cfm-yes style=background:#da3633;color:#fff;border:none;padding:8px 24px;border-radius:6px;cursor:pointer;font:14px monospace>Yes, delete</button><button id=cfm-no style=background:#30363d;color:#e6edf3;border:none;padding:8px 24px;border-radius:6px;cursor:pointer;font:14px monospace>No, keep it</button></div></div>";
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
