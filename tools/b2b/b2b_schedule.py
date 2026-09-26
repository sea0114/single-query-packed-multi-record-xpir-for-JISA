"""Complete pair schedule generated before any observation, using SHA256 ordering."""
from b2b_common import *
def order_key(kind,meta): return hashlib.sha256((ORDER_SEED+'|'+kind+'|'+canonical(meta)).encode()).hexdigest()
def generate(points):
    cells=[dict(point_id=p['point_id'],alpha=p['alpha'],N=p['N'],ell_bits=p['ell_bits'],view=v) for p in points for v in ('COLD','ONLINE')]
    orientation={}
    for c in cells:
        ranked=sorted(range(10),key=lambda r:order_key('orientation',dict(c,repetition=r)))
        orientation[c['point_id'],c['view']]=set(ranked[:5])
    out=[]
    for warmup,count in ((True,3),(False,10)):
        for r in range(count):
            for c in sorted(cells,key=lambda c:order_key('round',dict(c,warmup=warmup,repetition=r))):
                first=(r!=int(order_key('warmup-minority',c),16)%3) if warmup else r in orientation[c['point_id'],c['view']]
                if warmup and int(order_key('warmup-majority',c),16)%2: first=not first
                out.append(dict(c,ordinal=len(out),warmup=warmup,repetition=r,pair_id=f"{c['point_id']}_{c['view']}_{'W' if warmup else 'M'}{r:02}",method_order=['packed','repeated'] if first else ['repeated','packed']))
    return out
def validate_schedule(rows,points):
    from collections import Counter
    assert rows==generate(points), 'Schedule differs from deterministic generation'
    assert len(rows)==312 and len({r['pair_id'] for r in rows})==312
    assert sum(r['warmup'] for r in rows)==72
    assert sum(1+r['alpha'] for r in rows)==1248
    assert sum(1+r['alpha'] for r in rows if r['warmup'])==288
    for p in points:
        for view in ('COLD','ONLINE'):
            cell=[r for r in rows if r['point_id']==p['point_id'] and r['view']==view]
            assert len(cell)==13
            assert Counter(r['method_order'][0] for r in cell if not r['warmup'])=={'packed':5,'repeated':5}
    return True
