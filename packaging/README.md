# Packaging (deb / rpm / pacman)

Everything needed to ship Local Chat as native packages and to publish
apt / dnf / pacman repositories.

## Layout

| Path | Purpose |
|---|---|
| `common/wheels.sh` | builds the application wheel and downloads every dependency wheel for CPython 3.10–3.13 on x86_64/aarch64 |
| `common/postinst.sh` | the shared installer: service user, offline venv, `app.env`, systemd, setup wizard (same behaviour as the curl installer) |
| `deb/` | `control.in` template and `build.sh` |
| `rpm/` | spec file and `build.sh` |
| `arch/` | `PKGBUILD` and `build.sh` |
| `repo/` | repository metadata generation, signing and publishing |

## Offline wheels

The packages bundle Python wheels for every supported interpreter, so
`apt install local-chat` does **not** download from PyPI:

```bash
bash packaging/common/wheels.sh /tmp/wheels "3.10 3.11 3.12 3.13" \
    "manylinux2014_x86_64 manylinux2014_aarch64"
```

At install time `postinst.sh` runs `pip install --no-index --find-links`
and pip picks the wheels that match the host interpreter.

## Build a .deb

```bash
ARCH=amd64 WHEELS_DIR=/tmp/wheels OUT_DIR=/tmp/dist \
    bash packaging/deb/build.sh
```

## Install layout

| Path | Content |
|---|---|
| `/opt/local-chat-server` | application, migrations, scripts, `setup/`, `config/`, `data/` |
| `/opt/local-chat-server/.venv` | virtualenv created by the package (regenerated on upgrade) |
| `/usr/share/local-chat-server/wheels` | bundled wheels |
| `/usr/share/local-chat-server/postinst.sh` | shared install routine |
| `/usr/lib/systemd/system/local-chat-server.service` | service unit |
| `/usr/bin/lc` | management CLI (symlink) |

User data (`data/`) and configuration (`config/app.env`) are not owned by
the packages: upgrades keep them, removal keeps them, `purge` removes the
configuration and keeps the data.
