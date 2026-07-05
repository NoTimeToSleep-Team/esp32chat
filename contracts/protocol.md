# Protocol Contract (`v1.0`)

Базовый wire-contract между `server` и `firmware` для этапа `v0.01.06`.

## 1) Область действия

- Контракт описывает обмен сообщениями между главным сервером (Raspberry Pi 5) и устройствами.
- Формат сообщений: `JSON`.
- Ключи полей и `message_type` фиксируются как ASCII-строки.
- Контракт не заменяет бизнес-логику API, а задает единый транспортный слой событий.

## 2) Транспорт

- Основной канал: двусторонний `WebSocket`.
- Резервный канал: `HTTP push/pull` для constrained-устройств.
- Для внутреннего контура допускаются service-каналы, но payload и envelope остаются едиными.

## 3) Универсальный envelope

Каждое сообщение использует общий каркас:

```json
{
  "protocol_version": "1.0",
  "message_type": "device.register.request",
  "message_id": "msg-01J0A9H3V6WQ2SR8P4N7YTK3M1",
  "idempotency_key": "esp32-s3-01:boot-a1b2c3:000001",
  "correlation_id": null,
  "sender": {
    "kind": "device",
    "id": "esp32-s3-01"
  },
  "target": {
    "kind": "server",
    "id": "main"
  },
  "sent_at_ms": 1775300000123,
  "payload": {}
}
```

## 4) Поля envelope

| Поле | Тип | Обязательность | Назначение |
| --- | --- | --- | --- |
| `protocol_version` | string | обязательно | Версия протокола (`1.0`). |
| `message_type` | string | обязательно | Тип сообщения (`namespace.action.direction`). |
| `message_id` | string | обязательно | Уникальный ID конкретного сообщения. |
| `idempotency_key` | string/null | обязательно для mutating-операций | Дедупликация повторов. |
| `correlation_id` | string/null | обязательно | Ссылка на исходный запрос (в ответах/ack). |
| `sender.kind` | string | обязательно | `server`, `device`, `web_client`, `service`. |
| `sender.id` | string | обязательно | Уникальный ID отправителя. |
| `target.kind` | string | обязательно | Тип получателя. |
| `target.id` | string | обязательно | ID получателя. |
| `sent_at_ms` | integer | обязательно | Unix time в миллисекундах (UTC). |
| `payload` | object | обязательно | Полезные данные по типу сообщения. |

## 5) Каталог типов сообщений

### Регистрация и состояние устройства

- `device.register.request`
- `device.register.response`
- `device.heartbeat`
- `telemetry.snapshot`

### Аутентификация

- `auth.login.request`
- `auth.login.response`

### Чат

- `chat.send.request`
- `chat.send.response`
- `chat.message.event`

### Синхронизация

- `sync.push.request`
- `sync.push.response`
- `sync.pull.request`
- `sync.pull.response`
- `sync.ack`

### Ошибки

- `error.response`

## 6) Базовые payload-требования

### `device.register.request`

Обязательные поля payload:

- `device_uid`
- `device_type`
- `firmware_version`
- `capabilities` (возможности устройства)
- `boot_id` (ID текущего запуска)

### `device.register.response`

Обязательные поля payload:

- `status` (`accepted`/`rejected`)
- `server_device_id` (при `accepted`)
- `session_token` (при `accepted`)
- `heartbeat_interval_ms` (при `accepted`)
- `sync_profile`
- `server_time_ms`

### `device.heartbeat`

Минимум:

- `uptime_ms`
- `queue_depth`
- `status` (`ok`, `degraded`, `hold_state`)

### `chat.send.request`

Минимум:

- `chat_id`
- `client_message_id`
- `text`

### `sync.push.request`

Минимум:

- `base_cursor`
- `events[]` (каждый event содержит `event_id`, `event_type`, `event_ts_ms`, `payload`)

### `sync.pull.request`

Минимум:

- `since_cursor`
- `limit`

## 7) Идемпотентность

- Все mutating-запросы обязаны передавать `idempotency_key`.
- Сервер хранит дедуп-ключи минимум 48 часов.
- Повтор mutating-запроса с тем же ключом возвращает исходный результат без повторного применения.
- Рекомендуемый формат ключа: `<sender_id>:<boot_id>:<counter>`.

## 8) Timestamp и время

- Все временные поля в UTC (`*_ms`, unix epoch milliseconds).
- Серверное время является опорным для подтвержденных событий.
- При заметном расхождении часов устройство продолжает работу, но сервер может выставить флаг `clock_skew_detected` в ответе.

## 9) Семантика ответов и ошибок

- Ответ на запрос должен содержать `correlation_id = message_id` исходного запроса.
- Бизнес-ошибки и protocol-ошибки возвращаются как `error.response`.

Базовые `error.code`:

- `unauthorized`
- `forbidden`
- `invalid_payload`
- `unsupported_message_type`
- `rate_limited`
- `conflict`
- `resync_required`
- `internal_error`

## 10) Совместимость версий

- `protocol_version` использует схему `major.minor`.
- Изменение `major` означает потенциально несовместимый контракт.
- Неизвестные поля в `payload` должны безопасно игнорироваться, если не помечены как обязательные.

## 11) Примеры пакетов

Готовые JSON-примеры лежат в:

- `contracts/messages/auth.login.request.json`
- `contracts/messages/auth.login.response.json`
- `contracts/messages/device.register.request.json`
- `contracts/messages/device.register.response.json`
- `contracts/messages/device.heartbeat.json`
- `contracts/messages/chat.send.request.json`
- `contracts/messages/chat.send.response.json`
- `contracts/messages/chat.message.event.json`
- `contracts/messages/telemetry.snapshot.json`
- `contracts/messages/sync.push.request.json`
- `contracts/messages/sync.push.response.json`
- `contracts/messages/sync.pull.request.json`
- `contracts/messages/sync.pull.response.json`
- `contracts/messages/sync.ack.json`
- `contracts/messages/error.response.json`
