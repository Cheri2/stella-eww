# stella-eww
my eww setup

## Storage monitoring

The storage section refreshes every 5 seconds (`ZFS_INTERVAL` and
`NVMEOF_INTERVAL` in `.local/bin/telemetry/config.py`).

- **ZFS:** requires `zpool` from the desktop distribution's OpenZFS tools.
  Runs `zpool list -H -p -o name,size,alloc,free,health` without sudo and
  shows every imported pool's health and free/total bytes. Pool `free` is raw
  pool capacity; it is not dataset `available` and does not account for dataset
  quotas, reservations, or all allocation constraints. No pools are imported
  and no ZFS properties are changed. Verify the command as your desktop user;
  if access is denied, configure read-only access according to your platform.
- **NVMe-oF:** reads Linux `/sys/class/block` and NVMe controller attributes;
  no `nvme-cli`, root, discovery, or connection command is needed. Shows
  imported namespace block device paths using TCP or RDMA, one per line.
  Controller details remain in JSON only. Local PCIe devices, partitions, and
  native multipath controller-path devices (`nvmeXcYnZ`) are excluded from the
  display; the namespace head (`nvmeXnZ`) is shown once.
  This does not discover targets or establish connections.

`NONE` means a successful scan found no pools/devices. `UNAVAILABLE` means a
command, permission, parsing, or sysfs read failed (including a device changing
mid-scan); it is retried at the next refresh rather than reporting zero capacity.
JSON exposes `zfs.pools` and `nvmeof.devices` in addition to display text.

Run the storage tests without writing Python bytecode:

```sh
python3 -B -m unittest discover -s tests -v
```

The tests use command/sysfs fixtures; real ZFS, NVMe-oF, and Eww rendering need
validation on the target desktop.

## BGP summary

The routing panel uses FRR `vtysh -c 'show bgp summary json'` to report
IPv4/IPv6 unicast in the default VRF. It refreshes with `ROUTING_INTERVAL`
(default 5 seconds). Counts are peer/address-family sessions: a peer in both
families is counted twice. Each entry shows address, remote AS, session state,
and received prefixes (RX). Inactive sessions or missing prefix counts show
`N/A`. An empty peer table shows `NO PEERS`; missing FRR, denied access,
command failure, and unsupported output show `UNAVAILABLE`, with unknown counts
rather than zero. FRR's vtysh access must already be available to the desktop
user (configure the distribution's FRR/vty group permissions if needed); no
sudo or routing configuration changes are performed. Other VRFs and address
families are outside this basic summary.
