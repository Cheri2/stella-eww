import json
import subprocess
from collections import deque

from .config import CEPH_KEYRING, CEPH_NAME, HISTORY_LENGTH
from .formatting import human_bytes, human_bytes_rate, sparkline

CEPH_READ_HISTORY = deque(maxlen=HISTORY_LENGTH)
CEPH_WRITE_HISTORY = deque(maxlen=HISTORY_LENGTH)


def initial_ceph():
    return {
        "available": False,
        "health": "LOADING",
        "osd_total": 0,
        "osd_up": 0,
        "osd_in": 0,
        "pg_total": 0,
        "used": "N/A",
        "total": "N/A",
        "read": "N/A",
        "write": "N/A",
        "read_iops": 0,
        "write_iops": 0,
        "read_graph": "",
        "write_graph": "",
    }


def get_ceph():
    command = [
        "ceph", "--name", CEPH_NAME, "--keyring", str(CEPH_KEYRING),
        "-s", "--format", "json",
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=True)
        data = json.loads(result.stdout)
        health = data.get("health", {}).get("status", "UNKNOWN")
        osdmap = data.get("osdmap", {})
        pgmap = data.get("pgmap", {})

        osd_total = int(osdmap.get("num_osds", 0))
        osd_up = int(osdmap.get("num_up_osds", 0))
        osd_in = int(osdmap.get("num_in_osds", 0))
        pg_total = int(pgmap.get("num_pgs", 0))
        used_bytes = int(pgmap.get("bytes_used", 0))
        total_bytes = int(pgmap.get("bytes_total", 0))
        available_bytes = int(pgmap.get("bytes_avail", 0))
        read_bytes_sec = int(pgmap.get("read_bytes_sec", 0))
        write_bytes_sec = int(pgmap.get("write_bytes_sec", 0))
        read_iops = int(pgmap.get("read_op_per_sec", 0))
        write_iops = int(pgmap.get("write_op_per_sec", 0))

        CEPH_READ_HISTORY.append(read_bytes_sec)
        CEPH_WRITE_HISTORY.append(write_bytes_sec)

        return {
            "available": True,
            "health": health,
            "osd_total": osd_total,
            "osd_up": osd_up,
            "osd_in": osd_in,
            "pg_total": pg_total,
            "used_bytes": used_bytes,
            "total_bytes": total_bytes,
            "available_bytes": available_bytes,
            "used": human_bytes(used_bytes),
            "total": human_bytes(total_bytes),
            "available_space": human_bytes(available_bytes),
            "read_bps": read_bytes_sec,
            "write_bps": write_bytes_sec,
            "read": human_bytes_rate(read_bytes_sec),
            "write": human_bytes_rate(write_bytes_sec),
            "read_iops": read_iops,
            "write_iops": write_iops,
            "read_graph": sparkline(CEPH_READ_HISTORY),
            "write_graph": sparkline(CEPH_WRITE_HISTORY),
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        data = initial_ceph()
        data["health"] = "UNAVAILABLE"
        return data
