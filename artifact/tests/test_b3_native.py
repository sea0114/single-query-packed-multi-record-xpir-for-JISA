#!/usr/bin/env python3
"""Native B3 functional coverage. These observations are never performance data."""
import argparse
import datetime
import hashlib
import itertools
import json
import os
import pathlib
import resource
import select
import signal
import struct
import subprocess
import time

ROOT=pathlib.Path(__file__).resolve().parents[2]
LABEL='FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE'
SEED=0x8c3f47282900cee8
MASK=(1<<64)-1

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,indent=2);f.write('\n')

def normalize(x):
    if isinstance(x,dict):
        return {k:(v if k.endswith(('hash','fingerprint','hex')) or k in ('actual_hex','expected_hex') else normalize(v)) for k,v in x.items()}
    if isinstance(x,list):return [normalize(v) for v in x]
    if isinstance(x,str):
        if x in ('true','false'):return x=='true'
        if x.isdecimal():return int(x)
    return x

def fixture(N,ell,kind='pseudorandom'):
    state=SEED^(N<<32)^ell;rows=[]
    for i in range(N):
        row=bytearray()
        for _ in range((ell+63)//64):
            state=(state+0x9e3779b97f4a7c15)&MASK;z=state
            z=((z^(z>>30))*0xbf58476d1ce4e5b9)&MASK
            z=((z^(z>>27))*0x94d049bb133111eb)&MASK
            row.extend((z^(z>>31)).to_bytes(8,'little'))
        row=row[:(ell+7)//8]
        if kind=='zero':row=bytearray(len(row))
        elif kind=='max':row=bytearray([255])*len(row)
        elif kind=='alternating':row=bytearray(0x55 if (i+b)%2 else 0xaa for b in range(len(row)))
        elif kind!='pseudorandom':raise ValueError(kind)
        if ell%8:row[-1]&=(1<<(ell%8))-1
        rows.append(bytes(row))
    return rows

def encoded(raw,ell,a):
    L=((ell+7)//8+4095)//4096;out=[]
    for row in raw:
        b=bytearray(L*4096*a)
        for j,value in enumerate(row):b[j*a]=value
        out.append(bytes(b))
    return out

def stamp():return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)

def worker_setup(cpu):
    def apply():
        os.sched_setaffinity(0,{cpu})
        resource.setrlimit(resource.RLIMIT_AS,(8*2**30,)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    return apply

def run_case(binary,case,out,all_keys):
    out.mkdir(parents=True,exist_ok=False)
    raw=fixture(8,case['ell_bits'],case['fixture'])
    enc=encoded(raw,case['ell_bits'],case['alpha'])
    raw_hash=hashlib.sha256(b''.join(raw)).hexdigest()
    enc_hash=hashlib.sha256(b''.join(enc)).hexdigest()
    count=1 if case['method']=='packed' else case['alpha']
    cpus=sorted(os.sched_getaffinity(0));children=[];ready=set();done=set()
    release=False;validation=False;deadline=time.monotonic()+60
    try:
        for i in range(count):
            rr,rw=os.pipe();gr,gw=os.pipe();stem=out/f'worker{i}'
            targets=case['target_tuple'] if count==1 else [case['target_tuple'][i]]
            job={'N':8,'ell_bits':case['ell_bits'],'alpha':case['alpha'],'rho_0':8,'w':8*case['alpha'],
                'targets':targets,'method':case['method'],'worker_index':i,'preprocess_mode':case['view'],
                'fixture':case['fixture'],'timing_label':LABEL,'ready_fd':rw,'go_fd':gr}
            write(stem.with_suffix('.job.json'),job)
            stdout=stem.with_suffix('.stdout').open('xb');stderr=stem.with_suffix('.stderr').open('xb')
            p=subprocess.Popen([str(binary),str(stem.with_suffix('.job.json')),str(stem.with_suffix('.result.json'))],
                pass_fds=(rw,gr),stdout=stdout,stderr=stderr,
                env={**os.environ,'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1'},
                preexec_fn=worker_setup(cpus[i%len(cpus)]),start_new_session=True)
            os.close(rw);os.close(gr)
            children.append({'p':p,'rr':rr,'gw':gw,'stem':stem,'stdout':stdout,'stderr':stderr,'targets':targets})
        while not validation:
            if time.monotonic()>deadline:raise TimeoutError('Functional-only task timeout')
            wanted=ready if not release else done
            fds=[c['rr'] for c in children if c['rr'] not in wanted]
            for fd in select.select(fds,[],[],0.05)[0]:
                value=os.read(fd,1)
                if value!=(b'R' if not release else b'D'):raise RuntimeError('Bad worker barrier byte '+repr(value))
                wanted.add(fd)
            if not release and len(ready)==count:
                timestamp=stamp()+5_000_000
                for c in children:os.write(c['gw'],struct.pack('<Q',timestamp))
                release=True
            elif release and len(done)==count:
                for c in children:os.write(c['gw'],b'V')
                validation=True
        rows=[]
        for c in children:
            code=c['p'].wait(timeout=max(1,deadline-time.monotonic()))
            if code!=0:raise RuntimeError('Worker exit '+str(code)+' '+c['stem'].with_suffix('.stderr').read_text())
            row=normalize(json.loads(c['stem'].with_suffix('.result.json').read_text()))
            assert row['status']=='COMPLETE' and row['output_verified']
            assert row['actual_hex']==[raw[t].hex() for t in c['targets']]
            assert row['db_fixture_hash']==raw_hash and row['encoded_db_hash']==enc_hash
            assert row['variant_label']=='RECONSTRUCTED_SOURCE_VARIANT' and row['implementation_id']=='B3-'+case['implementation']
            assert row['timing_label']==LABEL and row['timing_collected'] is False
            assert not any(k in row for k in ('task_start_ns','task_end_ns','task_total_ns','phase_ns','cpu_user_ns','cpu_system_ns','peak_rss_kib'))
            J=(case['ell_bits']+7)//8;L=(J+4095)//4096
            assert (row['J'],row['L'])==(J,L)
            assert row['query_ciphertexts']==8 and row['reply_ciphertexts']==L
            assert row['query_payload_bytes']==8*131072 and row['reply_payload_bytes']==L*131072
            assert row['coefficient_checks']==L*4096 and row['segment_checks']==L*4096*len(c['targets'])
            assert row['record_checks']==len(c['targets'])
            assert row['all_coefficients_exact'] and row['all_segments_exact'] and row['padding_exact']
            assert row['key_generation_calls']==1 and row['rng_calls']==18 and row['validation_release_seen']
            assert row['omp_max_threads']==1
            assert row['key_fingerprint'] not in all_keys,'Duplicate fresh-key fingerprint'
            all_keys.add(row['key_fingerprint'])
            rows.append({'result':c['stem'].with_suffix('.result.json').relative_to(ROOT).as_posix(),
                'sha256':sha(c['stem'].with_suffix('.result.json')),'key_fingerprint':row['key_fingerprint'],
                'coefficient_checks':row['coefficient_checks'],'segment_checks':row['segment_checks'],
                'reply_ciphertexts':row['reply_ciphertexts']})
        summary={**case,'N':8,'J':J,'L':L,'status':'PASS','timing_label':LABEL,'timing_collected':False,
            'workers':rows,'task_reply_ciphertexts':sum(r['reply_ciphertexts'] for r in rows),
            'db_fixture_hash':raw_hash,'encoded_db_hash':enc_hash}
        write(out/'functional_summary.json',summary)
        return summary
    finally:
        for c in children:
            if c['p'].poll() is None:
                os.killpg(c['p'].pid,signal.SIGKILL);c['p'].wait()
            os.close(c['rr']);os.close(c['gw']);c['stdout'].close();c['stderr'].close()

def matrix():
    points=[('I1',2,512),('I1',2,2048),('I2',2,512),('I2',2,2048),('I2',3,256)]
    points += [('I2',4,e) for e in (4096,8192,12288,16384,32767,32768,32769,65536)]
    cases=[]
    for impl,a,ell in points:
        for pattern,view in itertools.product(('zero','max','alternating','pseudorandom'),('COLD','ONLINE')):
            # Both orderings occur for every fixture and length, across the two views.
            ts=[(2*r+1)*8//(2*a) for r in range(a)]
            if view=='ONLINE':ts.reverse()
            for method in ('packed','repeated'):
                cases.append({'implementation':impl,'alpha':a,'ell_bits':ell,'fixture':pattern,'view':view,
                    'target_tuple':ts,'method':method})
    return cases

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',default=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));p.add_argument('--quick',action='store_true');a=p.parse_args()
    current=json.loads((ROOT/'artifact/native/current_build.json').read_text())
    manifest_path=ROOT/current['build_manifest'];assert sha(manifest_path)==current['sha256']
    manifest=json.loads(manifest_path.read_text())
    for b in current['binaries'].values():assert sha(ROOT/b['path'])==b['sha256']
    out=ROOT/'artifact/results/native_validation'/a.run_id;out.mkdir(parents=True,exist_ok=False)
    cases=matrix()
    if a.quick:cases=[cases[6],cases[7],cases[-2],cases[-1]]
    write(out/'functional_matrix.json',cases)
    results=[];failures=[];keys=set()
    for i,case in enumerate(cases):
        try:
            result=run_case(ROOT/current['binaries'][case['implementation']]['path'],case,out/f'{i:04d}',keys)
            results.append(result)
        except Exception as e:
            failure={'case_index':i,'case':case,'error':repr(e)};failures.append(failure)
            write(out/f'{i:04d}'/'failure.json',failure)
        print(json.dumps({'accounted':i+1,'of':len(cases),'case':case,'pass':len(results),'fail':len(failures)}),flush=True)
    result={'status':'PASS' if not failures else 'FAIL','timing_label':LABEL,'formal_observations':0,
        'build_manifest':current['build_manifest'],'build_manifest_sha256':current['sha256'],
        'tests_script_sha256':sha(__file__),'expected_tasks':len(cases),'successful_tasks':len(results),'failed_tasks':len(failures),
        'successful_worker_processes':sum(len(r['workers']) for r in results),'unique_key_fingerprints':len(keys),
        'matrix_sha256':sha(out/'functional_matrix.json'),'results':results,'failures':failures,
        'limitations':['Finite functionality only; no security/sampler bridge/reliability certification.','No timings emitted; not benchmark data.']}
    write(out/'validation_report.json',result)
    print(json.dumps({k:result[k] for k in ('status','expected_tasks','successful_tasks','failed_tasks','successful_worker_processes')}),flush=True)
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
