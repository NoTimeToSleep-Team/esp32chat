# Project Roadmap

Этот файл хранит полный roadmap проекта.
Для активной работы и восстановления контекста использовать в таком порядке:

- [SESSION_CONTEXT.md](/D:/project/SESSION_CONTEXT.md) как постоянный блок правил;
- [STAGE_CONTEXT.md](/D:/project/STAGE_CONTEXT.md) как блок текущего этапа;
- [SUBSTAGE_CONTEXT.md](/D:/project/SUBSTAGE_CONTEXT.md) как блок текущего подэтапа.

`PLAN.md` нужен как полный источник дорожной карты и точечной сверки, а не как единственный активный контекст.

  - Стадии: 01 корень/архитектура/контракты, 02 server foundation, 03 auth и режимы, 04 chat, 05 blog/support/account/devices, 06 admin/RFID/security/ops/deploy, 07 firmware common, 08 внутренние контроллеры, 09 M5Tab, 10 встроенный M5Cardputer, 11 внешний M5Cardputer/Adv, 12
    M5StickC Plus 2, 13 T-Embed CC1101, 14 Flipper Zero, 15 интеграция, 16 стабилизация.
  - v0.01.01 Каркас репозитория: цель — базовая структура; делаем — README.md, .gitignore, каталоги; файлы — корень, server/README.md, firmware/README.md; результат — непустой репозиторий; проверка — дерево каталогов соответствует плану; далее — v0.01.02.
  - v0.01.02 Глоссарий: цель — единый язык проекта; делаем — термины, роли, сущности; файлы — docs/glossary.md; результат — убрана терминологическая путаница; проверка — все ключевые термины из ТЗ определены; далее — v0.01.03.
  - v0.01.03 MVP-рамки: цель — зафиксировать честные ограничения; делаем — список допустимого и недопустимого MVP; файлы — docs/mvp-scope.md; результат — меньше риска фантазий о железе; проверка — медиа/голос/автономность описаны только там, где реалистичны; далее — v0.01.04.
  - v0.01.04 Общая архитектура: цель — собрать целостную схему; делаем — роли Raspberry Pi, вспомогательных узлов и клиентов; файлы — docs/architecture.md; результат — единая архитектурная рамка; проверка — у каждого узла одна главная роль; далее — v0.01.05.
  - v0.01.05 Матрица устройств: цель — разложить hardware по возможностям; делаем — таблицу экранов, памяти, накопителей, транспорта; файлы — docs/device-matrix.md; результат — видно реальные границы устройств; проверка — для каждого устройства есть явные ограничения; далее —
    v0.01.06.
  - v0.01.06 Базовый протокол и sync-правила: цель — зафиксировать контракт server/firmware; делаем — типы сообщений, registration, heartbeat, timestamps, idempotency; файлы — contracts/protocol.md, contracts/sync-rules.md, contracts/messages/*.json; результат — общий wire-
    contract; проверка — есть примеры пакетов для auth, chat, telemetry и sync; далее — v0.02.01.
  - v0.02.01 Каркас backend: цель — поднять основу server; делаем — skeleton FastAPI и layout модулей; файлы — server/app/main.py, server/pyproject.toml; результат — runnable backend skeleton; проверка — app импортируется; далее — v0.02.02.
  - v0.02.02 Конфиг и запуск: цель — отделить код от настроек; делаем — env-конфиг, startup profile, примеры конфигов; файлы — server/app/config.py, server/config/*.example; результат — сервер конфигурируется без правки кода; проверка — конфиг валидируется на старте; далее —
    v0.02.03.
  - v0.02.03 Health и логирование: цель — базовая эксплуатационная основа; делаем — health endpoint, startup/shutdown hooks, app logging; файлы — server/app/api/health.py, server/app/logging.py; результат — базовая наблюдаемость; проверка — health route инициализируется
    корректно; далее — v0.02.04.
  - v0.02.04 БД, миграции и storage-layout: цель — заложить data layer; делаем — SQLite baseline, миграционный каркас, каталоги файлового хранилища; файлы — server/app/db/*, server/migrations/*, server/app/storage/*; результат — готова база хранения; проверка — чистая миграция
    создаёт рабочую схему и обязательные каталоги; далее — v0.03.01.
  - v0.03.01 Пользователи и роли: цель — основа auth-домена; делаем — guest/user/admin, статусы, ограничения; файлы — server/app/models/user*.py; результат — user model готова; проверка — роли покрывают открытый и закрытый режимы; далее — v0.03.02.
  - v0.03.02 Логин и сессии: цель — локальный вход; делаем — login/logout, password verification, session handling; файлы — server/app/services/auth.py, server/app/api/auth.py; результат — базовая аутентификация работает; проверка — неверные и верные данные обрабатываются
    различно; далее — v0.03.03.
  - v0.03.03 Закрытый режим: цель — подача заявок вместо свободной регистрации; делаем — форму, модель, очередь заявок; файлы — server/app/models/application.py, server/app/api/applications.py; результат — closed-mode flow готов; проверка — заявка создаётся и попадает в очередь;
    далее — v0.03.04.
  - v0.03.04 Открытый режим и guest web: цель — завершить open-mode; делаем — регистрацию, guest только для web, ограничения по устройству и номеру, переключение режима; файлы — server/app/services/registration.py, server/app/services/mode.py; результат — оба режима управляемы;
    проверка — guest не уходит в hardware-flow, свободная регистрация отключается в closed mode; далее — v0.04.01.
  - v0.04.01 Домен чатов: цель — chat storage и бизнес-логика; делаем — модели чатов, участников и сообщений; файлы — server/app/models/chat*.py, server/app/services/chat.py; результат — ядро чатов собрано; проверка — поддержаны общие и пользовательские чаты; далее — v0.04.02.
  - v0.04.02 Realtime-транспорт: цель — живая доставка сообщений; делаем — WebSocket/SSE слой; файлы — server/app/realtime/*; результат — чат получает live-updates; проверка — новое сообщение публикуется в realtime-канал; далее — v0.04.03.
  - v0.04.03 Web UI чата: цель — рабочая вкладка Чат; делаем — список чатов, история, отправка текста; файлы — server/app/templates/chat/*, server/app/static/chat/*; результат — usable web-chat MVP; проверка — цикл открыть чат → написать → прочитать историю поддержан; далее —
    v0.04.04.
  - v0.04.04 Приватные комнаты и лимиты: цель — добрать chat-правила; делаем — приватные комнаты, 4-значный код, лимиты пользовательских чатов; файлы — server/app/services/chat_limits.py, server/app/api/chat_private.py; результат — chat-логика ближе к ТЗ; проверка — обычный
    пользователь не превышает лимит, админ не ограничен; далее — v0.05.01.
  - v0.05.01 Блог: цель — вкладка Блог; делаем — post model, admin publish, user read; файлы — server/app/models/blog.py, server/app/api/blog.py, server/app/templates/blog/*; результат — блог работает; проверка — админ публикует пост, пользователь видит ленту; далее — v0.05.02.
  - v0.05.02 Поддержка: цель — вкладка Поддержка; делаем — обращения, статусы, диалоги user-admin; файлы — server/app/models/support*.py, server/app/api/support.py, server/app/templates/support/*; результат — support flow готов; проверка — обращение создаётся и отвечает по ролям;
    далее — v0.05.03.
  - v0.05.03 Аккаунт: цель — вкладка Аккаунт; делаем — профиль, аватар, отображение ограничений; файлы — server/app/api/account.py, server/app/templates/account/*; результат — базовый профиль готов; проверка — смена аватара не ломает сессию; далее — v0.05.04.
  - v0.05.04 Каталог устройств: цель — вкладка Устройства; делаем — карточки устройств, инструкции, флаг “у меня есть устройство”; файлы — server/app/models/device_catalog.py, server/app/api/devices.py, server/app/templates/devices/*; результат — device catalog готов; проверка —
    хотя бы один профиль проходит полный путь публикации; далее — v0.06.01.
  - v0.06.01 Админка пользователей: цель — дать admin-контроль доступа; делаем — бан, разбан, временные блокировки, blacklist, удаление аккаунтов; файлы — server/app/api/admin/users.py, server/app/templates/admin/users/*; результат — admin user-flow готов; проверка — ключевые
    операции меняют состояние предсказуемо; далее — v0.06.02.
  - v0.06.02 Админка контента и режимов: цель — ежедневные admin-сценарии; делаем — заявки, support-очередь, blog publish, toggle режима; файлы — server/app/api/admin/content.py, server/app/api/admin/mode.py; результат — operational admin-flow собран; проверка — админ проходит
    заявку, обращение и смену режима; далее — v0.06.03.
  - v0.06.03 RFID: цель — встроить PN532 в модель доступа; делаем — хранение карт, admin CRUD, разблокировку/включение режима; файлы — server/app/models/rfid.py, server/app/services/rfid.py, server/app/api/rfid.py; результат — RFID интегрирован логически; проверка — software-flow
    карты проходит без лишних крипто-обещаний; далее — v0.06.04.
  - v0.06.04 Security baseline: цель — defensive-минимум; делаем — rate limiting, brute-force guard, login attempt limits, audit log; файлы — server/app/security/*, server/config/logging.*; результат — сервер перестаёт быть “голым”; проверка — серия ошибочных входов вызывает
    защитное правило; далее — v0.06.05.
  - v0.06.05 Ops-safety: цель — backups, incidents, safe shutdown; делаем — incident logs, backup flow, shutdown orchestration, degraded mode; файлы — server/app/services/backup.py, server/app/services/incidents.py, server/app/services/shutdown.py; результат — база
    эксплуатационной безопасности; проверка — есть dry-run последовательности backup/restore и shutdown; далее — v0.06.06.
  - v0.06.06 Deploy для Raspberry Pi: цель — путь к Pi OS; делаем — systemd, nginx, layout /opt/local-chat-server, install docs; файлы — server/systemd/*, server/config/nginx/*, server/scripts/install_pi.*, server/docs/deploy-pi.md; результат — готов deploy-пакет; проверка —
    конфиги структурно согласованы, реальные Pi-проверки остаются отдельными; далее — v0.07.01.
  - v0.07.01 Каркас firmware workspace: цель — основа прошивочной части; делаем — общую структуру, профили устройств, build docs; файлы — firmware/common/*, firmware/profiles/*, firmware/docs/build.md; результат — firmware перестаёт быть пустым; проверка — каждому устройству есть
    место в структуре; далее — v0.07.02.
  - v0.07.02 Shared protocol code: цель — перенести контракт в код; делаем — сериализацию пакетов, типы сообщений, ошибки, версии; файлы — firmware/common/protocol/*; результат — общий код протокола готов; проверка — покрыты базовые пакеты из contracts/; далее — v0.07.03.
  - v0.07.03 Shared transport и queue: цель — устойчивый transport layer; делаем — retry, ack, local queue, reconnect logic; файлы — firmware/common/transport/*, firmware/common/queue/*; результат — transport-база готова; проверка — повторная отправка не ломает идемпотентность;
    далее — v0.08.01.
  - v0.08.01 ESP32-S3 сервисный контроллер: цель — главный внутренний embedded-узел; делаем — telemetry, watchdog, diagnostics, safe-shutdown commands; файлы — firmware/devices/esp32_service/*; результат — сервисный контроллер готов как MVP; проверка — команды совпадают с server
    telemetry/shutdown API; далее — v0.08.02.
  - v0.08.02 M5Stamp S3: цель — закрыть малые внутренние узлы; делаем — heartbeat, индикацию, telemetry hooks, аварийные сигналы; файлы — firmware/devices/m5stamp/*; результат — M5Stamp S3 получает честную роль; проверка — он не берёт на себя серверную логику; далее — v0.08.03.
  - v0.08.03 Atom S3: цель — status/alert узел; делаем — индикацию состояний и безопасные быстрые действия; файлы — firmware/devices/atom_s3/*; результат — Atom S3 получает лёгкую сервисную роль; проверка — набор действий ограничен безопасными командами; далее — v0.09.01.
  - v0.09.01 M5Tab shell и сведения: цель — старт аппаратной админ-панели; делаем — app shell, соединение с сервером, экран Сведения; файлы — firmware/devices/m5tab/*; результат — M5Tab показывает состояние системы; проверка — все поля приходят из telemetry API; далее — v0.09.02.
  - v0.09.02 M5Tab admin users: цель — базовые admin-действия на устройстве; делаем — список аккаунтов, бан, разбан, blacklist, удаление; файлы — firmware/devices/m5tab/screens/admin_users/*; результат — user-admin flow на M5Tab готов; проверка — операции идут только через server
    API; далее — v0.09.03.
  - v0.09.03 M5Tab admin ops: цель — добрать контент и режим; делаем — support, blog, RFID, toggle режима с удержанием; файлы — firmware/devices/m5tab/screens/admin_ops/*; результат — M5Tab покрывает локальные требования; проверка — смена режима использует safe sequence, а не
    мгновенное отключение; далее — v0.10.01.
  - v0.10.01 Встроенный M5Cardputer shell/login: цель — начать сервисную консоль; делаем — профиль встроенного устройства, secure login, базовую навигацию; файлы — firmware/devices/m5cardputer_console/*; результат — консольный профиль готов; проверка — guest-режим не
    используется; далее — v0.10.02.
  - v0.10.02 Встроенный M5Cardputer chat: цель — text-first chat MVP; делаем — список чатов, история, отправка текста; файлы — firmware/devices/m5cardputer_console/chat/*; результат — встроенный Cardputer работает с чатами; проверка — нет ложных медиа-обещаний; далее — v0.10.03.
  - v0.10.03 Встроенный M5Cardputer blog/service: цель — завершить сервисную консоль; делаем — чтение блога и безопасные service shortcuts; файлы — firmware/devices/m5cardputer_console/blog/*, .../service_actions/*; результат — встроенный Cardputer завершён как консоль; проверка
    — service actions ограничены безопасными функциями; далее — v0.11.01.
  - v0.11.01 Внешний M5Cardputer/Adv profiles: цель — развести внешний handheld и встроенную консоль; делаем — общую кодовую базу и device profiles; файлы — firmware/devices/m5cardputer_client/*, firmware/profiles/m5cardputer*.json; результат — профили внешних устройств готовы;
    проверка — Adv не получает лишнюю отдельную ветку без причины; далее — v0.11.02.
  - v0.11.02 Внешний M5Cardputer/Adv client MVP: цель — handheld chat/blog client; делаем — login, chat, blog, text send/read; файлы — firmware/devices/m5cardputer_client/ui/*; результат — внешний Cardputer работает как честный клиент; проверка — файлы и фото не обещаются без
    подтверждённого накопителя; далее — v0.12.01.
  - v0.12.01 M5StickC Plus 2 shell/login: цель — поднять компактный клиент; делаем — login flow и минимальную навигацию; файлы — firmware/devices/m5stickc_plus2/*; результат — базовый shell готов; проверка — нет guest-режима и фиктивной автономности; далее — v0.12.02.
  - v0.12.02 M5StickC Plus 2 client MVP: цель — text-first chat/blog; делаем — чат, блог, короткие реакции; файлы — firmware/devices/m5stickc_plus2/ui/*; результат — M5StickC Plus 2 получает честный MVP; проверка — UX остаётся простым и не перегруженным; далее — v0.13.01.
  - v0.13.01 T-Embed shell/login: цель — старт текстового клиента; делаем — login flow и базовую навигацию; файлы — firmware/devices/t_embed_cc1101/*; результат — T-Embed получает shell клиента; проверка — transport не перегружается неподходящими задачами; далее — v0.13.02.
  - v0.13.02 T-Embed client MVP: цель — chat/blog/templates/buffer; делаем — текстовый чат, блог, шаблоны, уведомления, локальный буфер; файлы — firmware/devices/t_embed_cc1101/ui/*; результат — T-Embed получает реалистичный профиль; проверка — тяжёлые потоки и лишние медиа не
    закладываются; далее — v0.14.01.
  - v0.14.01 Flipper Zero shell/capability detection: цель — честно стартовать отдельное приложение; делаем — skeleton, проверку Wi‑Fi dev board, разведение режимов; файлы — firmware/devices/flipper_zero/*, firmware/docs/flipper.md; результат — база Flipper-приложения готова;
    проверка — сценарии с dev board и без неё различаются явно; далее — v0.14.02.
  - v0.14.02 Flipper Zero limited client mode: цель — ограниченный chat/blog mode; делаем — облегчённый login, чтение блога, текстовый чат; файлы — firmware/devices/flipper_zero/ui/*; результат — Flipper встроен без ложных обещаний; проверка — Bluetooth/Wi‑Fi/files/photo не
    выходят за реальные границы; далее — v0.15.01.
  - v0.15.01 Device registration и telemetry e2e: цель — связать server и firmware на базовом уровне; делаем — полный flow register → heartbeat → status; файлы — доработки server и firmware, docs/integration-device.md; результат — server видит устройства как узлы; проверка — хотя
    бы один тип устройства проходит software-flow регистрации; далее — v0.15.02.
  - v0.15.02 Chat e2e web + device: цель — сквозной chat-flow; делаем — совместимость message delivery между web и hardware; файлы — доработки chat-модулей server и firmware; результат — чат становится сквозным; проверка — одно событие сообщения одинаково понимают web и
    устройство; далее — v0.15.03.
  - v0.15.03 Blog/support/admin e2e: цель — свести остальные обязательные сценарии; делаем — интеграцию blog/support/admin workflows; файлы — доработки соответствующих модулей, docs/integration-ops.md; результат — ключевые бизнес-потоки согласованы; проверка — каждый обязательный
    раздел ТЗ имеет минимум один сквозной сценарий; далее — v0.15.04.
  - v0.15.04 Автономность и sync-профили: цель — честно закрепить offline-возможности; делаем — матрицу автономности и device-level sync profiles; файлы — docs/autonomy-matrix.md, firmware/profiles/autonomy/*; результат — автономность описана без фантазий; проверка — устройства
    без накопителя не получают фиктивную глубокую офлайн-историю; далее — v0.16.01.
  - v0.16.01 Acceptance checklist: цель — формализовать приёмку; делаем — список обязательных сценариев и критериев готовности; файлы — docs/acceptance.md, docs/verification-plan.md; результат — появляется чёткий план проверки проекта; проверка — каждый крупный блок roadmap имеет
    приёмочный сценарий; далее — v0.16.02.
  - v0.16.02 Known limitations и operator docs: цель — честно зафиксировать ограничения; делаем — known issues, границы MVP, операторские инструкции; файлы — docs/known-limitations.md, docs/operator-guide.md; результат — проект не маскирует слабые места; проверка — все
    неподтверждённые hardware/field-пункты перечислены явно; далее — v0.16.03.
  - v0.16.03 RC1 стабилизация: цель — собрать первый честный release candidate; делаем — cleanup, финальные правки, release docs; файлы — docs/release-candidate.md и точечные доработки проекта; результат — появляется первый системный RC1; проверка — незакрытые ограничения
    перечислены отдельно, а не скрыты; далее — следующий цикл по багфиксам.
