#!/usr/bin/env python3
"""Build the isolated core runner against immutable pinned upstream files.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from common import BACKEND_COMMIT, CORE, ROOT, sha, write_new

SOURCES = ['crypto/AbstractPublicParameters.cpp', 'crypto/HomomorphicCrypto.cpp',
           'crypto/LatticesBasedCryptosystem.cpp', 'crypto/NFLLWE.cpp',
           'crypto/NFLLWEPublicParameters.cpp', 'crypto/NFLlib.cpp',
           'crypto/NFLParams.cpp', 'crypto/prng/fastrandombytes.cpp',
           'crypto/prng/randombytes.cpp', 'crypto/prng/crypto_stream_salsa20_amd64_xmm6.s',
           'pir/replyGenerator/GenericPIRReplyGenerator.cpp',
           'pir/replyGenerator/PIRReplyGeneratorNFL_internal.cpp',
           'pir/dbhandlers/DBHandler.cpp', 'pir/dbhandlers/DBGenerator.cpp']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--build-id', default='build_001')
    args = parser.parse_args()
    for name in (args.run_id, args.build_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('run/build identifiers must be simple leaf names')
    upstream = ROOT / 'native_xpir/upstream'
    pin = json.loads((ROOT / 'revision_notes/B0_logs/build_environment.json').read_text())
    pinned = pin['upstream_files']
    for name, digest in pinned.items():
        if sha(ROOT / name) != digest:
            raise ValueError('pinned source changed: ' + name)
    build = CORE / 'runs' / args.run_id / 'build' / args.build_id
    build.mkdir(parents=True, exist_ok=False)
    compiler = Path(shutil.which('g++')).resolve()
    flags = ['-std=gnu++11', '-O2', '-g', '-fopenmp', '-DMULTI_THREAD',
             '-maes', '-mavx2', '-DSHARED_C', '-include', 'cstdint',
             '-I' + str(upstream), '-I' + str(upstream / 'crypto'),
             '-I' + str(upstream / 'pir/replyGenerator'),
             '-I' + str(ROOT / 'native_xpir'), '-I' + str(CORE / 'src')]
    # Preserve the known compatible-header fallback only when it actually exists.
    fallback = Path('/var/tmp/s4f-sage/include')
    if fallback.is_dir():
        flags += ['-idirafter', str(fallback)]
    sources = [upstream / name for name in SOURCES] + [CORE / 'src/core_native.cpp']
    links = ['-Wl,--wrap=crypto_stream_salsa20_amd64_xmm6', '-lboost_thread',
             '-lboost_system', '-lgmpxx', '-lgmp', '-lmpfr', '-l:libcrypto.so.3', '-pthread']
    commands, objects = [], []
    status = 'BUILD_FAILED'
    error = None
    binary = build / 'core_native'
    with (build / 'build.log').open('xb') as log:
        try:
            for index, source in enumerate(sources):
                obj = build / f'{index:02}_{source.stem}.o'
                command = [str(compiler), *flags, '-MD', '-MF', str(obj) + '.d',
                           '-c', str(source), '-o', str(obj)]
                commands.append(command)
                log.write(('COMMAND ' + shlex.join(command) + '\n').encode())
                log.flush()
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                objects.append(obj)
            command = [str(compiler), *flags, *map(str, objects), *links, '-o', str(binary)]
            commands.append(command)
            log.write(('COMMAND ' + shlex.join(command) + '\n').encode())
            log.flush()
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            status = 'BUILT_NOT_FUNCTIONALLY_VALIDATED'
        except subprocess.CalledProcessError as exc:
            error = {'returncode': exc.returncode, 'command': exc.cmd}
    libraries, dependencies = {}, {}
    for dep in build.glob('*.d'):
        # GCC dependency names escape spaces and join continued lines.
        text = dep.read_text().replace('\\\n', '')
        for name in shlex.split(text.split(':', 1)[1]):
            p = Path(name)
            if p.is_file():
                dependencies[str(p.resolve())] = sha(p)
    ldd = subprocess.check_output(['ldd', str(binary)], text=True) if binary.is_file() else ''
    for name in re.findall(r'(?:=> )?(/[^\s]+)', ldd):
        p = Path(name)
        if p.is_file():
            libraries[str(p.resolve())] = sha(p)
    result = {'status': status, 'error': error, 'run_id': args.run_id,
              'build_id': args.build_id,
              'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'backend_commit': BACKEND_COMMIT, 'upstream_files': pinned,
              'source_hashes': {str(p.relative_to(ROOT)): sha(p) for p in sources +
                                list((CORE / 'src').glob('*.hpp'))},
              'compiler': str(compiler), 'compiler_sha256': sha(compiler),
              'compiler_version': subprocess.check_output([str(compiler), '--version'], text=True),
              'flags': flags, 'links': links, 'commands': commands,
              'dependencies': dependencies, 'libraries': libraries, 'ldd': ldd,
              'binary': str(binary.relative_to(ROOT)),
              'binary_sha256': sha(binary) if binary.is_file() else None}
    write_new(build / 'build_manifest.json', result)
    print(json.dumps({'status': status, 'manifest': str(build / 'build_manifest.json'),
                      'error': error}))
    if error:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
