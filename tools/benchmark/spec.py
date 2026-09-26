"""Frozen B0 definitions. Seeds here never enter cryptographic randomness."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
LOG=ROOT/"revision_notes/B0_logs"
VERSION="B0-1.1"
COMMIT="75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c"
Q="5316911983137472318178862960259203073"
DATA_SEED=0x42305f4441544131
SCHEDULE_SEED="B0-order-20260924-v1"
ANALYSIS_SEED=2026092401
PHASES=["ConfigureClient","ClientSetupKeyGen","ConfigureServer","EncodeDB","ImportPreprocess","QueryGen","ReplyGen","ReplyExt","ValidationOverhead"]
STATUSES=["COMPLETE","TIMEOUT","RESOURCE_LIMIT","RUNTIME_FAIL","WRONG_OUTPUT"]
METHODS=["packed","repeated"]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(path,x):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def targets(N):
    if N<2:raise ValueError("two distinct targets require N >= 2")
    a,b=N//4,3*N//4
    return [a,b if b!=a else (a+1)%N]
def fixture(N,ell):
    state=DATA_SEED^(N<<32)^ell;mask=(1<<64)-1;rows=[]
    for i in range(N):
        row=bytearray()
        for offset in range(0,(ell+7)//8,8):
            state=(state+0x9e3779b97f4a7c15)&mask;z=state
            z=((z^(z>>30))*0xbf58476d1ce4e5b9)&mask
            z=((z^(z>>27))*0x94d049bb133111eb)&mask
            row.extend((z^(z>>31)).to_bytes(8,"little"))
        row=row[:(ell+7)//8]
        if ell%8:row[-1]&=(1<<(ell%8))-1
        rows.append(bytes(row))
    return rows
def db_hashes(N,ell,rho):
    raw=fixture(N,ell);h=hashlib.sha256();J=(ell+rho-1)//rho;L=(J+4095)//4096
    for row in raw:
        n=int.from_bytes(row,"little");value=0
        for j in range(J):value|=((n>>(j*rho))&((1<<rho)-1))<<(j*2*rho)
        h.update(value.to_bytes(L*4096*2*rho//8,"little"))
    return hashlib.sha256(b"".join(raw)).hexdigest(),h.hexdigest()
def point(N,ell,rho):
    J=(ell+rho-1)//rho;L=(J+4095)//4096
    return {"id":f"N{N}_ell{ell}_rho{rho}","N":N,"ell_bits":ell,"rho_0":rho,"w":2*rho,"J":J,"L":L,
        "target_tuple":targets(N),"layout_id":f"LSB-rho{rho}-w{2*rho}-n4096-L{L}-v1",
        "encoded_record_bytes":L*4096*2*rho//8}
def matrix():return [point(N,ell,rho) for N in (256,1024,4096,16384) for ell in (256,512,1024,2048) for rho in (8,12,16)]
def ordered(items,tag):
    return sorted(items,key=lambda x:hashlib.sha256((SCHEDULE_SEED+"/"+tag+"/"+json.dumps(x,sort_keys=True)).encode()).digest())
def schedule(points):
    # Interleave workload/profile pairs within every round, not entire profile blocks.
    rows=[]
    for warmup in (True,False):
        for k in range(3 if warmup else 30):
            eligible=[p for p in points if warmup or k<({256:30,1024:30,4096:20,16384:10}[p["N"]])]
            for p in ordered(eligible,f"round/{warmup}/{k}"):
                for mode in ordered(["COLD","ONLINE"],f"view/{p['id']}/{warmup}/{k}"):
                    n=3 if warmup else {256:30,1024:30,4096:20,16384:10}[p["N"]]
                    orientations=ordered(list(range(n)),f"orientation/{p['id']}/{mode}/{warmup}")
                    first=orientations.index(k)%2
                    pair=f"{p['id']}/{mode}/{'W' if warmup else 'M'}{k:02}"
                    for method in METHODS[first:]+METHODS[:first]:
                        rows.append({"ordinal":len(rows),"run_id":f"B0-plan-{len(rows):05}","pair_id":pair,
                            "point_id":p["id"],"method":method,"preprocess_mode":mode,"warmup":warmup,"repetition":k})
    return rows
def preflight(p):
    N=p["N"];L=p["L"];ct=131072
    encoded=N*p["encoded_record_bytes"];imported=N*L*65536
    raw=N*((p["ell_bits"]+7)//8)
    # Resident components plus 512 MiB reserve; allocator/runtime overhead remains an estimate.
    process=2*N*ct+encoded+imported+raw+512*1024**2
    return {"point_id":p["id"],"single_query_ciphertexts":N,"packed_query_ciphertexts":N,"repeated_query_ciphertexts":2*N,
        "packed_query_bytes":N*ct,"repeated_query_bytes":2*N*ct,
        "packed_reply_ciphertexts":L,"repeated_reply_ciphertexts":2*L,
        "packed_reply_bytes":L*ct,"repeated_reply_bytes":2*L*ct,
        "encoded_db_bytes_per_worker":encoded,"imported_RNS_bytes_per_worker":imported,
        "query_plus_Shoups_bytes_per_worker":2*N*ct,"raw_db_bytes_per_worker":raw,
        "estimated_process_resident_class_bytes":process,"repeated_estimated_resident_upper_bytes":2*process,
        "estimate_not_measured":True,"ciphertexts_persisted_to_disk":False,
        "task_log_estimate_bytes":65536,"task_log_hard_bound_bytes":8*1024**2}
