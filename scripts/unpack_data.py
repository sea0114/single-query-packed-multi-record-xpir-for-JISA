#!/usr/bin/env python3
"""Verify and restore versioned evidence without overwriting different files.

SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path,PurePosixPath
import hashlib,json,tarfile
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    manifest=json.loads((ROOT/'manifests/data-archives.json').read_text(encoding='utf-8'))
    archive=ROOT/manifest['archive'];assert sha(archive.read_bytes())==manifest['sha256'],'Archive SHA256 mismatch'
    expected={r['path']:r for r in manifest['members']};prepared=[]
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers();assert len(members)==len(expected) and len({m.name for m in members})==len(members)
        for member in members:
            rel=PurePosixPath(member.name)
            assert member.isfile() and not rel.is_absolute() and '..' not in rel.parts and '\\' not in member.name
            assert member.name in expected and member.size==expected[member.name]['bytes']
            p=ROOT.joinpath(*rel.parts);assert p.resolve().is_relative_to(ROOT)
            for node in (p,*p.parents):
                if node==ROOT:break
                assert not node.is_symlink() and not getattr(node,'is_junction',lambda:False)()
            data=tar.extractfile(member).read();assert sha(data)==expected[member.name]['sha256']
            if p.exists():assert p.is_file() and sha(p.read_bytes())==sha(data),'Different existing file: '+member.name
            prepared.append((p,data))
    restored=0
    for p,data in prepared:
        if p.exists():continue
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(data)
        restored+=1
    print(json.dumps({'status':'PASS','verified':len(prepared),'restored':restored,'archive_sha256':manifest['sha256']}))
if __name__=='__main__':main()
