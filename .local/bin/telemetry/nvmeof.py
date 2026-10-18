"""Discover imported TCP/RDMA NVMe namespaces without nvme-cli or root."""
from pathlib import Path
import re


NAMESPACE = re.compile(r"nvme\d+(?:c\d+)?n\d+$")
CONTROLLER = re.compile(r"nvme\d+$")


def initial_nvmeof():
    return {"available": False, "status": "LOADING", "devices": [], "text": "LOADING"}


def get_nvmeof(block_root=Path("/sys/class/block")):
    try:
        devices = []
        for block in sorted(block_root.iterdir()):
            if not NAMESPACE.fullmatch(block.name):
                continue
            namespace = block.resolve(strict=True)
            # Ordinary namespaces live under their controller. Native multipath
            # heads live under a subsystem, whose controller links expose paths.
            controllers = [p for p in namespace.parents if CONTROLLER.fullmatch(p.name)]
            if not controllers:
                nsid = (namespace / "nsid").read_text().strip()
                for candidate in namespace.parent.iterdir():
                    if not CONTROLLER.fullmatch(candidate.name):
                        continue
                    if any(
                        NAMESPACE.fullmatch(child.name)
                        and (child / "nsid").read_text().strip() == nsid
                        for child in candidate.iterdir()
                    ):
                        controllers.append(candidate)
            paths = []
            for controller in sorted(controllers):
                transport = (controller / "transport").read_text().strip()
                if transport not in {"tcp", "rdma"}:
                    continue
                paths.append({
                    "controller": controller.name, "transport": transport,
                    "address": (controller / "address").read_text().strip(),
                    "state": (controller / "state").read_text().strip(),
                })
            if paths:
                devices.append({"device": f"/dev/{block.name}", "paths": paths})
        text = "\n".join(
            f'{d["device"]}  {p["transport"].upper()}  {p["state"]}\n{p["address"]}'
            for d in devices for p in d["paths"]
        )
        return {"available": True, "status": "OK" if devices else "NONE",
                "devices": devices, "text": text or "No NVMe-oF block devices"}
    except (OSError, ValueError):
        # A disappearing path or denied sysfs read is not a verified empty list.
        return {**initial_nvmeof(), "status": "UNAVAILABLE", "text": "UNAVAILABLE"}
