# Installing from packages (apt / dnf / pacman)

Local Chat ships native packages with signed repositories hosted on GitHub
Pages. The curl installer keeps working — packages are an alternative with the
same result: the same setup wizard, the same `lc` command, the same
`/opt/local-chat-server` layout and the same data directory. An existing
curl-installed server can switch to packages in place.

Repository: <https://notimetosleep-team.github.io/esp32chat/>

## Debian / Ubuntu / Raspberry Pi OS

One-time repository setup (adds the signing key and the apt source, then
installs the package):

```bash
curl -fsSL https://notimetosleep-team.github.io/esp32chat/setup-apt.sh | sudo sh
```

Afterwards use the standard commands:

```bash
sudo apt install local-chat     # install
sudo apt upgrade                # update everything, including local-chat
sudo apt remove local-chat      # remove the code; data and config stay
sudo apt purge local-chat       # also remove config; user data stays
```

Manual setup instead of the bootstrap script:

```bash
sudo curl -fsSL https://notimetosleep-team.github.io/esp32chat/local-chat.gpg \
    -o /usr/share/keyrings/local-chat.gpg
echo "deb [signed-by=/usr/share/keyrings/local-chat.gpg] https://notimetosleep-team.github.io/esp32chat/apt stable main" \
    | sudo tee /etc/apt/sources.list.d/local-chat.list
sudo apt update
sudo apt install local-chat
```

Supported: Debian 12 (bookworm) and 13 (trixie), Ubuntu 22.04 and 24.04,
Raspberry Pi OS bookworm/trixie — `arm64` and `amd64`. One package per
architecture works on all of these: it bundles Python wheels for CPython
3.10–3.14 and pip picks the matching ones at install time.

## Fedora (dnf)

```bash
sudo dnf install https://notimetosleep-team.github.io/esp32chat/rpm/local-chat-release-1-1.noarch.rpm
sudo dnf install local-chat
```

The `local-chat-release` package installs the repository definition
(`/etc/yum.repos.d/local-chat.repo`) and imports the signing key. Updates:

```bash
sudo dnf upgrade local-chat
```

Supported: Fedora 41/42, `x86_64` and `aarch64`.

## Arch Linux (pacman)

```bash
curl -fsSL https://notimetosleep-team.github.io/esp32chat/setup-arch.sh | sudo sh
```

The script imports the signing key, adds the `[localchat]` section to
`/etc/pacman.conf` and installs the package. Afterwards:

```bash
sudo pacman -S local-chat      # install
sudo pacman -Syu               # update
sudo pacman -R local-chat      # remove; data and config stay
```

Supported: Arch Linux `x86_64` (rolling; the package is rebuilt for new Python
versions).

## After installation

The package starts `local-chat-server` and, when installed from a terminal,
runs the same setup wizard as the curl installer (administrator, Wi-Fi access
point on Raspberry Pi OS/Debian, port, registration mode). Non-interactive
installs (`apt -y`, `DEBIAN_FRONTEND=noninteractive`, CI) skip the wizard:

```bash
sudo lc setup     # create the administrator and configure the server
lc status         # version, service, port, /health
sudo lc logs      # install log + journal
```

The portal is at `http://<host>:18080/`.

## What the package does

- installs the application into `/opt/local-chat-server` (identical to the curl
  installer), the management CLI as `/usr/bin/lc` and the systemd unit;
- creates the `localchat` service user and the `data/` directories;
- builds the virtualenv **offline** from the bundled wheels — no PyPI access is
  needed during installation;
- generates `config/app.env` with a random session secret (kept on upgrades);
- starts and enables `local-chat-server`, waits for `/health`;
- records the install channel in `LC_INSTALL_CHANNEL` so `lc` can tell a
  package install from a curl install.

## Data, updates and removal

- `data/` and `config/app.env` are **not owned by the package**: upgrades keep
  them, `remove` keeps them, `purge` removes only the configuration — the chat
  database, media and avatars stay until you delete them manually.
- `lc update` and `lc uninstall` on a package-managed server print the matching
  `apt` / `dnf` / `pacman` command instead of touching files behind the package
  manager's back.
- `lc status` shows the install channel (`deb package (apt)`, `rpm package
  (dnf)`, `pacman package` or `curl installer`).

## Signing

All repository metadata is signed with the Local Chat packages key:

```
1D55 7025 0631 2852 42CA  1452 42D6 CB6B FF7C 1541
```

Public key: <https://notimetosleep-team.github.io/esp32chat/local-chat.gpg>.
apt verifies `InRelease`, dnf verifies `repomd.xml` and package signatures,
pacman verifies the database signature (`SigLevel = Optional DatabaseOptional`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `apt update`: `NO_PUBKEY` / signature error | re-run `setup-apt.sh` (refreshes the keyring file) |
| `dnf`: `repomd.xml GPG signature verification error: Signing key not found` | install `local-chat-release` first — it imports the key |
| `pacman`: `key ... could not be looked up` | `sudo pacman-key --lsign-key <fingerprint>` after importing |
| service does not start | `systemctl status local-chat-server`, `journalctl -u local-chat-server -n 50`, `/var/log/lc-install.log` |
| data kept after removal | intended: delete `/opt/local-chat-server` manually for a full cleanup |

Offline installation: download the `.deb` / `.rpm` / `.pkg.tar.zst` from the
[releases page](https://github.com/NoTimeToSleep-Team/esp32chat/releases) and
install it directly (`apt install ./local-chat_*.deb`,
`dnf install ./local-chat-*.rpm`, `pacman -U local-chat-*.pkg.tar.zst`).
