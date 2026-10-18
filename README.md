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
  imported namespace block devices using TCP or RDMA, their controller state,
  and transport address. Local PCIe devices and partitions are excluded.
  Native multipath namespace heads list the matching controller paths as well.
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
