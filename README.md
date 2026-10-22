# stella-eww
Linux desktop telemetry panels built with Eww and a modular Python collector.
The collector emits one JSON object per update; Eww consumes it with `deflisten`.
Python uses only the standard library.

## Monitoring features

| Section | Displayed information | Source / requirements |
| --- | --- | --- |
| LAN / WAN | Receive/transmit bit rates, receive sparkline; LAN NIC temperature when exposed | Linux network sysfs counters and NIC hwmon |
| SYSTEM | CPU utilization and history, CPU temperature, RAM and swap used/total, load averages, uptime | `/proc` and hwmon (`coretemp`, `k10temp`, `zenpower`) |
| CPU identity | Model name, online physical core count and logical thread count | `/proc/cpuinfo`; unavailable topology shows `N/A` |
| Hugepages | Used/total page counts and used size for 2 MiB and 1 GiB pages | `/sys/kernel/mm/hugepages` |
| NVIDIA dGPU | Model, utilization, temperature, power draw, VRAM used/total | NVIDIA driver and `nvidia-smi`; first GPU returned |
| Intel iGPU | Utilization, actual/requested frequency, RC6 residency, GPU power where supported | Intel DRM device and driver-specific tools below |
| Ceph | Cluster health, OSD up/total/in counts, used/total capacity, PG count, read/write throughput and IOPS, separate read/write sparklines | Ceph CLI, cluster configuration and readable client keyring |
| ZFS | Imported pool names, health, free/total capacity | OpenZFS `zpool`; read-only pool listing |
| NVMe-oF | Imported block device paths and TCP/RDMA transport; one row per namespace head | Linux block/NVMe sysfs; no `nvme-cli` required |
| Internet routing | Selected default route interface, source address, gateway and metric | `ip -j route show table main` (iproute2) |
| OSPF neighbors | Neighbor router IDs, addresses, states and FULL/total summary | FRR `vtysh`, OSPF neighbor JSON |
| OSPF topology | Router IDs classified as SELF, DIRECT or REMOTE | FRR OSPF router-LSA database; DIRECT means present in the neighbor list |
| BGP | Established/total sessions, peer addresses, remote AS, state and received prefixes | FRR `vtysh`; default-VRF IPv4/IPv6 unicast summary |
| VM networks | Configured local networks with UP/DOWN and interfaces; remote OSPF networks and next hops | Main IPv4 route table filtered by `VM_NETWORKS` |

The network JSON also includes interface operational state, numeric bit rates,
transmit history and temperature for each interface. Ceph JSON additionally
includes available capacity. These are collected even when the default panel
does not display them. Sparklines scale to the largest value in their own
history; they do not represent a fixed link speed or a shared I/O scale.

Intel GPU collection prefers the `xe` driver, using `gputop` and GNU `timeout`.
For `i915`, it uses `intel_gpu_top` JSON output and `timeout`. These tools are
commonly supplied by Intel GPU Tools; availability depends on the distribution.
Xe currently supplies utilization and frequencies only: RC6 and power remain
zero placeholders, not measured values. The desktop user needs permission to
read the relevant DRM/performance counters; configure access according to the
distribution rather than running the entire collector as root.

Default-route selection uses the lowest metric among main-table default routes;
it is not a connectivity probe and does not inspect policy-routing tables.
VM local routes must use protocol `kernel` with no gateway; remote routes must
use protocol `ospf`. BGP-learned VM routes are not included in that list.

### CPU identity details

SYSTEM shows the CPU model and online core/thread counts visible in
`/proc/cpuinfo`, refreshed with system telemetry. Physical cores are counted by
(socket ID, core ID), so SMT siblings are not counted twice. Threads are logical
processor entries. These are OS-visible counts, not per-process CPU affinity or
container quota limits. If topology is absent (for example in some VMs or ARM
systems), core count shows `N/A` rather than assuming one core per thread.
No additional packages or elevated permissions are required.

### Storage details

- **ZFS:** requires `zpool` from the desktop distribution's OpenZFS tools.
  Runs `zpool list -H -p -o name,size,alloc,free,health` without sudo and
  shows every imported pool's health and free/total bytes. Pool `free` is raw
  pool capacity; it is not dataset `available` and does not account for dataset
  quotas, reservations, or all allocation constraints. No pools are imported
  and no ZFS properties are changed. Verify the command as your desktop user;
  if access is denied, configure read-only access according to your platform.
