# Установка Local Chat Server (v0.1)

Сервер + веб-портал для Raspberry Pi 4/5. Установка одной командой, после неё
сразу запускается мастер настройки (whiptail).

## Требования

- Raspberry Pi 4/5, **Raspberry Pi OS Bookworm и новее, 64-bit** (Python ≥ 3.10).
- Bullseye 64-bit (Python 3.9) не поддерживается — установщик вежливо объяснит
  и подскажет обновиться.
- Интернет для доустановки пакетов и зависимостей Python.

## Установка (одна команда)

```bash
curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash
```

- Конкретная версия: `LC_VERSION=0.1.0 curl -fsSL … | sudo bash`.
- Свой источник тарбола (офлайн/тест): `LC_TARBALL_URL=file:///tmp/lc-server-v0.1.0.tar.gz bash install.sh`.
- Неинтерактивная установка без мастера: `… | sudo bash -s -- --no-setup`.
- Значения мастера из файла: `… | sudo bash -s -- --preseed /path/preseed.txt`
  (файл `KEY=VALUE`; ключи — из `server/setup/settings-schema.json`).

Установщик сам готовит себе место: проверяет ОС/архитектуру/Python/диск,
доустанавливает пакеты (переживает занятый apt-лок, чистит устаревшие локи,
повторяет попытки), поднимает venv и systemd-службу, ждёт `/health` и запускает
мастер. Лог — `/var/log/lc-install.log`. Повторный запуск = обновление, данные не
затираются.

## Мастер настройки (whiptail)

Запускается сразу после установки. Экраны: администратор (логин/пароль) →
точка доступа Wi-Fi (вкл/выкл, SSID, пароль, канал, страна) → порт (18080) →
режим регистрации → сводка → применение.

- `Esc` на любом шаге — отмена без изменений.
- Повторить: `sudo lc setup` (текущие значения подставляются как дефолты).
- Логин администратора по умолчанию — `admin`, пароль задаётся в мастере.
- Session secret генерируется автоматически.

## Обслуживание

```
lc status              состояние службы и health
lc setup               повторить мастер
lc update              обновление новым релизом (data/ и app.env сохраняются)
lc backup              архив data/ + app.env
lc logs                журнал установки + журнал службы
lc uninstall           удалить (данные сохраняются); --purge — удалить всё
lc version             версия
```

## Раскладка

```
/opt/local-chat-server/        код, venv, data/, config/app.env
/etc/systemd/system/local-chat-server.service
/usr/local/bin/lc
/var/log/lc-install.log
```

- Пользователь службы: `localchat`; портал слушает `0.0.0.0:<LCS_PORT>` (18080).
- Настройки: `config/app.env` (файл 600, содержит секреты).

## Schema-driven

Все изменяемые настройки установки — в `server/setup/settings-schema.json`
(apt-пакеты, min-Python, поля мастера, действия). Движки (`install_pi.sh`,
`wizard.sh`) манифест только читают: **новый параметр = новая запись в
манифесте, скрипты не меняются.**

## Сборка релизного тарбола

```bash
bash server/scripts/make_release_tarball.sh
# dist/lc-server-v0.1.0.tar.gz + .sha256 (server/ без data/.venv/__pycache__)
```

## Известные ограничения v0.1 (pre-release)

- **Живой RPi 4/5 не проверен** (плата была недоступна). Полный цикл прогонялся в
  WSL Debian (x86_64, systemd): установка → мастер → health → логин → update →
  backup → uninstall. Логика идентична, но на «железе» нужен приёмочный прогон.
- Точка доступа настраивается существующим скриптом (`configure_pi_ap_nat.sh`,
  dhcpcd-подход). На Bookworm с NetworkManager AP может потребовать ручной
  доводки — на живой плате не проверено.
- Только чистые установки; миграция со старой раскладки (`/home/gamecat/lc-server`)
  не поддерживается.
- Мастер на русском (поля переключаются `LC_LANG=en`).
- Пароль администратора кратко виден в списке процессов (передаётся аргументом CLI).
- `x86_64` установщик допускает с предупреждением — только для тестов.
