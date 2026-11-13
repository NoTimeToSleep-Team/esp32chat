> **Решение проекта (2026-11-13):** `/camp` остаётся отдельным приложением.
> Мы не сливаем его с основным чатом. Рекомендация ниже «вожатый входит в
> обычный чат, без `/camp`» **не применяется**; берём из неё паттерны карточек,
> ролей, офлайна и импорта, но сохраняем отдельную camp-оболочку на основе чата.

**[camp-redesign] Searcher: рынок 2026 — 6 систем, что берём и что не берём**

**Вывод.** Ни CampMinder, ни CampBrain, ни Brightwheel/Procare не являются chat-first: это модульные дашборды с отдельными экранами переклички, здоровья, платежей и родительским приложением. Их сила — полный контур данных; слабость — ровно та, на которую жалуется пользователь: «набор инструментов». Значит chat-first — реальная дифференциация, но только если чат остаётся лентой объектов, а не свалкой сообщений.

**Сравнение.** По публичным материалам, не hands-on. «Скорость» ниже — маркетинговые утверждения, не независимый замер.

| Система | Дом / IA | Перекличка и выдача | Родители и медицина | Бухгалтерия | Что берём / не берём |
|---|---|---|---|---|---|
| **CampMinder** | «Unified Person Record» + модули; родительское приложение Campanion = фото-лента + формы + оплаты | Check-in/out, привязан к транспорту; paperless attendance; мобильный check-in/out | Email/SMS, microposts, фото-лента; Health Center, eMAR, аллергии; роли | Integrated Financial Management, automated billing, card reconciliation, API в бухгалтерию | Берём: единая карточка человека, родительская лента, аудит. Не берём: facial recognition, 20 модулей |
| **CampBrain** | Набор модулей: camp / staff / medical / store / attendance / payments / fundraising | Отдельный модуль Attendance; родительский портал регистрации | Регистрация, statements; медицинский модуль | Payments, финансовые сводки, parent statements, кастомные отчёты | Берём: attendance как first-class, statements. Не берём: модульную свалку |
| **CampDoc** | Health record на ребёнка + регистрация + daily operations + eMAR | Check-in/out, ростеры; мед-события | Формы, аллергии, иммунизации, incident logs, eMAR, role-based, HIPAA/FERPA/SOC2, PDF/CSV, бумажный backup | Payment plans, купоны, donations | Берём: модель здоровья, audit trail, paper fallback. Не берём: полный EHR в MVP |
| **CircuiTree + Bunk1** | All-in-one camp ops + Bunk1 как родительское приложение | Secure check-in/out со сверкой с фото; mobile-first | Bunk1: push/SMS, фото, Bunk Notes, invitation code; broadcast, не чат. Digital health forms, аллергии/лекарства, permissions | Billing, revenue reporting | Берём: gate «фото + право», родительский broadcast. Не берём: фото/facial recognition |
| **Brightwheel** | Teacher app = ростер/посещаемость + лента daily report; parent app = персональная лента ребёнка | Quick scan или код; ratio/capacity; check-in/out | Messaging, newsletters, alerts, daily reports, фото; read receipts не проверены; allergy alerts не проверены | Automated billing, billing reports, expense tracking | Берём: daily report как лента, ratio, scan. Не берём: родительский чат, фото-ленту |
| **Procare** | Дашборд центра с ratio по комнатам; parent app = отчёты/сообщения; kiosk | QR/geolocation, digital sign-in/out, absences, transfer; **offline mode** | Two-way comms, newsletters, daily reports, фото; kiosk 4-digit PIN + signature + drop-off form; incident signature | Invoices, payments/refunds/credits, licensing reports | Берём: kiosk/PIN/подпись, offline, ratio. Не берём: 30-летнюю ширину модулей |

**Соседние паттерны (не camp-продукты).** Front и Missive показывают рабочий shared inbox: список + переписка + внутренние комментарии/@mentions + назначение + правила. Slack продаёт себя как «one operating system for your entire workday» (channels + Canvas + Lists + Workflow Builder), Zulip лечит шум темами внутри каналов. Remind/ClassDojo — broadcast + messaging + multilingual + границы; Telegram/WhatsApp — broadcast-канал + админский announcement + группы, привычно родителям, но без ролей, аудита и медданных.

**7 паттернов, которые берём**
1. **Exception-based roll call.** По умолчанию «все на месте»; вожатый отмечает только отсутствующих/опоздавших. Список — крупные строки, без скролла на 25 детей, оптимистичный UI.
2. **Карточка = объект, а не кнопка.** Состояния `open → claimed → done → closed(reason)`, владелец, дедлайн, аудит; карточка живёт в ленте, действия — внутри неё.
3. **Канал = отряд, состав из ростера.** Один канал на отряд, служебные «Сегодня», «Тревоги», «Ворота»; членство вычисляется из `camp_people`, не назначается руками.
4. **Медданные слоями.** Аллергия/ограничение — need-to-know флаг для вожатого/кухни; диагноз, дозы, eMAR — только медик. В канал отряда не попадает ничего медицинского, кроме «медик в курсе».
5. **Ворота как журнал.** Список доверенных взрослых (фото, родство, код), событие выпуска/возврата с timestamp, сотрудником, устройством, подписью/PIN; исключение — отдельный сценарий «нет в списке → звонок директору → одноразовый код».
6. **Родитель = broadcast + daily report, не чат.** Объявления отряда, дневник своего ребёнка, согласия; read receipts только для критичных объявлений, не для всей переписки.
7. **Импорт/экспорт CSV/XLSX с маппингом.** Dry-run, предпросмотр, идемпотентный upsert по ID, отчёт об ошибках, тот же schema на экспорт. 1C-коннектор — не в MVP.

