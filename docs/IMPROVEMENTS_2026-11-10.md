# Local Chat — улучшения по отчёту агента (2026-11-10)

Реализовано поверх `a0aea84` без bump версии: это набор UX/ops-улучшений,
а не новый релизный тег.

## Что изменено

### 1. Живые обновления списка чатов и непрочитанного
- SPA опрашивает существующий `GET /chat/api/updates` раз в 10 секунд только
  при видимой вкладке, с backoff при ошибке.
- Список чатов и бейджи обновляются без F5; активный диалог сохраняется.
- Заголовок вкладки показывает `(N) Local Chat`, favicon получает красный
  бейдж.
- Браузерные уведомления показываются для скрытой вкладки, если разрешение
  выдано и чат не в mute. Кнопка разрешения — в аккаунте.

### 2. WebSocket для активного диалога
- SPA подключается к `/realtime/chat/{chat_id}` при открытии чата, закрывает
  сокет при переключении и переподключается с задержкой 3 секунды.
- Новые сообщения добавляются в текущий список; HTTP polling остаётся
  fallback и для старых клиентов.
- Ошибочные коды 4401/4403/4503/4429 не вызывают бесконечный reconnect.

### 3. Жизненный цикл вложений
- `DELETE /media/api/attachments/{id}`: владелец может удалить файл, если он
  не используется в сообщении, поддержке, жалобе или блоге.
- Аккаунт показывает «Мои файлы», занятую квоту и удаляет файлы.
- `POST /media/api/cleanup-orphans` (admin/moderator) удаляет записи и файлы
  без ссылок; `MediaService.cleanup_orphan_attachments()` доступен и для
  cron/systemd.

### 4. Язык и модули
- Первый визит выбирает `rus`/`eng` по `navigator.language`, ручной выбор
  сохраняется.
- About, разделители дат и основные ошибки входа локализованы.
- `LCS_FEATURES` (по умолчанию все модули) скрывает Devices/Blog/Support в
  навигации и перенаправляет выключенные маршруты на чат.
- `/health` отдаёт список включённых features.

### 5. Доступность
- Общий `openDialog()`: `role=dialog`, `aria-modal`, `aria-labelledby`,
  focus trap, Escape, возврат фокуса.
- Тосты получили `role=status/alert` и `aria-live`; добавлен видимый
  `:focus-visible`.

### 6. CI и эксплуатация
- Добавлен pytest-слой `tests/unit` (медиа, квоты, конфиг) и job в
  `.github/workflows/ci.yml`.
- Добавлены `local-chat-backup.service`/`.timer`: ежедневный бэкап,
  проверка архива, retention 7 копий, последняя копия в `lc status`.
- `create-admin --password-stdin`; wizard передаёт пароль через stdin, а не
  через argv.
- README/INSTALL/frontend-spec синхронизированы: версия не дублируется,
  room code 6-значный, тестовые креды убраны.

## Проверки

- `python -m pytest -q tests/unit` — 5 passed.
- `node --check server/app/static/app.js` — ok.
- `python -m compileall -q server/app server/setup server/scripts` — ok.
- `bash -n` для `wizard.sh`, `lc.sh`, `install_pi.sh` — ok (Git Bash).
- UI smoke `tests/ui/ui_test.js` — 24/24.
- UI improvements `tests/ui/improvements_check.js` — 12/12:
  live list/badge, WebSocket <5 s, My Files, a11y, locale.
- Server `test_chat_updates.py` — 10/10; `test_business_logic_p123_2026_11_10.py` — 28/28.

## Что осталось отдельными решениями

- Полноценный push/service worker при закрытой вкладке (сейчас title/favicon
  и Notification при скрытой вкладке).
- Автоматическое тестовое восстановление бэкапа раз в месяц (сейчас
  проверяется целостность архива).
- Feature-флаги скрывают UI/маршруты, но API выключенных модулей не
  блокируются на уровне прав — это следующий шаг, если модули будут
  отключаться в продакшене.
