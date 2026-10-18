"""Read-only pool capacity reporting (free space, not dataset available space)."""
import subprocess

from .formatting import human_bytes


def initial_zfs():
    return {"available": False, "status": "LOADING", "pools": [], "text": "LOADING"}


def get_zfs():
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-p", "-o", "name,size,alloc,free,health"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        pools = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            name, size, allocated, free, health = line.split()
            size, allocated, free = int(size), int(allocated), int(free)
            if min(size, allocated, free) < 0:
                raise ValueError("Invalid capacity")
            pools.append({
                "name": name, "health": health, "size_bytes": size,
                "allocated_bytes": allocated, "free_bytes": free,
                "size": human_bytes(size), "free": human_bytes(free),
            })
        return {
            "available": True, "status": "OK" if pools else "NONE", "pools": pools,
            "text": "\n".join(
                f'{p["name"]}  {p["health"]}\nFREE {p["free"]} / {p["size"]}'
                for p in pools
            ) or "No imported pools",
        }
    except (OSError, subprocess.SubprocessError, ValueError):
        return {**initial_zfs(), "status": "UNAVAILABLE", "text": "UNAVAILABLE"}
