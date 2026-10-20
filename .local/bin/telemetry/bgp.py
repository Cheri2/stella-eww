"""FRR default-VRF IPv4/IPv6 unicast BGP summary, read through vtysh."""
import json
import subprocess


def initial_bgp(state="LOADING"):
    return {"available": False, "state": state, "established": None,
            "total": None, "peers": [], "text": state}


def get_bgp():
    try:
        result = subprocess.run(
            ["vtysh", "-c", "show bgp summary json"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError("Invalid BGP summary")
        peers = []
        families = [(key, data[key]) for key in ("ipv4Unicast", "ipv6Unicast") if key in data]
        if not families:
            raise ValueError("No unicast summary available")
        for family, summary in families:
            if not isinstance(summary, dict) or not isinstance(summary.get("peers"), dict):
                raise ValueError("Invalid address family summary")
            for address, peer in sorted(summary["peers"].items()):
                if not isinstance(peer, dict) or not isinstance(peer.get("state"), str):
                    raise ValueError("Invalid peer")
                established = peer["state"].lower() == "established"
                # Prefix counts are meaningful only while established; absent
                # values must not look like a verified zero.
                received = peer.get("pfxRcd") if established else None
                peers.append({"address": address, "family": family,
                              "remote_as": peer.get("remoteAs", "N/A"),
                              "state": peer["state"], "received": received})
        established = sum(p["state"].lower() == "established" for p in peers)
        state = "NO PEERS" if not peers else f"{established}/{len(peers)} ESTABLISHED"
        text = "\n".join(
            f'{p["address"]}  AS{p["remote_as"]}  {p["family"]}\n'
            f'{p["state"]}  RX {p["received"] if p["received"] is not None else "N/A"}'
            for p in peers
        ) or "NONE"
        return {"available": True, "state": state, "established": established,
                "total": len(peers), "peers": peers, "text": text}
    except (OSError, subprocess.SubprocessError, ValueError):
        return initial_bgp("UNAVAILABLE")
