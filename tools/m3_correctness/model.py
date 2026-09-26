"""Exact support and no-wrap arithmetic; no parameter search or estimator."""
N_RING=4096
Q=5316911983137472318178862960259203073
PRIMES=(2305843009213317121,2305843009213120513)
WORKLOAD_N=(256,1024,4096,16384)
ELL=(256,512,1024,2048)
RHO=(8,12,16)

def supports(ell,rho,n):
    if min(ell,rho,n)<1 or n&(n-1):
        raise ValueError("positive dimensions and power-of-two n required")
    J=(ell+rho-1)//rho
    L=(J+n-1)//n
    m=[min(n,max(0,J-j*n)) for j in range(L)]
    assert all(1<=x<=n for x in m) and sum(m)==J
    return J,L,m

def maximum_h(q,A,D):
    if q<=1 or q%2!=1 or A<0 or not D or any(d<=0 for d in D):
        raise ValueError("odd q, A>=0 and strictly positive block denominators required")
    C=(q-1)//2-A
    if C<0:
        return None,None
    per_block=[C//d for d in D]
    return min(per_block),per_block

def structural(alpha,rho,N,w=None):
    if min(alpha,rho,N)<1:
        raise ValueError("positive parameters required")
    w=alpha*rho if w is None else w
    reasons=[]
    if alpha>N: reasons.append("TARGET_COUNT")
    if not 1<=w<=56: reasons.append("NATIVE_WIDTH")
    if w<alpha*rho: reasons.append("RADIX_CAPACITY")
    K=[1<<(rho*k) for k in range(alpha)]
    if max(K)>2**32-1: reasons.append("WEIGHT_API_RANGE")
    return reasons,K,w

def row(N,ell,rho,alpha=2):
    n=N_RING; q=Q
    reasons,K,w=structural(alpha,rho,N)
    B=1<<rho; t=1<<w
    J,L,m=supports(ell,rho,n)
    out={"N":N,"ell_bits":ell,"alpha":alpha,"rho_0":rho,"w":w,
        "n":n,"q":str(q),"B":B,"t":str(t),"K":list(map(str,K)),
        "J":J,"L":L,"m_j":m,"A":str(B**alpha-1),
        "structural_reasons":reasons,"r":None}
    if reasons:
        return out | {"status":"STRUCTURAL_REJECTION","D_j":None,
                      "h_max_j":None,"h_max":None}
    A=B**alpha-1
    D=[t*N*x*(B-1) for x in m]
    h,per=maximum_h(q,A,D)
    return out | {"status":"SCREEN_DEFINED" if h is not None else "NO_NONNEGATIVE_H",
        "D_j":list(map(str,D)),"h_max_j":None if per is None else list(map(str,per)),
        "h_max":None if h is None else str(h),
        "method":"sufficient uniform coefficient-event screen; not selected r"}
