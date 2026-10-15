# Local Chat Server

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](server/pyproject.toml)
[![GitHub release](https://img.shields.io/github/v/release/NoTimeToSleep-Team/esp32chat)](https://github.com/NoTimeToSleep-Team/esp32chat/releases)

Self-hosted chat for a private local network. A Raspberry Pi runs the server and
the web portal; the same portal and ESP32-based devices (starting with the
M5Cardputer) connect to it as chat clients over HTTP and WebSocket. Everything
lives on your own hardware — no cloud services, no external accounts.

- [Features](#features)
- [Hardware clients](#hardware-clients)
- [Install (Raspberry Pi)](#install-raspberry-pi)
- [Management](#management)
- [On-device layout](#on-device-layout)
- [Repository layout](#repository-layout)
- [Development](#development)
- [Releases](#releases)
- [Documentation](#documentation)
- [Status](#status)
- [License](#license)

## Features

v0.1.0 is the first public release and ships the server side of the product.

**Accounts and access**

- Registration in open mode, or by application when the server runs in closed
  mode (admins review the queue).
- Login with session tokens; guest access is available only for web clients.
- Roles: user / moderator / admin, with per-user restrictions and a device
  blacklist.

**Chat**

- Direct chats and private rooms (optional 4-digit room code to join).
- Custom chat limits: up to 5 per user, unlimited for admins; guests cannot
  create chats; admins can access all chats.
- Message history, media attachments, chat avatars.
- Realtime delivery over WebSocket (`/realtime/chat/{chat_id}`); REST endpoints
  for history, sending and moderation.

**Admin panel** (`/admin`)

- User management: ban / unban, temporary block, device blacklist, delete.
- Content: applications queue, support queue, blog publishing.
- Access-mode switch (open / closed registration).
- Reports, warnings and moderation tools.

**Security baseline**

- Global and per-route rate limiting.
- Login brute-force guard (per-IP attempt budget with temporary blocks).
- Security events are written to the `audit_log`.

**Ops safety**

- Backups: snapshot files plus history; restore runs as dry-run.
- Incidents journal, degraded-mode state, safe-shutdown dry-run.

**Install & management**

- One-command installer with an English setup wizard.
- systemd service — start on boot or start manually (your choice in the wizard).
- `lc` management CLI: status, setup, update, backup, logs, uninstall.

## Hardware clients

Firmware for ESP32-based devices lives in `firmware/`. The first target is the
**M5Cardputer** (PlatformIO project with a small screen and keyboard); the
roadmap then adds M5StickC Plus 2, T-Embed CC1101 and Flipper Zero. Clients talk
to the server over HTTP + WebSocket, and the message formats are pinned in
`contracts/`.

## Install (Raspberry Pi)

### Requirements

- Raspberry Pi 4/5, 64-bit. Raspberry Pi OS Bookworm or newer
  (Debian 13 trixie is verified; Python ≥ 3.10 is required).
- Internet access during installation (apt packages + Python wheels).
- Bullseye 64-bit (Python 3.9) is not supported — the installer explains why
  and suggests upgrading.

### One command

```bash
curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash
```

Run it as any regular user — `sudo` asks for the password once. The installer:

1. downloads the release archive and verifies its sha256;
2. checks OS / architecture / Python / disk space and installs missing apt
   packages (waits out busy apt locks);
3. lays out `/opt/local-chat-server`, creates a venv and installs dependencies;
4. generates `config/app.env` with a random session secret, starts the systemd
   service and waits for `/health`;
5. launches the setup wizard.

Install log: `/var/log/lc-install.log`. Re-running the installer acts as an
update; `data/` is never wiped.

### Setup wizard

The whiptail wizard (English-only in v0.1) walks through:

- administrator account (login + password);
- Wi-Fi access point (on/off, SSID, password, channel, country);
- portal port (default 18080);
- registration mode (open / closed);
- start on boot or start manually;
- summary and apply.

The wizard can be re-run anytime with `sudo lc setup`; current values are
offered as defaults.

### Installer options

```bash
# pin a version
LC_VERSION=0.1.0 curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash

# skip the wizard (install only)
curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash -s -- --no-setup

# wizard answers from a file
curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash -s -- --preseed ./preseed.txt

# offline / custom archive
LC_TARBALL_URL=file:///tmp/lc-server-v0.1.0.tar.gz bash install.sh
```

After install the portal is available at `http://<pi-address>:18080`.

## Management

`lc` manages the installation (installed as `/usr/local/bin/lc`):

| Command | What it does |
| --- | --- |
| `lc status` | service and portal status |
| `lc setup` | run the setup wizard (current values as defaults) |
| `lc start` / `lc stop` | start / stop the server now |
| `lc update` | update from the newest release (`data/` and `app.env` are kept) |
| `lc backup` | archive `data/` + `app.env` |
| `lc export [FILE]` | bundle `data/` + `app.env` for moving to another server (a `.sha256` is written too) |
| `lc import FILE [--yes]` | restore an export on this server (checks the checksum, keeps a safety backup) |
| `lc logs` | install log and service journal |
| `lc uninstall` | remove the service; `data/` is kept (`--purge` removes everything) |
| `lc version` | server version |

### Moving the server to another device

```bash
# on the old server
sudo lc export /tmp/lc-export.tar.gz

# copy /tmp/lc-export.tar.gz (+ its .sha256) to the new device,
# install the server there (one command), then:
sudo lc import /tmp/lc-export.tar.gz
```

The export contains the database, uploads, avatars and settings. `lc import`
verifies the checksum, exports the current data to `/var/backups/` first (when
it is not empty — roll back any time with `sudo lc import <that file> --yes`),
and restarts the service. The setup wizard can also import an export file
directly during a fresh install ("Start the server with: data from an export
file").

## On-device layout

```
/opt/local-chat-server/        code, venv, data/, config/app.env
/etc/systemd/system/local-chat-server.service
/usr/local/bin/lc
/var/log/lc-install.log
```

- Service user: `localchat`; the portal listens on `0.0.0.0:<LCS_PORT>` (18080).
- Settings live in `config/app.env` (mode 600, contains secrets).

## Repository layout

| Path | Contents |
| --- | --- |
| `server/` | FastAPI server, web portal, SQLite migrations, installer (`setup/`), `lc` CLI, systemd units |
| `server/app/` | application code — API routers, services, models, realtime transport, templates/static UI |
| `firmware/` | ESP32 client firmware (M5Cardputer first) and the bridge |
| `contracts/` | message and sync contracts shared by server and firmware |
| `tests/` | server API suites (`tests/server`) and browser UI checks (`tests/ui`) |
| `docs/` | installation guide, architecture, glossary, device matrix |
| `scripts/` | development and deployment helpers |
| `prompts/` | prompt sources used to build the project |

## Development

Run the server locally:

```bash
cd server
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Useful endpoints:

- `GET /health`, `GET /health/ready` — liveness / readiness;
- `POST /auth/login`, `POST /auth/register` — auth API;
- `GET /realtime/chat/{chat_id}?session_token=…` — WebSocket transport
  (`ping`, `chat.history`, `chat.send` in; `realtime.connected`,
  `chat.message`, `chat.history`, `chat.ack`, `error` out).

Tests: `tests/server` are Python scripts that talk to a running server
(`LC_BASE`, `LC_ADMIN_PASSWORD` env vars point to a device); `tests/ui` are
browser checks against a live portal (`tests/ui/README.md` explains the setup).

Build the release tarball:

```bash
bash server/scripts/make_release_tarball.sh
# → dist/lc-server-v<version>.tar.gz + .sha256 (server/ only; no data/.venv/__pycache__)
```

## Releases

Release tags live on `main` (e.g. `v0.1.0`). Every release publishes:

- `install.sh` — the standalone bootstrap installer;
- `lc-server-v<version>.tar.gz` — the server archive;
- `lc-server-v<version>.tar.gz.sha256` — checksum.

`lc update` on a device pulls the newest release. Older releases stay available
on the releases page.

## Documentation

- `docs/INSTALL.md` — full install guide: requirements, options, wizard,
  management, uninstall and known limitations.
- `docs/architecture.md` — server architecture and data flows.
- `docs/device-matrix.md` — device roles and constraints.
- `docs/glossary.md` — project terms.

## Status

v0.1.0 is the first public release. The server and web portal are the primary
deliverable; hardware firmware is in early development. Known limitations of
this release (access-point setup on NetworkManager, the admin password briefly
visible in the process list, fresh installs only) are listed at the end of
`docs/INSTALL.md`.

## License

MIT — see [LICENSE](LICENSE).
