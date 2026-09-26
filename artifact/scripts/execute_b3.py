#!/usr/bin/env python3
"""One append-only B3 formal run. No effect-dependent choices or retries."""
import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

from b3_common import ROOT, ART, CAPS, POLICIES, NATIVE_COMMIT, cells as available_cells, read, sha, now, write_new

SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')
METHODS = {'packed', 'repeated'}
MANDATORY_FROZEN = {'artifact/scripts/execute_b3.py', 'artifact/scripts/b3_runner.py', 'artifact/scripts/b3_common.py'}

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def relative_file(name):
    require(isinstance(name, str), 'Artifact path must be a string')
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts, 'Unsafe relative artifact path: '+name)
    resolved = (ROOT/path).resolve()
    require(resolved.is_relative_to(ROOT.resolve()), 'Path leaves workspace: '+name)
    return resolved

def verify_frozen(config):
    checks = {}
    for name, expected in config['frozen_files'].items():
        path = relative_file(name)
        actual = sha(path) if path.is_file() else None
        checks[name] = {'expected_sha256':expected, 'actual_sha256':actual, 'pass':actual==expected}
    for implementation, binary in config['binaries'].items():
        path=relative_file(binary['path'])
        actual=sha(path) if path.is_file() else None
        checks['binary:'+implementation]={'path':binary['path'], 'expected_sha256':binary['sha256'], 'actual_sha256':actual, 'pass':actual==binary['sha256']}
    for name, expected in config.get('runtime_library_hashes',{}).items():
        path=Path(name)
        actual=sha(path) if path.is_file() else None
        checks['runtime_library:'+name]={'expected_sha256':expected,'actual_sha256':actual,'pass':actual==expected}
    if config.get('compiler'):
        compiler=config['compiler'];path=Path(compiler['path']);actual=sha(path) if path.is_file() else None
        checks['compiler']={'path':compiler['path'],'expected_sha256':compiler['sha256'],'actual_sha256':actual,'pass':actual==compiler['sha256']}
    return {'checked_utc':utc(), 'status':'PASS' if all(c['pass'] for c in checks.values()) else 'FAIL', 'checks':checks}

