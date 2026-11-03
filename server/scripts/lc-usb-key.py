#!/usr/bin/env python3
"""Physical USB key gate for root SSH.

The USB stick is an enrolled physical token.  While an enrolled stick is
inserted, the udev/systemd gate starts the local SSH daemon.  When the stick is
removed, the daemon is stopped again.  Root authentication itself remains
normal OpenSSH public-key authentication using keys listed in
``/root/.ssh/authorized_keys``.

Only the root account can run this tool.  The web application has no route to
it: it is installed under ``/opt/local-chat-server/scripts`` and exposed as
``/usr/local/sbin/lc-usb-key`` for the udev service.

The module is deliberately stdlib-only so it can run before the app virtualenv
exists (installer/early boot).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # Unix only; unit tests can import this module on other platforms.
    import pwd
except ImportError:  # pragma: no cover - Windows test host
    pwd = None  # type: ignore[assignment]


STATE_VERSION = 1
MARKER_NAME = "LC_ROOT_KEY.json"
KEY_DIR = "lc-root-key"
README_NAME = "LC_ROOT_KEY_README.txt"
MAX_USB_KEYS = 8
MAX_SSH_KEYS = 32

STATE_DIR = Path(os.environ.get("LC_ROOT_KEY_STATE_DIR", "/etc/lc-root-key"))
RUN_DIR = Path(os.environ.get("LC_ROOT_KEY_RUN_DIR", "/run/lc-root-key"))
AUTHORIZED_KEYS = Path(
    os.environ.get("LC_ROOT_KEY_AUTHORIZED_KEYS", "/root/.ssh/authorized_keys")
)
UDEV_RULES = Path(
    os.environ.get(
        "LC_ROOT_KEY_UDEV_RULES", "/etc/udev/rules.d/70-lc-usb-key.rules"
    )
)
SYSTEMD_UNIT = Path(
    os.environ.get(
        "LC_ROOT_KEY_SYSTEMD_UNIT",
        "/etc/systemd/system/lc-usb-key@.service",
    )
)
SSHD_DROPIN = Path(
    os.environ.get(
        "LC_ROOT_KEY_SSHD_DROPIN",
        "/etc/ssh/sshd_config.d/10-lc-root-key.conf",
    )
)
SSH_UNIT_OVERRIDE = os.environ.get("LC_ROOT_KEY_SSH_UNIT", "")
SSH_SOCKET_OVERRIDE = os.environ.get("LC_ROOT_KEY_SSH_SOCKET", "")
SKIP_SSH = os.environ.get("LC_ROOT_KEY_SKIP_SSH", "") in ("1", "yes", "true")
FS_TYPES = {"vfat", "exfat", "ext2", "ext3", "ext4", "ntfs", "ntfs3", "msdos"}

KEY_TYPE_RE = re.compile(
    r"^(?:ssh-(?:ed25519|rsa|dss)|ecdsa-sha2-[^ ]+|"
    r"sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com)$"
)
UUID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ToolError(RuntimeError):
    """Expected, user-facing failure."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def token_hash(token: str) -> str:
    return sha256_hex(token)


def key_fingerprint(blob: bytes) -> str:
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii")
    return "SHA256:" + digest.rstrip("=")


def parse_key_line(line: str) -> dict[str, str] | None:
    """Parse one OpenSSH public-key line, including lines with key options."""
    text = (line or "").strip()
    if not text or text.startswith("#"):
        return None
    parts = text.split()
    key_index = next(
        (index for index, part in enumerate(parts) if KEY_TYPE_RE.match(part)),
        None,
    )
    if key_index is None or key_index + 1 >= len(parts):
        return None
    key_type = parts[key_index]
    encoded = parts[key_index + 1]
    try:
        blob = base64.b64decode(encoded, validate=True)
    except Exception:
        return None
    if not blob:
        return None
    canonical = f"{key_type} {encoded}"
    return {
        "type": key_type,
        "blob": encoded,
        "canonical": canonical,
        "fingerprint": key_fingerprint(blob),
        "comment": " ".join(parts[key_index + 2 :]).strip(),
        "options": " ".join(parts[:key_index]).strip(),
        "id": sha256_hex(canonical)[:16],
    }


def _truthy(value: Any) -> bool:
    return value is True or value in (1, "1", "true", "True", "yes", "on")


def run(
    arguments: list[str],
    *,
    check: bool = True,
    timeout: int = 60,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"required command not found: {arguments[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"command timed out: {arguments[0]}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-500:]
        raise ToolError(
            f"command failed: {' '.join(arguments[:3])} "
            f"(exit {result.returncode}){': ' + detail if detail else ''}"
        )
    return result


def _chown_root(path: Path) -> None:
    if os.name == "nt" or pwd is None:
        return
    try:
        info = pwd.getpwnam("root")
        os.chown(path, info.pw_uid, info.pw_gid)
    except (KeyError, OSError):
        pass


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        _chown_root(temporary_path)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    _chown_root(path)


