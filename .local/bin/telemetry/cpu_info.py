"""CPU identity and online topology visible through Linux procfs."""
from pathlib import Path
import re


def get_cpu_info(cpuinfo_path=Path("/proc/cpuinfo")):
    unknown = {"cpu_model": "N/A", "cpu_cores": "N/A", "cpu_threads": "N/A"}
    try:
        records = []
        for section in re.split(r"\n\s*\n", cpuinfo_path.read_text()):
            fields = {}
            for line in section.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip()] = value.strip()
            if fields:
                records.append(fields)
        processors = [r for r in records if r.get("processor", "").isdigit()]
        models = list(dict.fromkeys(
            r["model name"] for r in processors if r.get("model name")
        ))
        if not models:
            models = list(dict.fromkeys(
                r["Hardware"] for r in records if r.get("Hardware")
            ))
        cores = set()
        for record in processors:
            # Core IDs repeat across sockets. Missing topology cannot establish
            # physical core count, even when logical CPU count is known.
            cores.add((int(record["physical id"]), int(record["core id"])))
        return {
            "cpu_model": " / ".join(models) or "N/A",
            "cpu_cores": len(cores) if processors else "N/A",
            "cpu_threads": len({r["processor"] for r in processors}) or "N/A",
        }
    except (KeyError, ValueError):
        return {**unknown, "cpu_model": " / ".join(models) or "N/A",
                "cpu_threads": len({r["processor"] for r in processors}) or "N/A"}
    except OSError:
        return unknown
