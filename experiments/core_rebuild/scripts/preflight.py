#!/usr/bin/env python3
"""Read-only environment/process inventory, or write one new run record.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def inventory():
    processes = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            cmd = (path / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            processes.append({'pid': int(path.name), 'ppid': int(stat[1]),
                              'start_ticks': int(stat[19]), 'command': cmd})
        except (OSError, ValueError, IndexError):
            continue
    values = {'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'platform': platform.platform(), 'machine': platform.machine(),
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'affinity': sorted(os.sched_getaffinity(0)), 'processes': processes,
              'lscpu': subprocess.check_output(['lscpu', '-J'], text=True),
              'meminfo': Path('/proc/meminfo').read_text(),
              'loadavg': Path('/proc/loadavg').read_text(),
              'cgroup': Path('/proc/self/cgroup').read_text(),
              'cgroup_mounts': [s for s in Path('/proc/mounts').read_text().splitlines()
                                if 'cgroup' in s],
              'tools': {x: shutil.which(x) for x in ('python3', 'g++', 'taskset')},
              'python': platform.python_version(),
              'disk': dict(zip(('total', 'used', 'free'), shutil.disk_usage(Path.cwd())))}
    if values['tools']['g++']:
        values['compiler'] = subprocess.check_output(['g++', '--version'], text=True)
    values['existing_lock_paths'] = []
    root = Path(__file__).resolve().parents[3]
    for name in ('experiments/measurement.lock', 'measurement.lock', '.measurement.lock'):
        p = root / name
        if p.exists():
            values['existing_lock_paths'].append({'path': name, 'content': p.read_text()})
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = inventory()
    if args.out:
        root = Path(__file__).resolve().parents[1]
        target = args.out.resolve()
        if not target.is_relative_to((root / 'runs').resolve()):
            raise ValueError('preflight output must be under core_rebuild/runs')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
        print(json.dumps({'written': str(target), 'platform': result['platform'],
                          'affinity': result['affinity'], 'processes': result['processes'],
                          'locks': result['existing_lock_paths']}))
    else:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