def load_authorized_keys() -> list[str]:
    if not AUTHORIZED_KEYS.exists():
        return []
    try:
        return AUTHORIZED_KEYS.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ToolError(f"cannot read {AUTHORIZED_KEYS}: {exc}") from exc


def write_authorized_keys(lines: list[str]) -> None:
    ensure_private_dir(AUTHORIZED_KEYS.parent)
    text = "\n".join(lines).rstrip("\n")
    if text:
        text += "\n"
    atomic_write(AUTHORIZED_KEYS, text, 0o600)


def authorized_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(load_authorized_keys()):
        parsed = parse_key_line(line)
        if parsed:
            parsed["line"] = line_number
            entries.append(parsed)
    return entries


def add_public_keys(public_lines: list[str], source: str = "usb") -> list[dict[str, str]]:
    """Add unique public keys to root's authorized_keys, preserving order."""
    lines = load_authorized_keys()
    existing = {
        entry["canonical"]
        for entry in (parse_key_line(line) for line in lines)
        if entry is not None
    }
    added: list[dict[str, str]] = []
    for raw in public_lines:
        parsed = parse_key_line(raw)
        if parsed is None:
            continue
        if parsed["canonical"] in existing:
            continue
        if len(existing) >= MAX_SSH_KEYS:
            raise ToolError(f"too many root SSH keys (max {MAX_SSH_KEYS})")
        lines.append(raw.strip())
        existing.add(parsed["canonical"])
        added.append(parsed)
    if added:
        write_authorized_keys(lines)
    return added


def remove_authorized_key(selector: str) -> dict[str, Any]:
    entries = authorized_entries()
    if not entries:
        raise ToolError("there are no root SSH public keys")
    chosen: dict[str, Any] | None = None
    selector = selector.strip()
    if selector.isdigit():
        number = int(selector)
        if 1 <= number <= len(entries):
            chosen = entries[number - 1]
    else:
        needle = selector.removeprefix("SHA256:").strip()
        for entry in entries:
            if (
                entry["fingerprint"].removeprefix("SHA256:") == needle
                or entry["id"] == selector
                or entry["canonical"] == selector
            ):
                chosen = entry
                break
    if chosen is None:
        raise ToolError(f"root SSH key not found: {selector}")
    lines = load_authorized_keys()
    del lines[chosen["line"]]
    write_authorized_keys(lines)
    return chosen


def state_path() -> Path:
    return STATE_DIR / "state.json"


def default_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "ssh_gate": False, "usb_keys": []}


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ToolError(f"invalid state file: {path}")
    if data.get("version") != STATE_VERSION:
        raise ToolError(f"unsupported state version in {path}")
    if not isinstance(data.get("usb_keys"), list):
        data["usb_keys"] = []
    return data


def save_state(state: dict[str, Any]) -> None:
    ensure_private_dir(STATE_DIR)
    state["version"] = STATE_VERSION
    atomic_write(
        state_path(),
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        0o600,
    )


def _find_token(
    state: dict[str, Any], uuid: str, serial: str = ""
) -> dict[str, Any] | None:
    for item in state.get("usb_keys", []):
        if not isinstance(item, dict) or item.get("uuid") != uuid:
            continue
        if serial and item.get("serial") and item["serial"] != serial:
            continue
        return item
    return None


def add_usb_token(
    state: dict[str, Any],
    token: str,
    *,
    uuid: str,
    serial: str = "",
    label: str = "",
    fstype: str = "",
) -> dict[str, Any]:
    if not uuid or not UUID_RE.match(uuid):
        raise ToolError("the USB partition has no usable filesystem UUID")
    existing = _find_token(state, uuid)
    if existing is None and len(state.get("usb_keys", [])) >= MAX_USB_KEYS:
        raise ToolError(f"too many USB keys (max {MAX_USB_KEYS})")
    entry = {
        "id": sha256_hex(f"{uuid}:{token}")[:16],
        "uuid": uuid,
        "serial": serial,
        "label": label,
        "fstype": fstype,
        "token_sha256": token_hash(token),
        "enrolled_at": now_iso(),
    }
    if existing is not None:
        entry["enrolled_at"] = existing.get("enrolled_at", entry["enrolled_at"])
        state["usb_keys"] = [
            item for item in state.get("usb_keys", []) if item is not existing
        ]
    state.setdefault("usb_keys", []).append(entry)
    state["ssh_gate"] = True
    return entry


def remove_usb_token(state: dict[str, Any], selector: str) -> dict[str, Any]:
    selector = selector.strip()
    for item in list(state.get("usb_keys", [])):
        if selector in (
            str(item.get("id", "")),
            str(item.get("uuid", "")),
            str(item.get("label", "")),
        ):
            state["usb_keys"].remove(item)
            if not state["usb_keys"]:
                state["ssh_gate"] = False
            save_state(state)
            return item
    raise ToolError(f"USB key not found: {selector}")


