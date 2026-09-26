"""Materialize the contract before any formal measurement; never overwrite a frozen version."""
import os,platform,subprocess,json,shutil,argparse,sys
from spec import *
from validate import schema
def command(*args):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return {"returncode":p.returncode,"output":p.stdout.strip()}
def host():
    info={k:v for k,v in (line.split(":",1) for line in Path("/proc/meminfo").read_text().splitlines())}
    data={"host_id":"B0-Ryzen7-3700X-WSL2-Ubuntu24.04-v1","human_confirmed":True,
        "human_confirmation":"2026-09-24 conversation: 使用目前這台 WSL2／Ubuntu",
        "cpu_model":"AMD Ryzen 7 3700X 8-Core Processor","sockets":1,"physical_cores":8,"logical_cpus":16,"SMT":"2 threads/core",
        "NUMA_nodes":1,"virtualization":"WSL2 guest, Microsoft kernel; not a physical bare-metal timing claim",
        "kernel":platform.release(),"kernel_full":platform.version(),"python":sys.version,"distro":Path("/etc/os-release").read_text(),
        "lscpu":command("lscpu","-J"),"allowed_affinity":sorted(os.sched_getaffinity(0)),
        "memory_total_bytes":int(info["MemTotal"].split()[0])*1024,"swap_total_bytes":int(info["SwapTotal"].split()[0])*1024,
        "storage":command("df","-B1","-T",str(ROOT)),"mount":command("findmnt","-T",str(ROOT)),
        "cpu_topology":{str(i):{"physical_package_id":Path(f"/sys/devices/system/cpu/cpu{i}/topology/physical_package_id").read_text().strip(),
                              "core_id":Path(f"/sys/devices/system/cpu/cpu{i}/topology/core_id").read_text().strip(),
                              "thread_siblings_list":Path(f"/sys/devices/system/cpu/cpu{i}/topology/thread_siblings_list").read_text().strip()} for i in (0,2)},
        "governor":"HOST_MANAGED_NOT_EXPOSED_TO_WSL","turbo_state":"HOST_MANAGED_NOT_EXPOSED_TO_WSL",
        "frequency_policy":"fixed Windows power plan recorded separately; no frequency changes during batch",
        "temperature_frequency_collection":"record when exposed; WSL hardware sensors unavailable, no fabricated values",
        "background_load_policy":"one benchmark parent; no parallel builds, estimators or other deliberate CPU/GPU jobs; close heavy host applications before B1; record process/load snapshots",
        "environment_failure_policy":"known host suspend/reboot, host resource failure, swapping/thrashing or observed throttling invalidates entire batch; keep every row and failure; never trim individual timings",
        "windows":json.loads((LOG/"windows_host.json").read_text(encoding="utf-8-sig"))}
    assert data["cpu_topology"]["0"]["core_id"]!=data["cpu_topology"]["2"]["core_id"]
    return data
