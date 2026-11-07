"""Best-effort local resource snapshots and conservative inference budgets."""
from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess
import sys
import time


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    timestamp: float
    total_ram_bytes: int | None
    available_ram_bytes: int | None
    total_disk_bytes: int | None
    available_disk_bytes: int | None
    gpu_name: str | None = None
    total_vram_bytes: int | None = None
    free_vram_bytes: int | None = None
    gpu_source: str = "unavailable"


@dataclass(frozen=True, slots=True)
class InferenceBudget:
    max_context_tokens: int
    max_parallel_requests: int
    estimated_model_memory_bytes: int | None
    warnings: tuple[str, ...]


def _ram() -> tuple[int | None, int | None]:
    if sys.platform == "win32":
        try:
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                            ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                            ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                            ("avail_extended", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.total_phys, status.avail_phys
        except Exception:
            pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        available = os.sysconf("SC_AVPHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return pages * size, available * size
    except (AttributeError, OSError, ValueError):
        return None, None


class ResourceMonitor:
    """Uses OS memory APIs and optional nvidia-smi; no telemetry leaves the machine."""

    def snapshot(self, disk_path: str | None = None) -> ResourceSnapshot:
        total, available = _ram()
        disk = shutil.disk_usage(disk_path or os.path.expanduser("~"))
        gpu_name = total_vram = free_vram = None
        source = "unavailable"
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2, check=True,
            )
            line = result.stdout.strip().splitlines()[0]
            name, total_mib, free_mib = [part.strip() for part in line.split(",", 2)]
            gpu_name, total_vram, free_vram = name, int(total_mib) * 1024**2, int(free_mib) * 1024**2
            source = "nvidia-smi"
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass
        return ResourceSnapshot(time.time(), total, available, disk.total, disk.free,
                                gpu_name, total_vram, free_vram, source)


class ResourceBudgetManager:
    def __init__(self, reserve_ram_bytes: int = 4 * 1024**3,
                 reserve_vram_bytes: int = 1 * 1024**3) -> None:
        self.reserve_ram_bytes = reserve_ram_bytes
        self.reserve_vram_bytes = reserve_vram_bytes

    def budget(self, snapshot: ResourceSnapshot, requested_context: int = 8192,
               requested_parallel: int = 1,
               estimated_model_memory_bytes: int | None = None) -> InferenceBudget:
        if requested_context < 1 or requested_parallel < 1:
            raise ValueError("Context and parallel request limits must be positive.")
        warnings = []
        context = requested_context
        parallel = requested_parallel
        if snapshot.available_ram_bytes is not None:
            usable = max(0, snapshot.available_ram_bytes - self.reserve_ram_bytes)
            if usable < 2 * 1024**3:
                context = min(context, 4096)
                parallel = 1
                warnings.append("Low available RAM: reduced context and serialized inference.")
            elif usable < 6 * 1024**3:
                context = min(context, 8192)
                parallel = min(parallel, 1)
                warnings.append("Moderate RAM pressure: limited inference concurrency.")
        if snapshot.free_vram_bytes is not None:
            usable_vram = max(0, snapshot.free_vram_bytes - self.reserve_vram_bytes)
            if estimated_model_memory_bytes is not None and estimated_model_memory_bytes > usable_vram:
                warnings.append("Estimated model memory exceeds available VRAM; prefer a smaller or CPU-offloaded model.")
                parallel = 1
        return InferenceBudget(context, parallel, estimated_model_memory_bytes, tuple(warnings))