def render_udev_rules(state: dict[str, Any]) -> str:
    lines = [
        "# Managed by lc keys.  Do not edit by hand.",
        "# Root SSH is available only while one of these USB partitions is present.",
    ]
    for item in state.get("usb_keys", []):
        uuid = str(item.get("uuid", "")).strip()
        if not uuid or not UUID_RE.match(uuid):
            continue
        lines.append(
            'ACTION=="add", SUBSYSTEM=="block", '
            f'ENV{{ID_FS_UUID}}=="{uuid}", TAG+="systemd", '
            'ENV{SYSTEMD_WANTS}="lc-usb-key@%k.service"'
        )
    return "\n".join(lines) + "\n"


SSH_GATE_UNIT = """[Unit]
Description=Local Chat USB root SSH gate (%i)
BindsTo=dev-%i.device
After=dev-%i.device

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=45
TimeoutStopSec=30
ExecStart=/usr/local/sbin/lc-usb-key open /dev/%i
ExecStop=/usr/local/sbin/lc-usb-key close /dev/%i
"""

SSHD_DROPIN_TEXT = """# Managed by lc keys.
# Root may log in with an enrolled public key; passwords are not accepted for
# root.  The SSH daemon itself is started by the USB-key gate.
PermitRootLogin prohibit-password
PubkeyAuthentication yes
"""


def systemd_available() -> bool:
    return Path("/run/systemd/system").is_dir() and shutil.which("systemctl") is not None


def ssh_service_unit() -> str:
    if SSH_UNIT_OVERRIDE:
        return SSH_UNIT_OVERRIDE
    if not systemd_available():
        return "ssh.service"
    for candidate in ("ssh.service", "sshd.service"):
        result = run(["systemctl", "cat", candidate], check=False)
        if result.returncode == 0:
            return candidate
    return "ssh.service"


def ssh_socket_unit() -> str:
    if SSH_SOCKET_OVERRIDE:
        return SSH_SOCKET_OVERRIDE
    if not systemd_available():
        return "ssh.socket"
    result = run(["systemctl", "cat", "ssh.socket"], check=False)
    return "ssh.socket" if result.returncode == 0 else ""


def disable_ssh() -> None:
    if SKIP_SSH or not systemd_available():
        return
    socket = ssh_socket_unit()
    service = ssh_service_unit()
    if socket:
        run(["systemctl", "disable", "--now", socket], check=False)
    run(["systemctl", "disable", "--now", service], check=False)
    run(["systemctl", "reset-failed", service], check=False)


def start_ssh() -> None:
    if SKIP_SSH:
        return
    if not systemd_available():
        raise ToolError("systemd is required to start the SSH gate")
    service = ssh_service_unit()
    run(["systemctl", "reset-failed", service], check=False)
    run(["systemctl", "start", service])
    active = run(["systemctl", "is-active", service], check=False)
    if active.stdout.strip() != "active":
        raise ToolError(f"{service} did not start")


def ssh_active() -> bool:
    if not systemd_available():
        return False
    result = run(["systemctl", "is-active", ssh_service_unit()], check=False)
    return result.stdout.strip() == "active"


def install_gate_files(state: dict[str, Any]) -> None:
    ensure_private_dir(STATE_DIR)
    atomic_write(SYSTEMD_UNIT, SSH_GATE_UNIT, 0o644)
    if state.get("usb_keys"):
        atomic_write(UDEV_RULES, render_udev_rules(state), 0o644)
    else:
        UDEV_RULES.unlink(missing_ok=True)
    atomic_write(SSHD_DROPIN, SSHD_DROPIN_TEXT, 0o644)
    if systemd_available():
        run(["systemctl", "daemon-reload"], check=False)
    if shutil.which("udevadm"):
        run(["udevadm", "control", "--reload-rules"], check=False)
    if shutil.which("sshd"):
        run(["sshd", "-t"], check=True)


def lsblk_devices() -> list[dict[str, Any]]:
    if not shutil.which("lsblk"):
        raise ToolError("lsblk is required (util-linux)")
    result = run(
        [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,PATH,TYPE,RM,RO,FSTYPE,LABEL,UUID,SERIAL,TRAN,MOUNTPOINT,SIZE,MODEL",
        ]
    )
    try:
        payload = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise ToolError(f"cannot parse lsblk output: {exc}") from exc
    devices: list[dict[str, Any]] = []

    def walk(
        node: dict[str, Any],
        inherited_tran: str = "",
        inherited_rm: bool = False,
        inherited_serial: str = "",
    ) -> None:
        tran = (node.get("tran") or inherited_tran or "").lower()
        removable = _truthy(node.get("rm")) or inherited_rm
        serial = str(node.get("serial") or inherited_serial or "")
        if node.get("type") in ("part", "disk"):
            fstype = str(node.get("fstype") or "").lower()
            path = str(node.get("path") or "")
            uuid = str(node.get("uuid") or "")
            mountpoint = str(node.get("mountpoint") or "")
            if (
                path
                and fstype in FS_TYPES
                and uuid
                and (tran == "usb" or removable)
                and mountpoint != "/"
            ):
                devices.append(
                    {
                        "name": str(node.get("name") or ""),
                        "path": path,
                        "fstype": fstype,
                        "label": str(node.get("label") or ""),
                        "uuid": uuid,
                        "serial": serial,
                        "tran": tran,
                        "removable": removable,
                        "size": str(node.get("size") or ""),
                        "model": str(node.get("model") or ""),
                        "mountpoint": mountpoint,
                    }
                )
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, tran, removable, serial)

    for device in payload.get("blockdevices", []):
        if isinstance(device, dict):
            walk(device)
    return sorted(devices, key=lambda item: item["path"])


