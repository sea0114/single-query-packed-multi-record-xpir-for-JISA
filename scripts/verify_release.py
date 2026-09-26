#!/usr/bin/env python3
"""Verify distributed files and optionally restored data; never execute experiments.

SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,csv,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--data',action='store_true');a=ap.parse_args()
    with (ROOT/'manifests/release-files.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    if a.data:rows+=json.loads((ROOT/'manifests/data-archives.json').read_text())['members']
    for row in rows:
        p=ROOT/row['path'];assert p.resolve().is_relative_to(ROOT) and p.is_file(),row['path']
        b=p.read_bytes();assert len(b)==int(row['bytes']) and hashlib.sha256(b).hexdigest()==row['sha256'],row['path']
    print(json.dumps({'status':'PASS','verified_files':len(rows),'restored_data_checked':a.data,'new_observations':0}))
if __name__=='__main__':main()
