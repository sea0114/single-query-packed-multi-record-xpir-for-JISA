"""Process-isolated completed-task runner. B0 invokes only run_task(..., dry=True)."""
import os,sys,time,json,struct,subprocess,resource,signal,select,hashlib,argparse,shutil
from pathlib import Path
from spec import *
NOW=lambda:time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
NUMERIC=["pid","ppid","task_start_ns","task_end_ns","task_total_ns","release_ns","preprocess_start_ns","preprocess_end_ns",
         "cpu_user_ns","cpu_system_ns","query_ciphertexts","reply_ciphertexts","query_payload_bytes","reply_payload_bytes",
         "peak_rss_kib","key_generation_calls","server_unused_key_generation_calls","query_encrypt_calls","rng_calls","clock_resolution_ns","omp_max_threads"]
def load_manifest(path,verify=True):
    path=Path(path);raw=path.read_bytes()
    expected=path.with_suffix(path.suffix+".sha256").read_text().split()[0]
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError("immutable manifest digest mismatch")
    m=json.loads(raw)
    if verify:
        for name,digest in m["frozen_files"].items():
            if sha(ROOT/name)!=digest:raise ValueError("frozen file changed: "+name)
        for name,digest in m["build"]["libraries"].items():
            if sha(name)!=digest:raise ValueError("linked library changed: "+name)
    return m
def normalize(x):
    for k in NUMERIC:
        if k in x:x[k]=int(x[k])
    x["phase_ns"]={k:int(v) for k,v in x["phase_ns"].items()}
    x["phase_events"]={k:{a:int(b) for a,b in v.items()} for k,v in x["phase_events"].items()}
    x["cpu_affinity"]=[int(v) for v in x["cpu_affinity"]]
    x["output_verified"]=str(x["output_verified"]).lower()=="true"
    return x