def device_info(path: str) -> dict[str, Any]:
    wanted = str(Path(path))
    for item in lsblk_devices():
        if item["path"] == wanted or Path(item["path"]).resolve() == Path(wanted).resolve():
            return item
    raise ToolError(f"not a supported USB partition: {path}")


class MountedUSB:
    def __init__(self, entry: dict[str, Any], *, rw: bool) -> None:
        self.entry = entry
        self.rw = rw
        self.mountpoint: Path | None = None
        self.source: Path | None = None

    def __enter__(self) -> Path:
        source = self.entry.get("source")
        if source:
            self.source = Path(str(source))
            if not self.source.is_dir():
                raise ToolError(f"USB source directory not found: {self.source}")
            return self.source
        ensure_private_dir(RUN_DIR)
        mountpoint = Path(tempfile.mkdtemp(prefix="usb-", dir=str(RUN_DIR)))
        options = "rw" if self.rw else "ro"
        options += ",nosuid,nodev,noexec"
        try:
            run(["mount", "-o", options, str(self.entry["path"]), str(mountpoint)])
        except Exception:
            mountpoint.rmdir()
            raise
        self.mountpoint = mountpoint
        return mountpoint

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.mountpoint is None:
            return
        run(["umount", str(self.mountpoint)], check=False)
        if self.mountpoint.exists():
            run(["umount", "-l", str(self.mountpoint)], check=False)
            try:
                self.mountpoint.rmdir()
            except OSError:
                pass


def read_marker(mountpoint: Path) -> dict[str, Any] | None:
    path = mountpoint / MARKER_NAME
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > 65536:
            raise ToolError("USB key marker is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"cannot read USB key marker: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ToolError("unsupported USB key marker")
    return data


def write_marker(
    mountpoint: Path,
    token: str,
    entry: dict[str, Any],
) -> None:
    payload = {
        "version": 1,
        "token": token,
        "uuid": entry.get("uuid", ""),
        "serial": entry.get("serial", ""),
        "label": entry.get("label", ""),
        "created_at": now_iso(),
    }
    atomic_write(mountpoint / MARKER_NAME, json.dumps(payload, indent=2) + "\n", 0o600)
    readme = (
        "Local Chat root USB key\n"
        "========================\n\n"
        "This USB stick is a physical key for root SSH on the Raspberry Pi.\n"
        "Keep it safe: anyone who has it and a matching private SSH key can\n"
        "open root SSH while it is inserted.\n\n"
        "Insert it into the Raspberry Pi to start the SSH daemon; remove it to\n"
        "stop the SSH daemon. Existing SSH sessions may stay connected until\n"
        "they are closed.\n\n"
        "Public keys were imported from *.pub files into /root/.ssh/authorized_keys.\n"
        "If this USB contains lc-root-key/id_ed25519, copy that private key to\n"
        "your computer before relying on it and keep a secure backup.\n\n"
        "Manage keys on the Pi from a local console/root SSH session:\n"
        "  sudo lc keys\n"
    )
    atomic_write(mountpoint / README_NAME, readme, 0o644)
    key_dir = mountpoint / KEY_DIR
    if key_dir.is_dir():
        atomic_write(key_dir / "README.txt", readme, 0o644)


def read_public_keys(mountpoint: Path) -> list[str]:
    candidates: list[Path] = []
    for pattern in ("*.pub", f"{KEY_DIR}/*.pub"):
        candidates.extend(sorted(mountpoint.glob(pattern))[:MAX_SSH_KEYS])
    key_dir = mountpoint / KEY_DIR
    for name in ("authorized_keys", "authorized_keys.pub"):
        path = key_dir / name
        if path.is_file():
            candidates.append(path)
    lines: list[str] = []
    for path in candidates:
        if path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if parse_key_line(line):
                lines.append(line.strip())
    return lines[:MAX_SSH_KEYS]


def generate_key_on_usb(mountpoint: Path, label: str) -> tuple[str, str]:
    if not shutil.which("ssh-keygen"):
        raise ToolError("ssh-keygen is required to create a new USB key")
    key_dir = mountpoint / KEY_DIR
    ensure_private_dir(key_dir)
    stem = "id_ed25519"
    private = key_dir / stem
    suffix = 2
    while private.exists():
        private = key_dir / f"{stem}_{suffix}"
        suffix += 1
    comment = f"lc-usb-root-{label or 'key'} {now_iso()}"
    run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            comment,
            "-f",
            str(private),
        ]
    )
    try:
        private.chmod(0o600)
    except OSError:
        pass
    public = Path(str(private) + ".pub")
    if not public.is_file():
        raise ToolError("ssh-keygen did not create a public key")
    return public.read_text(encoding="utf-8").strip(), str(private)


