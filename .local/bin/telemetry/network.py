import time
from collections import deque
from pathlib import Path

from .config import HISTORY_LENGTH
from .formatting import human_bits, sparkline


def get_netdev_temperature(interface):
    base = Path(f"/sys/class/net/{interface}/device/hwmon")
    try:
        hwmons = list(base.glob("hwmon*"))
    except OSError:
        return None

    temperatures = []
    for hwmon in hwmons:
        for temp_file in hwmon.glob("temp*_input"):
            try:
                temperatures.append(int(temp_file.read_text().strip()) / 1000.0)
            except (OSError, ValueError):
                continue

    return round(max(temperatures)) if temperatures else None


class NetworkInterface:
    def __init__(self, interface):
        self.interface = interface
        self.last_rx = None
        self.last_tx = None
        self.last_time = None
        self.rx_history = deque(maxlen=HISTORY_LENGTH)
        self.tx_history = deque(maxlen=HISTORY_LENGTH)

    def read_counter(self, counter):
        path = Path("/sys/class/net") / self.interface / "statistics" / counter
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            return 0

    def get_state(self):
        path = Path("/sys/class/net") / self.interface / "operstate"
        try:
            return path.read_text().strip()
        except OSError:
            return "unknown"

    def update(self):
        now = time.monotonic()
        rx = self.read_counter("rx_bytes")
        tx = self.read_counter("tx_bytes")
        rx_rate = 0.0
        tx_rate = 0.0

        if self.last_time is not None and self.last_rx is not None and self.last_tx is not None:
            elapsed = now - self.last_time
            if elapsed > 0:
                rx_rate = max(0.0, (rx - self.last_rx) / elapsed)
                tx_rate = max(0.0, (tx - self.last_tx) / elapsed)

        self.last_rx = rx
        self.last_tx = tx
        self.last_time = now
        self.rx_history.append(rx_rate)
        self.tx_history.append(tx_rate)

        temperature = get_netdev_temperature(self.interface)
        return {
            "interface": self.interface,
            "state": self.get_state(),
            "rx_bps": round(rx_rate * 8),
            "tx_bps": round(tx_rate * 8),
            "rx": human_bits(rx_rate * 8),
            "tx": human_bits(tx_rate * 8),
            "rx_graph": sparkline(self.rx_history),
            "tx_graph": sparkline(self.tx_history),
            "temperature": temperature if temperature is not None else "N/A",
        }