def validate_protocol(config, check_files=True):
    require(config.get('config_status')=='FROZEN_BEFORE_FORMAL', 'Config must be frozen before formal observations')
    require(config.get('formal_budget_seconds')==5400, 'Formal wall-time budget must be 5400 seconds')
    require(config.get('session_break_seconds')==30, 'Study/session break must be 30 seconds')
    require(config.get('caps')==CAPS, 'Config resource caps differ from reviewed runner caps')
    require(config.get('resource_policies')==POLICIES, 'Config resource policies differ from reviewed runner policies')
    require(set(config.get('binaries',{}))=={'I1','I2'}, 'Both pinned reconstructed variants are required')
    require(isinstance(config.get('frozen_files'),dict) and config['frozen_files'], 'Frozen file hash inventory is required')
    for name, digest in config['frozen_files'].items():
        relative_file(name)
        require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest), 'Invalid frozen digest '+name)
    for binary in config['binaries'].values():
        relative_file(binary['path'])
        require(isinstance(binary.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',binary['sha256']), 'Invalid binary digest')
    if check_files:
        require(MANDATORY_FROZEN<=set(config['frozen_files']), 'Driver/common/runner must be in frozen_files')
        require(all(b['path'] in config['frozen_files'] for b in config['binaries'].values()), 'Both binary paths must be in frozen_files')
        require(isinstance(config.get('runtime_library_hashes'),dict) and config['runtime_library_hashes'], 'Pinned runtime library hashes required')
        require(isinstance(config.get('compiler'),dict) and {'path','sha256'}<=set(config['compiler']), 'Pinned compiler identity required')
        for name,digest in [*config['runtime_library_hashes'].items(),(config['compiler']['path'],config['compiler']['sha256'])]:
            require(Path(name).is_absolute() and isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest), 'Invalid runtime/compiler pin')
    reference={c['cell_id']:c for c in available_cells(include_multiblock=True)}
    registered=config.get('cells')
    require(isinstance(registered,list) and registered, 'Nonempty frozen cell matrix required')
    by_cell={}
    for cell in registered:
        identifier=cell.get('cell_id')
        require(isinstance(identifier,str) and SAFE_ID.fullmatch(identifier), 'Invalid cell_id')
        require(identifier not in by_cell, 'Duplicate cell '+identifier)
        require(identifier in reference, 'Cell is not in the reviewed common matrix: '+identifier)
        require(all(cell.get(k)==v for k,v in reference[identifier].items()), 'Cell parameters differ from reviewed common matrix: '+identifier)
        by_cell[identifier]=cell
    schedule=config.get('schedule')
    require(isinstance(schedule,list) and schedule, 'Nonempty schedule required')
    ids=set(); rounds=set(); groups=[]; closed=set(); current=None
    seen_measured=set(); counts=Counter(); order_counts=Counter(); covered=set(); session_ids=defaultdict(set)
    for ordinal, entry in enumerate(schedule):
        require(isinstance(entry,dict), 'Schedule entry must be a mapping')
        identifier=entry.get('pair_id')
        require(isinstance(identifier,str) and SAFE_ID.fullmatch(identifier), 'Invalid pair_id')
        require(identifier not in ids, 'Duplicate pair_id '+identifier);ids.add(identifier)
        cid=entry.get('cell_id')
        require(cid in by_cell, 'Unknown scheduled cell '+str(cid))
        cell=by_cell[cid]
        require(entry.get('study')==cell['study'], 'Schedule study/cell mismatch')
        session=entry.get('session_id')
        require(isinstance(session,(str,int)) and not isinstance(session,bool) and SAFE_ID.fullmatch(str(session)), 'Invalid session_id')
        require(isinstance(entry.get('round'),int) and not isinstance(entry['round'],bool) and entry['round']>=0, 'Invalid round')
        phase=entry.get('phase')
        require(phase in ('warmup','measured'), 'Invalid phase')
        order=entry.get('method_order')
        require(isinstance(order,list) and len(order)==2 and set(order)==METHODS, 'Each pair must contain both methods exactly once')
        key=(cell['study'],str(session)); cell_session=(cid,str(session))
        if key!=current:
            if current is not None:closed.add(current)
            require(key not in closed, 'Study/session cannot recur after leaving it')
            groups.append({'study':key[0],'session_id':session,'first_schedule_ordinal':ordinal})
            current=key
        if phase=='measured':seen_measured.add(cell_session)
        require(phase!='warmup' or cell_session not in seen_measured, 'Warmup after measured pair in same cell/session')
        round_key=(cid,str(session),phase,entry['round'])
        require(round_key not in rounds, 'Duplicate round within cell/session/phase');rounds.add(round_key)
        counts[(cid,str(session),phase)]+=1
        order_counts[(cid,str(session),phase,order[0])]+=1
        covered.add(cid);session_ids[cell['study']].add(str(session))
    require(covered==set(by_cell), 'Every frozen cell must be scheduled')
    sampling=config.get('sampling')
    require(isinstance(sampling,dict), 'Explicit frozen sampling design required')
    n_sessions=sampling.get('sessions'); n_warm=sampling.get('warmup_pairs_per_cell_session');n_measured=sampling.get('measured_pairs_per_cell_session')
    for value in (n_sessions,n_warm,n_measured):require(isinstance(value,int) and not isinstance(value,bool) and value>0, 'Sampling counts must be positive integers')
    require((n_sessions,n_warm,n_measured)==(3,3,10), 'Reviewed design requires 3 sessions, 3 warmups and 10 measured pairs per cell/session')
    count_report=[]
    for study,sessions in session_ids.items():
        require(len(sessions)==n_sessions, 'Wrong number of sessions for '+study)
        for cid,cell in by_cell.items():
            if cell['study']!=study:continue
            for session in sessions:
                for phase,expected in (('warmup',n_warm),('measured',n_measured)):
                    actual=counts[(cid,session,phase)]
                    require(actual==expected, 'Wrong pair count for '+str((cid,session,phase,actual,expected)))
                    balance=abs(order_counts[(cid,session,phase,'packed')]-order_counts[(cid,session,phase,'repeated')])
                    require(balance<=1, 'Method order is not balanced within cell/session/phase')
                    count_report.append({'cell_id':cid,'session_id':session,'phase':phase,'pairs':actual})
    frozen=verify_frozen(config) if check_files else None
    if check_files:require(frozen['status']=='PASS', 'Frozen file or binary hash mismatch')
    return {'status':'PASS','cells':len(by_cell),'pairs':len(schedule),'tasks':2*len(schedule),'study_session_groups':groups,
        'counts':count_report,'frozen_verification':frozen,'sampling':sampling}

def host_snapshot():
    def text(path):
        try:return Path(path).read_text()
        except OSError:return None
    cpuinfo=text('/proc/cpuinfo') or ''
    model=next((line.split(':',1)[1].strip() for line in cpuinfo.splitlines() if line.startswith('model name')),None)
    osrelease=text('/etc/os-release') or ''
    try:topology=subprocess.check_output(['lscpu','-J'],text=True,timeout=10)
    except (OSError,subprocess.SubprocessError):topology=None
    return {'captured_utc':utc(),'monotonic_raw_ns':now(),'platform':platform.platform(),'kernel':platform.release(),
        'python':sys.version,'cpu_model':model,'logical_cpu_count':os.cpu_count(),'allowed_affinity':sorted(os.sched_getaffinity(0)),
        'os_release':osrelease,'boot_id':(text('/proc/sys/kernel/random/boot_id') or '').strip(),
        'loadavg':text('/proc/loadavg'),'meminfo':text('/proc/meminfo'),'vmstat':text('/proc/vmstat'),
        'lscpu_json':topology,'topology_scope':'OS/WSL-visible topology; physical host scheduling isolation is not established',
        'host_turbo_governor_control':'NOT_CLAIMED'}

def validate_host(host, initial=None):
    checks={
        'cpu_model':bool(host.get('cpu_model') and 'Ryzen 7 3700X' in host['cpu_model']),
        'ubuntu':bool(re.search(r'^ID=ubuntu\s*$',host.get('os_release',''),re.M)),
        'wsl2_kernel':all(s in host.get('kernel','').lower() for s in ('microsoft','wsl2')),
        'allowed_cpus':{0,2,4,6}<=set(host.get('allowed_affinity',[])),
        'boot_id_present':bool(host.get('boot_id')),
    }
    if initial is not None:
        checks.update(same_boot_id=host['boot_id']==initial['boot_id'],same_kernel=host['kernel']==initial['kernel'],same_cpu=host['cpu_model']==initial['cpu_model'])
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks}