def validate_marker(
    state: dict[str, Any],
    entry: dict[str, Any],
    marker: dict[str, Any],
) -> dict[str, Any]:
    token = str(marker.get("token") or "")
    uuid = str(marker.get("uuid") or "")
    if not token or not uuid:
        raise ToolError("USB key marker is incomplete")
    if entry.get("uuid") and uuid != entry["uuid"]:
        raise ToolError("USB key UUID does not match the enrolled key")
    marker_serial = str(marker.get("serial") or "")
    if entry.get("serial") and marker_serial and marker_serial != entry["serial"]:
        raise ToolError("USB key serial does not match the enrolled key")
    enrolled = _find_token(state, uuid, marker_serial)
    if enrolled is None:
        raise ToolError("this USB key is not enrolled")
    if not hmac.compare_digest(
        str(enrolled.get("token_sha256", "")), token_hash(token)
    ):
        raise ToolError("USB key token is invalid")
    return enrolled


def open_usb(path: str) -> None:
    if SKIP_SSH:
        return
    entry = device_info(path)
    state = load_state()
    with MountedUSB(entry, rw=False) as mountpoint:
        marker = read_marker(mountpoint)
        if marker is None:
            raise ToolError("this USB stick is not an enrolled root key")
        enrolled = validate_marker(state, entry, marker)
    start_ssh()
    ensure_private_dir(RUN_DIR)
    atomic_write(
        RUN_DIR / "active.json",
        json.dumps(
            {
                "usb_id": enrolled.get("id"),
                "uuid": entry.get("uuid"),
                "opened_at": now_iso(),
            },
            indent=2,
        )
        + "\n",
        0o600,
    )
    print(f"SSH enabled by USB key {enrolled.get('id')}")


def _other_enrolled_key_present(state: dict[str, Any], exclude_uuid: str) -> bool:
    wanted = {
        str(item.get("uuid"))
        for item in state.get("usb_keys", [])
        if str(item.get("uuid")) != exclude_uuid
    }
    if not wanted:
        return False
    for entry in lsblk_devices():
        if entry["uuid"] not in wanted:
            continue
        try:
            with MountedUSB(entry, rw=False) as mountpoint:
                marker = read_marker(mountpoint)
                if marker is not None:
                    validate_marker(state, entry, marker)
                    return True
        except ToolError:
            continue
    return False


def close_usb(device: str = "") -> None:
    (RUN_DIR / "active.json").unlink(missing_ok=True)
    if SKIP_SSH:
        return
    try:
        state = load_state()
        current_uuid = ""
        if device:
            try:
                current_uuid = str(device_info(device).get("uuid", ""))
            except ToolError:
                current_uuid = ""
        if current_uuid:
            still_present = _other_enrolled_key_present(state, current_uuid)
        else:
            # The kernel name may already be gone after a remove event.  Check
            # every enrolled token; if any other one is present, keep SSH.
            still_present = any(
                _other_enrolled_key_present(state, str(item.get("uuid", "")))
                for item in state.get("usb_keys", [])
            )
        if still_present:
            print("Another enrolled USB key is still present; SSH left active")
            return
    except ToolError:
        pass
    disable_ssh()
    print("SSH disabled: no enrolled USB root key is present")


