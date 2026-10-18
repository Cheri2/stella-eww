from .config import SPARK_CHARS


def human_bits(value):
    value = float(value)
    units = ["bit/s", "Kbit/s", "Mbit/s", "Gbit/s", "Tbit/s"]
    for unit in units:
        if value < 1000.0 or unit == units[-1]:
            if value >= 100:
                return f"{value:.0f} {unit}"
            if value >= 10:
                return f"{value:.1f} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1000.0
    return "0 bit/s"


def human_bytes(value):
    value = float(value)
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if value >= 100:
                return f"{value:.0f} {unit}"
            if value >= 10:
                return f"{value:.1f} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return "0 B"


def human_bytes_rate(value):
    return f"{human_bytes(value)}/s"


def human_uptime(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def sparkline(values):
    values = list(values)
    if not values:
        return ""
    maximum = max(values)
    if maximum <= 0:
        return SPARK_CHARS[0] * len(values)
    output = []
    for value in values:
        ratio = max(0.0, min(1.0, value / maximum))
        index = round(ratio * (len(SPARK_CHARS) - 1))
        output.append(SPARK_CHARS[index])
    return "".join(output)
