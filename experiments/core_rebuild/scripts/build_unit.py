#!/usr/bin/env python3
"""Build native functional tests separately from measured runner.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import json
from pathlib import Path
import subprocess
from common import CORE, sha, write_new

p=argparse.ArgumentParser()
p.add_argument('--manifest',type=Path,required=True)
a=p.parse_args()
manifest=json.loads(a.manifest.read_text())
build=a.manifest.resolve().parent
output=build/'unit'
output.mkdir(exist_ok=False)
command=[manifest['compiler'],*manifest['flags'],str(CORE/'tests/test_native_unit.cpp'),
         *[str(path) for path in sorted(build.glob('*.o')) if path.name!='14_core_native.o'],
         *[flag for flag in manifest['links'] if not flag.startswith('-Wl,--wrap=')],
         '-o',str(output/'test_native_unit')]
with (output/'build.log').open('xb') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
write_new(output/'build_manifest.json',{'command':command,'returncode':result.returncode,
                                      'source_sha256':sha(CORE/'tests/test_native_unit.cpp'),
                                      'binary_sha256':sha(output/'test_native_unit') if result.returncode==0 else None})
print(json.dumps({'returncode':result.returncode,'binary':str(output/'test_native_unit')}))
raise SystemExit(result.returncode)