def enroll(
    *,
    device: str = "",
    source: str = "",
    uuid: str = "",
    serial: str = "",
    label: str = "",
    generate: bool = False,
    force: bool = False,
    activate: bool = True,
    interactive: bool = False,
    wait_seconds: int = 90,
) -> dict[str, Any]:
    require_root()
    if source:
        source_path = Path(source)
        if not source_path.is_dir():
            raise ToolError(f"source directory not found: {source}")
        if not uuid:
            raise ToolError("--uuid is required with --source")
        entry: dict[str, Any] = {
            "path": str(source_path),
            "source": str(source_path),
            "uuid": uuid,
            "serial": serial,
            "label": label or source_path.name,
            "fstype": "dir",
        }
    else:
        entry = choose_device(device, interactive=interactive, wait_seconds=wait_seconds)

    if source:
        # A directory is useful for tests and for enrolling an already-mounted
        # medium; it has no udev device to start the gate.
        activate = False
    state = load_state()
    existing = _find_token(state, str(entry.get("uuid", "")), str(entry.get("serial", "")))
    with MountedUSB(entry, rw=True) as mountpoint:
        marker = read_marker(mountpoint)
        token = ""
        if marker is not None:
            candidate = str(marker.get("token") or "")
            if candidate and existing is not None:
                if hmac.compare_digest(
                    str(existing.get("token_sha256", "")), token_hash(candidate)
                ):
                    token = candidate
            if not token and not force:
                raise ToolError(
                    "this USB stick already has a marker; use a different stick "
                    "or pass --force to re-enroll it"
                )
        if not token:
            token = secrets.token_hex(32)
        public_lines = read_public_keys(mountpoint)
        generated_private = ""
        if generate or not public_lines:
            should_generate = generate
            if not public_lines and not should_generate and interactive:
                should_generate = ask_yes_no(
                    "No *.pub key was found on the USB stick.\n\n"
                    "Create a new ed25519 key on it now?\n"
                    "The private key will stay on the USB stick."
                )
            if should_generate:
                public_line, generated_private = generate_key_on_usb(
                    mountpoint, label or str(entry.get("label", ""))
                )
                public_lines.append(public_line)
        if not public_lines:
            raise ToolError(
                "the USB stick has no public key (*.pub). Put a key there "
                "or run 'sudo lc keys new' to create one."
            )
        write_marker(mountpoint, token, entry)
        added = add_public_keys(public_lines, source="usb")
        if not added:
            # Still refresh ownership/permissions of an existing file.
            write_authorized_keys(load_authorized_keys())
        usb_entry = add_usb_token(
            state,
            token,
            uuid=str(entry.get("uuid", "")),
            serial=str(entry.get("serial", "")),
            label=str(entry.get("label", "")),
            fstype=str(entry.get("fstype", "")),
        )
        save_state(state)

    install_gate_files(state)
    if activate:
        disable_ssh()
        try:
            open_usb(str(entry.get("path", "")))
            active_note = "SSH is open while this USB key is inserted"
        except ToolError as exc:
            active_note = f"key saved, but activation failed: {exc}"
    else:
        active_note = "activation skipped (--no-activate)"
    keys_text = ", ".join(
        f"{item['fingerprint']} ({item['comment'] or 'no comment'})"
        for item in added
    ) or "no new keys (already present)"
    print("USB root key enrolled")
    print(f"  USB:    {entry.get('path')} ({entry.get('label') or 'no label'})")
    print(f"  token:  {usb_entry['id']}")
    print(f"  keys:   {keys_text}")
    if generated_private:
        print(f"  new private key on USB: {generated_private}")
        print("  Copy it to your computer before relying on it; keep a backup.")
    print(f"  state:  {state_path()}")
    print(f"  {active_note}")
    return {"entry": entry, "usb": usb_entry, "added": added}


def choose_device(
    explicit: str = "",
    *,
    interactive: bool,
    wait_seconds: int = 90,
) -> dict[str, Any]:
    if explicit:
        return device_info(explicit)
    deadline = time.monotonic() + max(0, wait_seconds)
    while True:
        candidates = lsblk_devices()
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            if not interactive:
                names = ", ".join(item["path"] for item in candidates)
                raise ToolError(
                    "more than one USB partition found; choose one with --device: "
                    + names
                )
            return choose_from_menu(candidates)
        if not interactive or time.monotonic() >= deadline:
            raise ToolError("no USB partition found (insert the key and retry)")
        print("Insert the USB key to enroll it, then press Enter...", file=sys.stderr)
        try:
            read_tty_line()
        except EOFError:
            pass
        time.sleep(1)


