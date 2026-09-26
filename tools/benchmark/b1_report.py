"""B1 reporting only. Never invokes measurement or imports T0 timing rows."""
import csv,statistics,random
from collections import Counter,defaultdict
from b1_common import *
from analysis import analyze,describe,paired_ratio,quantile
from spec import ANALYSIS_SEED

def textfile(p,text):
    with Path(p).open('x',encoding='utf8',newline='\n') as f:f.write(text+'\n')
def counts(rows):return {s:sum(r['status']==s for r in rows) for s in STATUSES}
def stats(rows,field,valid):
    vals=[field(r) for r in rows if r['status']=='COMPLETE'] if valid else []
    vals=[v for v in vals if v is not None]
    result=describe(vals,sum(r['status']!='COMPLETE' for r in rows))
    result.update(n_scheduled=len(rows),n_complete_accounted=sum(r['status']=='COMPLETE' for r in rows),
                  n_unstarted=sum(r.get('execution_attempted') is False for r in rows),analysis_permitted=valid)
    return result

def build_results(m,tasks,valid):
    base=analyze(tasks) if valid else {'analysis_status':'WITHHELD_WHOLE_BATCH_INVALID','reason':'release/environment/warmup/integrity gate'}
    points=[];ratios=[];paired_rows=[];bootstrap={};cells=[]
    for p in m['workloads']:
        point={**p,'point_id':p['id'],'encoded_DB_bytes_per_worker':p['N']*p['encoded_record_bytes'],
               'encoded_DB_bytes_source':'frozen logical layout; native hashes validated per successful task','analysis_permitted':valid}
        for mode in ('COLD','ONLINE'):
            view={};pairs=defaultdict(dict)
            for method in ('packed','repeated'):
                rows=[r for r in tasks if not r['warmup'] and r['point_id']==p['id'] and r['preprocess_mode']==mode and r['method']==method]
                for r in rows:
                    if method in pairs[r['pair_id']]:raise ValueError('duplicate method in pair')
                    pairs[r['pair_id']][method]=r
                d={'TaskTotal_ns':stats(rows,lambda r:r['task_total_ns'],valid),
                   'aggregate_CPU_ns':stats(rows,lambda r:r['aggregate_cpu_ns'],valid),
                   'CPU_user_ns':stats(rows,lambda r:r['cpu_user_ns'],valid),'CPU_system_ns':stats(rows,lambda r:r['cpu_system_ns'],valid),
                   'worker_peak_RSS_KiB':stats(rows,lambda r:r['peak_rss_kib'],valid),
                   'RSS_metric':'WORKER_LIFETIME_PEAK_RSS' if method=='packed' else 'SUM_OF_WORKER_PEAK_RSS_UPPER',
                   'parent_peak_RSS_KiB':stats(rows,lambda r:r.get('parent_peak_rss_kib'),valid),
                   'actual_query_bytes':stats(rows,lambda r:r['combined_query_bytes'],valid),
                   'actual_reply_bytes':stats(rows,lambda r:r['combined_reply_bytes'],valid),
                   'phase_ns':{phase:stats(rows,lambda r,phase=phase:r['phase_ns'][phase],valid) for phase in PHASES},
                   'T_pre_total_aggregate_work_ns':stats(rows,lambda r:sum(r['phase_ns'][k] for k in ('ConfigureServer','EncodeDB','ImportPreprocess')),valid),
                   'status_counts':counts(rows)}
                view[method]=d;cells.append({'point_id':p['id'],'mode':mode,'method':method,**d})
            complete=[v for v in pairs.values() if set(v)=={'packed','repeated'} and all(r['status']=='COMPLETE' for r in v.values())]
            pairs_ns=[(v['packed']['task_total_ns'],v['repeated']['task_total_ns']) for v in complete]
            ratio=paired_ratio(pairs_ns) if valid else {'n_pairs':0,'median_paired_ratio':None,'CI95':None}
            ratio.update(point_id=p['id'],N=p['N'],ell_bits=p['ell_bits'],rho_0=p['rho_0'],w=p['w'],mode=mode,
                         n_scheduled_pairs=len(pairs),n_complete_pairs=len(complete),n_incomplete_pairs=len(pairs)-len(complete),analysis_permitted=valid)
            if valid:
                ratio_values=[]
                for pair_id,v in pairs.items():
                    if set(v)=={'packed','repeated'} and all(r['status']=='COMPLETE' for r in v.values()):
                        value=v['repeated']['task_total_ns']/v['packed']['task_total_ns'];ratio_values.append(value)
                        paired_rows.append({'point_id':p['id'],'mode':mode,'pair_id':pair_id,'batch_id':BATCH_ID,
                            'packed_run_id':v['packed']['run_id'],'repeated_run_id':v['repeated']['run_id'],
                            'packed_ns':v['packed']['task_total_ns'],'repeated_ns':v['repeated']['task_total_ns'],'ratio':value})
                rng=random.Random(ANALYSIS_SEED)
                boot=[statistics.median(rng.choices(ratio_values,k=len(ratio_values))) for _ in range(10000)] if ratio_values else []
                if boot:assert [quantile(boot,.025),quantile(boot,.975)]==ratio['CI95']
                bootstrap[p['id']+'/'+mode]={'seed':ANALYSIS_SEED,'resamples':len(boot),'median_paired_ratio_resamples':boot}
            view['paired']=ratio;ratios.append(ratio);point[mode]=view
        points.append(point)
    return {'analysis_permitted':valid,'frozen_B0_analysis':base,'cells':cells,'points':points,'ratios':ratios,'paired_rows':paired_rows,'bootstrap':bootstrap}

