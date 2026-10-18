import json
import re
import subprocess
from pathlib import Path


ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ANSI_OSC = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
HEADER_RE = re.compile(
    r"DRM\s+minor\s+(?P<minor>\d+).*?Frequency\(MHz\)"
    r"(?P<frequencies>.*)"
)
FREQUENCY_RE = re.compile(r"GT\d+-(?P<actual>\d+)/(?P<requested>\d+)")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


def initial_intel_gpu():
    return {
        "available": False,
        "name": "Intel GPU",
        "utilization": 0.0,
        "frequency_mhz": 0,
        "requested_mhz": 0,
        "rc6": 0.0,
        "power_w": 0.0,
    }


def _intel_cards():
    """Return Intel primary DRM nodes as (driver, minor) pairs."""
    cards = []
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        try:
            driver = (card / "device/driver").resolve().name
            vendor = (card / "device/vendor").read_text().strip().lower()
        except OSError:
            continue
        if driver in {"xe", "i915"} and vendor == "0x8086":
            cards.append((driver, int(card.name.removeprefix("card"))))
    return cards


def _strip_terminal_control(text):
    text = ANSI_OSC.sub("", text)
    text = ANSI_CSI.sub("", text)
    # gputop pads its TUI with non-breaking spaces on some builds.
    return text.replace("\x1b", "").replace("\xa0", " ").replace("\r", "\n")


def _parse_gputop(text, drm_minor):
    """Parse the newest gputop block belonging to the Xe primary node."""
    # Parse line-by-line instead of treating the terminal redraw stream as one
    # large regex. CSI clear-screen/style sequences may occur immediately
    # before every header and differ between gputop versions.
    blocks = []
    current = None
    for line in _strip_terminal_control(text).splitlines():
        header = HEADER_RE.search(line)
        if header:
            if current is not None:
                blocks.append(current)
            current = {
                "minor": int(header.group("minor")),
                "frequencies": header.group("frequencies"),
                "body": [],
            }
        elif current is not None:
            current["body"].append(line)
    if current is not None:
        blocks.append(current)

    matches = [block for block in blocks if block["minor"] == drm_minor]
    if not matches:
        raise ValueError(f"gputop returned no DRM minor {drm_minor} block")

    # With -n 2, the second screen is the useful measured interval.
    block = matches[-1]
    frequencies = list(FREQUENCY_RE.finditer(block["frequencies"]))
    if not frequencies:
        raise ValueError("gputop returned no GT frequency")

    actual = max(int(match.group("actual")) for match in frequencies)
    requested = max(int(match.group("requested")) for match in frequencies)

    engine_totals = []
    for line in block["body"]:
        percentages = [float(value) for value in PERCENT_RE.findall(line)]
        if not percentages:
            continue
        if not engine_totals:
            engine_totals = [0.0] * len(percentages)
        for index, value in enumerate(percentages[:len(engine_totals)]):
            engine_totals[index] += value

    # Sum every client's usage per engine, then report the busiest engine.
    utilization = min(max(engine_totals, default=0.0), 100.0)
    return actual, requested, utilization


def _decode_intel_gpu_top_samples(text):
    """Decode complete objects from intel_gpu_top's streaming JSON array."""
    decoder = json.JSONDecoder()
    text = text.lstrip()
    if text.startswith("["):
        text = text[1:]

    samples = []
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text) or text[pos] == "]":
            break
        try:
            obj, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            samples.append(obj)
        pos = end
    return samples


def _get_xe_gpu(drm_minor):
    result = subprocess.run(
        [
            "timeout", "--signal=TERM", "1.2s",
            "gputop", "-d", "0.2",
        ],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    actual, requested, utilization = _parse_gputop(result.stdout, drm_minor)
    return {
        "available": True,
        "name": "Intel GPU (Xe)",
        "utilization": round(utilization, 1),
        "frequency_mhz": actual,
        "requested_mhz": requested,
        # gputop does not expose these, but keep the Eww JSON stable.
        "rc6": 0.0,
        "power_w": 0.0,
    }


def _get_i915_gpu(drm_minor):
    result = subprocess.run(
        [
            "timeout", "0.65s", "intel_gpu_top",
            "-d", f"drm:/dev/dri/card{drm_minor}",
            "-J", "-s", "250",
        ],
        capture_output=True,
        text=True,
        timeout=1,
        check=False,
    )
    samples = _decode_intel_gpu_top_samples(result.stdout)
    if not samples:
        raise ValueError("intel_gpu_top returned no complete samples")

    sample = samples[-1]
    frequency = sample.get("frequency", {})
    power = sample.get("power", {})
    rc6 = sample.get("rc6", {})
    engines = sample.get("engines", {})
    utilization = max(
        (
            float(engine.get("busy", 0.0))
            for engine in engines.values()
            if isinstance(engine, dict)
        ),
        default=0.0,
    )
    return {
        "available": True,
        "name": "Intel GPU (i915)",
        "utilization": round(utilization, 1),
        "frequency_mhz": round(float(frequency.get("actual", 0.0))),
        "requested_mhz": round(float(frequency.get("requested", 0.0))),
        "rc6": round(float(rc6.get("value", 0.0)), 1),
        "power_w": round(float(power.get("GPU", 0.0)), 2),
    }


def get_intel_gpu():
    try:
        cards = _intel_cards()
        for driver in ("xe", "i915"):
            for card_driver, drm_minor in cards:
                if card_driver == driver:
                    if driver == "xe":
                        return _get_xe_gpu(drm_minor)
                    return _get_i915_gpu(drm_minor)
        raise ValueError("no Intel xe/i915 DRM device found")

    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        data = initial_intel_gpu()
        data["name"] = "Intel GPU unavailable"
        return data
