# RPi — оперативные заметки

Короткая памятка по доступу к плате и деплою. Портал платы: `http://169.254.93.1:18080` (прямое подключение Ethernet).

## Если RPi «недоступен», хотя он включён

Проверить, куда уходит трафик:

```powershell
Find-NetRoute -RemoteIPAddress 169.254.93.1
```

Если первым в списке идёт `Tailscale` — это и есть причина. Tailscale держит маршрут
`169.254.0.0/16` с метрикой интерфейса `5`, у Ethernet — `500`; меньшая метрика выигрывает,
и link-local трафик к плате уходит в туннель. Плата при этом жива.

Лечение (один раз, нужны права администратора). Маршрут точечный — только на IP платы,
Tailscale не ломается; `-p` сохраняет его после перезагрузки:

```powershell
# индекс интерфейса Ethernet:
Get-NetRoute -AddressFamily IPv4 | Where-Object { $_.DestinationPrefix -eq '169.254.0.0/16' } |
  Select-Object InterfaceAlias, InterfaceIndex

# добавить маршрут (подставить <index>):
route -p add 169.254.93.1 mask 255.255.255.255 0.0.0.0 if <index> metric 1
```

Проверка: `ping 169.254.93.1` отвечает, `Find-NetRoute -RemoteIPAddress 169.254.93.1` показывает Ethernet.

Полезно: `New-NetRoute -PolicyStore PersistentStore` на этом ПК падает с «Invalid parameter PolicyStore»,
поэтому используется классический `route -p add`.

## Деплой

```powershell
$env:LC_RPI_PASS = "<пароль gamecat>"
$env:PYTHONIOENCODING = "utf-8"

.venv\Scripts\python.exe scripts\deploy_ui_to_rpi.py    # UI: app.js/app.css/шаблоны, без рестарта службы
.venv\Scripts\python.exe scripts\deploy_chat_to_rpi.py  # код чата + рестарт службы
```

Обе кладут бэкап в `/home/gamecat/backups/…` и печатают версию UI из удалённого `index.html`.

## Тесты на живом портале

```powershell
$env:LC_BASE = 'http://169.254.93.1:18080'
node tests\ui\mobile_chrome_check.js
# остальные сьюты так же: tests\ui\<suite>.js
```

## Служба на плате

```powershell
ssh gamecat@169.254.93.1 "systemctl status local-chat-server --no-pager | head -n 20"
```