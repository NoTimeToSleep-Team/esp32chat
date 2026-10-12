# Installing Local Chat Server (v0.1)

The chat server + web portal for Raspberry Pi 4/5. One command installs
everything (the installer downloads the release archive itself), followed by a
whiptail setup wizard.

## Requirements

- Raspberry Pi 4/5, **Raspberry Pi OS Bookworm or newer, 64-bit** (Python ≥ 3.10).
- Bullseye 64-bit (Python 3.9) is not supported — the installer explains why
  and suggests upgrading.
- Internet access for apt packages and Python dependencies.

## Install (one command)

```bash
curl -fsSL https://github.com/NoTimeToSleep-Team/esp32chat/releases/latest/download/install.sh | sudo bash
```

Run it as any regular user — `sudo` asks for the password once. The installer:

- downloads the release tarball and verifies its sha256;
- checks OS/architecture/Python/disk space, installs missing apt packages
  (waits out busy apt locks, cleans stale locks, retries);
- lays out `/opt/local-chat-server`, creates a venv, installs dependencies;
- generates `app.env` with a random session secret, starts and enables the
  systemd service, waits for `/health`;
- launches the setup wizard.

Log: `/var/log/lc-install.log`. Re-running = update; `data/` is never wiped.

Options:

```bash
LC_VERSION=0.1.0 curl -fsSL …/install.sh | sudo bash     # pin a version
LC_TARBALL_URL=file:///tmp/lc-server-v0.1.0.tar.gz bash install.sh   # offline/custom
curl -fsSL …/install.sh | sudo bash -s -- --no-setup   # skip the wizard
curl -fsSL …/install.sh | sudo bash -s -- --preseed ./preseed.txt   # wizard answers from a file
```

## Setup wizard (whiptail)

Runs right after the install. Steps: administrator (login/password) → Wi-Fi
access point (on/off, SSID, password, channel, country) → portal port (18080)
→ registration mode → **start on boot or start manually** → summary → apply.

- `Esc` on any step cancels without changes.
- Re-run: `sudo lc setup` (current values are offered as defaults).
- Default administrator login is `admin`; the password is set in the wizard.
- The session secret is generated automatically.

## Management

```
lc status              service and health
lc setup               re-run the wizard
lc start               start the server now
lc stop                stop the server
lc update              update from a new release (data/ and app.env kept)
lc backup              archive data/ + app.env
lc logs                install log + service journal
lc uninstall           remove (data kept); --purge removes everything
lc version             version
```

## Layout

```
/opt/local-chat-server/        code, venv, data/, config/app.env
/etc/systemd/system/local-chat-server.service
/usr/local/bin/lc
/var/log/lc-install.log
```

- Service user: `localchat`; the portal listens on `0.0.0.0:<LCS_PORT>` (18080).
- Settings: `config/app.env` (mode 600, contains secrets).

## Schema-driven

All changeable installer settings live in
`server/setup/settings-schema.json` (apt packages, minimum Python, wizard
fields, defaults). The engines (`install_pi.sh`, `wizard.sh`) only read the
manifest: **a new server setting = a new manifest entry; the scripts do not
change.**

## Building the release tarball

```bash
bash server/scripts/make_release_tarball.sh
# dist/lc-server-v0.1.0.tar.gz + .sha256 (server/ only, no data/.venv/__pycache__)
```

## Known limitations (v0.1, pre-release)

- The full cycle was verified in WSL Debian (x86_64, systemd): install → wizard
  → health → admin login → update → backup → uninstall; and the schema-driven
  acceptance check passed. A real RPi 4/5 acceptance run is pending.
- The access point reuses the existing `configure_pi_ap_nat.sh` (dhcpcd-based):
  on Bookworm with NetworkManager it may need manual tweaks (not verified on
  real hardware).
- Fresh installs only; migrating the legacy layout (`/home/gamecat/lc-server`)
  is not supported.
- The wizard is English-only in v0.1.
- The administrator password is briefly visible in the process list (passed as
  a CLI argument).
- `x86_64` is allowed with a warning — for testing only.
