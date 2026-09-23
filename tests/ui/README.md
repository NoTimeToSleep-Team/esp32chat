# UI test suites (SPA)

Требуется запущенный локальный сервер на `127.0.0.1:18080` и Playwright (берётся из npx-кэша, см. `lib.js`).

## Запуск сервера (Windows, из корня репозитория)

```powershell
$env:PYTHONIOENCODING = "utf-8"
$p = Start-Process -FilePath python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","18080" `
  -WorkingDirectory "D:\opencode\LC_PROJECT\server" `
  -RedirectStandardOutput "C:\WINDOWS\TEMP\opencode\lc-server.log" `
  -RedirectStandardError "C:\WINDOWS\TEMP\opencode\lc-server.err.log" -PassThru -WindowStyle Hidden
try {
  for ($i=0; $i -lt 12; $i++) { Start-Sleep 1; try { if ((Invoke-WebRequest "http://127.0.0.1:18080/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { break } } catch {} }
  node tests/ui/ui_test.js
} finally { Stop-Process -Id $p.Id -Force }
```

Важно: сервер всегда останавливать (`Stop-Process` в `finally`). Между сьютами сервер перезапускать — у сервера есть in-memory rate-limit, иначе будут 429.

## Сьюты

| Файл | Что проверяет |
| --- | --- |
| `ui_test.js` | Десктоп-смоук: логин, чат (поиск, отправка, правка через модалку, удаление, вложение-фото), страница устройств, аккаунт, админка, логаут |
| `mobile_chrome_check.js` | Мобильный chrome (одна шапка), тач-скролл, фиксация страницы и следование за видимой областью (iOS), меню, модалки, правка сообщения |
| `devices_check.js` | Страница «Устройства»: сопряжение по 6-значному коду (валидация ввода, ошибки), список сопряжённых, мобильная раскладка |
| `avatar_check.js` | Фото-аватар: загрузка (png/jpeg/webp, лимит), отказ для неверного типа, показ в чате, возврат к эмодзи |
| `admin_check.js` | Автономная админка (`/static/admin.html`): палитра, сессия (свои ключи, восстановление после reload), табы, мобильные карточки таблиц |
| `voice_check.js` | Голосовые сообщения: запись/отмена/предпросмотр/отправка, плеер (fake media stream) |
| `support_check.js` | Страница поддержки (`/support`): авто-загрузка обращений, создание, ответ с вложением, статусы, мобильный переход список↔диалог |

Скриншоты складываются в `experiments/ui/shots/`.
