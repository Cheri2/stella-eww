import json
import time

from .ceph import get_ceph, initial_ceph
from .config import (
    CEPH_INTERVAL,
    INTEL_GPU_INTERVAL,
    INTERFACES,
    INTERVAL,
    NVIDIA_INTERVAL,
    ROUTING_INTERVAL,
)
from .network import NetworkInterface
from .intel_gpu import get_intel_gpu, initial_intel_gpu
from .nvidia import get_nvidia, initial_nvidia
from .routing import get_routing, initial_routing
from .system import SystemMonitor


def main():
    network_monitors = {
        name: NetworkInterface(interface)
        for name, interface in INTERFACES.items()
    }
    system_monitor = SystemMonitor()

    nvidia = initial_nvidia()
    intel_gpu = initial_intel_gpu()
    ceph = initial_ceph()
    routing = initial_routing()

    last_nvidia = 0.0
    last_intel_gpu = 0.0
    last_ceph = 0.0
    last_routing = 0.0

    while True:
        loop_start = time.monotonic()

        network = {
            name: monitor.update()
            for name, monitor in network_monitors.items()
        }
        system = system_monitor.update()

        if loop_start - last_nvidia >= NVIDIA_INTERVAL:
            nvidia = get_nvidia()
            last_nvidia = loop_start

        if loop_start - last_intel_gpu >= INTEL_GPU_INTERVAL:
            intel_gpu = get_intel_gpu()
            last_intel_gpu = loop_start

        if loop_start - last_ceph >= CEPH_INTERVAL:
            ceph = get_ceph()
            last_ceph = loop_start

        if loop_start - last_routing >= ROUTING_INTERVAL:
            routing = get_routing()
            last_routing = loop_start

        payload = {
            "network": network,
            "nvidia": nvidia,
            "intel_gpu": intel_gpu,
            "ceph": ceph,
            "system": system,
            "routing": routing,
        }

        print(json.dumps(payload, separators=(",", ":")), flush=True)

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, INTERVAL - elapsed))
