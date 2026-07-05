from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.db.migrate import apply_sql_migrations
from app.storage import ensure_storage_layout


@dataclass(frozen=True)
class DataLayerState:
    database_path: Path
    storage_root: Path
    applied_migrations: tuple[str, ...]
    discovered_migrations: tuple[str, ...]
    created_storage_directories: tuple[Path, ...]


def initialize_data_layer(
    settings: Settings,
    *,
    logger: logging.Logger | None = None,
) -> DataLayerState:
    storage_state = ensure_storage_layout(settings.storage_root)
    migration_state = apply_sql_migrations(settings.database_url)

    state = DataLayerState(
        database_path=migration_state.database_path,
        storage_root=storage_state.root,
        applied_migrations=migration_state.applied_versions,
        discovered_migrations=migration_state.discovered_versions,
        created_storage_directories=storage_state.created_directories,
    )

    if logger is not None:
        logger.info(
            "Data layer ready db=%s applied_migrations=%s storage_root=%s created_storage_dirs=%s",
            state.database_path,
            len(state.applied_migrations),
            state.storage_root,
            len(state.created_storage_directories),
        )

    return state
