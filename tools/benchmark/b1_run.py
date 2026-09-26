"""One non-resumable B1 batch; call only the immutable B0 measurement function."""
import os,time,shutil,subprocess
from b1_common import *
from b1_release import release,linux_environment

def vmstat():return {k:int(v) for k,v in (s.split() for s in Path('/proc/vmstat').read_text().splitlines())}
def memory():return {k:int(v.split()[0]) for k,v in (s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines())}
def footprint(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())

def main():
    if BATCH.exists():raise SystemExit('No resume/replacement of an existing B1 batch')
    m,entries,points,result=release('windows_start.json','release_check.json')
    if result['status']!='PASS':raise SystemExit('B1 release blocked; zero native observations')
    dump(LOG/'environment_start.json',{'windows':result['Windows_snapshot'],'linux':result['Linux_environment']})
    pr=read(LOG/'preregistration.json'); frozen={**m['frozen_files'],**pr['tool_hashes'],
        'revision_notes/B0_benchmark_manifest.json':B0_HASH,'revision_notes/B0_run_schedule.json':SCHEDULE_HASH,
        'revision_notes/T0_secondary_selection_manifest.json':T0_HASH,
        'revision_notes/B1_primary_execution.md':pr['execution_protocol_hash']}
    BATCH.mkdir();os.sched_setaffinity(0,{0,2})
    start=result['Linux_environment'];v0=vmstat();mem0=memory();incidents=[];warmup_failures=[]
    stop=None;stop_status='RUNTIME_FAIL';tasks=[];worker_counts={s:0 for s in STATUSES};worker_started=0;key_fingerprints=set()
    disk_done=footprint(LOG)
    from runner import run_task
    def incident(kind,ordinal,detail):
        nonlocal stop,stop_status
        item={'kind':kind,'ordinal':ordinal,'detail':detail,'utc':now()};incidents.append(item)
        dump(LOG/f'incident_{len(incidents):03}.json',item)
        stop='BATCH ENVIRONMENT_INVALID: '+kind;stop_status='RESOURCE_LIMIT' if kind in ('batch_disk_cap','disk_reserve') else 'RUNTIME_FAIL'
    with (LOG/'raw_rows.jsonl').open('x') as raw,(LOG/'task_rows.jsonl').open('x') as ledger,(LOG/'failure_ledger.jsonl').open('x') as failures:
        for original in entries:
            e={**original,'batch_id':BATCH_ID};p=points[e['point_id']];out=BATCH/f"{e['ordinal']:05}"
            if not stop:
                if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=start['boot_id']:incident('boot_drift',e['ordinal'],{})
                drift=(time.clock_gettime_ns(time.CLOCK_BOOTTIME)-start['boottime_ns'])-(time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)-start['raw_ns'])
                if abs(drift)>1_000_000_000:incident('suspend_or_clock_drift',e['ordinal'],{'drift_ns':drift})
                v=vmstat();mem=memory()
                if mem['SwapFree']<mem0['SwapFree'] or v['pswpout']>v0['pswpout']:incident('swap_activity',e['ordinal'],{'before':v0['pswpout'],'after':v['pswpout']})
                if shutil.disk_usage(ROOT).free<m['resource_caps']['disk_free_reserve_bytes']:incident('disk_reserve',e['ordinal'],{})
                # Completed task directories are immutable; count each once. Active root ledgers are stat'ed each time.
                disk_current=disk_done+sum(f.stat().st_size for f in LOG.iterdir() if f.is_file() and f.name in ('raw_rows.jsonl','task_rows.jsonl','failure_ledger.jsonl','launcher.stdout','launcher.stderr'))
                if disk_current>m['resource_caps']['batch_disk_bytes']:incident('batch_disk_cap',e['ordinal'],{'bytes':disk_current})
                if e['ordinal']%2==0:
                    changed=hash_check(frozen)
                    if changed:incident('source_build_hash_drift',e['ordinal'],changed)
                    names=subprocess.check_output(['ps','-eo','comm='],text=True).splitlines()
                    competitors=[n.strip() for n in names if n.strip() in ('cc1plus','cc1','g++','gcc','sage','b0_worker','s4_n_e2e','nvcc','stress','stress-ng')]
                    if competitors:incident('competing_process',e['ordinal'],competitors)
            attempted=not stop
            if stop:parent,workers=unavailable(m,p,e,stop_status,'NOT_STARTED: '+stop)
            else:
                try:
                    parent,workers=run_task(m,p,e,out,False)
                    for i,w in enumerate(workers):
                        stderr=(out/f'worker{i}.stderr').read_text(errors='replace').strip()
                        if w['status']=='RUNTIME_FAIL' and stderr in {'worker exception: '+s for s in ('backend degree','moduli','width/noise','import','fresh RNG path','payload ABI')}:
                            w.update(status='WRONG_OUTPUT',failure_reason=stderr,output_verified=False)
                        if w.get('key_fingerprint') in key_fingerprints:
                            w.update(status='WRONG_OUTPUT',failure_reason='reused fresh-key fingerprint across tasks',output_verified=False)
                        if w.get('key_fingerprint'):key_fingerprints.add(w['key_fingerprint'])
                    validate_completed(parent,workers,p)
                except Exception as error:
                    incident('runner_or_schema_exception',e['ordinal'],f'{type(error).__name__}: {error}')
                    parent,workers=unavailable(m,p,e,'RUNTIME_FAIL','Partial task directory retained; '+stop)
                    parent['execution_attempted']=out.exists()
                    for i,w in enumerate(workers):
                        w['execution_attempted']=None if (out/f'worker{i}.job.json').exists() else False
                        w['notes'].append('Worker launch/completion unknown after runner exception; native files retained')
            annotate(parent,workers,e,'ENVIRONMENT_INVALID' if incidents else ('WARMUP_INVALID' if warmup_failures else 'VALID_AT_TASK_COMPLETION'))
            for row in workers+[parent]:
                try:validate_row(row)
                except Exception as error:incident('row_schema',e['ordinal'],f'{type(error).__name__}: {error}')
                raw.write(json.dumps(row)+'\n')
                if row['status']!='COMPLETE':failures.write(json.dumps(row)+'\n')
            ledger.write(json.dumps(parent)+'\n');raw.flush();ledger.flush();failures.flush()
            tasks.append(parent)
            for w in workers:
                worker_counts[w['status']]+=1
                if w['execution_attempted'] is True:worker_started+=1
            if attempted and out.exists():disk_done+=footprint(out)
            if attempted and e['warmup'] and parent['status']!='COMPLETE':
                warmup_failures.append(e['run_id']);stop='BATCH_ANALYSIS_INVALID: required warmup failed';stop_status='RUNTIME_FAIL'
                dump(LOG/'warmup_invalid_incident.json',{'failed_run_id':e['run_id'],'status':parent['status'],'reason':parent['failure_reason'],'next_action':'STOP; no replacement; account all remaining slots'})
            if attempted or e['ordinal']==len(entries)-1:
                print(json.dumps({'accounted':e['ordinal']+1,'of':len(entries),'run_id':e['run_id'],'point':p['id'],
                    'method':e['method'],'view':e['preprocess_mode'],'warmup':e['warmup'],'status':parent['status'],
                    'stopped':stop,'utc':now()}),flush=True)
    end=linux_environment();dump(LOG/'linux_environment_end.json',end)
    if hash_check(frozen):incident('final_source_build_hash_drift',4896,hash_check(frozen))
    status={'stage':'EXECUTION_FINISHED_AWAITING_WINDOWS_AND_PROTECTION_AUDIT','batch_id':BATCH_ID,
            'parent_accounted':len(tasks),'worker_accounted':sum(worker_counts.values()),
            'parent_execution_attempted':sum(r['execution_attempted'] is True for r in tasks),'worker_execution_attempted':worker_started,
            'parent_status_counts':{s:sum(r['status']==s for r in tasks) for s in STATUSES},'worker_status_counts':worker_counts,
            'warmup_failed_run_ids':warmup_failures,'incidents':incidents,'environment_valid':not incidents,
            'raw_dataset_sha256':sha(LOG/'raw_rows.jsonl'),'task_rows_sha256':sha(LOG/'task_rows.jsonl'),
            'all_schedule_slots_retained':len(tasks)==4896 and len({r['run_id'] for r in tasks})==4896,
            'schedule_sha256':sha(SCHEDULE),'utc':now()}
    dump(LOG/'execution_status.json',status)
    print('B1 execution closed; no statistical analysis until final environment audit.',flush=True)

if __name__=='__main__':main()
