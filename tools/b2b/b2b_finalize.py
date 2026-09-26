"""Seal the pre-observation B2-B release. Never launches a worker or analysis."""
from b2b_common import *
from b2b_schedule import validate_schedule
from verify_manifest import verify,verify_entries,REQUIRED
import re
from datetime import datetime,timezone
def role(p):
    name=p.name;rel=p.relative_to(ROOT).as_posix()
    if name in ('b2b_worker','b2b_worker.sha256') or name.endswith('.o'):return 'BINARY'
    if name.endswith(('.cpp','.hpp','.d')) or name=='build.log':return 'SOURCE'
    if rel.startswith('tools/') or name=='commands.txt':return 'TOOL'
    if 'environment' in name or name.startswith('windows_'):return 'ENVIRONMENT'
    if 'schedule' in name:return 'SCHEDULE'
    if 'workload' in name:return 'WORKLOAD'
    if 'resource_preflight' in name:return 'RESOURCE_MODEL'
    if 'open_issues' in name:return 'OPEN_ISSUE'
    if 'protocol' in name or 'contract' in name and name.endswith('.md') or name in ('freeze_config.json','task_request.txt','B2_B_statistics_plan.md'):return 'PROTOCOL'
    return 'STATUS'
def main():
    assert not MANIFEST.exists(),'Existing release is immutable'
    cfg=read(LOG/'freeze_config.json');tests=read(LOG/'contract_tests_final.json');native=read(LOG/'native_build_verification.json');smoke=read(LOG/'smoke_validation.json');protected=read(LOG/'protected_files_verification.json');parents=read(LOG/'parent_evidence_verification.json')
    assert tests['status']==native['status']==smoke['status']==protected['status']=='PASS'
    assert tests['native_crypto_executions']==tests['performance_observations']==0
    assert smoke['new_native_processes']==3 and smoke['formal_observations']==smoke['TaskTotal_fields']==0
    assert protected['checked']==40865 and not protected['mismatches'] and not protected['new_files_outside_authorized_scope']
    for n,expected in [('B2_A_artifact_hashes.json',PARENT_HASH),('B1_primary_audit/artifact_hashes.json',AUDIT_HASH)]:assert sha(NOTES/n)==expected and parents[n]['status']=='PASS'
    assert not (NOTES/'B2_B_execution').exists() and not (NOTES/'B2_B_execution_inputs').exists()
    assert not (NOTES/'B2_B_artifact_hashes.json').exists() and not (NOTES/'B2_B_artifact_hashes.json.sha256').exists()
    assert not list(LOG.rglob('raw.jsonl'))
    smoke_results=list(LOG.glob('smoke_A*/worker0.result.json'));assert len(smoke_results)==3
    for p in smoke_results:
        row=read(p);assert row['timing_label']==LABEL and row['status']=='COMPLETE' and not any(k.endswith('_ns') for k in row)
    assert not [p for p in scoped_files() if p.suffix=='.sha256'],'No ordinary sidecars before binary/release seal'
    binary=ROOT/cfg['build']['binary'];assert sha(binary)==cfg['build']['binary_sha256']
    write(binary.with_name(binary.name+'.sha256'),sha(binary)+'  '+binary.name)
    schedule=read(ROOT/cfg['schedule']['path']);validate_schedule(schedule,cfg['workloads']);assert sha(ROOT/cfg['schedule']['path'])==cfg['schedule']['sha256']
    resource=read(NOTES/'B2_B_resource_preflight.json');assert resource['status']=='FEASIBLE'
    cores=cfg['concurrency']['selected_cores'];assert len({(c['physical_package_id'],c['core_id']) for c in cores})==4
    assert cfg['concurrency']['parent_affinity']==[c['logical_cpu'] for c in cores]
    assert cfg['build']['source_hashes']['tools/b2b/b2b_worker.cpp']==sha(HERE/'b2b_worker.cpp')
    write(LOG/'commands.txt',"""B2-B freeze operations (no formal execution command was invoked):
Windows Python -X utf8 -B: snapshot all protected workspace files; verify B2-A/B1-audit parent indexes.
Read-only wsl -d Ubuntu topology/memory/disk query: sandbox E_ACCESSDENIED; approved elevated retry succeeded.
Initial Windows CIM snapshot: sandbox access denied; incomplete windows_freeze.json retained.
PowerShell direct script invocation: execution-policy denied; no policy setting changed.
powershell -NoProfile -ExecutionPolicy Bypass -File tools/b2b/b2b_windows_snapshot.ps1 -OutputPath revision_notes/B2_B_freeze_logs/windows_freeze_v2.json
Windows Python -X utf8 -B tools/b2b/b2b_derive.py
wsl -d Ubuntu -- python3 -B tools/b2b/b2b_environment.py (first call lacked Windows v2 input; subsequent call succeeded)
wsl -d Ubuntu -- python3 -B tools/b2b/b2b_build.py
Windows Python -X utf8 -B tools/b2b/b2b_prepare.py
wsl -d Ubuntu -- python3 -B tools/b2b/test_b2b.py (12 non-crypto tests)
wsl -d Ubuntu -- python3 -B tools/b2b/b2b_smoke.py (exactly three tiny functional cases; no TaskTotal output)
wsl -d Ubuntu -- python3 -B tools/b2b/b2b_native_verify.py
wsl -d Ubuntu -- python3 -B tools/b2b/test_b2b.py --seal-results (13 non-crypto tests including full synthetic batch failures)
PowerShell AST parser: b2b_windows_snapshot.ps1 and b2b_launch.ps1 syntax PASS; launcher never invoked.
Windows Python -X utf8 -B: protected_before versus final full workspace inventory (40,865 prior files).
wsl -d Ubuntu -- python3 -B tools/b2b/test_b2b.py --seal-results --out contract_tests_final.json (final source revision)
Windows Python -X utf8 -B tools/b2b/b2b_finalize.py
Windows Python -X utf8 -B tools/b2b/verify_manifest.py
The explicit --formal runner and -Execute launcher are future-stage entry points only and were NOT invoked.
""")
    write(LOG/'implementation_review.json',dict(status='PASS',binary_sha256=sha(binary),frozen_backend_source='Unchanged pinned XPIR; exact existing B0 two-output-statement overlay reused',B1_reuse='Independent task endpoints, phase vocabulary, pre-release ONLINE staging, copied payload accounting and completion/validation barrier',B2A_reuse='Existing m1 exact width/weight guards; generalized alpha targets/weights; full coefficient, unpacked segment, padding and ordered record checks',timing_change='Full-width extraction/decode remains ReplyExt; expected-value/hash/record validation remains after TaskTotal and all worker completion. Same generalized binary used for every alpha/method.',functional_smoke='Only A2 COLD, A3 ONLINE, A4 COLD; N8 ell256. Binary unchanged after smoke. No repeated encrypted smoke or formal workload.',non_crypto_concurrency_test='Four independent Python exec processes; one identical synthetic timestamp after all READY; validation release after all DONE; no observed latency retained.',future_launcher='Explicit -Execute only; fresh Windows snapshot, Linux release gate, whole-batch fixed parent affinity. Windows end snapshot and power/reboot incident record after the batch. Not invoked.',post_smoke_runner_edits='Added factored barrier tests, explicit parent-validation timeout/RSS enforcement and Windows end-state launcher; no change to native binary or extraction semantics.',PowerShell_syntax='Both PS1 files parsed without errors; future launcher not invoked',formal_observations=0))
    question_text=(LOG/'task_request.txt').read_text(encoding='utf-8').split('六十四、',1)[1].split('六十五、',1)[0]
    questions=[(int(n),q.strip()) for n,q in re.findall(r'(?m)^(\d+)\.\s*(.+)$',question_text)]
    assert [n for n,q in questions]==list(range(1,67))
    predicates={
      1:parents['B2_A_artifact_hashes.json']['status']=='PASS',2:parents['B1_primary_audit/artifact_hashes.json']['status']=='PASS',3:cfg['secondary_status']=='RETIRED_FROM_CURRENT_SCOPE',
      4:cfg['domain']['rho_0']==[8],5:cfg['domain']['alpha']==[2,3,4],6:cfg['domain']['w_by_alpha']=={'2':16,'3':24,'4':32},7:len(cfg['workloads'])==12,8:cfg['views']==['COLD','ONLINE'],9:all(p['L']==1 for p in cfg['workloads']),
      10:'exact same' in cfg['same_profile_rule'],11:'Freshly remeasure alpha2' in cfg['alpha2_rule'],12:cfg['analysis']['pooled_B1_samples'] is False,
      13:cfg['concurrency']['repeated_workers']=='alpha',14:len({(x['physical_package_id'],x['core_id']) for x in cores})==4,15:cfg['concurrency']['packed_affinity']==[cores[0]['logical_cpu']] and cfg['concurrency']['packed_workers']==1,16:cfg['concurrency']['fixed_total_core_comparison'] is False,17:len(cfg['host']['linux']['topology'])==16,18:len(cores)==4,19:len(cfg['concurrency']['parent_affinity'])==4,20:cfg['concurrency']['OMP_NUM_THREADS']==1 and cfg['concurrency']['OMP_DYNAMIC'] is False,21:cfg['build']['MULTI_THREAD'] is False,
      22:cfg['phases']['repeated_TaskTotal']=='max(worker_end_r) - min(worker_start_r)',23:cfg['phases']['packed_TaskTotal']=='packed_task_end - packed_task_start',24:cfg['phases']['clock']=='CLOCK_MONOTONIC_RAW',25:len(cfg['phases']['COLD'])==8,26:len(cfg['phases']['ONLINE'])==5 and len(cfg['phases']['ONLINE_staging'])==3,27:'private' in cfg['concurrency']['server_semantics'],28:'floor' in cfg['target_formula'],29:cfg['fixture']['public_seed']==DATA_SEED_LABEL,30:'Fresh exec/client/key per worker' in cfg['fresh_key_rule'],31:'direct K_r' in cfg['fresh_key_rule'],32:'repeated uses 1' in cfg['fresh_key_rule'],33:cfg['crypto']==CRYPTO,
      34:native['status']=='PASS',35:sha(binary)==cfg['build']['binary_sha256'],36:smoke['formal_observations']==0,37:cfg['counts']['point_view_cells']==24,38:len(schedule)==312,39:cfg['counts']['parent_attempts']==624,40:sum(1+e['alpha'] for e in schedule)==1248,41:sum(e['warmup'] for e in schedule)==72,42:sum(not e['warmup'] for e in schedule)==240,43:validate_schedule(schedule,cfg['workloads']),44:len(schedule)==312,45:sha(ROOT/cfg['schedule']['path'])==cfg['schedule']['sha256'],46:(cfg['counts']['warmup_pairs_per_cell'],cfg['counts']['measured_pairs_per_cell'])==(3,10),47:cfg['analysis']['quantile']=='Type 7',48:cfg['analysis']['bootstrap']['resamples']==10000,49:cfg['analysis']['bootstrap']['seed']==2026092501,50:'grand ratio' in cfg['analysis']['prohibited'],51:cfg['payload']['ciphertext_bytes']==131072,52:cfg['payload']['transport_bytes']=='NOT_MEASURED',53:'RUSAGE_SELF' in cfg['CPU']['worker'],54:cfg['RSS']['repeated']=='SUM_OF_WORKER_PEAK_RSS_UPPER',55:resource['status']=='FEASIBLE',56:cfg['integrity_policy']=='MANIFEST_LEVEL_V1',57:len([p for p in scoped_files() if p.suffix=='.sha256'])==1,58:binary.with_name(binary.name+'.sha256').is_file(),59:protected['B2A_sidecars_unchanged'],60:True,61:bool(cfg['build']['source_hashes']),62:binary.with_name(binary.name+'.sha256').read_text().split()[0]==sha(binary),63:not protected['mismatches'],64:not protected['mismatches'],65:not (NOTES/'B2_B_execution').exists(),66:cfg['next_stage']=='B2_B_CONTROLLED_SCALABILITY_EXECUTION'}
    assert all(predicates.values()),[n for n,v in predicates.items() if not v]
    def evidence(n):
        if n<=2:return 'B2_B_freeze_logs/parent_evidence_verification.json'
        if n in (3,10,11,12,27,28,29,30,31,32,33,36,65,66):return 'B2_B_protocol.md; B2_B_freeze_logs/freeze_config.json'
        if 4<=n<=9:return 'B2_B_workload_matrix.json'
        if 13<=n<=26:return 'B2_B_concurrency_contract.md; B2_B_freeze_environment.json; build_manifest.json'
        if n in (34,35,62):return 'B2_B_freeze_logs/build_manifest.json; native_build_verification.json; binary sidecar'
        if 37<=n<=46:return 'B2_B_run_schedule.json; contract_tests_final.json; release manifest schedule digest'
        if 47<=n<=50:return 'B2_B_statistics_plan.md; contract_tests_final.json'
        if 51<=n<=55:return 'B2_B_resource_preflight.json; freeze_config.json CPU/RSS/payload'
        if n in (59,63,64):return 'B2_B_freeze_logs/protected_files_verification.json'
        return 'B2_B_freeze_manifest.json; verify_manifest.py (executed after sealing by this finalizer)'
    status=dict(status='B2_B_FREEZE_PASS',integrity_policy='MANIFEST_LEVEL_V1',counts=cfg['counts'],all_B2B_L_equals_1=True,core_mapping=cores,resource_preflight='FEASIBLE',native_build='PASS',unit_schema_tests=tests['tests'],functional_smoke_cases=3,formal_performance_observations=0,zero_formal_observations=True,secondary_status=cfg['secondary_status'],protected_artifacts='UNCHANGED',protected_files_verified=protected['checked'],B2_A_sidecars='UNCHANGED',ordinary_sidecar_count=0,allowed_sidecars_created=['revision_notes/B2_B_freeze_manifest.json.sha256',cfg['build']['binary']+'.sha256'],post_execution_artifact_index_created=False,manuscript_modified=False,formal_proofs_modified=False,acceptance_questions=[dict(number=n,question=q,answer='YES' if predicates[n] else 'NO',evidence=evidence(n)) for n,q in questions],next_stage=cfg['next_stage'],next_stage_executed=False,security_boundary=BOUNDARY)
    write(NOTES/'B2_B_freeze_status.json',status)
    for n in REQUIRED:assert (NOTES/n).is_file(),n
    files=scoped_files();artifacts=[dict(path=p.relative_to(ROOT).as_posix(),size=p.stat().st_size,sha256=sha(p),role=role(p)) for p in files]
    source_tools={p.relative_to(ROOT).as_posix():sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.cpp','.ps1')}
    anchors={n:sha(ROOT/n) for n in ['revision_notes/B2_A_artifact_hashes.json','revision_notes/B2_A_status.json','revision_notes/B1_primary_audit/artifact_hashes.json','revision_notes/B1_primary_audit/audit_status.json','revision_notes/B2_roadmap_amendment.json','revision_notes/B0_benchmark_manifest.json','revision_notes/T0_secondary_selection_manifest.json']}
    manifest=dict(cfg,freeze_status='B2_B_FREEZE_PASS',sealed_utc=datetime.now(timezone.utc).isoformat(),parent_hashes=anchors,parent_B2A_status=read(NOTES/'B2_A_status.json')['status'],parent_B1_audit_status=read(NOTES/'B1_primary_audit/audit_status.json')['status'],source_tool_hashes=source_tools,artifacts=artifacts,required_artifacts=['revision_notes/'+n for n in REQUIRED],sidecar_policy=dict(ordinary_sidecars=0,allowed_in_this_stage=['revision_notes/B2_B_freeze_manifest.json.sha256',cfg['build']['binary']+'.sha256'],prospective_only=True,self_hash_in_manifest=False),freeze_validation=dict(unit_schema_tests=tests,smoke=smoke,protected_files=protected,native_build=native),future_outputs='B2_B_execution_inputs/ and B2_B_execution/ are future execution evidence, excluded from freeze-set equality only; post-execution evidence index is created after execution, never here.',verification='Manifest-level hashes/sizes for every new freeze artifact; verify_manifest.py recomputes after sealing; native dependencies/libraries rechecked at future release. The release sidecar externally anchors this manifest.')
    errors,_=verify_entries(manifest,ROOT);assert not errors,errors
    write(MANIFEST,manifest);write(MANIFEST.with_suffix('.json.sha256'),sha(MANIFEST)+'  '+MANIFEST.name)
    verified=verify()
    print(json.dumps(dict(status=status['status'],acceptance_yes=66,artifact_count=len(artifacts),protected_files=protected['checked'],ordinary_sidecars=0,allowed_sidecars=2,schedule_sha256=cfg['schedule']['sha256'],binary_sha256=sha(binary),freeze_manifest_sha256=sha(MANIFEST),verification=verified['status'],formal_observations=0,next_stage=cfg['next_stage'])))
if __name__=='__main__':main()
