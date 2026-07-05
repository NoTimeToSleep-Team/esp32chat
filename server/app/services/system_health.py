from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class SystemHealthSnapshot:
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_usage_percent: float
    disk_free_mb: float
    uptime_seconds: float
    python_version: str
    server_version: str
    db_size_mb: float
    storage_free_mb: float
    error: str | None = None


class SystemHealthService:
    def __init__(self, db_path: str | Path, storage_root: str | Path, server_version: str = "1.0.0") -> None:
        self._db_path = Path(db_path)
        self._storage_root = Path(storage_root)
        self._server_version = server_version
        self._started_ms = _now_ms()

    def get_snapshot(self) -> SystemHealthSnapshot:
        cpu = self._get_cpu()
        mem = self._get_memory()
        disk = self._get_disk_usage()
        db_size = self._get_db_size()
        storage_free = self._get_storage_free()
        uptime = self._get_uptime()

        return SystemHealthSnapshot(
            cpu_percent=cpu,
            memory_percent=mem.percent,
            memory_available_mb=mem.available_mb,
            disk_usage_percent=disk.percent,
            disk_free_mb=disk.free_mb,
            uptime_seconds=uptime,
            python_version=sys.version.split()[0] if hasattr(sys, "version") else "unknown",
            server_version=self._server_version,
            db_size_mb=db_size,
            storage_free_mb=storage_free,
        )

    def _get_cpu(self) -> float:
        try:
            import psutil
            return psutil.cpu_percent(interval=0.3)
        except ImportError:
            pass
        if os.name == "posix":
            try:
                with open("/proc/stat") as f:
                    for line in f:
                        if line.startswith("cpu "):
                            vals = [int(v) for v in line.split()[1:5]]
                            total1 = sum(vals)
                            idle1 = vals[3]
                            time.sleep(0.3)
                            with open("/proc/stat") as f2:
                                for line2 in f2:
                                    if line2.startswith("cpu "):
                                        vals2 = [int(v) for v in line2.split()[1:5]]
                                        total2 = sum(vals2)
                                        idle2 = vals2[3]
                                        return round(100.0 * (1 - (idle2 - idle1) / (max(total2 - total1, 1))), 1)
            except Exception:
                pass
        return -1.0

    def _get_memory(self):
        class M:
            percent = 0.0
            available_mb = 0.0
        try:
            import psutil
            m = psutil.virtual_memory()
            M.percent = m.percent
            M.available_mb = round(m.available / (1024 * 1024), 1)
            return M
        except ImportError:
            pass
        if os.name == "posix":
            try:
                with open("/proc/meminfo") as f:
                    d = {}
                    for line in f:
                        p = line.split(":")
                        if len(p) == 2:
                            k = p[0].strip()
                            try:
                                d[k] = int(p[1].strip().split()[0])
                            except (ValueError, IndexError):
                                pass
                    total = d.get("MemTotal", 0)
                    avail = d.get("MemAvailable", 0)
                    if total > 0:
                        M.percent = round(100.0 * (1 - avail / total), 1)
                        M.available_mb = round(avail / 1024, 1)
            except Exception:
                pass
        return M

    def _get_disk_usage(self):
        class D:
            percent = 0.0
            free_mb = 0.0
        try:
            if os.name == "posix":
                s = os.statvfs(str(self._storage_root))
                total = s.f_frsize * s.f_blocks
                free = s.f_frsize * s.f_bfree
                D.free_mb = round(free / (1024 * 1024), 1)
                D.percent = round(100.0 * (1 - free / (total or 1)), 1) if total > 0 else 0.0
            else:
                import shutil
                u = shutil.disk_usage(self._storage_root)
                D.free_mb = round(u.free / (1024 * 1024), 1)
                D.percent = round(100.0 * u.used / (u.total or 1), 1) if u.total > 0 else 0.0
        except Exception:
            D.percent = -1.0
            D.free_mb = -1.0
        return D

    def _get_db_size(self) -> float:
        try:
            return round(self._db_path.stat().st_size / (1024 * 1024), 2)
        except Exception:
            return -1.0

    def _get_storage_free(self) -> float:
        try:
            if os.name == "posix":
                s = os.statvfs(str(self._storage_root))
                return round(s.f_frsize * s.f_bfree / (1024 * 1024), 1)
            else:
                import shutil
                return round(shutil.disk_usage(self._storage_root).free / (1024 * 1024), 1)
        except Exception:
            return -1.0

    def _get_uptime(self) -> float:
        try:
            if os.name == "posix":
                with open("/proc/uptime") as f:
                    return float(f.read().split()[0])
            else:
                import ctypes
                return ctypes.windll.kernel32.GetTickCount64() / 1000.0
        except Exception:
            return (_now_ms() - self._started_ms) / 1000.0
