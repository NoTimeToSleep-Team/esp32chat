const STATE = {
  token: localStorage.getItem('lc_session_token') || null,
  user: JSON.parse(localStorage.getItem('lc_user') || 'null'),
  chatCache: {},
  ticketCache: {},
};

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
  try {
    const r = await fetch(url, {...opts, headers});
    const d = await r.json();
    if (!r.ok) throw new Error(d?.detail?.message || d?.detail?.code || `HTTP ${r.status}`);
    return d;
  } catch(e) {
    if (e.name!=='TypeError') throw e;
    throw new Error('Server unreachable');
  }
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
  const isAdmin = STATE.user?.role === 'admin';
  if (authed) {
    show('#nav-links'); show('#nav-right');
  } else {
    hide('#nav-links'); hide('#nav-right');
  }
  const adminLink = $('#admin-link');
  if (adminLink) adminLink.style.display = isAdmin ? '' : 'none';
  const userEl = $('#nav-user');
  if (userEl) userEl.textContent = STATE.user?.login || '';
  $$('.nav-links a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === window.location.hash);
  });
}

/* ===== PAGES ===== */

function renderLogin() {
  const c = $('#content');
  let mode = 'login';
  function renderForm() {
    const isLogin = mode === 'login';
    c.innerHTML = `
      <div class="login-page">
        <div class="login-card">
          <div class="login-title">Local Chat</div>
          <div class="login-subtitle">${isLogin ? 'Sign in to your account' : 'Create an account'}</div>
          <div id="login-error" class="login-error"></div>
          <div class="form-group">
            <label>Login</label>
            <input class="form-input" id="login-login" type="text" placeholder="Enter login" autocomplete="username">
          </div>
          <div class="form-group">
            <label>Password</label>
            <input class="form-input" id="login-pass" type="password" placeholder="${isLogin ? 'Enter password' : 'Password (min 8 chars)'}" autocomplete="${isLogin ? 'current-password' : 'new-password'}">
          </div>
          ${isLogin ? '' : `<div class="form-group"><label>Phone (optional)</label><input class="form-input" id="login-phone" type="text" placeholder="+7..."></div>`}
          <button class="btn btn-primary" id="login-btn" style="width:100%;justify-content:center">${isLogin ? 'Sign In' : 'Create Account'}</button>
          <div style="text-align:center;margin-top:16px;font-size:14px;color:var(--text2)">
            ${isLogin ? "Don't have an account? <a href='#' id='login-toggle'>Register</a>" : "Already have an account? <a href='#' id='login-toggle'>Sign in</a>"}
          </div>
        </div>
      </div>`;
    $('#login-toggle').onclick = (e) => { e.preventDefault(); mode = isLogin ? 'register' : 'login'; renderForm(); };
    const btn = $('#login-btn');
    const loginInput = $('#login-login');
    const passInput = $('#login-pass');
    const phoneInput = $('#login-phone');
    btn.onclick = isLogin ? doLogin : doRegister;
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
    const phone = ($('#login-phone')?.value||'').trim() || '000';
    if (!login || !pass) {show('#login-error');$('#login-error').textContent='Fill in all fields';return}
    if (pass.length < 8) {show('#login-error');$('#login-error').textContent='Password must be at least 8 characters';return}
    hide('#login-error');
    $('#login-btn').disabled = true; $('#login-btn').textContent = 'Registering...';
    try {
      const data = await api('/auth/register', {method:'POST',body:JSON.stringify({login,password:pass,phone,device_id:'web',client_kind:'web'})});
      if (data.status !== 'ok') throw new Error(data.message || 'Registration failed');
      setAuth(data); window.location.hash = '#/chat';
    } catch(e) { show('#login-error'); $('#login-error').textContent = e.message; $('#login-btn').disabled = false; $('#login-btn').textContent = 'Create Account'; }
  }
  renderForm();
}

async function renderChat() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Chat</div><div class="page-subtitle">Workspace messages</div></div>
      <button class="btn btn-success btn-sm" id="create-chat-btn">+ New Chat</button>
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
      item.innerHTML = `<div class="chat-item-title">${esc(chat.title)}</div>
        <div class="chat-item-desc">${chat.description ? esc(chat.description) : 'No description'}</div>`;
      item.onclick = () => loadChatMessages(chat.chat_id, chat.title, item);
      list.append(item);
    });
    $('#chat-list').innerHTML = '';
    $('#chat-list').append(list);
    // auto-select first
    if (data.items.length) {
      const firstChat = data.items[0];
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
}

