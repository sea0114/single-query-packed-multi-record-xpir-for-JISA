"""Independent exec workers with one common release and a post-completion validation barrier."""
from b2b_common import *
from b2b_schema import normalize,validate
import time,struct,subprocess,resource,signal,select,shutil
NOW=lambda:time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
def preexec(core,caps):
    def setup():
        os.sched_setaffinity(0,[core]);resource.setrlimit(resource.RLIMIT_AS,(caps['per_worker_address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(caps['per_file_bytes'],)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    return setup
def sample(pid):
    try:
        fields={}
        for s in Path(f'/proc/{pid}/status').read_text().splitlines():
            if s.startswith(('VmRSS:','VmSize:','Threads:')):
                k,v,*_=s.split();fields[k[:-1]]=int(v)
        return fields
    except (FileNotFoundError,ProcessLookupError):return {}
def size_tree(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
def release_ready(children,ready,clock=NOW):
    """Only a complete READY set can obtain the shared future release."""
    if ready!={c['rr'] for c in children}:return None
    release=clock()+5_000_000
    for c in children:os.write(c['gw'],struct.pack('<Q',release))
    return release
def release_validation(children,done):
    if done!={c['rr'] for c in children}:return False
    for c in children:os.write(c['gw'],b'V')
    return True
def aggregate(workers):
    intervals=[dict(start_ns=w['task_start_ns'],end_ns=w['task_end_ns']) for w in workers if w.get('task_start_ns') is not None and w.get('task_end_ns') is not None]
    def total(k): return sum(w[k] for w in workers) if all(w.get(k) is not None for w in workers) else None
    start=min(x['start_ns'] for x in intervals) if len(intervals)==len(workers) and workers else None
    end=max(x['end_ns'] for x in intervals) if start is not None else None
    u=total('cpu_user_ns');s=total('cpu_system_ns')
    return dict(worker_intervals=intervals,task_start_ns=start,task_end_ns=end,task_total_ns=end-start if start is not None else None,start_skew_ns=max(x['start_ns'] for x in intervals)-start if start is not None else None,cpu_user_ns=u,cpu_system_ns=s,aggregate_cpu_ns=u+s if u is not None and s is not None else None,phase_ns={p:sum(w['phase_ns'][p] for w in workers) if all(w.get('phase_ns',{}).get(p) is not None for w in workers) else None for p in PHASES},phase_aggregation='aggregate phase work; not critical-path phase latency',**{k:total(k) for k in ('query_ciphertexts','reply_ciphertexts','query_payload_bytes','reply_payload_bytes','peak_rss_kib')})
def run_task(config,p,entry,out,functional=False,release=None):
    if functional:
        if p['N']!=8 or p['ell_bits']!=256 or entry['method']!='packed':raise ValueError('Only one tiny packed smoke per alpha is authorized during freeze')
    elif release is None or release.get('status')!='PASS' or release.get('freeze_manifest_sha256')!=sha(MANIFEST):
        raise ValueError('Formal execution requires a fresh verified release and explicit execution-stage invocation')
    count=1 if entry['method']=='packed' else p['alpha']; caps=config['resource_caps'];cores=config['concurrency']['parent_affinity']; partitions=[[cores[i]] for i in range(count)]
    if count>4:raise ValueError('Process cap')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if shutil.disk_usage(out).free<caps['disk_free_reserve_bytes']:raise RuntimeError('Free-disk reserve')
    base={'stage':'B2-B','timing_label':LABEL if functional else 'FORMAL',**entry,**{k:p[k] for k in ('point_id','alpha','rho_0','w','N','ell_bits','J','L','target_tuple')},'transport_bytes':'NOT_MEASURED','backend_commit':COMMIT,'binary_sha256':config['build']['binary_sha256']}
    if not functional:base['freeze_manifest_sha256']=sha(MANIFEST)
    children=[];ready=set();done=set();closed=set();release_ns=None;validation_released=False;failure=None;reason=''
    began=NOW();parent_usage=resource.getrusage(resource.RUSAGE_SELF);original=os.sched_getaffinity(0)
    os.sched_setaffinity(0,cores)
    def terminate():
        for c in children:
            proc=c['process']
            if proc.returncode is None:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                _,st,ru=os.wait4(proc.pid,0);proc.returncode=os.waitstatus_to_exitcode(st);c['usage']=ru
    try:
        for i in range(count):
            rr,rw=os.pipe();gr,gw=os.pipe();stem=out/f'worker{i}'
            t=p['target_tuple'] if entry['method']=='packed' else [p['target_tuple'][i]]
            job=dict(p,targets=t,method=entry['method'],worker_index=i,preprocess_mode=entry['view'],timing_label=base['timing_label'],ready_fd=rw,go_fd=gr)
            write(stem.with_suffix('.job.json'),job)
            stdout=stem.with_suffix('.stdout').open('xb');stderr=stem.with_suffix('.stderr').open('xb')
            try:
                proc=subprocess.Popen([str(ROOT/config['build']['binary']),str(stem.with_suffix('.job.json')),str(stem.with_suffix('.result.json'))],stdout=stdout,stderr=stderr,env={**os.environ,'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1'},pass_fds=(rw,gr),preexec_fn=preexec(cores[i],caps),start_new_session=True)
            except Exception:
                for fd in (rr,rw,gr,gw):os.close(fd)
                stdout.close();stderr.close();raise
            os.close(rw);os.close(gr)
            children.append(dict(process=proc,rr=rr,gw=gw,stem=stem,stdout=stdout,stderr=stderr,usage=None,targets=t,max_threads=0))
        while any(c['process'].returncode is None for c in children):
            rss=0;vm=0
            if NOW()-began>caps['wall_timeout_ns']:failure='TIMEOUT';reason='Whole-task timeout including staging and validation'
            for c in children:
                proc=c['process']
                if proc.returncode is not None:continue
                sm=sample(proc.pid);rss+=sm.get('VmRSS',0)*1024;vm+=sm.get('VmSize',0)*1024;c['max_threads']=max(c['max_threads'],sm.get('Threads',0))
                pid,st,ru=os.wait4(proc.pid,os.WNOHANG)
                if pid:
                    proc.returncode=os.waitstatus_to_exitcode(st);c['usage']=ru
                    if proc.returncode not in (0,20):failure='RESOURCE_LIMIT' if proc.returncode==-signal.SIGXFSZ else 'RUNTIME_FAIL';reason=f'Worker exit {proc.returncode}'
                    elif proc.returncode==0 and not validation_released:failure='RUNTIME_FAIL';reason='Worker exited before completion barrier'
            if rss>caps['aggregate_rss_bytes'] or vm>caps['aggregate_address_space_bytes']:failure='RESOURCE_LIMIT';reason='Aggregate worker RSS/address-space threshold'
            if sample(os.getpid()).get('VmRSS',0)*1024>caps['parent_rss_bytes']:failure='RESOURCE_LIMIT';reason='Parent RSS threshold'
            if size_tree(out)>caps['task_disk_bytes']:failure='RESOURCE_LIMIT';reason='Task disk/log threshold'
            if shutil.disk_usage(out).free<caps['disk_free_reserve_bytes']:failure='RESOURCE_LIMIT';reason='Free-disk reserve'
            if failure:terminate();break
            awaiting=ready if release_ns is None else done
            if not validation_released:
                fds=[c['rr'] for c in children if c['rr'] not in awaiting|closed]
                readable,_,_=select.select(fds,[],[],caps['monitor_interval_ns']/1e9)
                for fd in readable:
                    value=os.read(fd,1)
                    if value==(b'R' if release_ns is None else b'D'):awaiting.add(fd)
                    else:closed.add(fd)
                if release_ns is None and len(ready)==count:
                    release_ns=release_ready(children,ready)
                elif release_ns is not None and len(done)==count:
                    validation_released=release_validation(children,done)
            else:time.sleep(caps['monitor_interval_ns']/1e9)
    except Exception as e:
        failure='RUNTIME_FAIL';reason=f'Parent exception: {type(e).__name__}: {e}';terminate()
    finally:
        terminate()
        for c in children:
            c['stdout'].close();c['stderr'].close();os.close(c['rr']);os.close(c['gw'])
        os.sched_setaffinity(0,original)
    rows=[];raw=fixture(p['N'],p['ell_bits'])
    for i,c in enumerate(children):
        row=dict(base,record_type='worker',worker_index=i,run_id=entry['run_id']+f'/w{i}',parent_run_id=entry['run_id'],worker_targets=c['targets'],status=failure or 'RUNTIME_FAIL',failure_reason=reason or 'Missing result',output_verified=False,exit_code=c['process'].returncode,observed_max_threads=c['max_threads'])
        result=c['stem'].with_suffix('.result.json')
        if result.is_file():
            try:row.update(normalize(read(result)))
            except Exception as e:row.update(status='RUNTIME_FAIL',failure_reason='Malformed worker result: '+str(e))
        if row['status']=='COMPLETE':
            checks=[row.get('actual_hex')==[raw[t].hex() for t in c['targets']],row.get('db_fixture_hash')==p['db_fixture_hash'],row.get('encoded_db_hash')==p['encoded_db_hash'],row.get('cpu_affinity')==partitions[i],row.get('key_generation_calls')==1,row.get('exit_code')==0,row.get('validation_release_seen') is True,row.get('all_coefficients_exact') is True,row.get('all_segments_exact') is True,row.get('padding_exact') is True,row.get('query_ciphertexts')==p['N'],row.get('reply_ciphertexts')==p['L'],row.get('rng_calls')==2+2*p['N'],row.get('omp_max_threads')==1]
            if not all(checks):row.update(status='WRONG_OUTPUT',output_verified=False,failure_reason='Independent fixture/layout/affinity/lifecycle/output check')
        if not functional:
            row['peak_rss_kib']=max(row.get('peak_rss_kib',0),c['usage'].ru_maxrss)
            row['lifetime_cpu_user_ns']=int(c['usage'].ru_utime*1e9);row['lifetime_cpu_system_ns']=int(c['usage'].ru_stime*1e9)
        if row['status']=='COMPLETE':
            try:validate(row)
            except (AssertionError,KeyError,TypeError) as error:row.update(status='RUNTIME_FAIL',output_verified=False,failure_reason='Worker schema violation: '+repr(error))
        rows.append(row)
    keys=[r.get('key_fingerprint') for r in rows if r['status']=='COMPLETE']
    if len(set(keys))!=len(keys):failure='RUNTIME_FAIL';reason='Duplicate fresh key fingerprint'
    precedence=['RESOURCE_LIMIT','TIMEOUT','RUNTIME_FAIL','WRONG_OUTPUT','COMPLETE']
    if NOW()-began>caps['wall_timeout_ns']:failure='TIMEOUT';reason='Whole-task timeout including parent validation'
    if sample(os.getpid()).get('VmRSS',0)*1024>caps['parent_rss_bytes']:failure='RESOURCE_LIMIT';reason='Parent RSS after validation'
    status=min([failure or ('COMPLETE' if len(rows)==count else 'RUNTIME_FAIL')]+[r['status'] for r in rows],key=precedence.index)
    parent=dict(base,record_type='task',status=status,failure_reason=reason or '; '.join(r.get('failure_reason','') for r in rows if r['status']!='COMPLETE'),output_verified=status=='COMPLETE',expected_workers=count,attempted_workers=len(rows),worker_ids=[r['run_id'] for r in rows],cpu_affinity=cores,barrier_ready_count=len(ready),barrier_completion_count=len(done),validation_released=validation_released)
    if not functional:
        after=resource.getrusage(resource.RUSAGE_SELF)
        parent.update(aggregate(rows),barrier_release_ns=release_ns,parent_cpu_user_ns=int((after.ru_utime-parent_usage.ru_utime)*1e9),parent_cpu_system_ns=int((after.ru_stime-parent_usage.ru_stime)*1e9),parent_peak_rss_kib=after.ru_maxrss,aggregate_peak_metric='WORKER_LIFETIME_PEAK_RSS' if count==1 else 'SUM_OF_WORKER_PEAK_RSS_UPPER')
    else:parent.update(timing_collected=False)
    validate(parent)
    write(out/'functional_records.json' if functional else out/'raw.jsonl',dict(parent=parent,workers=rows) if functional else ''.join(json.dumps(r)+'\n' for r in rows+[parent]))
    return parent,rows
def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--formal',action='store_true');p.add_argument('--windows-snapshot',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    if not a.formal:raise SystemExit('Execution requires explicit --formal; freeze stage must not call this command')
    from b2b_release import release_check
    config,release=release_check(a.windows_snapshot)
    if release['status']!='PASS':raise SystemExit('Release blocked: '+str(release['failed_checks']))
    out=Path(a.out)
    if out.resolve()!= (NOTES/'B2_B_execution').resolve():raise SystemExit('Use the single immutable B2_B_execution batch path')
    out.mkdir(exist_ok=False);write(out/'release.json',release)
    schedule=read(NOTES/'B2_B_run_schedule.json');points={p['point_id']:p for p in config['workloads']};keys=set();valid=True;stop_reason=None
    original=os.sched_getaffinity(0);os.sched_setaffinity(0,config['concurrency']['parent_affinity'])
    try:
        with (out/'task_rows.jsonl').open('x',encoding='utf-8') as ledger:
            for e in schedule:
                for method in e['method_order']:
                    entry=dict(e,method=method,run_id=e['pair_id']+'_'+method,batch_id='B2_B_execution')
                    if stop_reason:
                        row=dict(entry,stage='B2-B',record_type='task',timing_label='FORMAL',freeze_manifest_sha256=sha(MANIFEST),rho_0=8,w=8*e['alpha'],transport_bytes='NOT_MEASURED',status='RESOURCE_LIMIT',failure_reason=stop_reason,output_verified=False,execution_attempted=False);workers=[]
                    else:
                        row,workers=run_task(config,points[e['point_id']],entry,out/entry['run_id'],release=release)
                    fingerprints=[w.get('key_fingerprint') for w in workers if w['status']=='COMPLETE']
                    if any(k in keys for k in fingerprints):row.update(status='RUNTIME_FAIL',failure_reason='Cross-task duplicate client key');valid=False
                    keys.update(fingerprints)
                    ledger.write(json.dumps(row)+'\n');ledger.flush()
                    if e['warmup'] and row['status']!='COMPLETE':valid=False
                    if size_tree(out)>CAPS['batch_disk_bytes'] or shutil.disk_usage(out).free<CAPS['disk_free_reserve_bytes']:stop_reason='Batch disk/free reserve reached';valid=False
            ledger.flush();os.fsync(ledger.fileno())
    finally:os.sched_setaffinity(0,original)
    from b2b_environment import capture
    end=capture();write(out/'environment_end.json',end)
    if end['boot_id']!=release['linux']['boot_id'] or end['memory_bytes']['SwapFree']<end['memory_bytes']['SwapTotal']:valid=False
    write(out/'batch_status.json',dict(status='COMPLETE' if valid else 'BATCH_ANALYSIS_INVALID',environment_valid=valid,scheduled_parent_attempts=624,scheduled_worker_attempts=1248,no_retries=True,manual_incident_policy='Host suspend/reboot/throttling/swapping invalidates whole batch; preserve observations and add incident record'))
    write((out/'task_rows.jsonl').with_suffix('.jsonl.sha256'),sha(out/'task_rows.jsonl')+'  task_rows.jsonl')
if __name__=='__main__':main()
