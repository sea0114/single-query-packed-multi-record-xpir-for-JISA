"""B3 public fixtures, explicit contracts, and append-only output utilities."""
from pathlib import Path
from functools import lru_cache
import hashlib,json,os,time
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifact'
CT=131072
NATIVE_COMMIT='75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c'
Q=5316911983137472318178862960259203073
SEED=0x8c3f47282900cee8
PHASES=['ConfigureClient','ClientSetupKeyGen','ConfigureServer','EncodeDB','ImportPreprocess','QueryGen','ReplyGen','ReplyExt','ValidationOverhead']
POLICIES={
 'R1':{'parent_affinity':[0,2],'packed_affinity':[0,2],'repeated_affinity':[[0],[2]],'packed_as_bytes':16*2**30,'repeated_worker_as_bytes':8*2**30,'enforce_aggregate_vm':False,'description':'B1-derived resource bundle; per-task total RLIMIT_AS allowance16GiB; aggregate RSS sampled, not aggregate VmSize.'},
 'R2':{'parent_affinity':[0,2,4,6],'packed_affinity':[0],'repeated_affinity':[[0],[2],[4],[6]],'packed_as_bytes':8*2**30,'repeated_worker_as_bytes':8*2**30,'enforce_aggregate_vm':True,'description':'B2-B-derived bundle; each worker8GiB; aggregate16GiB VmSize/RSS sampled.'}}
CAPS={'wall_timeout_ns':900_000_000_000,'aggregate_rss_bytes':16*2**30,'aggregate_vm_bytes':16*2**30,'parent_rss_bytes':2**30,'per_file_bytes':4*2**20,'task_disk_bytes':32*2**20,'disk_reserve_bytes':20*2**30,'monitor_interval_ns':10_000_000}
def now():return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write_new(p,data):
    p=Path(p);assert p.resolve().is_relative_to(ART.resolve()) or p.resolve().is_relative_to((ROOT/'revision_m1_m7').resolve())
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:f.write(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def append(p,data):
    p=Path(p);assert p.resolve().is_relative_to(ART.resolve())
    with p.open('a',encoding='utf-8') as f:f.write(json.dumps(data,ensure_ascii=False,allow_nan=False)+'\n')
def normalize(v,key=''):
    if key.endswith(('hash','fingerprint','hex')) or key in ('actual_hex','expected_hex'):return v
    if isinstance(v,dict):return {k:normalize(x,k) for k,x in v.items()}
    if isinstance(v,list):return [normalize(x) for x in v]
    if isinstance(v,str):
        if v in ('true','false'):return v=='true'
        if v.isdecimal():return int(v)
    return v
@lru_cache(maxsize=32)
def fixture(N,ell):
    state=SEED^(N<<32)^ell;mask=2**64-1;rows=[]
    for _ in range(N):
        row=bytearray()
        for _ in range((ell+63)//64):
            state=(state+0x9e3779b97f4a7c15)&mask;z=state
            z=((z^(z>>30))*0xbf58476d1ce4e5b9)&mask;z=((z^(z>>27))*0x94d049bb133111eb)&mask
            row.extend((z^(z>>31)).to_bytes(8,'little'))
        row=row[:(ell+7)//8]
        if ell%8:row[-1]&=(1<<(ell%8))-1
        rows.append(bytes(row))
    return rows
@lru_cache(maxsize=32)
def point(a,N,ell):
    assert a in (2,3,4) and N>=a and ell>0
    J=(ell+7)//8;L=(J+4095)//4096;w=8*a
    rows=fixture(N,ell);raw_h=hashlib.sha256();enc_h=hashlib.sha256()
    for row in rows:
        raw_h.update(row);encoded=bytearray(L*4096*a)
        for i,b in enumerate(row):encoded[i*a]=b
        enc_h.update(encoded)
    return {'alpha':a,'N':N,'ell_bits':ell,'rho_0':8,'w':w,'n':4096,'q_id':'Q2','q':str(Q),'J':J,'L':L,'u':a*J/4096,'target_tuple':[(2*r-1)*N//(2*a) for r in range(1,a+1)],'db_fixture_hash':raw_h.hexdigest(),'encoded_db_hash':enc_h.hexdigest(),'fixture_id':'B3_COMMON_PUBLIC_SPLITMIX64_8c3f47282900cee8','ciphertext_bytes':CT,'layout_id':f'LSB-rho8-w{w}-n4096-L{L}-v1'}
def cells(include_multiblock=False):
    out=[]
    for N,ell in ((1024,512),(4096,2048)):
        for view in ('COLD','ONLINE'):
            for impl in ('I1','I2'):
                for policy in ('R1','R2'):
                    out.append({'study':'M6','cell_id':f'M6_{impl}{policy}_N{N}_e{ell}_{view}','implementation_id':impl,'resource_policy_id':policy,'view':view,**point(2,N,ell)})
    for ell in (4096,8192,12288,16384)+((65536,) if include_multiblock else ()):
        for view in ('COLD','ONLINE'):
            out.append({'study':'M5','cell_id':f'M5_I2R2_N1024_e{ell}_{view}','implementation_id':'I2','resource_policy_id':'R2','view':view,**point(4,1024,ell)})
    return out
