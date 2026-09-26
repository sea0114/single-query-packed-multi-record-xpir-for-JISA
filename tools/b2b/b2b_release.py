"""Future pre-observation release gate; this module never launches crypto."""
from b2b_common import *
from b2b_environment import capture
from verify_manifest import verify
from datetime import datetime,timezone
import re,shutil,subprocess
def release_check(windows_path):
    verify();m=read(MANIFEST);env=capture();win=read(windows_path);frozen=m['host'];checks={}
    checks['status']=m['freeze_status']=='B2_B_FREEZE_PASS' and m['zero_formal_observations']
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(win['captured_utc'].replace('Z','+00:00'))).total_seconds()
    checks['fresh_Windows_snapshot']=0<=age<=300
    checks['same_Windows_host']=all(win['computer'][k]==frozen['windows']['computer'][k] for k in ('Name','Manufacturer','Model','TotalPhysicalMemory'))
    checks['same_CPU']=win['processor']==frozen['windows']['processor'] and env['cpu_model']==frozen['linux']['cpu_model']
    guid=lambda s:re.search(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',s,re.I).group().lower()
    checks['same_power_policy']=guid(win['power_plan'])==guid(frozen['windows']['power_plan'])
    checks['same_Windows_OS']=all(win['os'][k]==frozen['windows']['os'][k] for k in ('Version','BuildNumber'))
    checks['same_WSL_host']=all(env[k]==frozen['linux'][k] for k in ('hostname','kernel','distro','python'))
    # A reboot between preregistration and execution is allowed, but is captured anew; changes during a batch invalidate it.
    checks['same_core_topology']=env['topology']==frozen['linux']['topology'] and env['selected_cores']==frozen['linux']['selected_cores']
    checks['cores_available']=set(m['concurrency']['parent_affinity'])<=set(env['allowed_cpus'])
    checks['RAM']=env['memory_bytes']['MemAvailable']>=CAPS['aggregate_rss_bytes']+CAPS['parent_rss_bytes']
    checks['no_swap']=env['memory_bytes']['SwapFree']==env['memory_bytes']['SwapTotal']
    checks['disk']=env['disk']['free']>=CAPS['disk_free_reserve_bytes']+CAPS['batch_disk_bytes']
    checks['clock']=env['clock_resolution_ns']==frozen['linux']['clock_resolution_ns']
    build=m['build'];compiler=Path(shutil.which('g++')).resolve()
    checks['compiler']=str(compiler)==build['compiler'] and sha(compiler)==build['compiler_sha256'] and subprocess.check_output(['g++','--version'],text=True)==build['compiler_version']
    checks['sources_and_headers']=all(Path(n).is_file() and sha(n)==h for n,h in build['dependencies'].items())
    checks['libraries']=all(Path(n).is_file() and sha(n)==h for n,h in build['libraries'].items())
    checks['upstream']=all(sha(ROOT/n)==h for n,h in build['unchanged_upstream_files'].items())
    names=subprocess.check_output(['ps','-eo','comm='],text=True).splitlines()
    checks['no_competing_Linux_workers']=not any(n.strip() in ('b2b_worker','b2_worker','b0_worker','cc1plus','cc1','g++','gcc','sage','stress','stress-ng') for n in names)
    checks['single_batch']=not (NOTES/'B2_B_execution').exists()
    failed=[k for k,v in checks.items() if not v]
    return m,dict(status='PASS' if not failed else 'BLOCKED',failed_checks=failed,checks=checks,freeze_manifest_sha256=sha(MANIFEST),captured_utc=datetime.now(timezone.utc).isoformat(),linux=env,windows=win,formal_observations_before_release=0)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--windows-snapshot',required=True);a=p.parse_args();_,r=release_check(a.windows_snapshot);print(json.dumps({'status':r['status'],'failed_checks':r['failed_checks']}))
