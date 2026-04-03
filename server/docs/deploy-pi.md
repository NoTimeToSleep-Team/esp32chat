# Deploy to Raspberry Pi (Pi OS)

This document describes the deploy package for `v0.06.06`.

## Deploy Artifacts

- systemd unit: `server/systemd/local-chat-server.service`
- nginx site config: `server/config/nginx/local-chat-server.conf`
- Pi env template: `server/config/pi.env.example`
- Linux installer: `server/scripts/install_pi.sh`
- Windows remote helper: `server/scripts/install_pi.ps1`

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

1. Copy or clone the `server` directory to the Pi.
2. Run:

```bash
sudo bash ./scripts/install_pi.sh
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

Run these commands on the Pi:

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
- Real hardware/network validation remains required on the target Pi.
