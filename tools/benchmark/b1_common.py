"""B1 additive orchestration. Frozen B0 code and measurements remain authoritative."""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, copy, os
from spec import ROOT, PHASES, STATUSES, COMMIT, Q, sha

LOG = ROOT / 'revision_notes/B1_primary_logs'
BATCH_ID = 'B1-primary-1'
BATCH = LOG / BATCH_ID
MANIFEST = ROOT / 'revision_notes/B0_benchmark_manifest.json'
SCHEDULE = ROOT / 'revision_notes/B0_run_schedule.json'
B0_HASH = '69c130a37990ce1262292476b29f6b365974ecdbe383df0511b66822f5e3bd6e'
SCHEDULE_HASH = '07925546f8a3a7b42d8e78ad4ee3ef3698ab075d6c8e681a2ca8a3fb802f6d30'
BINARY_HASH = 'bb650809753603bb942e4b2a792333a5eefefdd8b4517ac174f02b6e48fcaaba'
T0_HASH = 'b96eac15d8747f7ebf40a7cd064b39f4d30116a52f04a1879603f6a055a8456e'
TOOLS = ['b1_common.py','b1_release.py','b1_run.py','b1_report.py','b1_test.py','b1_windows_snapshot.ps1','b1_launch.ps1']

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p, obj):
    with Path(p).open('x', encoding='utf8', newline='\n') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False); f.write('\n')
