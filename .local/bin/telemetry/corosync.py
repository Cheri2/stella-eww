"""Corosync membership/quorum; no pcs, Pacemaker, or elevated collector."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def initial_corosync(state="LOADING", reason=""):
    return {"available": False, "state": state, "quorate": None,
            "node_count": None, "local_node_id": None, "members": [],
            "expected_votes": None, "total_votes": None,
            "text": state + (f"\n{reason}" if reason else "")}


def parse_status(output, returncode):
    if returncode not in (0, 2):
        raise ValueError("Query failed (IPC access or service unavailable)")
    fields = {}
    header = None
    members = []
    for line in output.splitlines():
        words = line.split()
        if words and words[0] == "Nodeid":
            if words not in (["Nodeid", "Votes", "Qdevice", "Name"],
                             ["Nodeid", "Votes", "Name"], ["Nodeid", "Name"]):
                raise ValueError("Unsupported membership columns")
            header = words
        elif header and words:
            # The synthetic qdevice row omits its Qdevice status column.
            if int(words[0], 16 if words[0].startswith('0x') else 10) == 0:
                continue
            values = line.split(None, len(header) - 1)
            if len(values) != len(header):
                raise ValueError("Incomplete membership row")
            row = dict(zip(header, values))
            node_id = int(row['Nodeid'], 16 if row['Nodeid'].startswith('0x') else 10)
            name = row['Name']
            local = name.endswith(' (local)')
            members.append({"node_id": node_id, "name": name.removesuffix(' (local)'),
                            "local": local, "votes": int(row['Votes']) if 'Votes' in row else None})
        elif ':' in line:
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()
    quorate = fields.get('Quorate')
    count = int(fields['Nodes'])
    local_id = int(fields['Node ID'], 16 if fields['Node ID'].startswith('0x') else 10)
    if (quorate not in {'Yes', 'No'} or (returncode == 0) != (quorate == 'Yes')
            or not header or count <= 0 or count != len(members)
            or len({m['node_id'] for m in members}) != count
            or sum(m['local'] and m['node_id'] == local_id for m in members) != 1):
        raise ValueError("Incomplete or inconsistent quorum status")
    expected = int(fields['Expected votes']) if 'Expected votes' in fields else None
    total = int(fields['Total votes']) if 'Total votes' in fields else None
    if any(v is not None and v < 0 for v in (expected, total, *(m['votes'] for m in members))):
        raise ValueError("Invalid vote count")
    state = 'QUORATE' if quorate == 'Yes' else 'NOT QUORATE'
    text = f'{state}  {count} members'
    if total is not None and expected is not None:
        text += f'\nVotes {total}/{expected}'
    text += '\n' + '\n'.join(
        f'{m["node_id"]}  {m["name"]}' + ('  LOCAL' if m['local'] else '')
        for m in members
    )
    return {"available": True, "state": state, "quorate": quorate == 'Yes',
            "node_count": count, "local_node_id": local_id, "members": members,
            "expected_votes": expected, "total_votes": total, "text": text}


def query_status():
    result = subprocess.run(
        ['corosync-quorumtool', '-s', '-p', '-i'], capture_output=True,
        text=True, timeout=3, check=False, env={**os.environ, 'LC_ALL': 'C'},
    )
    return {"collected_at": time.time(), "returncode": result.returncode, "stdout": result.stdout}


def get_corosync(snapshot=None, max_age=30):
    try:
        if snapshot is None:
            data = query_status()
        else:
            with Path(snapshot).open() as stream:
                raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Snapshot too large')
            data = json.loads(raw)
            if not isinstance(data, dict) or type(data.get('collected_at')) not in (int, float):
                raise ValueError('Invalid snapshot')
            age = time.time() - data['collected_at']
            if not 0 <= age <= max_age:
                return initial_corosync('STALE', 'Snapshot expired or clock changed')
        if type(data.get('returncode')) is not int or not isinstance(data.get('stdout'), str):
            raise ValueError('Invalid query result')
        return parse_status(data['stdout'], data['returncode'])
    except FileNotFoundError:
        return initial_corosync('UNAVAILABLE', 'Snapshot missing' if snapshot is not None else 'corosync-quorumtool missing')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return initial_corosync('UNAVAILABLE', 'Check IPC access/service or snapshot')


def write_snapshot(destination):
    """Publish only fixed query results, atomically, in an admin-owned directory."""
    try:
        data = query_status()
    except (OSError, subprocess.SubprocessError):
        data = {"collected_at": time.time(), "returncode": 1, "stdout": ""}
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-snapshot', required=True, type=Path)
    args = parser.parse_args()
    write_snapshot(args.write_snapshot)
