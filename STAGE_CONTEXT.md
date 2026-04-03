# Stage Context

Этот файл — блок 2 из системы контекста `30/30/40`.
Он хранит контекст текущего этапа и меняется только при смене этапа или общих параметров этого этапа.

## Текущий этап

- Код этапа: `16`
- Название: `stabilization`
- Дата фиксации: `3 апреля 2026`
- Активный диапазон подэтапов: `v0.16.01` -> `v0.16.03`

## Цель этапа

Собрать честный стабилизационный контур перед RC:

- формализовать acceptance checklist;
- собрать verification plan;
- зафиксировать known limitations и operator docs;
- подготовить первый release candidate (`RC1`) без сокрытия ограничений.

## Что одинаково для всех подэтапов этого этапа

- Raspberry Pi 5 остаётся единственным главным сервером (`server/*`).
- Все runtime-операции устройств выполняются через server API; прямой доступ к БД в логике устройств запрещён.
- Guest-flow допустим только в web-интерфейсе и не используется в hardware client flow.
- Интеграционные и стабилизационные проверки фиксируются честно: только реально выполненные команды/сценарии.
- Неподтверждённые аппаратные возможности и field-checks не заявляются как закрытые.

## Параметры и опорные данные этапа

- Серверные опоры: `server/app/*`, `server/docs/*`, `server/config/*`.
- Прошивочные опоры: `firmware/common/*`, `firmware/devices/*`, `firmware/profiles/*`.
- Контрактная база: `contracts/protocol.md`, `contracts/sync-rules.md`, `contracts/messages/*.json`.
- План стабилизации: `PLAN.md` (стадия `16`).

## Артефакты этапа

- документы `docs/acceptance.md`, `docs/verification-plan.md`;
- документы `docs/known-limitations.md`, `docs/operator-guide.md`;
- документ `docs/release-candidate.md` и сопутствующие точечные правки.

## Фактическое состояние на момент фиксации

- Этапы `01`-`14` завершены.
- Этап `15` завершён:
  - `v0.15.01` device registration/telemetry e2e;
  - `v0.15.02` chat e2e web + device;
  - `v0.15.03` blog/support/admin e2e;
  - `v0.15.04` autonomy matrix + sync profiles.
- Добавлены интеграционные документы:
  - `docs/integration-device.md`;
  - `docs/integration-chat.md`;
  - `docs/integration-ops.md`;
  - `docs/autonomy-matrix.md`.
- Добавлены профили автономности `firmware/profiles/autonomy/*.json` и проверка `verify_profiles.py`.
- Подэтап `v0.16.01` закрыт: acceptance checklist и verification plan сформированы.
- Подэтап `v0.16.02` закрыт: known limitations и operator guide сформированы.
- Подэтап `v0.16.03` закрыт: документ `docs/release-candidate.md` (RC1 software baseline) сформирован.
- Выполнен полный software verification sweep по `docs/verification-plan.md`, отчёт: `docs/verification-report-2026-04-03.md`.
- Добавлен hardware execution pack: `docs/hardware-validation-checklist.md`, `docs/hardware-validation-log-template.md`.
- Добавлены field-ready gate артефакты: `docs/hardware-validation-log-bootstrap.md`, `docs/field-ready-gate.md`.
- Добавлен статусный срез field-ready: `docs/field-ready-status.md` (`NO-GO` до hardware evidence).
- Добавлен practical runbook: `docs/hardware-runbook.md`.
- Добавлен helper-скрипт: `docs/tools/evaluate_hardware_log.py` (оценка состояния hardware log).
- Добавлены helper-скрипты: `docs/tools/new_hardware_log.py`, `docs/tools/evaluate_field_ready_gate.py`.
- Добавлен helper-скрипт: `docs/tools/evaluate_all_hardware_logs.py` (сводка по датированным hardware session logs).
- Добавлен post-RC backlog: `docs/post-rc-backlog.md`.
- Создан стартовый hardware session log: `docs/hardware-validation-log-2026-04-03-session-01.md`.
- Сгенерирован дополнительный session log: `docs/hardware-validation-log-2026-04-03-session-02.md`.
- Git-репозиторий в `D:\project` пока не инициализирован.

## Критерии завершения этапа

- принят и зафиксирован acceptance checklist по ключевым блокам roadmap;
- verification plan покрывает обязательные проверки и порядок выполнения;
- known limitations и operator guide перечисляют реальные границы MVP;
- RC1 оформлен с явным списком незакрытых ограничений и рисков.

## Активный подэтап

- Текущий рабочий подэтап: `v0.16.03` (`completed`).
- Его оперативное состояние ведётся в [SUBSTAGE_CONTEXT.md](/D:/project/SUBSTAGE_CONTEXT.md).