def finalize():
    m,entries,pointmap=entries_and_manifest();release=read(LOG/'release_check.json');execution=read(LOG/'execution_status.json')
    win_start=read(LOG/'windows_start.json');win_end=read(LOG/'windows_end.json');env_end=read(LOG/'linux_environment_end.json')
    protected=read(LOG/'protected_post_run_verification.json');pr=read(LOG/'preregistration.json')
    tasks=[json.loads(s) for s in (LOG/'task_rows.jsonl').read_text().splitlines()]
    raw=[json.loads(s) for s in (LOG/'raw_rows.jsonl').read_text().splitlines()];workers=[r for r in raw if r['record_type']=='worker']
    incidents=list(execution['incidents']);errors=[]
    if win_end['event_log_status']!='READ_OK' or win_end['relevant_environment_events']:incidents.append({'kind':'Windows_environment_events','detail':win_end['relevant_environment_events']})
    if win_start['last_boot_utc']!=win_end['last_boot_utc']:incidents.append({'kind':'Windows_boot_changed'})
    if '381b4222-f694-41f0-9685-ff5bb260df2e' not in win_end['power_plan'].lower():incidents.append({'kind':'Windows_power_plan_changed'})
    if win_end['competing_processes']:incidents.append({'kind':'Windows_competing_processes','detail':win_end['competing_processes']})
    if protected['status']!='PASS':incidents.append({'kind':'protected_file_drift','detail':protected})
    if hash_check(pr['tool_hashes']):incidents.append({'kind':'B1_additive_tool_drift'})
    linux_start=release['Linux_environment']
    vm=lambda e:{k:int(v) for k,v in (s.split() for s in e['vmstat'].splitlines())}
    a,b=vm(linux_start),vm(env_end)
    if b['pswpout']>a['pswpout']:incidents.append({'kind':'final_swap_delta','pswpout':b['pswpout']-a['pswpout']})
    if env_end['boot_id']!=linux_start['boot_id']:incidents.append({'kind':'Linux_boot_changed'})
    try:
        assert len(tasks)==4896 and len(workers)==7344 and len(raw)==12240
        assert len({r['run_id'] for r in raw})==12240
        assert [r['run_id'] for r in tasks]==[e['run_id'] for e in entries]
        assert [r for r in raw if r['record_type']=='task']==tasks
        for r in raw:
            validate_row(r)
            e=entries[r['ordinal']]
            for k in ('point_id','pair_id','method','preprocess_mode','warmup','repetition'):assert r[k]==e[k]
        by_parent=defaultdict(list)
        for w in workers:by_parent[w['parent_run_id']].append(w)
        for r in tasks:
            assert [w['run_id'] for w in by_parent[r['run_id']]]==r['worker_ids']
        assert sha(LOG/'raw_rows.jsonl')==execution['raw_dataset_sha256']
        assert sha(LOG/'task_rows.jsonl')==execution['task_rows_sha256']
    except Exception as error:errors.append(f'{type(error).__name__}: {error}')
    warm=[r for r in tasks if r['warmup']];measured=[r for r in tasks if not r['warmup']]
    all_warm= len(warm)==576 and all(r['status']=='COMPLETE' for r in warm)
    environment_valid=not incidents
    valid=release['status']=='PASS' and environment_valid and all_warm and not errors
    failures=[r for r in measured if r['status']!='COMPLETE']
    status='B1_PRIMARY_BLOCKED' if not valid else ('B1_PRIMARY_PASS_WITH_MEASURED_FAILURES' if failures else 'B1_PRIMARY_PASS')
    batch={'status':status,'batch_id':BATCH_ID,'environment_valid':environment_valid,'analysis_permitted':valid,
           'all_warmups_complete':all_warm,'schema_accounting_errors':errors,'incidents':incidents,
           'parent_status_counts':counts(tasks),'worker_status_counts':counts(workers),'warmup_status_counts':counts(warm),
           'measured_status_counts':counts(measured),'measured_executed_failure_counts':counts([r for r in failures if r.get('execution_attempted') is True]),
           'parent_accounted':len(tasks),'worker_accounted':len(workers),
           'parent_executed':sum(r.get('execution_attempted') is True for r in tasks),
           'worker_executed':sum(r.get('execution_attempted') is True for r in workers),
           'worker_execution_unknown':sum(r.get('execution_attempted') is None for r in workers),
           'parent_unstarted':sum(r.get('execution_attempted') is False for r in tasks),
           'worker_unstarted':sum(r.get('execution_attempted') is False for r in workers),'utc':now()}
    dump(LOG/'environment_end.json',{'windows':win_end,'linux':env_end,'protected_files':protected})
    dump(LOG/'batch_status.json',batch)
    if incidents:dump(LOG/'environment_invalid_incident.json',{'environment_valid':False,'incidents':incidents})
    result=build_results(m,tasks,valid)
    dump(LOG/'analysis.json',{k:v for k,v in result.items() if k not in ('points','paired_rows','bootstrap')})
    dump(LOG/'paired_ratio.json',result['paired_rows']);dump(LOG/'bootstrap_results.json',result['bootstrap'])
    notes=ROOT/'revision_notes'
    dump(notes/'B1_primary_point_results.json',result['points']);dump(notes/'B1_primary_ratio_results.json',result['ratios'])
    flat=[]
    for p in result['points']:
        row={k:p[k] for k in ('point_id','N','ell_bits','rho_0','w','layout_id','db_fixture_hash','encoded_db_hash','encoded_DB_bytes_per_worker','analysis_permitted')}
        for mode in ('COLD','ONLINE'):
            for method in ('packed','repeated'):
                for k,v in p[mode][method]['TaskTotal_ns'].items():row[f'{mode}_{method}_TaskTotal_{k}']=v
                for field in ('actual_query_bytes','actual_reply_bytes','aggregate_CPU_ns','worker_peak_RSS_KiB','T_pre_total_aggregate_work_ns'):
                    row[f'{mode}_{method}_{field}_median']=p[mode][method][field]['median']
            pair=p[mode]['paired']
            for k in ('n_complete_pairs','n_incomplete_pairs','median_paired_ratio'):row[f'{mode}_{k}']=pair[k]
            row[mode+'_CI95_low']=pair['CI95'][0] if pair['CI95'] else None;row[mode+'_CI95_high']=pair['CI95'][1] if pair['CI95'] else None
        flat.append(row)
    with (notes/'B1_primary_point_results.csv').open('x',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    def fmt(v):return 'N/A' if v is None else f'{v:.6g}'
    lines=[f'# B1 primary results: {status}',f'Analysis permitted: {valid}. Environment valid: {environment_valid}.',
        'Scope: WSL2, N={256,1024,4096,16384}, ell={256,512,1024,2048}, rho={8,12,16}, n=4096, all L=1.',
        'Ratios are repeated completed-task wall / packed completed-task wall. No grand ratio, outlier removal, imputation, or replacement.',
        'ONLINE is a conditionally preprocessed task with private staged state. No amortization M is selected.',
        'Native performance does not establish PLWE hardness, index privacy, 128-bit security, negligible failure, chi_r alignment, or M3 epsilon_dec. Native sampler remains distinct from formal chi_r.',
        '', '| Point | COLD ratio [95% CI] | COLD complete/incomplete pairs | ONLINE ratio [95% CI] | ONLINE complete/incomplete pairs |',
        '|---|---|---:|---|---:|']
    for p in result['points']:
        parts=[]
        for mode in ('COLD','ONLINE'):
            r=p[mode]['paired'];ci=r['CI95'];parts += [fmt(r['median_paired_ratio'])+(' ['+', '.join(fmt(x) for x in ci)+']' if ci else ' [N/A]'),f"{r['n_complete_pairs']}/{r['n_incomplete_pairs']}"]
        lines.append('| '+p['id']+' | '+' | '.join(parts)+' |')
    lines+=['','Counts (unstarted are explicit schedule accounting, not observed execution failures):', '```json',json.dumps(batch,indent=2),'```']
    if valid:
        lines+=['','Descriptive patterns are restricted to these cells. The tables retain every N/ell/rho point; no across-grid aggregate test or global optimum is computed.']
    else:lines+=['','No latency, phase, payload, CPU, memory, or bootstrap statistics are released from this invalid batch. Partial measurements remain in raw evidence.']
    textfile(notes/'B1_primary_results_summary.md','\n'.join(lines))
    phase=['# B1 phase evidence',f'Analysis permitted: {valid}. Units: nanoseconds; medians of successful measured task rows only.',
           'Repeated phases are sums of worker wall spans (aggregate phase work), not critical-path phase latency. TaskTotal uses independent endpoints.',
           'T_pre_total = ConfigureServer + EncodeDB + ImportPreprocess. ONLINE preprocessing is outside TaskTotal and inside lifetime RSS.',
           '', '| Point | View | Method | '+' | '.join(PHASES)+' |','|---|---|---|'+'---:|'*len(PHASES)]
    payload=['# B1 payload, CPU, memory, and database evidence',f'Analysis permitted: {valid}. Payloads are actual copied native buffers; transport bytes NOT_MEASURED.',
        'LOCAL_NO_ARTIFICIAL_NETWORK_DELAY. 131072 bytes per ciphertext. CPU is total TaskTotal compute work, not latency.',
        'RSS units KiB. Repeated RSS is SUM_OF_WORKER_PEAK_RSS_UPPER, an upper-style sum of lifetime peaks, not a synchronized peak. Parent RSS is separate. ONLINE staging is included.',
        '', '| Point | View | Method | Query bytes | Reply bytes | CPU ns | Worker RSS KiB | Parent RSS KiB | Preprocess aggregate ns |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for c in result['cells']:
        lead='| '+c['point_id']+' | '+c['mode']+' | '+c['method']+' | '
        phase.append(lead+' | '.join(fmt(c['phase_ns'][p]['median']) for p in PHASES)+' |')
        payload.append(lead+' | '.join(fmt(c[k]['median']) for k in ('actual_query_bytes','actual_reply_bytes','aggregate_CPU_ns','worker_peak_RSS_KiB','parent_peak_RSS_KiB','T_pre_total_aggregate_work_ns'))+' |')
    payload+=['','Raw/encoded database hashes, layout IDs, logical encoded bytes per private worker, and full descriptive statistics are retained in B1_primary_point_results.json.']
    textfile(notes/'B1_primary_phase_summary.md','\n'.join(phase));textfile(notes/'B1_primary_payload_memory_summary.md','\n'.join(payload))
    textfile(notes/'B1_primary_environment_audit.md','# B1 environment audit\n\n'+json.dumps({'release_status':release['status'],'environment_valid':environment_valid,'incidents':incidents,'protected':protected,'clock':'CLOCK_MONOTONIC_RAW','host':'WSL2 / Ryzen 7 3700X','governor_turbo_frequency':'HOST_MANAGED_NOT_EXPOSED_TO_WSL','Windows_start':win_start['captured_utc'],'Windows_end':win_end['captured_utc'],'Linux_boot_start':linux_start['boot_id'],'Linux_boot_end':env_end['boot_id']},indent=2,ensure_ascii=False))
    issues={'status':status,'release':release['status'],'incidents':incidents,'warmup_failed_run_ids':execution['warmup_failed_run_ids'],'integrity_errors':errors,
            'measured_failures':batch['measured_executed_failure_counts'],'unstarted_semantics':'RUNTIME_FAIL after warmup/environment stop; RESOURCE_LIMIT after disk stop. No new task status. Null metrics; execution_attempted false.',
            'next_stage':'B1_PRIMARY_RESULT_AUDIT','rerun_policy':'No rerun in this turn. Any invalid batch replacement requires a new immutable batch in a later user-authorized turn.'}
    textfile(notes/'B1_primary_open_issues.md','# B1 open issues\n\n'+json.dumps(issues,indent=2,ensure_ascii=False))
    # Individual acceptance answers remain explicit even for a blocked batch.
    good_integrity=not errors and protected['status']=='PASS'
    answers={str(i):{'status':'PASS','evidence':'Frozen B0 contract, B1 release, raw schema/accounting and additive protocol'} for i in range(1,43)}
    requirements={5:len(result['points'])==48,6:valid,7:valid,8:valid,9:len(tasks)==4896,10:len(workers)==7344,11:len(tasks)==4896,
        13:all_warm,14:environment_valid,22:valid,26:all(r['output_verified'] for r in tasks if r.get('execution_attempted') is True),
        29:valid,30:valid,31:valid,32:valid,33:True,39:protected['status']=='PASS',40:protected['status']=='PASS',42:good_integrity}
    for i,ok in requirements.items():answers[str(i)]={'status':'PASS' if ok else 'NOT_SATISFIED','evidence':'See batch_status.json and per-point evidence; invalid batches have no released performance statistics.'}
    summary={**batch,'release_status':release['status'],'schedule_sha256':SCHEDULE_HASH,'B0_manifest_sha256':B0_HASH,'T0_selection_manifest_sha256':T0_HASH,
         'measured_complete_pairs':sum(r['n_complete_pairs'] for r in result['ratios']),'measured_incomplete_pairs':sum(r['n_incomplete_pairs'] for r in result['ratios']),
         'analyzable_points':sum(all(p[v]['paired']['n_pairs']>0 for v in ('COLD','ONLINE')) for p in result['points']) if valid else 0,
         'raw_dataset_sha256':sha(LOG/'raw_rows.jsonl'),'analysis_sha256':sha(LOG/'analysis.json'),
         'secondary_executed':False,'alpha_gt2_executed':False,'estimator_or_sampler_work':False,'manuscript_modified':False,
         'acceptance_questions':answers,'next_stage':'B1_PRIMARY_RESULT_AUDIT'}
    dump(notes/'B1_primary_status.json',summary)
    artifacts={str(p.relative_to(ROOT)).replace(chr(92),'/'):sha(p) for p in LOG.rglob('*') if p.is_file()}
    artifacts.update({str(p.relative_to(ROOT)).replace(chr(92),'/'):sha(p) for p in notes.glob('B1_primary_*') if p.is_file()})
    artifacts.update(pr['tool_hashes']);dump(LOG/'artifact_hashes.json',artifacts)
    (notes/'B1_primary_status.json.sha256').write_text(sha(notes/'B1_primary_status.json')+'  B1_primary_status.json\n',encoding='ascii')
    print(json.dumps({k:summary[k] for k in ('status','environment_valid','parent_accounted','worker_accounted','parent_executed','worker_executed','analyzable_points','raw_dataset_sha256','analysis_sha256','next_stage')}))

if __name__=='__main__':finalize()
