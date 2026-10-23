from pathlib import Path

INTERVAL = 1.0
NVIDIA_INTERVAL = 2.0
INTEL_GPU_INTERVAL = 2.0
CEPH_INTERVAL = 5.0
ROUTING_INTERVAL = 5.0

CEPH_NAME = "client.desktop-widget"
CEPH_KEYRING = Path.home() / ".config/ceph/ceph.client.desktop-widget.keyring"

INTERFACES = {
    "lan": "N/A",
    "wan": "wlan0",
}

VM_NETWORKS = {
    "172.30.168.0/24",
    "172.30.169.0/24",
    "172.30.170.0/24",
}

HISTORY_LENGTH = 32
SPARK_CHARS = "▁▂▃▄▅▆▇█"

ZFS_INTERVAL = 5.0
NVMEOF_INTERVAL = 5.0

COROSYNC_INTERVAL = 5.0
# None: direct non-root IPC; or a read-only snapshot path.
COROSYNC_SNAPSHOT = None