- **NVMe-oF:** reads Linux `/sys/class/block` and NVMe controller attributes;
  no `nvme-cli`, root, discovery, or connection command is needed. Shows
  imported namespace block device paths with `TCP` or `RDMA`, one per line.
  Multipath devices using both transports show `RDMA/TCP`.
  Controller details remain in JSON only. Local PCIe devices, partitions, and
  native multipath controller-path devices (`nvmeXcYnZ`) are excluded from the
  display; the namespace head (`nvmeXnZ`) is shown once.
  This does not discover targets or establish connections.

`NONE` means a successful scan found no pools/devices. `UNAVAILABLE` means a
command, permission, parsing, or sysfs read failed (including a device changing
mid-scan); it is retried at the next refresh rather than reporting zero capacity.
JSON exposes `zfs.pools` and `nvmeof.devices` in addition to display text.

### BGP details

The routing panel uses FRR `vtysh -c 'show bgp summary json'` to report
IPv4/IPv6 unicast in the default VRF. Counts are peer/address-family sessions:
a peer in both families is counted twice. Each entry shows address, remote AS, session state,
and received prefixes (RX). Inactive sessions or missing prefix counts show
`N/A`. An empty peer table shows `NO PEERS`; missing FRR, denied access,
command failure, and unsupported output show `UNAVAILABLE`, with unknown counts
rather than zero. FRR's vtysh access must already be available to the desktop
user (configure the distribution's FRR/vty group permissions if needed); no
sudo or routing configuration changes are performed. Other VRFs and address
families are outside this basic summary.

## Node-specific panels and automatic layout

Use a node JSON profile to select independent panels. Python generates an Eww
configuration in a separate directory; GTK stacks only the selected widgets,
so disabled panels leave no blank slots. One collector is shared by the whole
dashboard and schedules only selected features. In particular, OSPF and BGP
queries can be enabled independently; disabling GPU/Ceph/storage panels skips
their commands entirely.

Available panel names:

| Group | Panel names |
| --- | --- |
| System | `system` (including CPU identity), `hugepages` |
| Network interfaces | `lan`, `wan` |
| GPUs | `intel_gpu`, `nvidia` |
| Storage | `ceph`, `zfs`, `nvmeof` |
| Routing | `internet`, `ospf` (neighbors and topology), `bgp`, `vm` (local and remote) |

Example `~/.config/stella-eww/node.json`:

```json
{
  "panels": ["system", "lan", "zfs", "nvmeof"],
  "columns": 1,
  "column_width": 380,
  "gap": 12,
  "x": 30,
  "y": 70,
  "monitor": 0
}
```

Only `panels` is required. The other defaults are shown above. Panel names must
be unique and at least one must be selected. Panels keep list order, filling
one column from top to bottom before the next; counts are distributed evenly
between columns. Extra empty columns are removed. Widgets use their natural
heights, aligned to the top, and spacing is applied only between present
widgets. `gap` controls both panel and column spacing. Coordinates are pixel
offsets from the monitor's top right.

This is a single window with independent feature panels, not one fixed-position
window per feature. It does not measure available screen height or automatically
move overflowing content to another column. Long peer/device lists can exceed
the screen: adjust `columns`, `column_width`, the selected panels or styling.
Column distribution is by panel count, not measured height. Independent window
dragging and automatic monitor-size detection are not implemented.

Example profiles are provided in `profiles/desktop.json`,
`profiles/storage-node.json` and `profiles/router.json`. Copy one to a local
node configuration and customize it. From the checkout, generate and open:

```sh
python3 -B .local/bin/stella-panels.py ~/.config/stella-eww/node.json --open
```

With the files installed under your home directory, use:

```sh
python3 -B ~/.local/bin/stella-panels.py ~/.config/stella-eww/node.json --open
```

The default generated configuration is `$XDG_CACHE_HOME/stella-eww` (or
`~/.cache/stella-eww`). `--output /path/to/directory` overrides it; the directory
must be empty or previously generated by this helper. The generator does not
overwrite the source Eww configuration. Omit `--open` to generate files only;
`--open` starts/reloads that Eww daemon and reopens `dashboard`. Re-run after
editing the profile or updating the shared widgets/styles. Generated files
reference the source `widgets.yuck` and collector by absolute path, so regenerate
after moving the checkout. `--widgets /path/to/widgets.yuck` can override the
shared widgets location; `eww.scss` is read from the same directory.

Close the generated dashboard using its own configuration directory:

```sh
eww --config ~/.cache/stella-eww close dashboard
```

The original `telemetry-window` and `system-window` remain available with all
features enabled. Before switching to the generated dashboard, close these old
windows with `eww close telemetry-window` and `eww close system-window` to avoid
overlapping windows and duplicate collectors. If using `XDG_CACHE_HOME` or a
custom `--output`, use that path in the close command above.

For collector-only use, `STELLA_PANELS=system,zfs python3 -B .local/bin/eww.py`
selects the same features. Unset `STELLA_PANELS` preserves the all-features
behavior; an empty value disables all features. Disabled top-level sources are
omitted from JSON (network remains an empty object when disabled); consumers
must only reference selected widgets. The generated dashboard supplies loading
values before the first sample. Interface names and cluster settings still
come from `telemetry/config.py`.

## Desktop setup and configuration

Install Eww for the desktop's display backend and Python 3. Install the optional
GPU, Ceph, ZFS and routing tools above only for the features used on that machine.
The collector expects Linux procfs/sysfs; GUI and hardware checks need the target
desktop. It does not configure GPUs, networking, Ceph or hugepages.

Merge these paths into the desktop user's home directory, preserving any
existing configuration:

- `.config/eww/eww.yuck`, `.config/eww/widgets.yuck` and
  `.config/eww/eww.scss` → `~/.config/eww/`
- `.local/bin/eww.py` and `.local/bin/stella-panels.py` → `~/.local/bin/`
- `.local/bin/telemetry/` Python sources → `~/.local/bin/telemetry/`

Keep the entry point and package together. Make the entry point executable:

```sh
chmod +x ~/.local/bin/eww.py
```

Edit `~/.local/bin/telemetry/config.py` for the target machine:

- `INTERFACES`: the LAN default is `N/A` (a placeholder); WAN defaults to
  `wlan0`. Replace these with real interface names; LAN/WAN headings use these
  configured names automatically.
- `CEPH_NAME`: defaults to `client.desktop-widget`.
- `CEPH_KEYRING`: defaults to
  `~/.config/ceph/ceph.client.desktop-widget.keyring`. Supply the machine's Ceph
  configuration and an appropriately scoped read-only monitoring credential;
  keep the keyring private and outside the repository. The collector runs
  `ceph --name ... --keyring ... -s --format json` as the desktop user.
- `VM_NETWORKS`: exact destination prefixes to include in the VM route panels;
  defaults are `172.30.168.0/24`, `172.30.169.0/24`, `172.30.170.0/24`.
- `HISTORY_LENGTH`: defaults to 32 samples.

FRR queries require existing non-root `vtysh` access to the running daemons.
OSPF collection uses `show ip ospf neighbor json` and
`show ip ospf database router json`. Configure the desktop user's FRR group or
socket access according to the distribution; no routing changes are made.

| Setting | Default target interval |
| --- | --- |
| `INTERVAL` (system, network, JSON output loop) | 1 second |
| `NVIDIA_INTERVAL`, `INTEL_GPU_INTERVAL` | 2 seconds |
| `CEPH_INTERVAL`, `ROUTING_INTERVAL` | 5 seconds |
| `ZFS_INTERVAL`, `NVMEOF_INTERVAL` | 5 seconds |

Collectors run sequentially, so slow commands and timeouts can delay updates;
these are target intervals, not guaranteed sampling periods.

To inspect the stream directly (Ctrl-C to stop), then open the desktop panels:

```sh
python3 -B ~/.local/bin/eww.py
# Run the following after stopping the direct collector:
eww daemon
eww open telemetry-window
eww open system-window
```

The right panel contains network, GPU, Ceph and storage widgets; the left
sidecar contains system and routing widgets. Shared feature widgets are in
`widgets.yuck`. Legacy window geometry and monitor selection are in `eww.yuck`;
styling is in `eww.scss`. The current layout uses
monitor 0 and fixed offsets. Eww starts its own collector through `deflisten`.
Restart the collector/Eww after changing Python configuration.

Older collectors have different fallback behavior: missing GPU tools set
`available=false` with an unavailable name, and Ceph reports `UNAVAILABLE`.
Some legacy numeric fields still default to zero, including unreadable network
counters and some system metrics. Missing temperatures show `N/A`; missing
routes or OSPF database data may appear empty. These fallbacks do not prove a
healthy device or zero activity. Storage/BGP status handling is described in the feature notes above.

## Validation

Run the test suite without writing Python bytecode:

```sh
python3 -B -m unittest discover -s tests -v
```

The tests cover collectors, command/sysfs fixtures, profile validation,
repeatable generation, and execution of the generated collector command. Real
GPU/storage/FRR behavior and Eww rendering need validation on the target desktop.
