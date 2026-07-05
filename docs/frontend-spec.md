# Local Chat Server — Single Page Application

## Контекст

Raspberry Pi 5 (192.168.4.1, порт 18080) раздаёт Wi-Fi `LC-Hub` (без пароля). В этой же сети — ESP32-устройства (M5Cardputer, M5StickC Plus 2). Сервер — FastAPI, все данные в SQLite.

**С фронтенда нет доступа в интернет** — всё через RPi AP. Никаких CDN, внешних шрифтов, библиотек.

## Задача

Переписать фронтенд с нуля: **единая Single Page Application** (один HTML-файл), которая обслуживается по корневому пути `/`. Вместо текущего JSON-ответа.

## Страницы (все в одном SPA)

### 1. Логин (`/login`)
- Форма: логин, пароль
- `POST /auth/login` с `{"login": "...", "password": "...", "client_kind": "web"}`
- Успех → сохранить `session.token` в `localStorage`, редирект на `/chat`
- Ошибка — показать сообщение
- Тестовые креды: `device` / `devicepass`, `esp32-admin` / `admin`

### 2. Чат (`/chat`)
- Список чатов: `GET /chat/api/chats?session_token=...`
- Просмотр сообщений: `GET /chat/api/chats/{id}/messages?session_token=...&limit=50`
- Отправка: `POST /chat/api/chats/{id}/messages` с `{"session_token": "...", "body_text": "..."}`
- Авто-скролл вниз, периодический опрос (polling, без WebSocket)

### 3. Устройства (`/devices`)
- Список: `GET /devices/api/catalog?session_token=...`
- Карточка устройства: slug, title, description, guides

### 4. Аккаунт (`/account`)
- Профиль: `GET /account/api/profile?session_token=...`
- Поля: login, role, display_name, phone, avatar, bio
- Редактирование: `POST /account/api/profile`

### 5. Блог (`/blog`)
- Посты: `GET /blog/api/posts?session_token=...&limit=50`
- Заголовок, тело, автор, дата

### 6. Саппорт (`/support`)
- Тикеты: `GET /support/api/tickets?session_token=...`
- Просмотр сообщений тикета: `GET /support/api/tickets/{id}/messages?...`
- Создание сообщения: `POST /support/api/tickets/{id}/messages`

### 7. Админка (`/admin`) — только для role=admin
- **Пользователи**: `GET /admin/users?session_token=...`
- **Режим доступа**: `GET /mode` (open/closed), `POST /mode` (с заголовком `X-Session-Token`)

## Навигация

Хедер/сайдбар со ссылками:
- Чат
- Устройства
- Аккаунт
- Блог
- Саппорт
- Админка (только если роль admin)
- Выйти (очистить localStorage, редирект на /login)

Навигация должна быть и на мобильных (гамбургер или нижняя панель).

## Технические требования

### Файлы (создать в `D:\project\server\app\`)

- `templates/index.html` — единственный HTML, обновить роут `/` в `main.py`:
```python
@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    template = Path(__file__).resolve().parent / "templates" / "index.html"
    return HTMLResponse(content=template.read_text(encoding="utf-8"))
```

- `static/app.css` — все стили
- `static/app.js` — вся логика

### Аутентификация

- Токен хранить в `localStorage` (ключ `lc_session_token`)
- При загрузке любой страницы (кроме `/login`) проверять наличие токена
- Если токена нет — редирект на `/login`
- Токен передавать как query-параметр `?session_token=...` во все GET-запросы
- Для POST запросов токен внутри JSON-тела

### API-форматы

Все ответы:
```json
{"status": "ok", ...}
```

Ошибки:
```json
{"detail": {"code": "...", "message": "..."}}
```

### Формат сообщений чата

```json
{
  "message_id": 1,
  "chat_id": 1,
  "author_user_id": 1,
  "body_text": "hello",
  "client_message_id": null,
  "created_at_ms": 1718000000000,
  "edited_at_ms": null
}
```

### Формат списка чатов

```json
{
  "chat_id": 1,
  "kind": "common",
  "title": "General",
  "description": null,
  "owner_user_id": null,
  "is_private": false,
  "avatar_url": null,
  "has_room_code": false,
  "created_at_ms": 1718000000000,
  "updated_at_ms": 1718000000000
}
```

### Роли пользователей

- `"guest"`, `"user"`, `"admin"`
- Статусы: `"active"`, `"blocked"`, `"banned"`
- Режим доступа: `"open"`, `"closed"`

### Ограничения

- **Нет интернета** — никаких CDN, Google Fonts, Font Awesome. Всё своё.
- Кодировка UTF-8
- Работать на телефоне (Chrome mobile через Wi-Fi LC-Hub)
- Никаких фреймворков — чистый HTML + CSS + vanilla JS
- CSS — минималистичный, тёмная тема (сервер в подвале, глаза беречь)

### Формат для POST /auth/login

**Запрос:**
```json
{
  "login": "device",
  "password": "devicepass",
  "client_kind": "web"
}
```

**Ответ:**
```json
{
  "status": "ok",
  "access_mode": "open",
  "user": {
    "id": 2,
    "login": "device",
    "role": "user",
    "status": "active"
  },
  "session": {
    "token": "<urlsafe-base64-string>",
    "created_at_ms": 1718000000000,
    "expires_at_ms": 1718086400000
  }
}
```

### План действий для нейросети

1. Создать `static/app.css` — тёмная тема, мобильная адаптация, навигация
2. Создать `static/app.js` — роутинг (hash-based), API-клиент, управление страницами
3. Создать `templates/index.html` — SPA-оболочка (хедер, навигация, контейнер для контента)
4. Обновить `main.py` — заменить корневой роут на HTML-ответ
5. Не забудь файлы для статики — у них уже есть `app.mount("/static", ...)`

### Формат POST /chat/api/chats/{id}/messages

**Запрос:**
```json
{
  "session_token": "...",
  "body_text": "Привет!"
}
```

**Ответ:**
```json
{
  "status": "ok",
  "message": {
    "message_id": 42,
    "chat_id": 1,
    "author_user_id": 2,
    "body_text": "Привет!",
    "client_message_id": null,
    "created_at_ms": 1718000000000,
    "edited_at_ms": null
  },
  "delivered_to": 0
}
```

### POST /account/api/profile (обновление профиля)

**Запрос:**
```json
{
  "session_token": "...",
  "display_name": "Новое имя",
  "phone": "+71234567890",
  "profile_bio": "Описание"
}
```

**Ответ:** `{"status": "ok", "profile": {...}}` (та же структура, что GET).

### POST /mode (смена режима доступа)

**Заголовок:** `X-Session-Token: <token>`

**Тело:**
```json
{
  "access_mode": "closed"
}
```

**Ответ:**
```json
{
  "status": "ok",
  "access_mode": "closed",
  "updated_by_user_id": 1
}
```
