const ui = {
  sessionTokenInput: document.getElementById("sessionToken"),
  loadPostsBtn: document.getElementById("loadPostsBtn"),
  postList: document.getElementById("postList"),
  publishForm: document.getElementById("publishPostForm"),
  postTitleInput: document.getElementById("postTitle"),
  postBodyInput: document.getElementById("postBody"),
  publishHint: document.getElementById("publishHint"),
  postTemplate: document.getElementById("postTemplate"),
};

const state = {
  sessionToken: localStorage.getItem('lc_session_token') || "",
  posts: [],
};

(function init() {
  if (state.sessionToken && ui.sessionTokenInput) {
    ui.sessionTokenInput.value = state.sessionToken;
    ui.sessionTokenInput.parentElement && (ui.sessionTokenInput.parentElement.style.display = 'none');
  }
})();

function setHint(message, mode = "") {
  ui.publishHint.textContent = message;
  ui.publishHint.classList.remove("error", "ok");
  if (mode) {
    ui.publishHint.classList.add(mode);
  }
}

function formatDate(ts) {
  if (!ts) {
    return "";
  }
  const dt = new Date(ts);
  return dt.toLocaleString();
}

function renderPosts() {
  ui.postList.innerHTML = "";

  if (!state.posts.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Постов пока нет";
    ui.postList.appendChild(li);
    return;
  }

  for (const post of state.posts) {
    const fragment = ui.postTemplate.content.cloneNode(true);
    fragment.querySelector(".post-title").textContent = post.title;
    fragment.querySelector(".post-meta").textContent = `author:${post.author_user_id} | ${formatDate(
      post.published_at_ms
    )}`;
    fragment.querySelector(".post-body").textContent = post.body_text;
    ui.postList.appendChild(fragment);
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

async function loadPosts() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setHint("Укажите session token для загрузки ленты", "error");
    return;
  }

  const url = `/blog/api/posts?session_token=${encodeURIComponent(state.sessionToken)}&limit=50&offset=0`;
  const payload = await fetchJSON(url);
  state.posts = payload.items || [];
  renderPosts();
  setHint("Лента загружена", "ok");
}

async function publishPost() {
  state.sessionToken = state.sessionToken || ui.sessionTokenInput.value.trim();
  if (!state.sessionToken) {
    setHint("Сначала укажите session token", "error");
    return;
  }

  const title = ui.postTitleInput.value.trim();
  const bodyText = ui.postBodyInput.value.trim();
  if (!title || !bodyText) {
    setHint("Заполните заголовок и текст", "error");
    return;
  }

  await fetchJSON("/blog/api/posts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_token: state.sessionToken,
      title,
      body_text: bodyText,
    }),
  });

  ui.postTitleInput.value = "";
  ui.postBodyInput.value = "";
  setHint("Пост опубликован", "ok");
  await loadPosts();
}

ui.loadPostsBtn.addEventListener("click", async () => {
  try {
    await loadPosts();
  } catch (error) {
    setHint(`Ошибка загрузки: ${error.message}`, "error");
  }
});

ui.publishForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await publishPost();
  } catch (error) {
    setHint(`Ошибка публикации: ${error.message}`, "error");
  }
});

renderPosts();