def hash_check(mapping):
    return [str(p) for p,h in mapping.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
def protection():
    maps={'B1_before':read(LOG/'protected_before.json'),
          'T0_before':read(ROOT/'revision_notes/T0_logs/protected_before.json'),
          'T0_evidence':read(ROOT/'revision_notes/T0_logs/artifact_hashes.json')}
    t=read(ROOT/'revision_notes/T0_secondary_selection_manifest.json')
    maps.update(T0_selection_artifacts=t['artifact_hashes'],T0_tools=t['tool_hashes'])
    bad={k:hash_check(v) for k,v in maps.items()}
    return {'status':'PASS' if not any(bad.values()) else 'FAIL','checked_counts':{k:len(v) for k,v in maps.items()},'changed':bad,'utc':now()}

def entries_and_manifest():
    if sha(SCHEDULE)!=SCHEDULE_HASH: raise ValueError('STOP: authoritative schedule hash mismatch')
    if sha(MANIFEST)!=B0_HASH: raise ValueError('STOP: B0 manifest hash mismatch')
    m=read(MANIFEST); entries=read(SCHEDULE)
    assert m['experiment_version']=='B0-1.1' and m['readiness']=='B0_PASS'
    assert len(entries)==4896 and len({e['run_id'] for e in entries})==4896
    assert sum(e['method']=='packed' for e in entries)==2448
    assert sum(e['method']=='repeated' for e in entries)==2448
    points={p['id']:p for p in m['workloads']}
    assert len(points)==48
    from collections import Counter
    counts=Counter()
    for i,e in enumerate(entries):
        assert e['ordinal']==i and e['point_id'] in points
        p=points[e['point_id']]
        assert p['N'] in (256,1024,4096,16384) and p['ell_bits'] in (256,512,1024,2048)
        assert p['rho_0'] in (8,12,16) and p['w']==2*p['rho_0'] and p['L']==1
        assert p['target_tuple']==[p['N']//4,3*p['N']//4]
        counts[e['point_id'],e['method'],e['preprocess_mode'],e['warmup']]+=1
        mate=entries[i^1]
        assert mate['pair_id']==e['pair_id'] and mate['point_id']==e['point_id'] and mate['method']!=e['method']
        for k in ('warmup','repetition','preprocess_mode'): assert mate[k]==e[k]
    for p in points.values():
        for method in ('packed','repeated'):
            for mode in ('COLD','ONLINE'):
                assert counts[p['id'],method,mode,True]==3
                assert counts[p['id'],method,mode,False]=={256:30,1024:30,4096:20,16384:10}[p['N']]
    return m,entries,points

def unavailable(m,p,e,status,reason):
    from runner import unexecuted_row
    parent=unexecuted_row(m,p,e,status,reason)
    parent.update(phase_events={},network_policy='LOCAL_NO_ARTIFICIAL_NETWORK_DELAY',exit_code=None)
    workers=[];count=1 if e['method']=='packed' else 2
    for i in range(count):
        w=copy.deepcopy(parent)
        w.update(record_type='worker',run_id=e['run_id']+f'/w{i}',parent_run_id=e['run_id'],
                 baseline_worker_id=i if count==2 else None,pid=None,ppid=os.getpid(),worker_pids=[],
                 cpu_affinity=[0,2] if count==1 else [[0],[2]][i],
                 worker_targets=p['target_tuple'] if count==1 else [p['target_tuple'][i]],observed_max_threads=None)
        w['workload']['alpha']=2 if count==1 else 1
        workers.append(w)
    return parent,workers

def annotate(parent,workers,e,relation):
    for row in workers+[parent]:
        row.update(analysis_scope='B1_PRIMARY_SAME_PROFILE',primary_batch=BATCH_ID,
                   parent_B0_manifest_sha256=B0_HASH,environment_relation=relation)
        row.setdefault('execution_attempted',True)
    parent['worker_statuses']=[{'run_id':w['run_id'],'status':w['status'],'exit_code':w.get('exit_code'),
                              'execution_attempted':w['execution_attempted'],'failure_reason':w['failure_reason']} for w in workers]

def validate_completed(parent,workers,p):
    """Additional requested semantic checks, only after the frozen timing returns."""
    count=1 if parent['method']=='packed' else 2
    known=('frozen DB/affinity/key lifecycle mismatch','duplicate fresh-key fingerprint')
    for w in workers:
        if w['failure_reason'] in known: w.update(status='WRONG_OUTPUT',output_verified=False)
    if parent['failure_reason'] in known: parent.update(status='WRONG_OUTPUT',output_verified=False)
    problems=[]
    for i,w in enumerate(workers):
        if w['status']!='COMPLETE': continue
        expected_targets=p['target_tuple'] if count==1 else [p['target_tuple'][i]]
        checks={
            'ordered output':w['actual_hex']==w['expected_hex'] and len(w['actual_hex'])==len(expected_targets),
            'targets/layout':w['worker_targets']==expected_targets and w['target_tuple']==p['target_tuple'] and w['layout_id']==p['layout_id'],
            'DB hashes':(w['db_fixture_hash'],w['encoded_db_hash'])==(p['db_fixture_hash'],p['encoded_db_hash']),
            'backend':w['crypto']=={**read(MANIFEST)['crypto'],'w':p['w'],'B':1<<p['rho_0'],'t':1<<p['w']},
            'affinity/threads':w['cpu_affinity']==([0,2] if count==1 else [[0],[2]][i]) and w['omp_threads']==w['omp_max_threads']==w['observed_max_threads']==1,
            'key/RNG':w['key_generation_calls']==1 and w['server_unused_key_generation_calls']==1 and w['query_encrypt_calls']==p['N'] and w['rng_calls']==2+2*p['N'],
            'payload':w['query_ciphertexts']==p['N'] and w['reply_ciphertexts']==p['L'] and w['query_payload_bytes']==p['N']*131072 and w['reply_payload_bytes']==p['L']*131072,
            'clock':w['clock_resolution_ns']==1 and w['release_ns']<=w['task_start_ns'],
        }
        bad=[k for k,v in checks.items() if not v]
        if bad:
            w.update(status='WRONG_OUTPUT',output_verified=False,failure_reason='B1 post-timing validation: '+', '.join(bad));problems+=bad
    if all(w['status']=='COMPLETE' for w in workers):
        aggregate=[len(workers)==count,len({w['pid'] for w in workers})==count,len({w['key_fingerprint'] for w in workers})==count,
            parent['barrier_ready_count']==parent['barrier_completion_count']==count,parent['validation_released'],
            all(w['release_ns']==parent['barrier_release_ns'] for w in workers),
            parent['task_start_ns']==min(w['task_start_ns'] for w in workers),parent['task_end_ns']==max(w['task_end_ns'] for w in workers),
            parent['task_total_ns']==parent['task_end_ns']-parent['task_start_ns'],
            min(w['phase_events']['ValidationOverhead']['begin'] for w in workers)>=parent['task_end_ns'],
            parent['aggregate_cpu_ns']==sum(w['cpu_user_ns']+w['cpu_system_ns'] for w in workers),
            parent['peak_rss_kib']==sum(w['peak_rss_kib'] for w in workers),
            parent['combined_query_bytes']==sum(w['query_payload_bytes'] for w in workers),
            parent['combined_reply_bytes']==sum(w['reply_payload_bytes'] for w in workers)]
        if not all(aggregate):problems.append('task aggregation/barriers')
    if problems or any(w['status']=='WRONG_OUTPUT' for w in workers):
        if parent['status'] in ('COMPLETE','WRONG_OUTPUT') or all(w['status'] in ('COMPLETE','WRONG_OUTPUT') for w in workers):
            parent.update(status='WRONG_OUTPUT',output_verified=False,failure_reason='B1 validation: '+', '.join(problems or ['worker validation']))
    return problems

def validate_row(row):
    from validate import validate
    validate(row)
    assert row['analysis_scope']=='B1_PRIMARY_SAME_PROFILE' and row['timing_label']=='FORMAL'
    assert row['batch_id']==BATCH_ID and row['build_hash']==BINARY_HASH and row['backend_commit']==COMMIT
    assert row['experiment_version']=='B0-1.1' and row['crypto']['q']==Q
    assert row['workload']['N'] in (256,1024,4096,16384) and row['workload']['ell_bits'] in (256,512,1024,2048)

if __name__=='__main__':
    import sys
    dump(LOG/sys.argv[1],protection())
