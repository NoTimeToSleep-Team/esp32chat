from __future__ import annotations

import os
import shutil
import stat
import tarfile
import tempfile
import time
from pathlib import Path


PACKAGE_NAME = "local-chat-pi-zero2w"
PACKAGE_VERSION = "0.1.0"
PACKAGE_REVISION = "1"
ARCH = "arm64"


def build_tar_gz(source_dir: Path, out_file: Path, include_roots: list[str] | None = None) -> None:
    with tarfile.open(out_file, "w:gz") as archive:
        roots = include_roots or [""]
        for root_name in roots:
            root = source_dir / root_name if root_name else source_dir
            if not root.exists():
                continue
            for item in sorted(root.rglob("*")):
                arcname = item.relative_to(source_dir)
                archive.add(item, arcname=str(arcname))


def write_ar_archive(out_file: Path, members: list[Path]) -> None:
    with out_file.open("wb") as handle:
        handle.write(b"!<arch>\n")
        for member in members:
            data = member.read_bytes()
            name = member.name.encode("ascii")
            if len(name) > 16:
                raise SystemExit(f"ar member name too long: {member.name}")
            header = (
                name.ljust(16, b" ")
                + str(int(time.time())).encode("ascii").ljust(12, b" ")
                + b"0".ljust(6, b" ")
                + b"0".ljust(6, b" ")
                + b"100644".ljust(8, b" ")
                + str(len(data)).encode("ascii").ljust(10, b" ")
                + b"`\n"
            )
            handle.write(header)
            handle.write(data)
            if len(data) % 2 == 1:
                handle.write(b"\n")


def write_text(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_tree_filtered(src: Path, dst: Path, *, exclude_dirs: set[str], exclude_files: set[str]) -> None:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in exclude_files or name.endswith((".pyc", ".pyo")):
                continue
            source_file = Path(root) / name
            shutil.copy2(source_file, target_dir / name)


def build_deb(root: Path, out_file: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pi-zero2w-deb-") as tmp:
        tmp_path = Path(tmp)
        pkg_root = tmp_path / "pkg"
        control_dir = pkg_root / "DEBIAN"
        app_root = pkg_root / "opt" / "local-chat-server"

        server_src = root
        wheelhouse_src = Path(os.environ.get("CZ_WHEELHOUSE", "")).expanduser()
        if not wheelhouse_src.is_dir():
            raise SystemExit("Set CZ_WHEELHOUSE to a directory with ARM64 Linux wheels before building the deb.")

        copy_tree_filtered(
            server_src,
            app_root,
            exclude_dirs={".git", ".venv", "venv", "__pycache__", ".pytest_cache", "data", "build", "dist"},
            exclude_files={"server.json"},
        )

        wheelhouse_dst = app_root / "wheelhouse"
        shutil.copytree(wheelhouse_src, wheelhouse_dst)

        control = f"""Package: {PACKAGE_NAME}
Version: {PACKAGE_VERSION}-{PACKAGE_REVISION}
Section: net
Priority: optional
Architecture: {ARCH}
Maintainer: NoTimeToSleep-Team
Depends: bash, curl, python3, python3-venv, python3-pip, nginx
Description: Local Chat server bundle for Raspberry Pi Zero 2 W
 Offline-installable FastAPI/nginx/systemd package for Raspberry Pi Zero 2 W.
"""
        write_text(control_dir / "control", control)

        postinst = """#!/bin/sh
set -e

APP_ROOT=/opt/local-chat-server
APP_USER=localchat
APP_GROUP=localchat
ENV_FILE=$APP_ROOT/config/app.env
VENV_PATH=$APP_ROOT/.venv
WHEELHOUSE=$APP_ROOT/wheelhouse
SERVICE_NAME=local-chat-server
SYSTEMD_DST=/etc/systemd/system/$SERVICE_NAME.service
NGINX_AVAIL=/etc/nginx/sites-available/$SERVICE_NAME.conf
NGINX_ENABLED=/etc/nginx/sites-enabled/$SERVICE_NAME.conf

if ! getent group "$APP_GROUP" >/dev/null; then
    groupadd --system "$APP_GROUP"
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --gid "$APP_GROUP" --home "$APP_ROOT" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_ROOT/data/sqlite" "$APP_ROOT/data/media" "$APP_ROOT/data/avatars" "$APP_ROOT/data/uploads" "$APP_ROOT/data/rfid" "$APP_ROOT/data/backups" "$APP_ROOT/data/logs" "$APP_ROOT/data/incidents"

if [ ! -f "$ENV_FILE" ]; then
    cp "$APP_ROOT/config/pi-zero2w.env.example" "$ENV_FILE"
fi

install -m 0644 "$APP_ROOT/systemd/$SERVICE_NAME.service" "$SYSTEMD_DST"
install -m 0644 "$APP_ROOT/config/nginx/local-chat-server.conf" "$NGINX_AVAIL"
ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"
rm -f /etc/nginx/sites-enabled/default || true

python3 -m venv "$VENV_PATH"
"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/pip" install --no-index --find-links "$WHEELHOUSE" fastapi uvicorn

chown -R "$APP_USER:$APP_GROUP" "$APP_ROOT"

nginx -t || true
systemctl daemon-reload || true
systemctl enable "$SERVICE_NAME" || true
systemctl restart "$SERVICE_NAME" || true
systemctl enable nginx || true
systemctl restart nginx || true

exit 0
"""
        write_text(control_dir / "postinst", postinst, executable=True)

        prerm = """#!/bin/sh
set -e
systemctl stop local-chat-server || true
systemctl disable local-chat-server || true
exit 0
"""
        write_text(control_dir / "prerm", prerm, executable=True)

        debian_binary = tmp_path / "debian-binary"
        debian_binary.write_text("2.0\n", encoding="ascii")

        control_tar = tmp_path / "control.tar.gz"
        data_tar = tmp_path / "data.tar.gz"
        build_tar_gz(control_dir, control_tar)
        build_tar_gz(pkg_root, data_tar, include_roots=["opt"])

        if out_file.exists():
            out_file.unlink()

        write_ar_archive(out_file, [debian_binary, control_tar, data_tar])


def main() -> None:
    root = Path(__file__).resolve().parent
    out_dir = root.parent / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{PACKAGE_NAME}_{PACKAGE_VERSION}-{PACKAGE_REVISION}_{ARCH}.deb"
    build_deb(root, out_file)
    print(out_file)


if __name__ == "__main__":
    main()
