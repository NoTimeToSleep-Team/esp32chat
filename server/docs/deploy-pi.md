# Deploy to Raspberry Pi / ARM Linux (Pi OS)

This document describes the deploy package for `v0.06.06` and the ARM Linux deployment targets currently supported by the project.

## Ссылки

- [Recovery Guide](../../docs/recovery-guide.md) — восстановление сервера, быстрый старт с нуля, проверка состояния

## Deploy Artifacts

- systemd unit: `server/systemd/local-chat-server.service`
- nginx site config: `server/config/nginx/local-chat-server.conf`
- Pi env template: `server/config/pi.env.example`
- Pi Zero 2 W env template: `server/config/pi-zero2w.env.example`
- CardputerZero env template: `server/config/cardputerzero.env.example`
- Linux installer: `server/scripts/install_pi.sh`
- Pi Zero 2 W installer wrapper: `server/scripts/install_pi_zero2w.sh`
- CardputerZero installer wrapper: `server/scripts/install_cardputerzero.sh`
- Windows remote helper: `server/scripts/install_pi.ps1`
- AP+NAT setup helper: `server/scripts/configure_pi_ap_nat.sh`
- AP+NAT rollback helper: `server/scripts/disable_pi_ap_nat.sh`
- AP+NAT guide: `server/docs/pi-ap-nat.md`

## Supported ARM Targets

- Raspberry Pi 5
- Raspberry Pi Zero 2 W
- M5CardputerZero (Raspberry Pi CM0 based Linux handheld)

## Target Layout

The installer uses `/opt/local-chat-server` as the default root:

```text
/opt/local-chat-server/
├── app/
├── migrations/
├── config/
├── docs/
├── scripts/
├── systemd/
├── data/
│   ├── sqlite/
│   ├── media/
│   ├── avatars/
│   ├── uploads/
│   ├── rfid/
│   ├── backups/
│   ├── logs/
│   └── incidents/
└── .venv/
```

## Option A: Run Installer Directly on Pi

1. Copy or clone the `server` directory to the target.
2. Run:

```bash
sudo bash ./scripts/install_pi.sh
```

Target-specific wrappers:

```bash
sudo bash ./scripts/install_pi_zero2w.sh
sudo bash ./scripts/install_cardputerzero.sh
```

3. Edit runtime config if needed:

```bash
sudo nano /opt/local-chat-server/config/app.env
```

4. Restart service after config changes:

```bash
sudo systemctl restart local-chat-server
```

## Option B: Run Deploy from Windows (SSH)

From your workstation:

```powershell
pwsh .\server\scripts\install_pi.ps1 -Host 192.168.1.50 -User pi
```

With a custom SSH key:

```powershell
pwsh .\server\scripts\install_pi.ps1 -Host 192.168.1.50 -User pi -IdentityFile C:\Users\you\.ssh\id_rsa
```

The script packs `server`, uploads it to `/tmp/local-chat-server-deploy`, runs remote install, and verifies `http://127.0.0.1/health`.

## Post-Deploy Verification on Pi

Run these commands on the target:

```bash
sudo systemctl status local-chat-server --no-pager
sudo systemctl status nginx --no-pager
sudo nginx -t
curl -fsS http://127.0.0.1/health
curl -fsS http://127.0.0.1/health/ready
```

Expected:

- systemd service is `active (running)`;
- nginx config test passes;
- health endpoints return JSON with `status=ok` / `status=ready`.

## Notes

- `install_pi.sh` is idempotent for normal redeploys.
- By default, installer disables `/etc/nginx/sites-enabled/default`.
- Override defaults with env vars before running installer:
  - `APP_ROOT`, `APP_USER`, `APP_GROUP`, `DISABLE_DEFAULT_NGINX_SITE`, `HEALTH_URL`.
- Real hardware/network validation remains required on the target ARM board.
- AP+NAT setup is a separate controlled step; use `server/docs/pi-ap-nat.md`.

## Быстрый старт

См. [Recovery Guide — Быстрый старт (с нуля)](../../docs/recovery-guide.md#быстрый-старт-с-нуля):

1. Запиши Raspberry Pi OS Lite на SD-карту
2. В настройках Imager включи SSH, задай пароль, настрой Wi-Fi
3. Вставь SD в Pi, подключи питание
4. Через 2 минуты найди Pi по mDNS: `ssh user@raspberrypi.local`
5. Установи сервер:
   ```bash
   sudo bash /opt/local-chat-server/scripts/install_pi.sh
   ```
6. Проверь: `curl http://localhost:8000/health`
