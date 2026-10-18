import subprocess


def initial_nvidia():
    return {
        "available": False,
        "name": "Loading...",
        "utilization": 0,
        "temperature": 0,
        "power_w": 0,
        "memory_used_mib": 0,
        "memory_total_mib": 0,
        "memory": "N/A",
    }


def get_nvidia():
    command = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=True)
        fields = [field.strip() for field in result.stdout.strip().splitlines()[0].split(",")]
        name, utilization, temperature, power, memory_used, memory_total = fields
        memory_used = float(memory_used)
        memory_total = float(memory_total)
        return {
            "available": True,
            "name": name,
            "utilization": round(float(utilization)),
            "temperature": round(float(temperature)),
            "power_w": round(float(power), 1),
            "memory_used_mib": round(memory_used),
            "memory_total_mib": round(memory_total),
            "memory": f"{memory_used / 1024:.1f} / {memory_total / 1024:.1f} GiB",
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        data = initial_nvidia()
        data["name"] = "NVIDIA unavailable"
        return data
