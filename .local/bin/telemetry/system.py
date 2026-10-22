from collections import deque
from pathlib import Path

from .config import HISTORY_LENGTH
from .cpu_info import get_cpu_info
from .formatting import human_bytes, human_uptime, sparkline

CPU_HISTORY = deque(maxlen=HISTORY_LENGTH)


class SystemMonitor:
    def __init__(self):
        self.last_cpu_total = None
        self.last_cpu_idle = None

    def read_cpu(self):
        try:
            values = [
                int(v)
                for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:]
            ]
        except (OSError, ValueError, IndexError):
            return 0.0

        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        usage = 0.0

        if self.last_cpu_total is not None and self.last_cpu_idle is not None:
            total_delta = total - self.last_cpu_total
            idle_delta = idle - self.last_cpu_idle

            if total_delta > 0:
                usage = 100.0 * (total_delta - idle_delta) / total_delta

        self.last_cpu_total = total
        self.last_cpu_idle = idle

        return max(0.0, min(100.0, usage))

    def read_meminfo(self):
        result = {}

        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                fields = value.strip().split()

                if fields:
                    result[key] = int(fields[0]) * 1024
        except (OSError, ValueError):
            pass

        return result

    def read_hugepages(self):
        base = Path("/sys/kernel/mm/hugepages")
        result = {}

        for name, size_kb in (
            ("hp_2m", 2048),
            ("hp_1g", 1048576),
        ):
            path = base / f"hugepages-{size_kb}kB"

            try:
                total = int((path / "nr_hugepages").read_text().strip())
                free = int((path / "free_hugepages").read_text().strip())
            except (OSError, ValueError):
                total = 0
                free = 0

            used = max(0, total - free)
            page_bytes = size_kb * 1024
            used_bytes = used * page_bytes
            total_bytes = total * page_bytes

            result[name] = {
                "total": total,
                "free": free,
                "used": used,
                "used_bytes": used_bytes,
                "total_bytes": total_bytes,
                "used_size": human_bytes(used_bytes),
                "total_size": human_bytes(total_bytes),
            }

        return result

    def read_temperature(self):
        temperatures = []

        try:
            hwmons = list(Path("/sys/class/hwmon").glob("hwmon*"))
        except OSError:
            return None

        for hwmon in hwmons:
            try:
                name = (hwmon / "name").read_text().strip()
            except OSError:
                continue

            if name not in {"coretemp", "k10temp", "zenpower"}:
                continue

            for temp_file in hwmon.glob("temp*_input"):
                try:
                    temperatures.append(
                        int(temp_file.read_text().strip()) / 1000.0
                    )
                except (OSError, ValueError):
                    continue

        return round(max(temperatures)) if temperatures else None

    def update(self, include_hugepages=True):
        cpu = self.read_cpu()
        CPU_HISTORY.append(cpu)

        meminfo = self.read_meminfo()

        memory_total = meminfo.get("MemTotal", 0)
        memory_available = meminfo.get("MemAvailable", 0)
        memory_used = max(0, memory_total - memory_available)

        swap_total = meminfo.get("SwapTotal", 0)
        swap_free = meminfo.get("SwapFree", 0)
        swap_used = max(0, swap_total - swap_free)

        try:
            load1, load5, load15 = Path("/proc/loadavg").read_text().split()[:3]
        except (OSError, IndexError):
            load1 = load5 = load15 = "N/A"

        try:
            uptime_seconds = float(
                Path("/proc/uptime").read_text().split()[0]
            )
        except (OSError, ValueError, IndexError):
            uptime_seconds = 0

        temperature = self.read_temperature()
        hugepages = self.read_hugepages() if include_hugepages else {}

        return {
            **get_cpu_info(),
            "cpu": round(cpu, 1),
            "cpu_graph": sparkline(CPU_HISTORY),
            "temperature": temperature if temperature is not None else "N/A",

            "used_bytes": memory_used,
            "total_bytes": memory_total,
            "used": human_bytes(memory_used),
            "total": human_bytes(memory_total),

            "swap_used_bytes": swap_used,
            "swap_total_bytes": swap_total,
            "swap_used": human_bytes(swap_used),
            "swap_total": human_bytes(swap_total),

            "load1": load1,
            "load5": load5,
            "load15": load15,

            "uptime_seconds": round(uptime_seconds),
            "uptime": human_uptime(uptime_seconds),

            "hugepages": hugepages,
        }
