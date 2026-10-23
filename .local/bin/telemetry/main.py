import json
import time

from .ceph import get_ceph
from .corosync import get_corosync
from .config import (
    COROSYNC_INTERVAL, COROSYNC_SNAPSHOT,
    CEPH_INTERVAL, ZFS_INTERVAL, NVMEOF_INTERVAL, INTEL_GPU_INTERVAL,
    INTERFACES, INTERVAL, NVIDIA_INTERVAL, ROUTING_INTERVAL,
)
from .features import selected_features
from .network import NetworkInterface
from .intel_gpu import get_intel_gpu
from .nvidia import get_nvidia
from .routing import get_routing
from .system import SystemMonitor
from .zfs import get_zfs
from .nvmeof import get_nvmeof


class Collector:
    """Only selected panels schedule reads, including routing subfeatures."""

    def __init__(self, features):
        self.features = set(features)
        self.network = {
            name: NetworkInterface(interface)
            for name, interface in INTERFACES.items() if name in features
        }
        self.system = SystemMonitor() if self.features & {"system", "hugepages"} else None
        self.routing = self.features & {"internet", "ospf", "bgp", "vm"}
        self.jobs = {
            "corosync": (COROSYNC_INTERVAL, lambda: get_corosync(COROSYNC_SNAPSHOT)),
            "nvidia": (NVIDIA_INTERVAL, get_nvidia),
            "intel_gpu": (INTEL_GPU_INTERVAL, get_intel_gpu),
            "ceph": (CEPH_INTERVAL, get_ceph),
            "zfs": (ZFS_INTERVAL, get_zfs),
            "nvmeof": (NVMEOF_INTERVAL, get_nvmeof),
        }
        self.jobs = {key: job for key, job in self.jobs.items() if key in self.features}
        if self.routing:
            self.jobs["routing"] = (ROUTING_INTERVAL, lambda: get_routing(self.routing))
        self.last = {}
        self.cached = {}

    def update(self, now=None):
        now = time.monotonic() if now is None else now
        payload = {"network": {name: monitor.update() for name, monitor in self.network.items()}}
        if "system" in self.features:
            payload["system"] = self.system.update(include_hugepages="hugepages" in self.features)
        elif "hugepages" in self.features:
            payload["system"] = {"hugepages": self.system.read_hugepages()}
        for name, (interval, read) in self.jobs.items():
            if name not in self.last or now - self.last[name] >= interval:
                self.cached[name] = read()
                self.last[name] = now
            payload[name] = self.cached[name]
        return payload


def main():
    collector = Collector(selected_features())
    while True:
        loop_start = time.monotonic()
        print(json.dumps(collector.update(loop_start), separators=(",", ":")), flush=True)
        time.sleep(max(0.0, INTERVAL - (time.monotonic() - loop_start)))