def durable_append(path, item):
    with path.open('a',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())

def planned_tasks(schedule):
    return [{'schedule_ordinal':ordinal,**entry,'method':method,'task_id':entry['pair_id']+'_'+method}
        for ordinal,entry in enumerate(schedule) for method in entry['method_order']]

def validate_output(output):
    output=Path(output).resolve()
    require(output.parent==(ART/'raw').resolve() and output.name.startswith('B3-') and SAFE_ID.fullmatch(output.name),
        'Output must be a new immediate artifact/raw child named B3-*')
    return output

def exception_task(cell, entry, method, task_id, ordinal, run_id, config_sha, binary_sha, host_id, error):
    return {**cell,**entry,'method':method,'task_id':task_id,'schedule_ordinal':ordinal,'run_id':run_id,
        'experiment_id':'B3','record_type':'task','timing_label':'B3_FORMAL','source_revision':NATIVE_COMMIT,
        'binary_sha256':binary_sha,'host_id':host_id,'variant_label':'RECONSTRUCTED_SOURCE_VARIANT',
        'contract_id':config_sha,'config_sha256':config_sha,'status':'RUNTIME_FAIL','failure_reason':'Driver observed runner exception: '+repr(error),
        'validation_passed':False,'task_start_ns':None,'task_end_ns':None,'task_total_ns':None,
        'partial_task_directory_retained':True,'worker_outcomes':'UNKNOWN_INSPECT_RETAINED_TASK_DIRECTORY'}