def preexec(cpus,as_bytes,file_cap):
    def setup():
        os.sched_setaffinity(0,cpus)
        resource.setrlimit(resource.RLIMIT_AS,(as_bytes,as_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE,(file_cap,file_cap))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    return setup
def proc_sample(pid):
    try:
        fields={}
        for s in Path(f"/proc/{pid}/status").read_text().splitlines():
            if s.startswith(("VmRSS:","Threads:")):
                k,v,*_=s.split();fields[k.rstrip(":")]=int(v)
        return fields.get("VmRSS",0),fields.get("Threads",0)
    except FileNotFoundError:return 0,0
def run_task(m,p,entry,out,dry,inject=None,reverse=False):
    if not dry and m["readiness"]!="B0_PASS":raise ValueError("formal host/build not frozen")
    if not dry and (inject or reverse):raise ValueError("injection/reversal is dry-run only")
    if dry and (p["N"]>32 or p["id"] in {x["id"] for x in m["workloads"]}):
        raise ValueError("B0 dry-run cannot execute a main-matrix point")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    caps=m["dry_run_caps"] if dry else m["resource_caps"]
    if shutil.disk_usage(out).free<caps["disk_free_reserve_bytes"]:raise RuntimeError("disk reserve preflight")
    method=entry["method"];count=1 if method=="packed" else 2
    partitions=[m["concurrency"]["packed_affinity"]] if count==1 else m["concurrency"]["repeated_affinity"]
    original_affinity=os.sched_getaffinity(0)
    os.sched_setaffinity(0,m["concurrency"]["packed_affinity"])
    task_targets=list(reversed(p["target_tuple"])) if reverse else p["target_tuple"]
    base={"experiment_version":m["experiment_version"],"batch_id":entry.get("batch_id","B0-functional"),
        **entry,"method":method,"workload":{"N":p["N"],"ell_bits":p["ell_bits"],"rho_0":p["rho_0"],"alpha":2},
        "crypto":{**m["crypto"],"w":p["w"],"B":1<<p["rho_0"],"t":1<<p["w"]},
        "backend_commit":COMMIT,"build_hash":m["build"]["binary_sha256"],"host_id":m["host"]["host_id"],
        "layout_id":p["layout_id"],"target_tuple":task_targets,"preprocess_mode":entry["preprocess_mode"],
        "sampler_label":"native XPIR unchanged; not chi_r","timing_label":"DRY_RUN / NOT_FOR_ANALYSIS" if dry else "FORMAL",
        "transport_bytes":"NOT_MEASURED","network_policy":"LOCAL_NO_ARTIFICIAL_NETWORK_DELAY",
        "notes":["fresh exec process/key per worker","worker-private raw/encoded/imported DB","no artificial network delay"]}
    children=[];begun=NOW();failure=None;failure_reason="";readyset=set();doneset=set();closedpipes=set();validation_released=False
    try:
        for i in range(count):
            rr,rw=os.pipe();gr,gw=os.pipe();wid=f"{entry['run_id']}/w{i}"
            target=task_targets if count==1 else [task_targets[i]]
            stem=out/f"worker{i}"
            job={**p,"targets":target,"preprocess_mode":entry["preprocess_mode"],"ready_fd":rw,"go_fd":gr,
                 "inject":inject if i==count-1 else ""}
            dump(stem.with_suffix(".job.json"),job)
            stdout=stem.with_suffix(".stdout").open("wb");stderr=stem.with_suffix(".stderr").open("wb")
            env={**os.environ,"OMP_NUM_THREADS":"1","OMP_DYNAMIC":"FALSE","OPENBLAS_NUM_THREADS":"1"}
            process=subprocess.Popen([str(ROOT/m["build"]["binary"]),str(stem.with_suffix(".job.json")),str(stem.with_suffix(".result.json"))],
                stdout=stdout,stderr=stderr,env=env,pass_fds=(rw,gr),start_new_session=True,
                preexec_fn=preexec(partitions[i],caps["aggregate_address_space_bytes"]//count,caps["per_file_bytes"]))
            os.close(rw);os.close(gr)
            children.append({"process":process,"rr":rr,"gw":gw,"stem":stem,"worker_id":wid,"target":target,
                "affinity":partitions[i],"stdout":stdout,"stderr":stderr,"rusage":None,"max_threads":0,"sampled_peak_rss_kib":0})
        # Every worker is fully staged (ONLINE) or untouched (COLD) before release.
        release=None
        while any(c["process"].returncode is None for c in children):
            if NOW()-begun>caps["wall_timeout_ns"]:
                failure="TIMEOUT";failure_reason="fixed whole-task wall timeout (includes staging/validation)"
            totalrss=0
            for c in children:
                proc=c["process"]
                if proc.returncode is None:
                    rss,threads=proc_sample(proc.pid);totalrss+=rss
                    c["max_threads"]=max(c["max_threads"],threads);c["sampled_peak_rss_kib"]=max(c["sampled_peak_rss_kib"],rss)
                    pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
                    if pid:
                        proc.returncode=os.waitstatus_to_exitcode(status);c["rusage"]=usage
                        if proc.returncode and proc.returncode!=20 and not failure:
                            failure="RESOURCE_LIMIT" if proc.returncode in (18,-signal.SIGXFSZ) else "RUNTIME_FAIL"
                            failure_reason=f"worker exit {proc.returncode}"
            if totalrss*1024>caps["aggregate_rss_bytes"]:
                failure="RESOURCE_LIMIT";failure_reason="aggregate worker RSS cap"
            if proc_sample(os.getpid())[0]*1024>caps["parent_rss_bytes"]:
                failure="RESOURCE_LIMIT";failure_reason="parent RSS cap"
            if sum(f.stat().st_size for f in out.iterdir() if f.is_file())>caps["task_disk_bytes"]:
                failure="RESOURCE_LIMIT";failure_reason="fixed task disk/log cap"
            if failure:
                for c in children:
                    if c["process"].returncode is None:
                        os.killpg(c["process"].pid,signal.SIGKILL)
                        _,st,ru=os.wait4(c["process"].pid,0);c["process"].returncode=os.waitstatus_to_exitcode(st);c["rusage"]=ru
                break
            if release is None:
                pending=[c["rr"] for c in children if c["rr"] not in readyset and c["rr"] not in closedpipes]
                readable,_,_=select.select(pending,[],[],0.01)
                for fd in readable:
                    if os.read(fd,1)!=b"R":closedpipes.add(fd) # wait4 supplies authoritative failure class.
                    else:readyset.add(fd)
                if len(readyset)==count:
                    release=NOW()+5_000_000
                    for c in children:os.write(c["gw"],struct.pack("<Q",release))
            elif not validation_released:
                pending=[c["rr"] for c in children if c["rr"] not in doneset and c["rr"] not in closedpipes]
                readable,_,_=select.select(pending,[],[],0.01)
                for fd in readable:
                    if os.read(fd,1)!=b"D":closedpipes.add(fd) # Exit status wins over a generic pipe EOF.
                    else:doneset.add(fd)
                if len(doneset)==count:
                    for c in children:os.write(c["gw"],b"V")
                    validation_released=True
            else:time.sleep(0.01) # Parent monitor uses the same total CPU affinity budget.
    finally:
        for c in children:
            c["stdout"].close();c["stderr"].close();os.close(c["rr"]);os.close(c["gw"])
            if c["process"].returncode is None:
                os.killpg(c["process"].pid,signal.SIGKILL);_,st,ru=os.wait4(c["process"].pid,0)
                c["process"].returncode=os.waitstatus_to_exitcode(st);c["rusage"]=ru
        os.sched_setaffinity(0,original_affinity)
    workers=[]
    for i,c in enumerate(children):
        f=c["stem"].with_suffix(".result.json")
        row={**base,"record_type":"worker","run_id":c["worker_id"],"parent_run_id":entry["run_id"],
            "baseline_worker_id":i if count==2 else None,"worker_targets":c["target"],"pid":c["process"].pid,
            "ppid":os.getpid(),"cpu_affinity":c["affinity"],"omp_threads":1,
            "db_fixture_hash":None,"encoded_db_hash":None,"phase_ns":{p:None for p in PHASES},"phase_events":{},
            "task_total_ns":None,"task_start_ns":None,"task_end_ns":None,"cpu_user_ns":None,"cpu_system_ns":None,
            "query_ciphertexts":None,"reply_ciphertexts":None,"query_payload_bytes":None,"reply_payload_bytes":None,
            "peak_rss_kib":int(c["rusage"].ru_maxrss),"status":failure or "RUNTIME_FAIL","failure_reason":failure_reason or "missing worker result",
            "output_verified":False,"exit_code":c["process"].returncode,"observed_max_threads":c["max_threads"],
            "sampled_peak_rss_kib":c["sampled_peak_rss_kib"],"process_lifetime_cpu_user_ns":int(c["rusage"].ru_utime*1e9),
            "process_lifetime_cpu_system_ns":int(c["rusage"].ru_stime*1e9)}
        if f.exists():
            try:row.update(normalize(json.loads(f.read_text())))
            except (ValueError,KeyError):row["failure_reason"]="malformed result";row["status"]="RUNTIME_FAIL"
        if row["status"]=="COMPLETE" and row["exit_code"]!=0:row["status"]="RUNTIME_FAIL";row["failure_reason"]="exit after result"
        row["peak_rss_kib"]=max(row["peak_rss_kib"],int(c["rusage"].ru_maxrss))
        row["workload"]={**base["workload"],"alpha":2 if count==1 else 1}
        workers.append(row)
    # Independently check the deterministic ordered records, outside all native timings.
    expected=fixture(p["N"],p["ell_bits"])
    expected_hashes=(p["db_fixture_hash"],p["encoded_db_hash"]) if "db_fixture_hash" in p else db_hashes(p["N"],p["ell_bits"],p["rho_0"])
    for index,row in enumerate(workers):
        if row["status"]=="COMPLETE" and row.get("actual_hex")!=[expected[t].hex() for t in row["worker_targets"]]:
            row.update(status="WRONG_OUTPUT",failure_reason="parent ordered record check",output_verified=False)
        if row["status"]=="COMPLETE" and ((row["db_fixture_hash"],row["encoded_db_hash"])!=expected_hashes or
              row["cpu_affinity"]!=partitions[index] or row.get("key_generation_calls")!=1):
            row.update(status="RUNTIME_FAIL",failure_reason="frozen DB/affinity/key lifecycle mismatch",output_verified=False)
    if count==2 and all(w["status"]=="COMPLETE" for w in workers) and workers[0]["key_fingerprint"]==workers[1]["key_fingerprint"]:
        workers[1].update(status="RUNTIME_FAIL",failure_reason="duplicate fresh-key fingerprint",output_verified=False)
    precedence=["RESOURCE_LIMIT","TIMEOUT","RUNTIME_FAIL","WRONG_OUTPUT","COMPLETE"]
    status=min([failure or "COMPLETE"]+[w["status"] for w in workers],key=precedence.index)
    complete_intervals=all(w["task_start_ns"] is not None and w["task_end_ns"] is not None for w in workers)
    def total(field):
        return sum(w[field] for w in workers) if all(w[field] is not None for w in workers) else None
    start=min(w["task_start_ns"] for w in workers) if complete_intervals else None
    end=max(w["task_end_ns"] for w in workers) if complete_intervals else None
    parent={**base,"record_type":"task","baseline_worker_id":None,"worker_ids":[w["run_id"] for w in workers],
        "pid":os.getpid(),"worker_pids":[w["pid"] for w in workers],"cpu_affinity":m["concurrency"]["packed_affinity"],"omp_threads":1,
        "db_fixture_hash":workers[0]["db_fixture_hash"],"encoded_db_hash":workers[0]["encoded_db_hash"],
        "phase_ns":{p:total_phase(workers,p) for p in PHASES},"phase_aggregation":"sum of worker phases; NOT task latency",
        "phase_events":{},"task_start_ns":start,"task_end_ns":end,"task_total_ns":end-start if complete_intervals else None,
        "cpu_user_ns":total("cpu_user_ns"),"cpu_system_ns":total("cpu_system_ns"),
        "aggregate_cpu_ns":total("cpu_user_ns")+total("cpu_system_ns") if total("cpu_user_ns") is not None else None,
        "query_ciphertexts":total("query_ciphertexts"),"reply_ciphertexts":total("reply_ciphertexts"),
        "query_payload_bytes":total("query_payload_bytes"),"reply_payload_bytes":total("reply_payload_bytes"),
        "combined_query_bytes":total("query_payload_bytes"),"combined_reply_bytes":total("reply_payload_bytes"),
        "peak_rss_kib":total("peak_rss_kib"),"aggregate_peak_metric":"SUM_OF_WORKER_PEAK_RSS_UPPER",
        "parent_peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "status":status,"failure_reason":failure_reason or "; ".join(w["failure_reason"] for w in workers if w["failure_reason"]),
        "output_verified":status=="COMPLETE" and all(w["output_verified"] for w in workers),
        "barrier_release_ns":release,"barrier_ready_count":len(readyset),
        "barrier_completion_count":len(doneset),"validation_released":validation_released,
        "execution_envelope_ns":NOW()-begun,"injection":inject if dry else None,
        "partial_measurements_retained":status!="COMPLETE"}
    if all("preprocess_start_ns" in w for w in workers):
        parent["preprocess_wall_ns"]=max(w["preprocess_end_ns"] for w in workers)-min(w["preprocess_start_ns"] for w in workers)
    from validate import validate
    for row in workers+[parent]:validate(row)
    with (out/"raw.jsonl").open("w") as f:
        for row in workers+[parent]:f.write(json.dumps(row)+"\n")
    return parent,workers
def total_phase(workers,phase):
    values=[w["phase_ns"][phase] for w in workers]
    return sum(values) if all(v is not None for v in values) else None
def unexecuted_row(m,p,entry,status,reason):
    """A scheduled but unstarted task remains an explicit failed observation."""
    return {**entry,"experiment_version":m["experiment_version"],"record_type":"task","baseline_worker_id":None,
        "workload":{"N":p["N"],"ell_bits":p["ell_bits"],"rho_0":p["rho_0"],"alpha":2},
        "crypto":{**m["crypto"],"w":p["w"],"B":1<<p["rho_0"],"t":1<<p["w"]},
        "backend_commit":COMMIT,"build_hash":m["build"]["binary_sha256"],"host_id":m["host"]["host_id"],
        "layout_id":p["layout_id"],"pid":os.getpid(),"cpu_affinity":m["concurrency"]["packed_affinity"],"omp_threads":1,
        "target_tuple":p["target_tuple"],"db_fixture_hash":None,"encoded_db_hash":None,"phase_ns":{p:None for p in PHASES},
        "task_start_ns":None,"task_end_ns":None,"task_total_ns":None,"cpu_user_ns":None,"cpu_system_ns":None,
        "aggregate_cpu_ns":None,"query_ciphertexts":None,"reply_ciphertexts":None,"query_payload_bytes":None,"reply_payload_bytes":None,
        "combined_query_bytes":None,"combined_reply_bytes":None,"peak_rss_kib":None,"aggregate_peak_metric":"SUM_OF_WORKER_PEAK_RSS_UPPER",
        "status":status,"failure_reason":reason,"output_verified":False,"sampler_label":"native XPIR unchanged; not chi_r",
        "timing_label":"FORMAL","transport_bytes":"NOT_MEASURED","notes":["scheduled task not completed; no timing fabricated"],
        "worker_ids":[entry["run_id"]+f"/w{i}" for i in range(1 if entry["method"]=="packed" else 2)],"worker_pids":[],
        "execution_attempted":False}
def environment_snapshot():
    import platform
    return {"monotonic_raw_ns":NOW(),"kernel":platform.release(),"python":sys.version,
        "memory":Path("/proc/meminfo").read_text(),"loadavg":Path("/proc/loadavg").read_text(),
        "processes":subprocess.check_output(["ps","-eo","pid,ppid,comm,pcpu,pmem"],text=True),
        "windows_capture_policy":"fresh Windows-side snapshot required by formal launcher; do not depend on WSL PE interop",
        "frequency_sensor_paths":[str(p) for p in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_cur_freq")],
        "thermal_sensor_paths":[str(p) for p in Path("/sys/class/thermal").glob("thermal_zone*/temp")]}
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--manifest",required=True);parser.add_argument("--out",required=True)
    parser.add_argument("--formal",action="store_true");parser.add_argument("--windows-host-snapshot");args=parser.parse_args()
    if not args.formal:raise SystemExit("Use dry_run_tests.py for B0; formal execution requires explicit --formal.")
    m=load_manifest(args.manifest)
    if m["readiness"]!="B0_PASS":raise SystemExit("B0 blocked")
    if not args.windows_host_snapshot:raise SystemExit("use run_formal.ps1 to capture fresh Windows host state before B1")
    from datetime import datetime,timezone
    win=json.loads(Path(args.windows_host_snapshot).read_text(encoding="utf-8-sig"))
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(win["captured_utc"])).total_seconds()
    import re
    power_guid=re.search(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",win["power_plan"],re.I)
    if not 0<=age<=300 or not power_guid or power_guid.group().lower()!="381b4222-f694-41f0-9685-ff5bb260df2e":
        raise SystemExit("stale Windows snapshot or frozen Balanced power plan mismatch")
    if win["processor"]["Name"].strip()!=m["host"]["cpu_model"] or win["processor"]["NumberOfLogicalProcessors"]!=16:
        raise SystemExit("frozen Windows processor mismatch")
    import platform
    if platform.release()!=m["host"]["kernel"] or not set(m["concurrency"]["packed_affinity"])<=os.sched_getaffinity(0):
        raise SystemExit("frozen host mismatch")
    out=Path(args.out);out.mkdir(exist_ok=False)
    dump(out/"manifest.json",m)
    dump(out/"windows_host_start.json",win)
    env_start=environment_snapshot();dump(out/"environment_start.json",env_start)
    points={p["id"]:p for p in m["workloads"]}
    entries=json.loads((ROOT/m["schedule_file"]).read_text())
    stopped=None;batch_valid=True
    from validate import validate
    summary=(out/"task_rows.jsonl").open("x")
    for entry in entries:
        entry={**entry,"batch_id":out.name}
        p=points[entry["point_id"]]
        if stopped:row=unexecuted_row(m,p,entry,"RESOURCE_LIMIT",stopped)
        else:
            try:row,_=run_task(m,p,entry,out/f"{entry['ordinal']:05}",False)
            except Exception as error:
                row=unexecuted_row(m,p,entry,"RUNTIME_FAIL",f"runner exception, retain worker directory: {type(error).__name__}: {error}")
        validate(row);summary.write(json.dumps(row)+"\n");summary.flush()
        if entry["warmup"] and row["status"]!="COMPLETE":batch_valid=False
        if sum(p.stat().st_size for p in out.rglob("*") if p.is_file())>m["resource_caps"]["batch_disk_bytes"]:
            stopped="batch disk cap reached; remaining scheduled attempts recorded as RESOURCE_LIMIT";batch_valid=False
    summary.close()
    env_end=environment_snapshot();dump(out/"environment_end.json",env_end)
    swap=lambda x:int(re.search(r"SwapFree:\s+(\d+)",x["memory"]).group(1))
    if swap(env_end)<swap(env_start):batch_valid=False
    dump(out/"batch_status.json",{"environment_valid":batch_valid,"warmup_failure_or_resource_environment_invalid":not batch_valid,
        "manual_host_failure_override":"if known host suspend/throttling/background breach, invalidate ENTIRE batch; preserve this original record and add incident record",
        "scheduled_tasks_retained":len(entries)})
    print("Scheduled batch complete; raw data retained. Analysis is a separate operation.")
if __name__=="__main__":main()
