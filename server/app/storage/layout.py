from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_STORAGE_DIRS: tuple[str, ...] = (
    "sqlite",
    "media",
    "avatars",
    "uploads",
    "rfid",
    "backups",
    "logs",
    "incidents",
)


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StorageLayoutState:
    root: Path
    created_directories: tuple[Path, ...]
    all_directories: tuple[Path, ...]


def ensure_storage_layout(storage_root: str | Path) -> StorageLayoutState:
    root = Path(storage_root)
    if not root.is_absolute():
        root = (_server_root() / root).resolve()

    created: list[Path] = []
    all_directories: list[Path] = []

    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        created.append(root)

    for relative_name in REQUIRED_STORAGE_DIRS:
        path = root / relative_name
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
        all_directories.append(path)

    return StorageLayoutState(
        root=root,
        created_directories=tuple(created),
        all_directories=tuple(all_directories),
    )