def contract():
    points=matrix()
    for p in points:p["db_fixture_hash"],p["encoded_db_hash"]=db_hashes(p["N"],p["ell_bits"],p["rho_0"])
    build=json.loads((LOG/"build_environment.json").read_text())
    build_small={k:build[k] for k in ("binary","binary_sha256","backend_commit","compiler","compiler_sha256","compiler_version",
                                    "compile_flags","link_flags","PGO","LTO","MULTI_THREAD","libraries","overlay_base_sha256","overlay_sha256")}
    caps={"wall_timeout_ns":900_000_000_000,"aggregate_address_space_bytes":16*1024**3,"aggregate_rss_bytes":16*1024**3,
          "parent_rss_bytes":1024**3,"per_file_bytes":1024**2,"task_disk_bytes":8*1024**2,"batch_disk_bytes":16*1024**3,
          "disk_free_reserve_bytes":20*1024**3,"worker_processes_max":2,"parent_processes":1,"total_processes_max":3,
          "total_core_budget":2,"monitor_interval_ns":10_000_000}
    dry={**caps,"wall_timeout_ns":60_000_000_000,"aggregate_address_space_bytes":4*1024**3,"aggregate_rss_bytes":4*1024**3,
         "disk_free_reserve_bytes":1024**3}
    return {"experiment_version":VERSION,"readiness":"DRAFT_DRY_RUN_ONLY","comparison_unit":"completed ordered two-record task",
        "backend_commit":COMMIT,"crypto":{"n":4096,"q_id":"Q2","q":Q,"primes":[2305843009213317121,2305843009213120513],
              "Berr":200,"recursion_dimension":1,"aggregation_factor":1},
        "profiles":[{"rho_0":r,"w":2*r} for r in (8,12,16)],"workloads":points,
        "primary_comparator":{"packed":"one fresh-key alpha=2 task","repeated":"two concurrent independently exec-created fresh-key alpha=1 workers",
            "alignment":"same rho,w,layout,N,ell,raw DB and encoded DB; baseline weights K=[1]; packed K=[1,2^rho]"},
        "phase_taxonomy":PHASES+["TaskTotal"],
        "clock":{"implementation":"Linux clock_gettime(CLOCK_MONOTONIC_RAW)","resolution_ns":int(time_resolution()),
                 "parent":"Python time.clock_gettime_ns(CLOCK_MONOTONIC_RAW)","TaskTotal":"min(worker task_start) to max(worker task_end); independent endpoints"},
        "lifecycle":{"COLD":"all setup/key/encoding/import/query/reply/extraction inside task interval",
            "ONLINE":"each isolated worker stages private immutable server+encoded/imported DB before ready barrier; fresh client and key after release",
            "reuse":"same conditional already-preprocessed state for both methods; no actual cross-process cache or DB sharing",
            "amortization":"analytical only: T_pre_total/M + T_online for declared positive integer M; no M chosen in B0",
            "teardown":"outside TaskTotal after validation; isolated exec process for every task/worker",
            "validation":"all workers pass completion barrier before any worker begins comparison/hash/log formatting"},
        "concurrency":{"primary_core_budget":2,"packed_affinity":[0,2],"repeated_affinity":[[0],[2]],
            "parent_affinity":[0,2],"omp_threads_packed":1,"omp_threads_each_repeated":1,
            "native_threading":"MULTI_THREAD absent; source-native loops serial; actual thread counts sampled, no claimed 2-thread packed acceleration",
            "release":"all ready then identical future MONOTONIC_RAW timestamp via pipes (5 ms lead); actual starts retained",
            "PRNG":"separate exec processes; unchanged /dev/urandom-seeded process-global Salsa20 per worker"},
        "repetitions":{"warmup_per_point_method_mode":3,"measured_by_N":{"256":30,"1024":30,"4096":20,"16384":10},
            "failures":"fixed scheduled attempts; never adaptive repetitions; failed warmup invalidates batch readiness for analysis"},
        "run_randomization":{"seed":SCHEDULE_SEED,"algorithm":"SHA256 keyed ordering of rounds, workload/profile, modes and balanced pair orientation; generated before measurements",
                             "pairing":"adjacent packed/repeated tasks share pair_id; each measured view has exactly half packed-first"},
        "data_fixture":{"generator":"SplitMix64 stream; state=DATA_SEED xor (N<<32) xor ell; little-endian bytes per record; unused high bits zero",
            "public_seed":DATA_SEED,"hash":"SHA256 concatenation of fixed-length records in increasing index; same rule for encoded logical DB",
            "target_rule":"[floor(N/4),floor(3N/4)]; if equal use (first+1)%N; N<2 rejected","performance_class":"deterministic pseudorandom only"},
        "cooldown":{"policy":"A_NO_FORCED_COOLDOWN_RANDOMIZED_INTERLEAVING","adaptive":False},
        "statistics":{"primary":"TaskTotal","summary":["n_complete","n_failed","median","Q1","Q3","IQR","min","max","mean","sample_stddev"],
            "quantile":"linear interpolation h=(n-1)*p (Type 7)","outlier_removal":"NONE",
            "paired_ratio":"actual repeated-task wall / actual packed-task wall, matched pair_id and same mode/point",
            "CI":"percentile 95% bootstrap of median paired ratios; resample complete pairs with replacement",
            "bootstrap_resamples":10000,"analysis_seed":ANALYSIS_SEED,"incomplete_pairs":"retain failure counts; explicitly count missing ratios, no imputation"},
        "resource_caps":caps,"dry_run_caps":dry,"host":host(),"build":build_small,
        "payload":{"ciphertext_bytes":131072,"basis":"actual a||b native buffers copied; RNS-major uint64, tested little-endian ABI",
            "transport_bytes":"NOT_MEASURED","network_policy":"LOCAL_NO_ARTIFICIAL_NETWORK_DELAY",
            "modeled_network_schema":{"status":"FUTURE_ANALYTICAL_ONLY","bandwidth_bytes_per_second":None,"RTT_ns":None,"concurrent_rounds":None,"model_formula":None}},
        "memory":{"primary":"per-process lifetime peak RSS; repeated sum-of-worker-peaks upper bound",
            "parent":"separately reported, not silently assigned to worker sum","shared_preprocessing":False,
            "synchronized_peak":"not measured; never equate sum of peaks with synchronized peak"},
        "optimized_baseline":{"status":"ADMISSION_FROZEN_NOT_TUNED","candidates":[{"rho_0":r,"w":2*r} for r in (8,12,16)],
            "tuning_subset":[{"N":N,"ell_bits":ell} for N in (128,512) for ell in (384,1536)],
            "budget":{"warmup":3,"measured":10,"per":"candidate x tuning point x COLD/ONLINE","resources":"identical primary caps, fresh keys and concurrent repeated task"},
            "metric":"global candidate: geometric mean over four tuning points of median ONLINE repeated-task latency; no packed timings",
            "tie_break":"smaller rho_0; any candidate with a failed tuning attempt is ineligible; if none eligible N/A",
            "freeze_before_main_test":True,"main_coverage":"all 16 N/ell combinations, both views, chosen global configuration; separate secondary table",
            "unalignable":"QUALITATIVE/N/A; external schemes never built/run"},
        "status_vocabulary":STATUSES,"schedule_file":"revision_notes/B0_run_schedule.json",
        "preflight_file":"revision_notes/B0_resource_preflight.json","frozen_files":{},
        "security_boundary":["native sampler != chi_r","M3-A epsilon_dec not applied to native timing",
            "246 E2E successes are not a failure estimate","concrete-security diagnostics supplementary","no 128-bit native claim"],
        "formal_measurements_executed_in_B0":False,"version_policy":"new immutable version+explicit changelog for any change; no silent overrides"}
