"""B3 common runner: private exec workers, explicit resource bundles, native endpoints.

Public per-sample /proc diagnostics are buffered, then persisted after workers finish.
No cryptographic key/randomness state is recorded. This is a new runner contract.
"""
from b3_common import *
import subprocess,resource,signal,select,struct,shutil,re

def sample(pid):
    try:
        fields={}
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith(('VmRSS:','VmSize:','Threads:')):
                k,v,*_=line.split();fields[k[:-1]]=int(v)
        return fields
    except (FileNotFoundError,ProcessLookupError):return {}

def prepare_child(affinity,as_limit,caps):
    def setup():
        os.sched_setaffinity(0,affinity)
        resource.setrlimit(resource.RLIMIT_AS,(as_limit,as_limit))
        resource.setrlimit(resource.RLIMIT_FSIZE,(caps['per_file_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    return setup

def check_worker(w,cell,method,targets,affinity,latest_end):
    assert w['status']=='COMPLETE' and w['output_verified'] is True
    assert w['exit_code']==0 and w['cpu_affinity']==affinity
    assert w['actual_hex']==[fixture(cell['N'],cell['ell_bits'])[t].hex() for t in targets]
    assert w['db_fixture_hash']==cell['db_fixture_hash'] and w['encoded_db_hash']==cell['encoded_db_hash']
    assert w['native_db_fixture_hash']==cell['db_fixture_hash'] and w['native_encoded_db_hash']==cell['encoded_db_hash']
    assert w['native_fixture_id']=='pseudorandom-B3-common-seed-8c3f47282900cee8-v1'
    assert isinstance(w.get('key_fingerprint'),str) and re.fullmatch('[0-9a-f]{64}',w['key_fingerprint'])
    assert w['task_end_ns']-w['task_start_ns']==w['task_total_ns']>0
    assert w['key_generation_calls']==1 and w['query_encrypt_calls']==cell['N'] and w['rng_calls']==2+2*cell['N']
    assert w['omp_max_threads']==1 and w['validation_release_seen'] is True
    assert w['query_ciphertexts']==cell['N'] and w['reply_ciphertexts']==cell['L']
    assert w['query_payload_bytes']==cell['N']*CT and w['reply_payload_bytes']==cell['L']*CT
    assert all(w[k] is True for k in ('all_coefficients_exact','all_segments_exact','padding_exact'))
    assert set(w['phase_events'])==set(PHASES)==set(w['phase_ns'])
    assert w['native_implementation_id']=='B3-'+cell['implementation_id']
    assert all(w['native_parameters'][k]==cell[k] for k in ('N','ell_bits','alpha','rho_0','w','J','L'))
    assert w['native_timing_label']==w['timing_label']
    for name,event in w['phase_events'].items():
        begin,end=event['begin'],event['end'];assert end-begin==w['phase_ns'][name]>=0
        if name=='ValidationOverhead':assert begin>=latest_end
        elif cell['view']=='ONLINE' and name in ('ConfigureServer','EncodeDB','ImportPreprocess'):
            assert end<=w['task_start_ns']
        else:assert w['task_start_ns']<=begin<=end<=w['task_end_ns']
    return True

def run_task(cell,entry,binary,out,label='B3_PILOT',caps=None,contract_sha256=None,hard_deadline=None):
    if label not in ('B3_PILOT','B3_FORMAL'):raise ValueError('Functional-only calls belong to native validation harness.')
    if label=='B3_FORMAL' and not contract_sha256:raise ValueError('Unfrozen formal call')
    caps=caps or CAPS;policy=POLICIES[cell['resource_policy_id']]
    method=entry['method'];count=1 if method=='packed' else cell['alpha']
    affinities=[policy['packed_affinity']] if method=='packed' else policy['repeated_affinity'][:count]
    assert len(affinities)==count and count<=4
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if shutil.disk_usage(out).free<caps['disk_reserve_bytes']:raise RuntimeError('Free disk reserve')
    original_affinity=os.sched_getaffinity(0)
    begun=now();parent_before=resource.getrusage(resource.RUSAGE_SELF)
    children=[];ready=set();done=set();release=None;validation_release=None;failure=None;reason='';samples=[];sample_bytes=0
    base={'experiment_id':'B3','contract_id':contract_sha256 or 'PILOT_NOT_FROZEN','config_sha256':contract_sha256,
          **cell,**entry,'timing_label':label,'source_revision':NATIVE_COMMIT,'binary_sha256':sha(binary),'variant_label':'RECONSTRUCTED_SOURCE_VARIANT',
          'host_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'transport_bytes':'NOT_MEASURED','parent_affinity':policy['parent_affinity']}
    def reap(kill=False):
        for c in children:
            proc=c['process']
            if proc.returncode is None:
                if kill:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                pid,status,usage=os.wait4(proc.pid,0 if kill else os.WNOHANG)
                if pid:
                    proc.returncode=os.waitstatus_to_exitcode(status);c['rusage']=usage
    try:
        os.sched_setaffinity(0,policy['parent_affinity'])
        if hard_deadline is not None and now()>=hard_deadline:raise TimeoutError('Formal budget exhausted before launch')
        for i in range(count):
            if hard_deadline is not None and now()>=hard_deadline:raise TimeoutError('Formal budget exhausted before worker launch')
            rr,rw=os.pipe();gr,gw=os.pipe();stem=out/f'worker{i}'
            targets=cell['target_tuple'] if method=='packed' else [cell['target_tuple'][i]]
            job={**cell,'targets':targets,'method':method,'preprocess_mode':cell['view'],'ready_fd':rw,'go_fd':gr,'timing_label':label,'fixture_kind':'pseudorandom'}
            stdout=None;stderr=None
            as_limit=policy['packed_as_bytes'] if method=='packed' else policy['repeated_worker_as_bytes']
            try:
                write_new(stem.with_suffix('.job.json'),job)
                stdout=stem.with_suffix('.stdout').open('xb');stderr=stem.with_suffix('.stderr').open('xb')
                process=subprocess.Popen([str(binary),str(stem.with_suffix('.job.json')),str(stem.with_suffix('.result.json'))],stdout=stdout,stderr=stderr,
                    env={**os.environ,'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1'},pass_fds=(rw,gr),start_new_session=True,
                    preexec_fn=prepare_child(affinities[i],as_limit,caps))
            except BaseException:
                for fd in (rr,rw,gr,gw):os.close(fd)
                if stdout:stdout.close()
                if stderr:stderr.close()
                raise
            os.close(rw);os.close(gr)
            children.append({'process':process,'stem':stem,'rr':rr,'gw':gw,'stdout':stdout,'stderr':stderr,'rusage':None,'targets':targets,'max_threads':0})
        while any(c['process'].returncode is None for c in children):
            stamp=now();rss=0;vm=0;tick=[]
            if stamp-begun>caps['wall_timeout_ns'] or hard_deadline is not None and stamp>=hard_deadline:
                failure='TIMEOUT';reason='Fixed task or total formal wall-time ceiling'
            for c in children:
                proc=c['process']
                if proc.returncode is None:
                    observed=sample(proc.pid);c['max_threads']=max(c['max_threads'],observed.get('Threads',0))
                    rss+=observed.get('VmRSS',0)*1024;vm+=observed.get('VmSize',0)*1024
                    tick.append({'pid':proc.pid,**observed})
            parent=sample(os.getpid())
            samples.append({'sample_timestamp_ns':stamp,'workers':tick,'aggregate_rss_bytes':rss,'aggregate_vm_bytes':vm,'parent':parent})
            sample_bytes+=len((json.dumps(samples[-1])+'\n').encode('utf-8'))
            reap()
            if any(c['process'].returncode not in (None,0,20) for c in children):failure='RUNTIME_FAIL';reason='Worker nonzero exit'
            if rss>caps['aggregate_rss_bytes'] or policy['enforce_aggregate_vm'] and vm>caps['aggregate_vm_bytes']:
                failure='RESOURCE_LIMIT';reason='Frozen sampled RSS or VmSize cap'
            if parent.get('VmRSS',0)*1024>caps['parent_rss_bytes']:failure='RESOURCE_LIMIT';reason='Parent RSS cap'
            if sum(p.stat().st_size for p in out.iterdir() if p.is_file())+sample_bytes+2*2**20>caps['task_disk_bytes']:failure='RESOURCE_LIMIT';reason='Task disk cap including buffered trace and 2MiB final metadata reserve'
            if failure:reap(True);break
            active_set=ready if release is None else done
            if validation_release is None:
                fds=[c['rr'] for c in children if c['rr'] not in active_set]
                readable,_,_=select.select(fds,[],[],caps['monitor_interval_ns']/1e9)
                for fd in readable:
                    byte=os.read(fd,1)
                    if byte!=(b'R' if release is None else b'D'):
                        failure='RUNTIME_FAIL';reason='Unexpected barrier byte/EOF';break
                    active_set.add(fd)
                if failure:reap(True);break
                if release is None and len(ready)==count:
                    release=now()+5_000_000
                    for c in children:os.write(c['gw'],struct.pack('<Q',release))
                elif release is not None and len(done)==count:
                    validation_release=now()
                    for c in children:os.write(c['gw'],b'V')
            else:time.sleep(caps['monitor_interval_ns']/1e9)
    except BaseException as error:
        failure='TIMEOUT' if isinstance(error,TimeoutError) else 'RUNTIME_FAIL'
        reason=type(error).__name__+': '+str(error);reap(True)
    finally:
        reap(True)
        for c in children:
            c['stdout'].close();c['stderr'].close();os.close(c['rr']);os.close(c['gw'])
        os.sched_setaffinity(0,original_affinity)
    if not failure and (len(children)!=count or len(ready)!=count or len(done)!=count or release is None or validation_release is None):
        failure='RUNTIME_FAIL';reason='Parent did not complete every READY/DONE/validation barrier'
    workers=[]
    for i,c in enumerate(children):
        w={**base,'record_type':'worker','worker_index':i,'worker_targets':c['targets'],'status':failure or 'RUNTIME_FAIL','failure_reason':reason or 'No worker result','output_verified':False}
        result=c['stem'].with_suffix('.result.json')
        if result.exists():
            try:
                native=normalize(read(result));w.update(native)
                w['native_implementation_id']=native.get('implementation_id')
                w['native_fixture_id']=native.get('fixture_id')
                w['native_db_fixture_hash']=native.get('db_fixture_hash')
                w['native_encoded_db_hash']=native.get('encoded_db_hash')
                w['native_status']=native.get('status')
                w['native_parameters']={k:native.get(k) for k in ('N','ell_bits','alpha','rho_0','w','J','L')}
                w['native_timing_label']=native.get('timing_label')
                w.update(base)
            except Exception as error:w.update(status='RUNTIME_FAIL',failure_reason='Malformed result '+str(error))
        w.update(exit_code=c['process'].returncode,observed_max_threads=c['max_threads'])
        if c['rusage']:
            w['worker_lifetime_peak_rss_kib']=int(c['rusage'].ru_maxrss)
            w['worker_lifetime_cpu_ns']=int((c['rusage'].ru_utime+c['rusage'].ru_stime)*1e9)
        if failure:w.update(status=failure,failure_reason=reason,output_verified=False)
        if w['status'] not in ('RESOURCE_LIMIT','TIMEOUT','RUNTIME_FAIL','WRONG_OUTPUT','COMPLETE'):
            w.update(status='RUNTIME_FAIL',failure_reason='Unrecognized native status: '+repr(w.get('native_status')),output_verified=False)
        workers.append(w)
    latest_end=max((w.get('task_end_ns',0) for w in workers),default=0)
    for i,w in enumerate(workers):
        if w['status']=='COMPLETE':
            try:check_worker(w,cell,method,children[i]['targets'],affinities[i],latest_end)
            except (AssertionError,KeyError,TypeError) as error:w.update(status='WRONG_OUTPUT',failure_reason='Independent output/lifecycle/timing check: '+repr(error),output_verified=False)
    fps=[w.get('key_fingerprint') for w in workers if w['status']=='COMPLETE']
    if len(set(fps))!=len(fps):failure='RUNTIME_FAIL';reason='Duplicate fresh-key fingerprint'
    precedence=['RESOURCE_LIMIT','TIMEOUT','RUNTIME_FAIL','WRONG_OUTPUT','COMPLETE']
    status=min([failure or 'COMPLETE']+[w['status'] for w in workers],key=precedence.index)
    has_intervals=bool(workers) and all('task_start_ns' in w and 'task_end_ns' in w for w in workers)
    start=min(w['task_start_ns'] for w in workers) if has_intervals else None
    end=max(w['task_end_ns'] for w in workers) if has_intervals else None
    def total(key):return sum(w[key] for w in workers) if workers and all(key in w for w in workers) else None
    parent_after=resource.getrusage(resource.RUSAGE_SELF)
    task={**base,'record_type':'task','status':status,'failure_reason':reason or '; '.join(w['failure_reason'] for w in workers if w['status']!='COMPLETE'),
          'validation_passed':status=='COMPLETE','task_start_ns':start,'task_end_ns':end,'task_total_ns':end-start if has_intervals else None,
          'worker_intervals':[{'start_ns':w.get('task_start_ns'),'end_ns':w.get('task_end_ns')} for w in workers],
          'start_skew_ns':max(w['task_start_ns'] for w in workers)-start if has_intervals else None,
          'release_ns':release,'validation_release_ns':validation_release,'raw_worker_count':len(workers),
          'cpu_user_ns':total('cpu_user_ns'),'cpu_system_ns':total('cpu_system_ns'),
          'worker_lifetime_peak_rss_sum_kib':total('worker_lifetime_peak_rss_kib'),
          'rss_semantics':'sum of worker lifetime peaks, not synchronized peak; staging included',
          'parent_cpu_total_ns':int((parent_after.ru_utime+parent_after.ru_stime-parent_before.ru_utime-parent_before.ru_stime)*1e9),
          'parent_cpu_scope':'whole runner task including staging/validation; excluded from worker TaskTotal CPU',
          'phase_ns':{p:sum(w['phase_ns'][p] for w in workers) for p in PHASES} if workers and all(set(w.get('phase_ns',{}))==set(PHASES) for w in workers) else {},
          'phase_semantics':'worker duration sums, not concurrent critical-path attribution',
          **{k:total(k) for k in ('query_ciphertexts','reply_ciphertexts','query_payload_bytes','reply_payload_bytes')},
          'whole_task_wall_ns':now()-begun,'monitor_samples':len(samples),'monitor_time_series_persisted':True}
    write_new(out/'task.json',task);write_new(out/'workers.json',workers)
    write_new(out/'monitor_samples.jsonl',''.join(json.dumps(s)+'\n' for s in samples))
    return task,workers
