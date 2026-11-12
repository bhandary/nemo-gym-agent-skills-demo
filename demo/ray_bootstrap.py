"""Pin Ray to settings that survive a small Railway container.

NeMo Gym calls ``ray.init`` with no arguments. On Railway that picks a large
CPU count, the dashboard, and ``/dev/shm`` for the object store. ``/dev/shm``
there is tiny, and the dashboard agent is one more process that can stall
startup. This module wraps ``ray.init`` before the Gym CLI starts a cluster.
"""

from __future__ import annotations

from pathlib import Path


OBJECT_STORE_BYTES = 200 * 1024 * 1024
PLASMA_DIRECTORY = "/tmp"
TEMP_DIR = "/tmp/ray"

_INSTALLED = False


def cpu_budget() -> int:
    """At most two CPUs. An unreadable cgroup falls back to two, not the host size."""
    detected = _cgroup_cpus()
    if detected is None:
        return 2
    return max(1, min(2, int(detected)))


def _cgroup_cpus() -> float | None:
    try:
        v2 = Path("/sys/fs/cgroup/cpu.max")
        if v2.is_file():
            quota, period = v2.read_text(encoding="utf-8").split()
            if quota != "max" and period not in {"0", ""}:
                return float(quota) / float(period)
            return None
        quota_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if quota_path.is_file() and period_path.is_file():
            quota = float(quota_path.read_text(encoding="utf-8"))
            period = float(period_path.read_text(encoding="utf-8"))
            if quota > 0 and period > 0:
                return quota / period
    except (OSError, ValueError):
        return None
    return None


def constrain_ray_init(kwargs: dict) -> dict:
    """Add container settings only when this call is starting a cluster."""
    if kwargs.get("address"):
        return dict(kwargs)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    tuned = dict(kwargs)
    tuned.setdefault("include_dashboard", False)
    tuned.setdefault("num_cpus", cpu_budget())
    tuned.setdefault("object_store_memory", OBJECT_STORE_BYTES)
    tuned.setdefault("_plasma_directory", PLASMA_DIRECTORY)
    tuned.setdefault("_temp_dir", TEMP_DIR)
    return tuned


def install() -> None:
    """Wrap ``ray.init`` once. Connecting to an existing cluster is left unchanged."""
    global _INSTALLED
    if _INSTALLED:
        return
    import ray

    original = ray.init

    def patched(*args, **kwargs):
        return original(*args, **constrain_ray_init(kwargs))

    ray.init = patched
    _INSTALLED = True