Плюс два инженерных: **offline queue** для переклички/ворот (idempotency key, видимый статус синхронизации, бумажный fallback) и **одно главное действие** на экран (как в Slack/Front).

**5 анти-паттернов**
1. **Дашборд из модулей как дом.** CampMinder/CampBrain/Kinderpedia (27+ модулей) — это и есть «набор инструментов»; пользователь не должен выбирать экран, чтобы начать работу.
2. **Два параллельных продукта.** Отдельный `/camp` + отдельный чат = две личности, два unread, два дизайна. Это главная причина текущей боли.
3. **Открытый родительский чат/ЛС.** Модерация, границы, 152-ФЗ/COPPA; Bunk1 сознательно делает broadcast + фото + письма, а не чат.
4. **Read receipts везде.** Давление на вожатых и ложные ожидания; достаточно delivery state для тревог/критичных объявлений.
5. **Медданные и бухгалтерия внутри чата.** Здоровье — только в ограниченной записи; биллинг — только после выяснения формата. Иначе чат становится утечкой и бухгалтерским движком одновременно.

**Рекомендация: первый срез «отряд + карточка переклички»**
- Импорт 20–30 детей создаёт `users`, `camp_people`, канал отряда, `chat_members`; вожатый входит в обычный чат, без `/camp`.
- В ленте отряда — закреплённая карточка «Перекличка 08:15» от системного автора: список, счётчик, «Все на месте», «Отметить отсутствующих», «Закрыть с причиной».
- Отметка меняет payload карточки, а не создаёт 25 сообщений; повторное нажатие идемпотентно; директор видит статус в правой панели; ребёнок/родитель карточку не видят.
- Офлайн: действия в очередь, карточка показывает «ожидает синхронизации», после reconnect — merge по idempotency key.
- Приёмка: 25 детей < 60 секунд, ни одного перехода на другую страницу, два пользователя (вожатый/директор), WS-обновление, duplicate tap не дублирует отметку.
- Дальше по одной: карточка «Ворота/выдача» → родительский дневник (read-only) → мед-флаг (только медик) → карточка тревоги → импорт/экспорт финансов.

**Что проверить у пользователя (бухгалтерия)**
1. Откуда файл: 1С, Excel, банк, другая CRM? Пришлите обезличенный пример 5–10 строк.
2. Формат: CSV/XLSX/JSON/1C (CommerceML?), кодировка, разделитель, десятичный разделитель.
3. Колонки: ФИО, дата рождения, отряд/смена, номер договора, сумма, оплачено, льгота, долг, возврат, дата платежа, назначение.
4. Один файл — ростер или отдельно платежи? Нужен ли импорт платежей или только статус «оплачено/долг»?
5. Кто владелец и кто редактирует; кому видно (директор/бухгалтер, но не вожатый).
6. Нужен ли обратный экспорт в 1С/Excel и в каком виде; нужны ли квитанции/договоры/PDF.
7. Как отличать повторный импорт: ID договора, ID ребёнка, внешний ID?
8. Нужны ли возвраты/льготы/частичная оплата или достаточно списка и статуса?

**Источники (accessed 2026-11-13)**
- CampMinder: https://campminder.com/features/ ; transportation https://campminder.com/features/transportation/ ; health https://campminder.com/features/health-management/ ; email/text https://campminder.com/features/email-text-messages/ ; Campanion https://campminder.com/features/campanion-app/ ; API https://campminder.com/features/api/
- CampBrain: https://campbrain.com/software/
- CampDoc eMAR: https://www.campdoc.com/emar/
- CircuiTree: https://www.circuitree.com/ ; Bunk1: https://www.bunk1.com/services
- Brightwheel App Store: https://apps.apple.com/us/app/brightwheel-child-care-app/id902823296
- Procare: https://www.procaresoftware.com/ ; App Store: https://apps.apple.com/us/app/procare-childcare-app/id1309822135
- Lillio App Store: https://apps.apple.com/us/app/lillio/id1098305044
- Kinderpedia: https://www.kinderpedia.co/en/
- Front: https://front.com/product ; Missive App Store: https://apps.apple.com/us/app/missive-email-chat-tasks/id1231206084
- Slack: https://slack.com/features ; Zulip: https://zulip.com/why-zulip/
- Remind: https://www.remind.com/features
- 152-ФЗ, ст. 9: https://www.consultant.ru/document/cons_doc_LAW_61801/6c94959bc017ac80140621762d2ac59f6006b08c/ ; ст. 10: https://www.consultant.ru/document/cons_doc_LAW_61801/26edb2934b899bf9c74c3a8f7e574651c6565e6d/
- GDPR Art. 8: https://gdpr-info.eu/art-8-gdpr/ ; Art. 9: https://gdpr-info.eu/art-9-gdpr/

**Достоверность.** Это разбор публичных страниц и App Store, без hands-on и без интервью. IA «дом/экран» частично выведена из описаний и скриншотов; скорость и «real-time» — маркетинг. CampSite и ACTIVE Network Camp в этом срезе не проверены глубоко: CampSite не открылся, ACTIVE — в первую очередь регистрация/маркетплейс, не ежедневная операционка. COPPA-страница FTC не открылась из этой среды; для США нужен отдельный юр-разбор (under-13, verifiable parental consent, retention). 152-ФЗ/GDPR — только ориентиры, не юридическое заключение.
