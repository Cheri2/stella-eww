"""Generate a private Eww dashboard configuration from a node's JSON profile."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from .features import WIDGETS


def validate_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("Profile must be a JSON object")
    unknown = profile.keys() - {"panels", "columns", "column_width", "gap", "x", "y", "monitor"}
    if unknown:
        raise ValueError(f"Unknown profile settings: {sorted(unknown)}")
    panels = profile.get("panels")
    if not isinstance(panels, list) or not panels or any(not isinstance(p, str) or p not in WIDGETS for p in panels):
        raise ValueError(f"panels must be a nonempty list from: {', '.join(WIDGETS)}")
    if len(set(panels)) != len(panels):
        raise ValueError("Duplicate panels are not allowed")
    result = {"columns": 1, "column_width": 380, "gap": 12, "x": 30, "y": 70, "monitor": 0, **profile}
    for key in ("columns", "column_width", "gap", "x", "y", "monitor"):
        value = result[key]
        if type(value) is not int or value < (1 if key in {"columns", "column_width"} else 0):
            raise ValueError(f"{key} must be an integer >= {1 if key in {'columns', 'column_width'} else 0}")
    result["columns"] = min(result["columns"], len(panels))
    return result


def initial_payload():
    # Populate every referenced field before the first (possibly slow) sample.
    system = dict.fromkeys(("cpu_model", "cpu_cores", "cpu_threads", "cpu", "temperature",
                           "cpu_graph", "used", "total", "swap_used", "swap_total",
                           "load1", "load5", "load15", "uptime"), "LOADING")
    system["hugepages"] = {key: dict.fromkeys(("used", "total", "used_size"), "LOADING")
                           for key in ("hp_2m", "hp_1g")}
    from .corosync import initial_corosync
    from .ceph import initial_ceph
    from .intel_gpu import initial_intel_gpu
    from .nvidia import initial_nvidia
    from .routing import initial_routing
    return {
        "system": system, "corosync": initial_corosync(),
        "network": {key: {"interface": "LOADING", "rx": "LOADING", "tx": "LOADING",
                          "temperature": "N/A", "rx_graph": ""} for key in ("lan", "wan")},
        "nvidia": initial_nvidia(), "intel_gpu": initial_intel_gpu(),
        "ceph": initial_ceph(), "routing": initial_routing(),
        "zfs": {"text": "LOADING"}, "nvmeof": {"text": "LOADING"},
    }


def render(profile, widgets, collector):
    profile = validate_profile(profile)
    widgets, collector = Path(widgets).resolve(), Path(collector).resolve()
    if not widgets.is_file() or not collector.is_file():
        raise ValueError("widgets.yuck and eww.py must exist")
    # Column-major order; removing panels also removes empty columns and gaps.
    count = profile["columns"]
    size, extra = divmod(len(profile["panels"]), count)
    columns = []
    offset = 0
    for index in range(count):
        length = size + (index < extra)
        children = "\n".join(f'({WIDGETS[p]})' for p in profile["panels"][offset:offset + length])
        columns.append(f'(box :orientation "v" :valign "start" :space-evenly false :spacing {profile["gap"]} :width {profile["column_width"]}\n{children})')
        offset += length
    command = shlex.join(["env", "STELLA_PANELS=" + ",".join(profile["panels"]), sys.executable, "-B", str(collector)])
    # A quoted Yuck string is a shell command without backtick delimiters.
    # Reject interpolation syntax in filesystem paths rather than executing it.
    if any(mark in str(widgets) + command for mark in ("${", "\n", "\r")):
        raise ValueError("Paths cannot contain interpolation or newlines")
    initial = json.dumps(json.dumps(initial_payload(), separators=(",", ":")))
    return f'''(deflisten telemetry :initial {initial} {json.dumps(command, ensure_ascii=False)})
(include {json.dumps(str(widgets), ensure_ascii=False)})
(defwindow dashboard
  :monitor {profile["monitor"]}
  :geometry (geometry :x "{profile["x"]}px" :y "{profile["y"]}px" :width "{count * profile["column_width"] + (count - 1) * profile["gap"]}px" :anchor "top right")
  :stacking "bottom" :exclusive false :focusable false
  (box :class "telemetry" :orientation "h" :space-evenly false :spacing {profile["gap"]}
    {chr(10).join(columns)}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="Node JSON profile")
    base = Path(__file__).resolve().parents[3]
    parser.add_argument("--widgets", type=Path, default=base / '.config/eww/widgets.yuck')
    parser.add_argument("--output", type=Path, default=Path(os.environ.get("XDG_CACHE_HOME", Path.home() / '.cache')) / 'stella-eww')
    parser.add_argument("--open", action="store_true", help="Start/reload the generated Eww config and open dashboard")
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text())
        content = render(profile, args.widgets, base / '.local/bin/eww.py')
        style = args.widgets.with_name('eww.scss').read_text()
        output = args.output.expanduser().resolve()
        # Never overwrite the source or an unrelated Eww configuration.
        marker = output / '.stella-generated'
        if output.exists() and any(output.iterdir()) and not marker.is_file():
            raise ValueError("Output directory must be empty or generated by stella-panels")
        output.mkdir(parents=True, exist_ok=True)
        marker.touch()
        (output / 'eww.yuck').write_text(content)
        (output / 'eww.scss').write_text(style)
        print(f"Generated {output} ({', '.join(profile['panels'])})")
        if args.open:
            command = ["eww", "--config", str(output)]
            subprocess.run(command + ["daemon"], check=True)
            subprocess.run(command + ["reload"], check=True)
            subprocess.run(command + ["close", "dashboard"], check=False)
            subprocess.run(command + ["open", "dashboard"], check=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"stella-panels: {error}\n")
