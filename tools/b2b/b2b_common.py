"""B2-B preregistration constants and exact, non-cryptographic fixture logic."""
import sys
sys.dont_write_bytecode = True
import hashlib, json, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'tools/b2b'
NOTES = ROOT / 'revision_notes'
LOG = NOTES / 'B2_B_freeze_logs'
MANIFEST = NOTES / 'B2_B_freeze_manifest.json'
COMMIT = '75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c'
PARENT_HASH = '20c87c2ef18d8b082d1ccc8abd1fdd4f5723b84b2727415cd35b4f50e7db2ad7'
AUDIT_HASH = '5f7f501da96e7e5fdb8e26f6f9e497025282ed6d8b687bcc7a4916c02d05f2d5'
CRYPTO = dict(n=4096,q='5316911983137472318178862960259203073',primes=['2305843009213317121','2305843009213120513'],Berr=200,recursion_dimension=1,aggregation_factor=1)
CT = 131072
DATA_SEED_LABEL = 'B2B-DATA-20260925-v1'
DATA_SEED_DIGEST = hashlib.sha256(DATA_SEED_LABEL.encode()).hexdigest()
DATA_SEED = int.from_bytes(bytes.fromhex(DATA_SEED_DIGEST)[:8], 'little')
ORDER_SEED = 'B2B-order-20260925-v1'
BOOTSTRAP_SEED = 2026092501
LABEL = 'FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE'
PHASES = ['ConfigureClient','ClientSetupKeyGen','ConfigureServer','EncodeDB','ImportPreprocess','QueryGen','ReplyGen','ReplyExt','ValidationOverhead']
STATUSES = ['COMPLETE','TIMEOUT','RESOURCE_LIMIT','RUNTIME_FAIL','WRONG_OUTPUT']
CAPS = dict(wall_timeout_ns=900_000_000_000,per_worker_address_space_bytes=8*2**30,aggregate_address_space_bytes=16*2**30,aggregate_rss_bytes=16*2**30,parent_rss_bytes=2**30,per_file_bytes=2**20,task_disk_bytes=8*2**20,batch_disk_bytes=16*2**30,disk_free_reserve_bytes=20*2**30,monitor_interval_ns=10_000_000,worker_processes_max=4,parent_processes=1,total_processes_max=5)
BOUNDARY = 'Native implementation evidence only; no inference of PLWE hardness, index privacy, 128-bit security, negligible decryption failure, M3 epsilon_dec, chi_r alignment, or native/formal sampler equivalence.'
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def owned(p):
    rel=Path(p).resolve().relative_to(ROOT).as_posix()
    return rel.startswith(('tools/b2b/','revision_notes/B2_B_'))
def write(p,data):
    p=Path(p)
    if not owned(p): raise ValueError('Protected path: '+str(p))
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:
        f.write(data if isinstance(data,str) else json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)); f.write('\n')
def inventory():
    out={}
    for base,dirs,names in os.walk(ROOT):
        dirs[:]=sorted(d for d in dirs if d not in ('.git','.codex','.agents'))
        for n in sorted(names):
            p=Path(base)/n
            if not owned(p): out[p.relative_to(ROOT).as_posix()]=sha(p)
    return out
def targets(N,a): return [(2*r-1)*N//(2*a) for r in range(1,a+1)]
def fixture(N,ell):
    state=DATA_SEED^(N<<32)^ell; mask=2**64-1; rows=[]
    for _ in range(N):
        row=bytearray()
        for _ in range((ell+63)//64):
            state=(state+0x9e3779b97f4a7c15)&mask; z=state
            z=((z^(z>>30))*0xbf58476d1ce4e5b9)&mask; z=((z^(z>>27))*0x94d049bb133111eb)&mask
            row.extend((z^(z>>31)).to_bytes(8,'little'))
        row=row[:(ell+7)//8]
        if ell%8: row[-1]&=(1<<(ell%8))-1
        rows.append(bytes(row))
    return rows
def point(a,N,ell):
    assert a in (2,3,4) and N in (8,1024,4096) and ell in (256,512,2048)
    w=8*a; J=(ell+7)//8; raw=fixture(N,ell); rh=hashlib.sha256(); eh=hashlib.sha256()
    for row in raw:
        rh.update(row); enc=bytearray(4096*w//8)
        for i,b in enumerate(row): enc[i*a]=b
        eh.update(enc)
    return dict(point_id=f'A{a}_N{N}_ell{ell}',alpha=a,rho_0=8,w=w,B=256,t=str(1<<w),weights=[str(1<<(8*r)) for r in range(a)],N=N,ell_bits=ell,J=J,L=1,encoded_record_bytes=4096*w//8,target_tuple=targets(N,a),db_fixture_hash=rh.hexdigest(),encoded_db_hash=eh.hexdigest(),layout_id=f'LSB-rho8-w{w}-n4096-L1-v1')
def workloads(): return [point(a,N,e) for a in (2,3,4) for N in (1024,4096) for e in (512,2048)]
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)
def scoped_files():
    return sorted([p for p in HERE.rglob('*') if p.is_file()]+[p for p in NOTES.rglob('*') if p.is_file() and p.relative_to(NOTES).as_posix().startswith('B2_B_')])