def execute(config_path, output):
    from b3_runner import run_task
    config_path=config_path.resolve();config_bytes=config_path.read_bytes();config=json.loads(config_bytes.decode('utf-8-sig'));config_sha=hashlib.sha256(config_bytes).hexdigest()
    validation=validate_protocol(config)
    initial=host_snapshot();initial_validation=validate_host(initial)
    require(initial_validation['status']=='PASS','Host preflight failed: '+str(initial_validation['checks']))
    output=validate_output(output);run_id=output.name
    output.mkdir(parents=True,exist_ok=False)
    with (output/'config_snapshot.json').open('xb') as stream:stream.write(config_bytes)
    write_new(output/'release_validation.json',{'config_path':str(config_path),'config_sha256':config_sha,'protocol':validation,'host':initial_validation})
    write_new(output/'host_start.json',initial)
    for name in ('task_rows.jsonl','worker_rows.jsonl','attempts.jsonl','events.jsonl'):
        (output/name).open('x').close()
    schedule=config['schedule'];by_cell={c['cell_id']:c for c in config['cells']};expected=planned_tasks(schedule)
    attempted=[];tasks=[];key_sources={};first_launch=None;deadline=None;stop_reason=None;current_group=None;completed_studies=set();final_integrity=None
    study_pair_totals=Counter(e['study'] for e in schedule);study_completed=Counter()
    def event(kind,**values):durable_append(output/'events.jsonl',{'event':kind,'utc':utc(),'monotonic_raw_ns':now(),**values})
    try:
        for ordinal,entry in enumerate(schedule):
            group=(entry['study'],str(entry['session_id']))
            if group!=current_group:
                if current_group is not None:
                    event('SESSION_BREAK_START',from_group=list(current_group),to_group=list(group),seconds=config['session_break_seconds'])
                    rest_end=now()+config['session_break_seconds']*1_000_000_000
                    while now()<rest_end:
                        if deadline is not None and now()>=deadline:
                            stop_reason='FORMAL_WALL_BUDGET_EXHAUSTED_DURING_SESSION_BREAK';break
                        time.sleep(min(1.0,max(0,(rest_end-now())/1e9)))
                    if stop_reason:break
                    event('SESSION_BREAK_END',to_group=list(group))
                snap=host_snapshot();check=validate_host(snap,initial)
                session_integrity=verify_frozen(config);session_config_unchanged=sha(config_path)==config_sha
                write_new(output/f'integrity_session_{entry["study"]}_{entry["session_id"]}.json',{'files':session_integrity,'config_unchanged':session_config_unchanged})
                if session_integrity['status']!='PASS' or not session_config_unchanged:
                    stop_reason='SESSION_FROZEN_HASH_DRIFT';event('FROZEN_HASH_DRIFT',group=list(group));break
                write_new(output/f'host_session_{entry["study"]}_{entry["session_id"]}.json',{'snapshot':snap,'validation':check})
                if check['status']!='PASS':stop_reason='SESSION_HOST_PREFLIGHT_FAILED';event('HOST_PREFLIGHT_FAIL',group=list(group),checks=check);break
                event('SESSION_START',study=entry['study'],session_id=entry['session_id'],host_snapshot=f'host_session_{entry["study"]}_{entry["session_id"]}.json')
                current_group=group
            pair_complete=True
            for method in entry['method_order']:
                if deadline is not None and now()>=deadline:
                    stop_reason='FORMAL_WALL_BUDGET_EXHAUSTED_BEFORE_LAUNCH';pair_complete=False;break
                cell=by_cell[entry['cell_id']];binary_record=config['binaries'][cell['implementation_id']];binary=relative_file(binary_record['path'])
                if sha(config_path)!=config_sha or sha(binary)!=binary_record['sha256']:
                    stop_reason='PRELAUNCH_CONFIG_OR_BINARY_HASH_DRIFT';pair_complete=False;event('FROZEN_HASH_DRIFT',pair_id=entry['pair_id'],method=method);break
                launch=now()
                if first_launch is None:first_launch=launch;deadline=launch+config['formal_budget_seconds']*1_000_000_000
                task_id=entry['pair_id']+'_'+method
                attempt={'run_id':run_id,'task_id':task_id,'schedule_ordinal':ordinal,'pair_id':entry['pair_id'],'cell_id':entry['cell_id'],'study':entry['study'],
                    'session_id':entry['session_id'],'phase':entry['phase'],'round':entry['round'],'method':method,'method_order':entry['method_order'],
                    'launch_intent_utc':utc(),'launch_intent_raw_ns':launch,'status':'LAUNCH_INTENT_RECORDED','no_retry':True,
                    'config_sha256':config_sha,'hard_deadline_raw_ns':deadline}
                durable_append(output/'attempts.jsonl',attempt);attempted.append(task_id)
                try:
                    task,workers=run_task(cell,{**entry,'method':method,'task_id':task_id,'schedule_ordinal':ordinal,'run_id':run_id},binary,output/task_id,
                        label='B3_FORMAL',caps=config['caps'],contract_sha256=config_sha,hard_deadline=deadline)
                except BaseException as error:
                    workers=[]
                    task=exception_task(cell,entry,method,task_id,ordinal,run_id,config_sha,binary_record['sha256'],initial['boot_id'],error)
                duplicates=[]
                for worker in workers:
                    fingerprint=worker.get('key_fingerprint')
                    if fingerprint:
                        if fingerprint in key_sources:duplicates.append({'fingerprint':fingerprint,'first':key_sources[fingerprint],'duplicate':task_id+'/w'+str(worker.get('worker_index'))})
                        else:key_sources[fingerprint]=task_id+'/w'+str(worker.get('worker_index'))
                if duplicates:
                    task={**task,'runner_status':task['status'],'status':'RUNTIME_FAIL','validation_passed':False,
                        'driver_validation_status':'DUPLICATE_KEY_FINGERPRINT','failure_reason':'Fresh-key fingerprint repeated within formal run; retained native task.json is not overwritten'}
                    event('DUPLICATE_KEY_FINGERPRINT',task_id=task_id,duplicates=duplicates)
                for worker in workers:durable_append(output/'worker_rows.jsonl',worker)
                durable_append(output/'task_rows.jsonl',task);tasks.append(task)
                if task['status']!='COMPLETE':
                    stop_reason='TASK_'+task['status']+': '+task.get('failure_reason','');pair_complete=False;break
            print(json.dumps({'study':entry['study'],'session_id':entry['session_id'],'pair_id':entry['pair_id'],'phase':entry['phase'],
                'pairs_accounted':ordinal+1,'pairs_scheduled':len(schedule),'pair_completed':pair_complete,'stop_reason':stop_reason}),flush=True)
            if not pair_complete:break
            study_completed[entry['study']]+=1
            if study_completed[entry['study']]==study_pair_totals[entry['study']]:
                completed_studies.add(entry['study']);event('STUDY_COMPLETED',study=entry['study'],pairs=study_completed[entry['study']])
    except BaseException as error:
        stop_reason='DRIVER_EXCEPTION: '+repr(error)
        event('DRIVER_EXCEPTION',reason=stop_reason)
    finally:
        final_integrity=verify_frozen(config)
        config_unchanged=sha(config_path)==config_sha
        ending=host_snapshot();host_end=validate_host(ending,initial)
        write_new(output/'host_end.json',{'snapshot':ending,'validation':host_end})
        write_new(output/'frozen_verification_end.json',{'files':final_integrity,'config_unchanged':config_unchanged})
        if final_integrity['status']!='PASS' or not config_unchanged:stop_reason=(stop_reason+'; ' if stop_reason else '')+'FROZEN_HASH_DRIFT'
        if host_end['status']!='PASS':stop_reason=(stop_reason+'; ' if stop_reason else '')+'HOST_IDENTITY_DRIFT'
        attempted_set=set(attempted)
        unstarted=[{**task,'run_id':run_id,'status':'UNSTARTED','failure_reason':stop_reason or 'Not launched','execution_attempted':False} for task in expected if task['task_id'] not in attempted_set]
        counts=Counter(t['status'] for t in tasks)
        complete=not stop_reason and len(tasks)==len(expected) and counts=={'COMPLETE':len(expected)}
        summary={'status':'COMPLETE' if complete else 'STOPPED_INCOMPLETE','run_id':run_id,'observation_identity':['run_id','pair_id','method'],'config_sha256':config_sha,'created_utc':utc(),
            'first_launch_raw_ns':first_launch,'hard_deadline_raw_ns':deadline,'run_end_raw_ns':now(),'formal_budget_seconds':config['formal_budget_seconds'],
            'scheduled_pairs':len(schedule),'scheduled_tasks':len(expected),'launch_intents':len(attempted),'recorded_tasks':len(tasks),
            'status_counts':dict(counts),'unstarted_tasks':unstarted,'unstarted_count':len(unstarted),'completed_studies':sorted(completed_studies),
            'stop_reason':stop_reason,'distinct_key_fingerprints':len(key_sources),'frozen_files_end_status':final_integrity['status'],
            'config_unchanged':config_unchanged,'host_end_status':host_end['status'],'no_retries':True,
            'integrity_check_frequency':'All pinned files at start, every study/session boundary and end; config and selected binary before each launch.',
            'statistical_estimators_computed_during_execution':False,'stop_policy':'Only frozen wall/resource caps, correctness/lifecycle/runtime or integrity failure; never effect size or CI.',
            'raw_files':{name:sha(output/name) for name in ('task_rows.jsonl','worker_rows.jsonl','attempts.jsonl','events.jsonl')}}
        write_new(output/'run_summary.json',summary)
        print(json.dumps({k:summary[k] for k in ('status','scheduled_tasks','recorded_tasks','status_counts','unstarted_count','completed_studies','stop_reason')}),flush=True)
    return 0 if complete else 1

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--output',default=str(ART/'raw/B3-formal-v1'))
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    path=Path(args.config)
    if args.validate_only:
        result=validate_protocol(read(path));host=host_snapshot();check=validate_host(host)
        require(check['status']=='PASS','Host preflight failed: '+str(check['checks']))
        print(json.dumps({'status':'PASS','config_sha256':sha(path),'cells':result['cells'],'pairs':result['pairs'],'tasks':result['tasks'],
            'study_session_groups':result['study_session_groups'],'host_validation':check,'host_snapshot':host,'native_tasks_launched':0},indent=2))
        return 0
    return execute(path,Path(args.output))

if __name__=='__main__':raise SystemExit(main())
