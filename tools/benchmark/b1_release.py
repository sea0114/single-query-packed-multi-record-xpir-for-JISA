"""B1 release gate; never executes a native task."""
import os,sys,time,subprocess
from b1_common import *
from tuning_release import linux_environment

def release(windows_name,output_name):
    m,entries,points=entries_and_manifest(); checks={};details={}
    def check(k,ok,detail=None):
        checks[k]='PASS' if ok else 'FAIL'
        if detail is not None:details[k]=detail
    check('B0_version_manifest_schedule_counts',True)
    from runner import load_manifest
    try: load_manifest(MANIFEST); check('B0_frozen_files_and_libraries',True)
    except Exception as error:check('B0_frozen_files_and_libraries',False,str(error))
    check('binary',sha(ROOT/m['build']['binary'])==BINARY_HASH==m['build']['binary_sha256'])
    check('backend_commit',m['backend_commit']==m['build']['backend_commit']==COMMIT)
    build=read(ROOT/'revision_notes/B0_logs/build_environment.json')
    compiler=Path(subprocess.check_output(['which','g++'],text=True).strip()).resolve()
    check('compiler_path_hash_version',str(compiler)==m['build']['compiler'] and sha(compiler)==m['build']['compiler_sha256'] and subprocess.check_output(['g++','--version'],text=True)==m['build']['compiler_version'])
    check('flags',build['compile_flags']==m['build']['compile_flags'] and build['link_flags']==m['build']['link_flags'])
    check('sources_headers_overlay',all(Path(p).is_file() and sha(p)==h for p,h in build['dependencies'].items()))
    check('pinned_upstream',not hash_check(build['upstream_files']) and build['backend_commit']==COMMIT)
    check('T0_manifest',sha(ROOT/'revision_notes/T0_secondary_selection_manifest.json')==T0_HASH)
    protection_report=read(LOG/'protected_pre_release_verification.json')
    check('T0_all_artifacts_and_protected_files',protection_report['status']=='PASS',protection_report)
    check('prior_full_hash_confirmation',read(ROOT/'revision_notes/T0_logs/hash_confirmation.json')['confirmed_hash']==B0_HASH)
    env=linux_environment();win=read(LOG/windows_name)
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(win['captured_utc'])).total_seconds()
    check('fresh_Windows_snapshot',0<=age<=300,age)
    check('Windows_CPU',win['processor']['Name'].strip()==m['host']['cpu_model'] and win['processor']['NumberOfCores']==8 and win['processor']['NumberOfLogicalProcessors']==16)
    check('Windows_OS',win['os']['Version']==m['host']['windows']['os']['Version'])
    check('Balanced_power_plan','381b4222-f694-41f0-9685-ff5bb260df2e' in win['power_plan'].lower())
    check('host_events_and_boot',win['event_log_status']=='READ_OK' and not win['relevant_environment_events'] and datetime.fromisoformat(win['last_boot_utc'])<=datetime.fromisoformat(win['events_since_utc']),win['relevant_environment_events'])
    check('no_Windows_competitors',not win['competing_processes'],win['competing_processes'])
    check('kernel_distro_python',env['kernel']==m['host']['kernel'] and env['distro']==m['host']['distro'] and sys.version==m['host']['python'])
    check('CPU_model',m['host']['cpu_model'] in Path('/proc/cpuinfo').read_text())
    check('CPU_affinity',{0,2}<=set(env['affinity']))
    check('CPU_physical_topology',env['cpu_topology']==m['host']['cpu_topology'] and env['cpu_topology']['0']['core_id']!=env['cpu_topology']['2']['core_id'])
    check('free_disk',env['disk_free_bytes']>=m['resource_caps']['disk_free_reserve_bytes'],env['disk_free_bytes'])
    mem={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in env['memory'].splitlines())}
    check('available_RAM',mem['MemAvailable']>=m['resource_caps']['aggregate_rss_bytes']+m['resource_caps']['parent_rss_bytes'],mem['MemAvailable'])
    check('no_swap_in_use',mem['SwapFree']==mem['SwapTotal'])
    names=subprocess.check_output(['ps','-eo','comm='],text=True).splitlines()
    competitors=[n.strip() for n in names if n.strip() in ('cc1plus','cc1','g++','gcc','sage','b0_worker','s4_n_e2e','nvcc','stress','stress-ng')]
    check('no_Linux_competitors',not competitors,competitors)
    check('native_clock_resolution',round(time.clock_getres(time.CLOCK_MONOTONIC_RAW)*1e9)==m['clock']['resolution_ns'])
    check('no_existing_B1_native_batch',not BATCH.exists())
    others=[p.name for p in (ROOT/'revision_notes').iterdir() if p.is_dir() and (p.name.startswith('B1') or p.name.startswith('B2')) and p!=LOG]
    check('no_secondary_or_alpha_gt2_batch',not others,others)
    if (LOG/'preregistration.json').exists():
        pr=read(LOG/'preregistration.json')
        check('additive_tools_frozen',not hash_check(pr['tool_hashes']))
        check('execution_protocol_frozen',sha(ROOT/'revision_notes/B1_primary_execution.md')==pr['execution_protocol_hash'])
    result={'status':'PASS' if all(v=='PASS' for v in checks.values()) else 'BLOCKED','utc':now(),
            'checks':checks,'details':details,'Windows_snapshot':win,'Linux_environment':env,
            'B0_manifest_hash':B0_HASH,'schedule_hash':SCHEDULE_HASH,'binary_hash':BINARY_HASH,'T0_manifest_hash':T0_HASH,
            'B1_main_observations':0}
    dump(LOG/output_name,result)
    print(json.dumps({'release':result['status'],'failed_checks':[k for k,v in checks.items() if v!='PASS']}),flush=True)
    return m,entries,points,result

if __name__=='__main__':
    release(sys.argv[1],sys.argv[2])
