#!/usr/bin/env python3
"""Run required small synthetic pipeline checks outside measurement phases.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from common import CORE, sha, write_new

p=argparse.ArgumentParser();p.add_argument('--run-id',required=True)
p.add_argument('--check-id',default='pipeline_checks');p.add_argument('--ast-only',action='store_true');a=p.parse_args()
if Path(a.check_id).name!=a.check_id or Path(a.run_id).name!=a.run_id:
    raise ValueError('Identifiers must be simple leaf names')
output=CORE/'runs'/a.run_id/'functional'/a.check_id
output.mkdir(parents=True,exist_ok=False)
tmp=output/'tmp';tmp.mkdir()
files=list((CORE/'scripts').glob('*.py'))+list((CORE/'tests').glob('*.py'))
for path in files:ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
environment=dict(os.environ,TMPDIR=str(tmp))
command=[sys.executable,'-B','-m','unittest','discover','-s',str(CORE/'tests'),'-p','test_*.py','-v']
with (output/'tests.log').open('xb') as stream:
    if a.ast_only:
        stream.write(('AST PASS '+str(len(files))+' scripts/tests; prior synthetic tests not rerun\n').encode())
        code=0
    else:
        process=subprocess.run(command,cwd=CORE,env=environment,stdout=stream,stderr=subprocess.STDOUT)
        code=process.returncode
write_new(output/'report.json',{'status':'PASS' if code==0 else 'FAILED',
                               'returncode':code,'command':command if not a.ast_only else None,
                               'ast_checked':len(files),'source_hashes':{str(x.relative_to(CORE)):sha(x) for x in files},
                               'synthetic_only':True,'native_executions':0,'formal_samples':0})
print((output/'tests.log').read_text());raise SystemExit(code)
