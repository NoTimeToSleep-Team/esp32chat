# Recovery Guide — RPi-Only Server (v1.00.00)

## Быстрый старт (с нуля)
1. Запиши Raspberry Pi OS Lite на SD-карту
2. В настройках Imager включи SSH, задай пароль, настрой Wi-Fi
3. Вставь SD в Pi, подключи питание
4. Через 2 минуты найди Pi по mDNS: `ssh user@raspberrypi.local`
5. Установи сервер:
   ```bash
   cd /opt
   sudo bash /opt/local-chat-server/scripts/install_pi.sh
   ```
6. Проверь: `curl http://localhost:8000/health`

## Без дисплея (Pi Connect / SSH)
- SSH по mDNS: `ssh user@raspberrypi.local`
- Raspberry Pi Connect: https://connect.raspberrypi.com/
- Найди IP в админке роутера

## Проверка состояния
```bash
# Health endpoint
curl http://localhost:8000/health

# System health (CPU, RAM, disk)
curl http://localhost:8000/ops/system-health

# Service status
sudo systemctl status local-chat-server

# Последние логи
journalctl -u local-chat-server -n 50 --no-pager
```

## Если сервер не отвечает
1. Проверь зелёный светодиод на Pi (питание)
2. Подожди 2 минуты после включения
3. Подключись по SSH
4. Проверь статус: `sudo systemctl status local-chat-server`
5. Логи: `journalctl -u local-chat-server -n 100 --no-pager`
6. Перезапусти: `sudo systemctl restart local-chat-server`
7. Если не помогает — проверь файлы логов: `cat /opt/local-chat-server/data/logs/*.log`

## Автоматическое восстановление
- systemd настроен на auto-restart (перезапуск через 5 сек после падения)
- SQLite в WAL mode (устойчивость к сбоям питания)
- Логи ротируются ежедневно (14 дней хранения)
- Boot self-test при каждом старте

## 2-недельная стабильность
| Компонент | Механизм |
|-----------|----------|
| Auto-restart | systemd Restart=always |
| Целостность БД | SQLite WAL mode + PRAGMA integrity_check |
| Защита диска | logrotate (ежедневная ротация, 14 дней) |
| Мониторинг | /ops/system-health (CPU/RAM/disk) |
| Самопроверка | boot_selftest.py при старте |

## Важные пути
| Что | Где |
|-----|-----|
| Конфигурация | /opt/local-chat-server/config/app.env |
| База данных | /opt/local-chat-server/data/sqlite/local_chat.db |
| Логи | /opt/local-chat-server/data/logs/ |
| Бэкапы | /opt/local-chat-server/data/backups/ |

## Лимиты
- CPU > 90% длительно → проверь нагрузку
- RAM > 90% → перезагрузка
- Disk < 100 MB → срочно освободи место
- DB > 1 GB → нужна архивация

## После сбоя питания
1. Просто включи питание — сервер запустится автоматически
2. systemd перезапустит сервер если он упал
3. SQLite WAL защищает от повреждения при внезапном отключении
4. Через ~30 секунд сервер готов к работе