def time_resolution():
    import time
    return round(time.clock_getres(time.CLOCK_MONOTONIC_RAW)*1e9)
def main():
    p=argparse.ArgumentParser();p.add_argument("--final",action="store_true");p.add_argument("--revise-from");a=p.parse_args()
    destination=ROOT/"revision_notes/B0_benchmark_manifest.json"
    previous=None
    if a.final and destination.exists():
        previous=json.loads(destination.read_text())
        if not a.revise_from or previous["experiment_version"]!=a.revise_from or VERSION==a.revise_from:
            raise SystemExit("immutable freeze exists; revision requires explicit prior version and new VERSION")
        snapshot=ROOT/"revision_notes/B0_frozen"/(a.revise_from+".json")
        assert snapshot.read_bytes()==destination.read_bytes(),"prior immutable snapshot mismatch"
        assert sha(snapshot)==snapshot.with_suffix(".json.sha256").read_text().split()[0]
    m=contract();rows=schedule(m["workloads"]);pre=[preflight(p) for p in m["workloads"]]
    assert len(m["workloads"])==48 and len(rows)==4896
    dump(ROOT/"revision_notes/B0_run_schedule.json",rows);dump(ROOT/"revision_notes/B0_resource_preflight.json",pre)
    dump(HERE/"measurement.schema.json",schema());dump(LOG/"host_manifest.json",m["host"])
    lines=(HERE/"worker.cpp").read_text().splitlines()
    tokens=["Timer t(spans[","task_begin=now()","task_end=now()","transfer(readyfd,&done","Timer(Span&"]
    dump(LOG/"source_boundary_map.json",{"source":"tools/benchmark/worker.cpp","sha256":sha(HERE/"worker.cpp"),
        "boundaries":[{"line":i,"text":line.strip()} for i,line in enumerate(lines,1) if any(t in line for t in tokens)]})
    if not a.final:
        dump(LOG/"draft_dry_manifest.json",m);print("48 points, 4896 scheduled task attempts, resource preflight materialized; no formal execution");return
    test=json.loads((LOG/"dry_run_acceptance.json").read_text());assert test["status"]=="PASS"
    assert all(sha(ROOT/name)==digest for name,digest in test["tested_hashes"].items()),"acceptance used stale code"
    m["readiness"]="B0_PASS"
    if previous:
        m["supersedes"]={"experiment_version":previous["experiment_version"],"manifest_sha256":sha(destination),
            "reason":"mixed-newline manuscript utility and reliable Windows-side host snapshot; native binary, workload, resources, schedule and statistics unchanged",
            "changelog":"revision_notes/B0_change_log.md"}
    paths=[p for p in HERE.iterdir() if p.suffix in (".py",".cpp",".json",".ps1")]
    paths += [HERE/"build/b0_worker",LOG/"build_environment.json",LOG/"host_manifest.json",LOG/"source_boundary_map.json",
              ROOT/m["schedule_file"],ROOT/m["preflight_file"]]
    paths += list((ROOT/"revision_notes").glob("B0_*.md"))
    m["frozen_files"]={str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}
    destination=ROOT/"revision_notes/B0_benchmark_manifest.json"
    dump(destination,m)
    digest=sha(destination);destination.with_suffix(".json.sha256").write_text(digest+"  B0_benchmark_manifest.json\n")
    versioned=ROOT/"revision_notes/B0_frozen"/(VERSION+".json")
    if versioned.exists():raise RuntimeError("cannot replace versioned snapshot")
    dump(versioned,m);versioned.with_suffix(".json.sha256").write_text(digest+"\n")
    print("B0 immutable manifest frozen:",digest)
if __name__=="__main__":main()
