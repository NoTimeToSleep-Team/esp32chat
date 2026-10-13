# Local Chat Server

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](server/pyproject.toml)
[![GitHub release](https://img.shields.io/github/v/release/NoTimeToSleep-Team/esp32chat)](https://github.com/NoTimeToSleep-Team/esp32chat/releases)

Self-hosted chat for a private local network. A Raspberry Pi runs the server and
the web portal; ESP32-based devices connect to it as chat clients. Everything
lives on your own hardware — no cloud services, no external accounts.

## Features (v0.1)

- Web portal: registration (open or by admin-approved application), chats and
  private rooms, message attachments, blog, support tickets, account profiles.
- Admin panel at `/admin`: user management, applications, content (blog,
  support), moderation and access-mode switch.
- REST API and WebSocket transport for hardware clients.
- One-command installer with an English setup wizard.
- systemd service — start on boot or start manually (your choice in the wizard).
- `lc` management CLI: status, setup, update, backup, logs, uninstall.

## Install (Raspberry Pi)

```bash
curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash
```

Requirements: Raspberry Pi 4/5, Raspberry Pi OS Bookworm or newer (64-bit,
Python ≥ 3.10), internet access during install.

The installer downloads and verifies the release archive, sets up
`/opt/local-chat-server`, starts the service and launches the setup wizard.
Re-run the wizard anytime with `sudo lc setup`. The portal listens on port
18080 by default — open `http://<pi-address>:18080`.

Full details, options, update, backup and uninstall: `docs/INSTALL.md`.

## Repository layout

| Path         | Contents |
|--------------|----------|
| `server/`    | FastAPI server, web portal, SQLite migrations, installer (`setup/`), `lc` CLI |
| `firmware/`  | ESP32 client firmware (M5Cardputer first) and the bridge |
| `contracts/` | Message and sync contracts shared by server and firmware |
| `tests/`     | Server API and UI test suites |
| `docs/`      | Installation guide, architecture, glossary, device matrix |
| `scripts/`   | Development and deployment helpers |
| `prompts/`   | Prompt sources used to build the project |

## Documentation

- `docs/INSTALL.md` — install, setup wizard, management, uninstall.
- `docs/architecture.md` — server architecture and data flows.
- `docs/glossary.md` — project terms.
- `docs/device-matrix.md` — device roles and constraints.

## Status

v0.1.0 is the first public release. The server and web portal are the primary
deliverable; hardware firmware is in early development. Known limitations of
this release are listed in `docs/INSTALL.md`.

## Releases

Release tags live on `main` (e.g. `v0.1.0`). Each release publishes the server
archive, its sha256 checksum and a standalone `install.sh`; `lc update` pulls
the newest release. Tarball build: `bash server/scripts/make_release_tarball.sh`.

## License

MIT — see [LICENSE](LICENSE).
