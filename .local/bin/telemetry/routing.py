import json
import subprocess

from .config import VM_NETWORKS
from .bgp import get_bgp, initial_bgp


def get_routes():
    try:
        result = subprocess.run(
            ["ip", "-j", "route", "show", "table", "main"],
            capture_output=True, text=True, timeout=2, check=True,
        )
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def route_is_down(route):
    flags = route.get("flags", [])
    if isinstance(flags, list) and any(str(flag).lower() == "linkdown" for flag in flags):
        return True
    return route.get("linkdown") is True


def get_ospf_neighbors():
    try:
        result = subprocess.run(
            ["vtysh", "-c", "show ip ospf neighbor json"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        data = json.loads(result.stdout)
        table = data.get("neighbors", {})
        neighbors = []
        if not isinstance(table, dict):
            return neighbors

        for router_id, entries in table.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                iface_name = entry.get("ifaceName", "N/A")
                neighbors.append({
                    "router_id": router_id,
                    "address": entry.get("ifaceAddress", "N/A"),
                    "interface": iface_name.split(":", 1)[0],
                    "state": entry.get("nbrState", "UNKNOWN"),
                    "converged": entry.get("converged", "UNKNOWN"),
                    "role": entry.get("role", "UNKNOWN"),
                    "uptime": entry.get("upTime", "N/A"),
                })

        neighbors.sort(key=lambda n: (n["router_id"], n["address"]))
        return neighbors
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def get_ospf_routers():
    try:
        result = subprocess.run(
            ["vtysh", "-c", "show ip ospf database router json"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        data = json.loads(result.stdout)
        self_router_id = data.get("routerId", "N/A")
        areas = data.get("routerLinkStates", {}).get("areas", {})
        routers = {}

        for area_id, lsas in areas.items():
            if not isinstance(lsas, list):
                continue
            for lsa in lsas:
                if not isinstance(lsa, dict):
                    continue
                router_id = lsa.get("advertisingRouter")
                if not router_id:
                    continue
                routers[router_id] = {
                    "router_id": router_id,
                    "area": area_id,
                    "links": lsa.get("numOfLinks", 0),
                    "asbr": bool(lsa.get("asbr", False)),
                    "age": lsa.get("lsaAge", 0),
                }

        return {"self": self_router_id, "routers": list(routers.values())}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"self": "N/A", "routers": []}


def initial_routing():
    return {
        "available": False,
        "internet": {
            "available": False,
            "interface": "N/A",
            "address": "N/A",
            "gateway": "N/A",
            "metric": 0,
        },
        "ospf": {
            "state": "LOADING",
            "full": 0,
            "total": 0,
            "self": "N/A",
            "routers": [],
            "router_text": "LOADING",
            "topology": [],
            "topology_text": "LOADING",
        },
        "bgp": initial_bgp(),
        "vm_local": {"count": 0, "networks": "NONE", "interfaces": ""},
        "vm_remote": {"count": 0, "networks": "NONE", "via": "N/A"},
        "vm_local_routes": [],
        "vm_remote_routes": [],
    }


def get_routing():
    routes = get_routes()
    neighbors = get_ospf_neighbors()
    ospf_database = get_ospf_routers()

    internet = {
        "available": False,
        "interface": "N/A",
        "address": "N/A",
        "gateway": "N/A",
        "metric": 0,
    }

    defaults = [route for route in routes if route.get("dst") == "default"]
    if defaults:
        default_route = min(defaults, key=lambda route: route.get("metric", 0))
        internet = {
            "available": True,
            "interface": default_route.get("dev", "N/A"),
            "address": default_route.get("prefsrc", default_route.get("src", "N/A")),
            "gateway": default_route.get("gateway", "N/A"),
            "metric": default_route.get("metric", 0),
        }

    if neighbors is None:
        ospf_state = "UNAVAILABLE"
        ospf_full = 0
        ospf_total = 0
        ospf_routers = []
    else:
        ospf_total = len(neighbors)
        full_neighbors = [n for n in neighbors if n.get("converged", "").lower() == "full"]
        ospf_full = len(full_neighbors)
        if ospf_total == 0:
            ospf_state = "NO NEIGHBORS"
        elif ospf_full == ospf_total:
            ospf_state = "FULL"
        else:
            ospf_state = f"{ospf_full}/{ospf_total} FULL"
        ospf_routers = neighbors

    if ospf_routers:
        ospf_router_text = "\n".join(
            f'{r["router_id"]}  {r["address"]}  {r["state"]}' for r in ospf_routers
        )
    else:
        ospf_router_text = "NONE"

    neighbor_ids = {n["router_id"] for n in ospf_routers}
    self_router_id = ospf_database["self"]
    ospf_topology = []
    for router in ospf_database["routers"]:
        router_id = router["router_id"]
        if router_id == self_router_id:
            relation = "SELF"
        elif router_id in neighbor_ids:
            relation = "DIRECT"
        else:
            relation = "REMOTE"
        ospf_topology.append({**router, "relation": relation})

    ospf_topology.sort(
        key=lambda router: (
            0 if router["relation"] == "SELF" else 1 if router["relation"] == "DIRECT" else 2,
            router["router_id"],
        )
    )
    ospf_topology_text = "\n".join(
        f'{r["router_id"]}  {r["relation"]}' for r in ospf_topology
    ) if ospf_topology else "NONE"

    local_vm = []
    remote_vm = []
    for route in routes:
        destination = route.get("dst")
        if destination not in VM_NETWORKS:
            continue
        protocol = str(route.get("protocol", "")).lower()
        gateway = route.get("gateway")
        interface = route.get("dev", "N/A")
        if protocol == "kernel" and gateway is None:
            local_vm.append({
                "network": destination,
                "interface": interface,
                "state": "DOWN" if route_is_down(route) else "UP",
            })
        elif protocol == "ospf":
            remote_vm.append({
                "network": destination,
                "interface": interface,
                "via": gateway or "N/A",
                "metric": route.get("metric", 0),
            })

    local_vm.sort(key=lambda route: route["network"])
    remote_vm.sort(key=lambda route: route["network"])

    local_text = "   ".join(f'{r["network"]} {r["state"]}' for r in local_vm) if local_vm else "NONE"
    local_interfaces = "   ".join(r["interface"] for r in local_vm) if local_vm else ""
    remote_text = "   ".join(r["network"] for r in remote_vm) if remote_vm else "NONE"
    gateways = sorted({r["via"] for r in remote_vm})
    remote_via = "   ".join(gateways) if gateways else "N/A"

    return {
        "available": True,
        "internet": internet,
        "ospf": {
            "state": ospf_state,
            "full": ospf_full,
            "total": ospf_total,
            "self": self_router_id,
            "routers": ospf_routers,
            "router_text": ospf_router_text,
            "topology": ospf_topology,
            "topology_text": ospf_topology_text,
        },
        "bgp": get_bgp(),
        "vm_local": {
            "count": len(local_vm),
            "networks": local_text,
            "interfaces": local_interfaces,
        },
        "vm_remote": {
            "count": len(remote_vm),
            "networks": remote_text,
            "via": remote_via,
        },
        "vm_local_routes": local_vm,
        "vm_remote_routes": remote_vm,
    }
