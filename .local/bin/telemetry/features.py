"""Shared panel names for layout generation and collector selection."""
import os

WIDGETS = {
    "system": "system-summary-widget", "hugepages": "hugepages-widget",
    "lan": "lan-widget", "wan": "wan-widget", "intel_gpu": "intel-gpu-widget",
    "nvidia": "gpu-widget", "ceph": "ceph-widget", "zfs": "zfs-widget",
    "nvmeof": "nvmeof-widget", "internet": "internet-widget",
    "ospf": "ospf-widget", "bgp": "bgp-widget", "vm": "vm-widget",
}


def selected_features():
    value = os.environ.get("STELLA_PANELS")
    selected = set(WIDGETS) if value is None else set(filter(None, value.split(",")))
    unknown = selected - WIDGETS.keys()
    if unknown:
        raise ValueError(f"Unknown panels: {', '.join(sorted(unknown))}")
    return selected