let currentChatId = null;
let currentChatTitle = '';
let messagesPollTimer = null;

async function loadChatMessages(chatId, title, itemEl) {
  $$('.chat-item.active').forEach(e => e.classList.remove('active'));
  if (itemEl) itemEl.classList.add('active');
  currentChatId = chatId;
  currentChatTitle = title;
  if (messagesPollTimer) clearInterval(messagesPollTimer);
  await doLoadMessages();
  messagesPollTimer = setInterval(doLoadMessages, 3000);
}

async function doLoadMessages() {
  if (!currentChatId) return;
  const container = $('#chat-messages');
  try {
    const data = await api(`/chat/api/chats/${currentChatId}/messages?session_token=${encodeURIComponent(STATE.token)}&limit=50`);
    const msgs = data.items || [];
    container.innerHTML = `
      <div class="card" style="padding:16px">
        <div class="card-title" style="font-size:16px">${esc(currentChatTitle)}</div>
        <div id="msg-list" style="max-height:50vh;overflow-y:auto;margin-bottom:12px"></div>
        <div class="send-area">
          <textarea id="msg-input" placeholder="Type a message..." rows="1"></textarea>
          <button class="btn btn-primary btn-sm" id="send-btn">Send</button>
        </div>
      </div>`;
    const list = $('#msg-list');
    msgs.forEach(m => {
      const isMe = m.author_user_id === STATE.user?.id;
      const initial = (isMe ? STATE.user?.login?.charAt(0) : 'U').toUpperCase();
      const div = el('div',{class:'msg',style:{flexDirection:isMe?'row-reverse':undefined}});
      div.innerHTML = `
        <div class="msg-avatar" style="${isMe?'background:var(--accent2)':''}">${esc(initial)}</div>
        <div class="msg-body" style="text-align:${isMe?'right':'left'}">
          <div class="msg-header" style="justify-content:${isMe?'flex-end':'flex-start'}">
            <span class="msg-author">${isMe?esc(STATE.user?.login||'You'):'User #'+m.author_user_id}</span>
            <span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span>
          </div>
          <div class="msg-text">${esc(m.body_text)}</div>
        </div>`;
      list.append(div);
    });
    list.scrollTop = list.scrollHeight;
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
  try {
    await api(`/chat/api/chats/${currentChatId}/messages`, {
      method:'POST',
      body:JSON.stringify({session_token:STATE.token, body_text:text})
    });
    await doLoadMessages();
  } catch(e) {
    toast(e.message, 'error');
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
}

async function renderAccount() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Account</div><div class="page-subtitle">Your profile</div></div>
    </div>
    <div id="account-card"><div class="loading"><div class="spinner"></div></div></div>`;
  try {
    const data = await api(`/account/api/profile?session_token=${encodeURIComponent(STATE.token)}`);
    const p = data.profile;
    $('#account-card').innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
          <div style="width:56px;height:56px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;color:#fff">${esc((p.display_name||p.login).charAt(0).toUpperCase())}</div>
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
      </div>`;
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

let currentTicketId = null;

async function renderSupport() {
  if (!requireAuth()) return;
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Support</div><div class="page-subtitle">Help desk tickets</div></div>
      <button class="btn btn-success btn-sm" id="new-ticket-btn">+ New Ticket</button>
    </div>
    <div id="new-ticket-modal" class="overlay hidden">
      <div class="modal">
        <h3>New Ticket</h3>
        <div class="form-group"><label>Title</label><input class="form-input" id="ticket-title"></div>
        <div class="form-group"><label>Description</label><textarea class="form-input" id="ticket-body" rows="4"></textarea></div>
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
      data.items.forEach(t => {
        const item = el('div',{class:'ticket-item'});
        item.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <strong>${esc(t.title)}</strong>
            <span class="ticket-status ${t.status}">${t.status.replace('_',' ')}</span>
          </div>
          <div style="font-size:12px;color:var(--text2)">${fmtTime(t.created_at_ms)}</div>`;
        item.onclick = () => loadTicketDetail(t.ticket_id, t.title, item);
        list.append(item);
      });
      if (data.items.length) list.firstChild.click();
    } else {
      list.innerHTML = '<div class="empty"><div class="empty-text">No tickets</div></div>';
    }
  } catch(e) {
    $('#ticket-list').innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
  // always attach modal handlers regardless of API result
  $('#new-ticket-btn').onclick = () => show('#new-ticket-modal');
  $('#ticket-cancel').onclick = () => { hide('#new-ticket-modal'); $('#ticket-title').value=''; $('#ticket-body').value=''; };
  $('#ticket-submit').onclick = async () => {
    const title = $('#ticket-title').value.trim();
    const body = $('#ticket-body').value.trim();
    if (!title || !body) { toast('Fill in all fields', 'error'); return; }
    try {
      await api('/support/api/tickets', {
        method:'POST',
        body:JSON.stringify({session_token:STATE.token, title, body_text:body})
      });
      toast('Ticket created', 'success');
      hide('#new-ticket-modal');
      $('#ticket-title').value=''; $('#ticket-body').value='';
      renderSupport();
    } catch(e) { toast(e.message, 'error'); }
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
        <div style="max-height:40vh;overflow-y:auto;margin-bottom:12px">
          ${msgs.length ? msgs.map(m => `
            <div class="msg" style="margin-bottom:8px">
              <div class="msg-avatar" style="width:28px;height:28px;font-size:11px">${m.author_user_id===STATE.user?.id?'Y':'U'}</div>
              <div class="msg-body">
                <div class="msg-header">
                  <span class="msg-author">${m.author_user_id===STATE.user?.id?esc(STATE.user?.login||'You'):'User #'+m.author_user_id}</span>
                  <span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span>
                </div>
                <div class="msg-text">${esc(m.body_text)}</div>
              </div>
            </div>`).join('') : '<div style="color:var(--text2);text-align:center;padding:16px">No messages</div>'}
        </div>
        <div class="send-area">
          <textarea id="support-input" placeholder="Reply..." rows="1"></textarea>
          <button class="btn btn-primary btn-sm" id="support-send">Send</button>
        </div>
      </div>`;
    $('#support-send').onclick = async () => {
      const inp = $('#support-input');
      if (!inp?.value.trim()) return;
      const text = inp.value.trim();
      inp.value = '';
      try {
        await api(`/support/api/tickets/${currentTicketId}/messages`, {
          method:'POST',
          body:JSON.stringify({session_token:STATE.token, body_text:text})
        });
        await loadTicketDetail(currentTicketId, title, null);
      } catch(e) { toast(e.message, 'error'); }
    };
    $('#support-input').onkeydown = e => {if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#support-send')?.click()}};
  } catch(e) {
    container.innerHTML = `<div class="empty"><div class="empty-text">${esc(e.message)}</div></div>`;
  }
}

async function renderAdmin() {
  if (!requireAuth()) return;
  if (STATE.user?.role !== 'admin') { window.location.hash = '#/chat'; return; }
  const c = $('#content');
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">Admin Panel</div><div class="page-subtitle">System management</div></div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="users">Users</button>
      <button class="tab" data-tab="support">Support</button>
      <button class="tab" data-tab="blog">Blog</button>
      <button class="tab" data-tab="mode">Mode</button>
    </div>
    <div id="admin-users"></div>
    <div id="admin-support" class="hidden"></div>
    <div id="admin-blog" class="hidden"></div>
    <div id="admin-mode" class="hidden"></div>`;
  $$('.tab').forEach(t => t.onclick = () => {
    $$('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    ['users','support','blog','mode'].forEach(id => hide(`#admin-${id}`));
    show(`#admin-${t.dataset.tab}`);
  });
  await renderAdminUsers();
  await renderAdminSupport();
  await renderAdminBlog();
  await renderAdminMode();
}

async function renderAdminUsers() {
  const container = $('#admin-users');
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const data = await api(`/admin/users?session_token=${encodeURIComponent(STATE.token)}`);
    const items = data.items || [];
    container.innerHTML = `<div class="admin-card">
      <h3>Users (${items.length})</h3>
      ${items.map(u => `
        <div class="user-row">
          <div style="flex:1">
            <strong>${esc(u.login)}</strong>
            <span class="user-role ${u.role}">${u.role}</span>
            <span class="user-status ${u.status}" style="margin-left:8px">${u.status}</span>
            ${u.device_blacklisted ? '<span class="device-tag owned" style="font-size:10px">blacklisted</span>' : ''}
          </div>
          <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">
            ${u.user_id === STATE.user?.id ? '<span style="font-size:12px;color:var(--text2)">you</span>' : `
              ${u.status === 'active' ? `<button class="btn btn-sm btn-danger" data-action="ban" data-uid="${u.user_id}">Ban</button>
              <button class="btn btn-sm btn-outline" data-action="tempblock" data-uid="${u.user_id}">Temp Block</button>
              ${u.device_blacklisted ? `<button class="btn btn-sm btn-outline" data-action="unblacklist" data-uid="${u.user_id}">Unblacklist Dev</button>` : `<button class="btn btn-sm btn-outline" data-action="blacklist" data-uid="${u.user_id}">Blacklist Dev</button>`}
              <button class="btn btn-sm btn-danger" data-action="delete" data-uid="${u.user_id}" data-login="${esc(u.login)}">Delete</button>` : `
              <button class="btn btn-sm btn-success" data-action="unban" data-uid="${u.user_id}">Unban</button>`}
            `}
          </div>
          <div style="font-size:12px;color:var(--text2);min-width:30px;text-align:right">ID ${u.user_id}</div>
        </div>`).join('')}
    </div>`;
    container.querySelectorAll('[data-action]').forEach(btn => {
      btn.onclick = async () => {
        const uid = btn.dataset.uid;
        const action = btn.dataset.action;
        if (action === 'delete') {
          if (!confirm(`Delete user "${btn.dataset.login}" (ID ${uid})?`)) return;
          try {
            await api(`/admin/users/${uid}?session_token=${encodeURIComponent(STATE.token)}`, {method:'DELETE'});
            toast('User deleted', 'success');
            renderAdminUsers();
          } catch(e) { toast(e.message, 'error'); }
          return;
        }
        if (action === 'tempblock') {
          const mins = prompt('Block duration (minutes, max 10080):', '60');
          if (!mins) return;
          const dur = parseInt(mins);
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
    data.items.forEach(t => {
      const card = el('div',{class:'ticket-item',style:'margin-bottom:8px'});
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center">
          <strong>${esc(t.title)}</strong>
          <span class="ticket-status ${t.status}">${t.status}</span>
        </div>
        <div style="font-size:12px;color:var(--text2)">User #${t.user_id} · ${fmtTime(t.created_at_ms)}</div>
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
                  <div class="msg-header"><span class="msg-author">${m.author_user_id===STATE.user?.id?'Admin':'User #'+m.author_user_id}</span><span class="msg-time">${fmtTimeShort(m.created_at_ms)}</span></div>
                  <div class="msg-text">${esc(m.body_text)}</div>
                </div>
              </div>`).join('') || '<div style="color:var(--text2);text-align:center">No messages</div>';
          } catch(e) { msgsDiv.innerHTML = `<div style="color:var(--accent4)">${esc(e.message)}</div>`; }
        }
      };
      container.append(card);
    });
    container.querySelectorAll('[data-tid]').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const tid = btn.dataset.tid;
        const inp = $(`#admin-ticket-${tid}-input`);
        if (!inp?.value.trim()) return;
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

/* ===== ROUTER ===== */
function esc(s) {const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function handleRoute() {
  const hash = window.location.hash || '#/login';
  if (hash === '#/login' && STATE.token) {window.location.hash = '#/chat'; return}
  if (hash !== '#/login' && !STATE.token) {window.location.hash = '#/login'; return}
  updateNav();
  switch(hash.split('?')[0]) {
    case '#/login': renderLogin(); break;
    case '#/chat': renderChat(); break;
    case '#/devices': renderDevices(); break;
    case '#/account': renderAccount(); break;
    case '#/blog': renderBlog(); break;
    case '#/support': renderSupport(); break;
    case '#/admin': renderAdmin(); break;
    default: window.location.hash = '#/chat';
  }
}

window.onhashchange = handleRoute;
window.onload = () => {
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
