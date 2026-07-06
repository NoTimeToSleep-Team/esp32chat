from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import tarfile
import time
from pathlib import Path


PACKAGE_NAME = "local-chat-cardputerzero"
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
    with tempfile.TemporaryDirectory(prefix="cz-deb-") as tmp:
        tmp_path = Path(tmp)
        pkg_root = tmp_path / "pkg"
        control_dir = pkg_root / "DEBIAN"
        app_root = pkg_root / "opt" / "local-chat-server"
        launcher_root = pkg_root / "usr" / "share" / "APPLaunch"
        launcher_app_dir = launcher_root / "apps" / "local-chat-portal-cz"
        launcher_bin_dir = launcher_root / "bin"
        launcher_desktop_dir = launcher_root / "applications"

        server_src = root / "server"
        card_src = root / "cardputerzero" / "apps" / "local_chat_portal"
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

        shutil.copytree(card_src, launcher_app_dir)
        launcher_exec = launcher_bin_dir / "local-chat-portal"
        launcher_exec.parent.mkdir(parents=True, exist_ok=True)
        launcher_exec.write_text(
            "#!/bin/sh\ncd /usr/share/APPLaunch/apps/local-chat-portal-cz\nexec ./launch_local_chat_portal.sh \"$@\"\n",
            encoding="utf-8",
            newline="\n",
        )
        launcher_exec.chmod(0o755)

        desktop_path = launcher_desktop_dir / "local-chat-portal-cz.desktop"
        write_text(
            desktop_path,
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Local Chat Mode Switch\n"
            "Exec=/usr/share/APPLaunch/bin/local-chat-portal\n"
            "Icon=/usr/share/APPLaunch/apps/local-chat-portal-cz/packaging/local-chat-portal.svg\n"
            "Terminal=false\n"
            "Categories=Network;Utility;\n",
        )

        control = f"""Package: {PACKAGE_NAME}
Version: {PACKAGE_VERSION}-{PACKAGE_REVISION}
Section: net
Priority: optional
Architecture: {ARCH}
Maintainer: NoTimeToSleep-Team
Depends: bash, curl, python3, python3-venv, python3-pip, xdg-utils
Description: Local Chat server and mode switch launcher for M5CardputerZero
 Single-package deployment for the Local Chat server and CardputerZero mode switch launcher.
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

if ! getent group "$APP_GROUP" >/dev/null; then
    groupadd --system "$APP_GROUP"
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --gid "$APP_GROUP" --home "$APP_ROOT" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_ROOT/data/sqlite" "$APP_ROOT/data/media" "$APP_ROOT/data/avatars" "$APP_ROOT/data/uploads" "$APP_ROOT/data/rfid" "$APP_ROOT/data/backups" "$APP_ROOT/data/logs" "$APP_ROOT/data/incidents"

if [ ! -f "$ENV_FILE" ]; then
    cp "$APP_ROOT/config/cardputerzero.env.example" "$ENV_FILE"
fi

install -m 0644 "$APP_ROOT/systemd/$SERVICE_NAME.service" "$SYSTEMD_DST"

python3 -m venv "$VENV_PATH"
"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/pip" install --no-index --find-links "$WHEELHOUSE" fastapi uvicorn

chown -R "$APP_USER:$APP_GROUP" "$APP_ROOT"
chmod 0755 /usr/share/APPLaunch/bin/local-chat-portal || true
chmod 0755 /usr/share/APPLaunch/apps/local-chat-portal-cz/launch_local_chat_portal.sh || true

systemctl daemon-reload || true
systemctl enable "$SERVICE_NAME" || true
systemctl restart "$SERVICE_NAME" || true

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
        build_tar_gz(pkg_root, data_tar, include_roots=["opt", "usr"])

        if out_file.exists():
            out_file.unlink()

        write_ar_archive(out_file, [debian_binary, control_tar, data_tar])


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{PACKAGE_NAME}_{PACKAGE_VERSION}-{PACKAGE_REVISION}_{ARCH}.deb"
    build_deb(root, out_file)
    print(out_file)


if __name__ == "__main__":
    main()
