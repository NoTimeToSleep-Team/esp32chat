# LC Bridge (M5Stamp S3)

Мост между устройствами (ESP-NOW) и сервером на Raspberry Pi (USB).

```
Cardputer ⇄ ESP-NOW (радио) ⇄ Stamp S3 ⇄ USB-кабель ⇄ RPi (демон) ⇄ local-chat-server
```

- Мосту Wi-Fi не нужен: питание и данные — по USB.
- Устройства шлют JSON-запросы (те же, что по Wi-Fi) на broadcast ESP-NOW;
  мост пересылает их демону, ответы возвращает устройству.
- Канал ESP-NOW: **1** (совпадает с каналом AP RPi).

## Прошивка моста

```powershell
cd firmware\bridge
$env:PLATFORMIO_CORE_DIR = "D:\opencode\_tools\platformio"
& "D:\opencode\_tools\pio-venv\Scripts\platformio.exe" run -t upload
```

Прошивается по USB с ПК (как Cardputer): при необходимости зажать BOOT/G0
на Stamp S3, чтобы появился COM-порт.

## Демон на RPi

Файлы: `daemon/lc_bridge_daemon.py`, `daemon/lc-bridge.service`.

```bash
# на RPi
sudo -n /home/gamecat/lc-server/venv/bin/pip install pyserial
mkdir -p /home/gamecat/lc-server/bridge
# скопировать lc_bridge_daemon.py в /home/gamecat/lc-server/bridge/
sudo -n cp /home/gamecat/lc-server/bridge/lc-bridge.service /etc/systemd/system/
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now lc-bridge
sudo -n journalctl -u lc-bridge -n 20 --no-pager
```

Демон сам находит порт моста по VID Espressif (0x303A) и переподключается,
если мост отключили/подключили.

## Протокол

ESP-NOW кадр (≤ 204 байта payload):

```
[0x4C][type:1][frag_index:1][frag_count:1][payload ≤ 200]
type 0x01 запрос устройства, 0x02 ответ моста, 0x03 ping, 0x04 pong
```

USB кадр:

```
[0xAA][type:1][len:2 LE][mac:6][payload:len]
type 0x01 запрос к демону, 0x02 ответ устройству, 0x03 hello
```

Payload запроса: `{"id":12,"m":"GET","p":"/chat/api/chats?...","b":"..."}`
Payload ответа:  `{"id":12,"s":200,"b":"..."}`

## Состояние

- Прошивка моста и демон написаны, компиляция проверяется.
- Заливка на железо и живой тест — после подключения Stamp S3 по USB.
- Транспорт ESP-NOW в прошивке Cardputer и режим репитера — следующие шаги.