def choose_from_menu(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not tty_available():
        names = ", ".join(item["path"] for item in candidates)
        raise ToolError(
            "more than one USB partition found; choose one with --device: "
            + names
        )
    if shutil.which("whiptail"):
        args = [
            "whiptail",
            "--title",
            "USB root key",
            "--menu",
            "Choose the USB partition that should become the physical root key:",
            "20",
            "86",
            str(len(candidates)),
        ]
        for item in candidates:
            label_text = (
                f"{item['path']}  {item.get('label') or item.get('uuid')}  "
                f"{item.get('size') or ''}"
            )
            args.extend([item["path"], label_text])
        chosen = run_whiptail(args)
        if chosen:
            return device_info(chosen)
    print("USB partitions:", file=sys.stderr)
    for index, item in enumerate(candidates, 1):
        print(
            f"  {index}. {item['path']}  "
            f"{item.get('label') or item.get('uuid')}  {item.get('size') or ''}",
            file=sys.stderr,
        )
    raw = read_tty_line("Number [1]: ").strip() or "1"
    try:
        return candidates[int(raw) - 1]
    except (ValueError, IndexError) as exc:
        raise ToolError("invalid USB selection") from exc


def remove_all_gate() -> None:
    if STATE_DIR.exists():
        state = load_state()
        state["usb_keys"] = []
        state["ssh_gate"] = False
        save_state(state)
    UDEV_RULES.unlink(missing_ok=True)
    if shutil.which("udevadm"):
        run(["udevadm", "control", "--reload-rules"], check=False)
    disable_ssh()


def show_keys() -> None:
    entries = authorized_entries()
    if not entries:
        print("Root SSH keys: none")
        return
    print(f"Root SSH keys ({len(entries)}):")
    for index, entry in enumerate(entries, 1):
        print(
            f"  {index}. {entry['type']} {entry['fingerprint']} "
            f"{entry['comment'] or '(no comment)'}"
        )


def show_usb_keys() -> None:
    state = load_state()
    entries = state.get("usb_keys", [])
    if not entries:
        print("USB root keys: none")
        return
    print(f"USB root keys ({len(entries)}):")
    for index, entry in enumerate(entries, 1):
        print(
            f"  {index}. {entry.get('id', '?')}  UUID={entry.get('uuid', '?')}  "
            f"{entry.get('label') or '(no label)'}"
        )


def show_status() -> None:
    state = load_state()
    keys = authorized_entries()
    print("Root USB key gate")
    print(f"  state:       {state_path()}")
    print(f"  configured:  {'yes' if state.get('ssh_gate') else 'no'}")
    print(f"  USB keys:    {len(state.get('usb_keys', []))}")
    print(f"  SSH keys:    {len(keys)}")
    print(f"  udev rule:   {'present' if UDEV_RULES.exists() else 'absent'}")
    print(f"  SSH daemon:  {'active' if ssh_active() else 'inactive'}")
    if not state.get("usb_keys"):
        print("  next:        sudo lc keys  (add a USB key)")


class UI:
    def __init__(self) -> None:
        self.whiptail = bool(shutil.which("whiptail")) and tty_available()

    def menu(self, title: str, text: str, items: list[tuple[str, str]]) -> str | None:
        if not items:
            return None
        if self.whiptail:
            args = [
                "whiptail",
                "--title",
                title,
                "--menu",
                text,
                "22",
                "86",
                str(len(items)),
            ]
            for value, label in items:
                args.extend([value, label])
            return run_whiptail(args)
        print(f"\n{title}\n{text}\n")
        for index, (value, label) in enumerate(items, 1):
            print(f"  {index}. {label}  [{value}]")
        raw = read_tty_line("Choice: ").strip()
        try:
            return items[int(raw) - 1][0]
        except (ValueError, IndexError):
            return None

    def msg(self, title: str, text: str) -> None:
        if self.whiptail:
            run_whiptail(
                ["whiptail", "--title", title, "--msgbox", text, "18", "86"]
            )
        else:
            print(f"\n{title}\n{text}\n")

    def yes_no(self, title: str, text: str) -> bool:
        if self.whiptail:
            result = run_whiptail(
                ["whiptail", "--title", title, "--yesno", text, "12", "80"]
            )
            return result is not None
        answer = read_tty_line(f"\n{title}\n{text}\n[y/N]: ").strip().lower()
        return answer in ("y", "yes")

    def text(self, title: str, text: str, default: str = "") -> str:
        if self.whiptail:
            result = run_whiptail(
                [
                    "whiptail",
                    "--title",
                    title,
                    "--inputbox",
                    text,
                    "12",
                    "86",
                    default,
                ]
            )
            return result or ""
        return read_tty_line(f"\n{title}\n{text}\n[{default}]: ").strip() or default


def manager() -> None:
    require_root()
    if not tty_available():
        raise ToolError("the key manager needs an interactive terminal")
    ui = UI()
    print()
    show_keys()
    print()
    show_usb_keys()
    while True:
        choice = ui.menu(
            "Local Chat - root keys",
            "Root SSH is available only while an enrolled USB key is inserted.",
            [
                ("list", "Show root SSH public keys"),
                ("add", "Add key(s) from a USB stick"),
                ("new", "Create a new key on a USB stick"),
                ("remove", "Remove a root SSH key"),
                ("usb", "Show enrolled USB physical keys"),
                ("usb-remove", "Remove a USB physical key"),
                ("status", "Show SSH gate status"),
                ("exit", "Exit"),
            ],
        )
        if not choice or choice == "exit":
            return
        try:
            if choice == "list":
                print()
                show_keys()
                continue
            if choice == "add":
                enroll(interactive=True)
                continue
            if choice == "new":
                enroll(interactive=True, generate=True)
                continue
            if choice == "remove":
                entries = authorized_entries()
                if not entries:
                    ui.msg("Root keys", "There are no root SSH public keys.")
                    continue
                selected = ui.menu(
                    "Remove root SSH key",
                    "Choose the public key to remove from /root/.ssh/authorized_keys.",
                    [
                        (str(index), f"{entry['fingerprint']} {entry['comment']}")
                        for index, entry in enumerate(entries, 1)
                    ],
                )
                if not selected:
                    continue
                removed = remove_authorized_key(selected)
                ui.msg(
                    "Root key removed",
                    f"Removed {removed['fingerprint']} "
                    f"({removed['comment'] or 'no comment'}).",
                )
                continue
            if choice == "usb":
                print()
                show_usb_keys()
                continue
            if choice == "usb-remove":
                state = load_state()
                entries = state.get("usb_keys", [])
                if not entries:
                    ui.msg("USB keys", "There are no enrolled USB keys.")
                    continue
                selected = ui.menu(
                    "Remove USB physical key",
                    "The SSH gate stops when the last physical key is removed.",
                    [
                        (
                            str(entry.get("id")),
                            f"{entry.get('id')}  {entry.get('uuid')}  "
                            f"{entry.get('label') or ''}",
                        )
                        for entry in entries
                    ],
                )
                if not selected:
                    continue
                if not ui.yes_no(
                    "Remove USB key",
                    "Remove this physical USB key?\n"
                    "Root SSH will stay closed until another enrolled key is inserted.",
                ):
                    continue
                removed = remove_usb_token(state, selected)
                install_gate_files(state)
                if not state.get("usb_keys"):
                    disable_ssh()
                ui.msg("USB key removed", f"Removed {removed.get('id')}.")
                continue
            if choice == "status":
                print()
                show_status()
                continue
        except ToolError as exc:
            ui.msg("Error", str(exc))


def read_tty_line(prompt: str = "") -> str:
    if prompt:
        print(prompt, end="", flush=True)
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty:
            line = tty.readline()
    except OSError:
        line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\n")


def tty_available() -> bool:
    try:
        with open("/dev/tty", "r"):
            return True
    except OSError:
        return False


def run_whiptail(args: list[str]) -> str | None:
    if not shutil.which("whiptail"):
        return None
    try:
        with open("/dev/tty", "r+", encoding="utf-8", errors="replace") as tty:
            result = subprocess.run(
                [args[0], "--output-fd", "1", *args[1:]],
                stdin=tty,
                stdout=subprocess.PIPE,
                stderr=tty,
                text=True,
                timeout=120,
            )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def ask_yes_no(text: str) -> bool:
    if tty_available():
        answer = read_tty_line(f"\n{text}\n[y/N]: ").strip().lower()
        return answer in ("y", "yes")
    return False


def require_root() -> None:
    if not hasattr(os, "geteuid"):
        return
    if os.geteuid() != 0:
        raise ToolError("root required: run with sudo")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lc-usb-key",
        description="Manage the physical USB key that opens root SSH.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("manager", help="interactive root-key manager")
    sub.add_parser("list", help="list root SSH public keys")
    sub.add_parser("usb-list", help="list enrolled USB physical keys")
    sub.add_parser("status", help="show the gate status")
    p = sub.add_parser("enroll", help="enroll a USB key and import public keys")
    p.add_argument("--device", default="", help="USB partition, e.g. /dev/sda1")
    p.add_argument("--source", default="", help="already-mounted directory (testing)")
    p.add_argument("--uuid", default="", help="UUID for --source")
    p.add_argument("--serial", default="")
    p.add_argument("--label", default="")
    p.add_argument("--generate", action="store_true", help="create a new ed25519 key on USB")
    p.add_argument("--force", action="store_true", help="re-enroll an existing marker")
    p.add_argument("--no-activate", action="store_true", help="do not touch sshd")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--wait", type=int, default=90)
    p = sub.add_parser("new", help="create a new root key on a USB stick")
    p.add_argument("--device", default="")
    p.add_argument("--source", default="")
    p.add_argument("--uuid", default="")
    p.add_argument("--serial", default="")
    p.add_argument("--label", default="")
    p.add_argument("--no-activate", action="store_true")
    p.add_argument("--wait", type=int, default=90)
    p = sub.add_parser("remove-key", help="remove one root SSH public key")
    p.add_argument("selector")
    p = sub.add_parser("remove-usb", help="remove one USB physical key")
    p.add_argument("selector")
    sub.add_parser("remove-all-gate", help="disable the USB gate and stop SSH")
    for name in ("open", "close"):
        p = sub.add_parser(name)
        p.add_argument("device", nargs="?", default="")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        if args.command != "manager":
            require_root()
        if args.command == "manager":
            manager()
        elif args.command == "list":
            show_keys()
        elif args.command == "usb-list":
            show_usb_keys()
        elif args.command == "status":
            show_status()
        elif args.command == "enroll":
            enroll(
                device=args.device,
                source=args.source,
                uuid=args.uuid,
                serial=args.serial,
                label=args.label,
                generate=args.generate,
                force=args.force,
                activate=not args.no_activate,
                interactive=args.interactive,
                wait_seconds=args.wait,
            )
        elif args.command == "new":
            enroll(
                device=args.device,
                source=args.source,
                uuid=args.uuid,
                serial=args.serial,
                label=args.label,
                generate=True,
                activate=not args.no_activate,
                interactive=True,
                wait_seconds=args.wait,
            )
        elif args.command == "remove-key":
            removed = remove_authorized_key(args.selector)
            print(f"Removed root SSH key {removed['fingerprint']} ({removed['comment']})")
        elif args.command == "remove-usb":
            state = load_state()
            removed = remove_usb_token(state, args.selector)
            install_gate_files(state)
            if not state.get("usb_keys"):
                disable_ssh()
            print(f"Removed USB key {removed.get('id')}")
        elif args.command == "remove-all-gate":
            remove_all_gate()
            print("USB root-key gate removed; SSH is closed")
        elif args.command == "open":
            open_usb(args.device)
        elif args.command == "close":
            close_usb(args.device)
        return 0
    except ToolError as exc:
        print(f"lc-usb-key: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("lc-usb-key: cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
