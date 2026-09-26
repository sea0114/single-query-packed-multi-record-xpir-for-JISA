"""Read-only Linux host snapshot. No benchmark invocation."""
from b2b_common import *
import platform,shutil,time,subprocess
from datetime import datetime,timezone
def capture():
    allowed=sorted(os.sched_getaffinity(0)); topology=[]
    for c in allowed:
        d=Path(f'/sys/devices/system/cpu/cpu{c}/topology')
        topology.append(dict(logical_cpu=c,physical_package_id=int((d/'physical_package_id').read_text()),core_id=int((d/'core_id').read_text()),thread_siblings_list=(d/'thread_siblings_list').read_text().strip()))
    selected=[]; seen=set()
    for c in sorted(topology,key=lambda x:(x['physical_package_id'],x['core_id'],x['logical_cpu'])):
        key=c['physical_package_id'],c['core_id']
        if key not in seen: selected.append(dict(c,label='c'+str(len(selected)))); seen.add(key)
        if len(selected)==4: break
    assert len(selected)==4, 'Four distinct physical cores required'
    memory={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    cpu=Path('/proc/cpuinfo').read_text(); model=next(s.split(':',1)[1].strip() for s in cpu.splitlines() if s.startswith('model name'))
    return dict(captured_utc=datetime.now(timezone.utc).isoformat(),purpose='PRE_REGISTRATION_ENVIRONMENT_SNAPSHOT_NOT_EXECUTION_RELEASE',cpu_model=model,kernel=platform.release(),distro=Path('/etc/os-release').read_text(),python=sys.version,hostname=platform.node(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),allowed_cpus=allowed,topology=topology,selected_cores=selected,memory_bytes=memory,disk=shutil.disk_usage(ROOT)._asdict(),clock='CLOCK_MONOTONIC_RAW',clock_resolution_ns=round(time.clock_getres(time.CLOCK_MONOTONIC_RAW)*1e9),governor='HOST_MANAGED_NOT_EXPOSED_TO_WSL',turbo='HOST_MANAGED_NOT_EXPOSED_TO_WSL',frequency='HOST_MANAGED_NOT_EXPOSED_TO_WSL',loadavg=Path('/proc/loadavg').read_text().strip(),processes=subprocess.check_output(['ps','-eo','pid,ppid,comm'],text=True))
if __name__=='__main__':
    x=capture();write(NOTES/'B2_B_freeze_environment.json',dict(linux=x,windows=read(LOG/'windows_freeze_v2.json'),future_execution_release_required=True));print(json.dumps(dict(selected=x['selected_cores'],memory_available=x['memory_bytes']['MemAvailable'],disk_free=x['disk']['free'])))
