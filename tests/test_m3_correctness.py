"""Independent exact/numerical checks; numerical fixtures are not parameter choices."""
import hashlib,itertools,json,math,platform,random,sys,unittest
from fractions import Fraction as F
from pathlib import Path
import mpmath as mp
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools/m3_correctness"))
import model
import test_m1_encoding as ref
mp.mp.dps=200
NUMERICS=[]
def tail(r,h):
    return mp.erfc((mp.mpf(h)+mp.mpf("0.5"))/(mp.sqrt(2)*r))
def product_failure(p,k):
    return -mp.expm1(k*mp.log1p(-p))

class M3Correctness(unittest.TestCase):
    def test_rounding_cells_strict_and_nonstrict(self):
        for h in range(7):
            for k in range(-96,97):
                y=F(k,8)
                if (2*y).denominator==1 and (2*y).numerator%2: continue # null-set ties
                z=(y+F(1,2)).numerator//(y+F(1,2)).denominator
                self.assertEqual(abs(z)>h,abs(y)>=h+F(1,2))
                if h>=1: self.assertEqual(abs(z)>=h,abs(y)>=h-F(1,2))
        r=mp.mpf(3)/2
        for h in (0,1,4):
            a=mp.mpf(h)+mp.mpf("0.5")
            direct=2*mp.quad(lambda y: mp.exp(-y*y/(2*r*r))/(mp.sqrt(2*mp.pi)*r),[a,mp.inf])
            self.assertLess(abs(tail(r,h)-direct),mp.mpf("1e-170"))
            NUMERICS.append({"check":"tail_integral","r":"3/2","h":h,"erfc":mp.nstr(tail(r,h),190)})
        self.assertGreater(tail(r,0),tail(r,1)) # >=1 uses h=0 strict tail, not h=1

    def test_support_edges_and_actual_encoding(self):
        for n in (1,2,4,8):
            for rho in (1,3,5):
                for J in (1,n,max(1,n-1),n+1,2*n+1):
                    for ell in (J*rho,(J-1)*rho+1):
                        j,L,m=model.supports(ell,rho,n)
                        encoded=ref.encode([1]*ell,rho,n)
                        self.assertEqual(j,J)
                        self.assertEqual(L,len(encoded))
                        self.assertEqual(m,[len([k for k in range(n) if b*n+k<J]) for b in range(L)])
                        for block,support in zip(encoded,m):
                            self.assertLessEqual(sum(abs(x) for x in block),support*((1<<rho)-1))
                            self.assertEqual(block[support:],[0]*(n-support))
        with self.assertRaises(ValueError): model.supports(0,1,4)

    def test_negacyclic_signed_norm_and_aggregate(self):
        rng=random.Random(20260924)
        for n in (1,2,4,8):
            for _ in range(60):
                P=[rng.randrange(-3,4) for _ in range(n)]
                e=[rng.randrange(-2,3) for _ in range(n)]
                # Independent signed coefficient formula, not a call to poly_mul.
                result=[sum((1 if u<=k else -1)*P[u]*e[(k-u)%n] for u in range(n)) for k in range(n)]
                self.assertEqual(result,ref.poly_mul(P,e))
                self.assertLessEqual(max(map(abs,result)),sum(map(abs,P))*max(map(abs,e)))
            if n>1:
                X=[0]*n; X[1]=1
                high=[0]*n; high[-1]=1
                self.assertEqual(ref.poly_mul(high,X),[-1]+[0]*(n-1))
        N,n,m,B,h=3,4,2,8,2
        polys=[[B-1]*m+[0]*(n-m) for _ in range(N)]
        errors=[[h]*n for _ in range(N)]
        agg=[sum(ref.poly_mul(P,e)[u] for P,e in zip(polys,errors)) for u in range(n)]
        self.assertLessEqual(max(map(abs,agg)),N*m*(B-1)*h)

    def test_odd_strict_integer_conversion_and_hmax_bruteforce(self):
        for q in range(3,60,2):
            for A in range((q+1)//2+2):
                for D in ([1],[2],[1,3],[3,5]):
                    h,per=model.maximum_h(q,A,D)
                    legal=[z for z in range(q+1) if all(2*(A+d*z)<q for d in D)]
                    self.assertEqual(h,max(legal) if legal else None)
                    for z in range(q+1):
                        self.assertEqual(all(2*(A+d*z)<q for d in D),
                                         all(A+d*z<=(q-1)//2 for d in D))
        self.assertEqual(model.maximum_h(11,5,[3]),(0,[0]))
        self.assertEqual(model.maximum_h(11,6,[3]),(None,None))
        for bad in ([],[0],[2,0]):
            with self.assertRaises(ValueError): model.maximum_h(11,2,bad)
        with self.assertRaises(ValueError): model.maximum_h(10,2,[1])

    def test_all_48_main_rows_independent_arithmetic(self):
        data=json.loads((ROOT/"revision_notes/M3_A_logs/fixed_profile_table.json").read_text())
        rows=data["rows"]
        self.assertEqual(len(rows),48)
        self.assertEqual({(x["N"],x["ell_bits"],x["rho_0"]) for x in rows},
                         set(itertools.product((256,1024,4096,16384),(256,512,1024,2048),(8,12,16))))
        for x in rows:
            q=int(x["q"]); n=x["n"]; B=2**x["rho_0"]; t=int(x["t"])
            J=math.ceil(F(x["ell_bits"],x["rho_0"]))
            blocks=[list(range(a,min(a+n,J))) for a in range(0,J,n)]
            self.assertEqual(x["m_j"],list(map(len,blocks)))
            self.assertEqual(x["J"],J); self.assertEqual(x["L"],len(blocks))
            self.assertEqual(t,B**2); self.assertEqual(int(x["A"]),B**2-1)
            D=[t*x["N"]*len(b)*(B-1) for b in blocks]
            self.assertEqual(list(map(int,x["D_j"])),D)
            h=int(x["h_max"]); A=int(x["A"])
            self.assertTrue(all(2*(A+d*h)<q for d in D))
            self.assertTrue(any(2*(A+d*(h+1))>=q for d in D))
            # Quotient/remainder characterization, independently checks every h_max,j.
            for d,hj in zip(D,map(int,x["h_max_j"])):
                remainder=(q-1)//2-A-d*hj
                self.assertTrue(0<=remainder<d)
            self.assertIsNone(x["r"])

    def test_supplementary_structural_rejections(self):
        rows=json.loads((ROOT/"revision_notes/M3_A_logs/supplementary_alpha.json").read_text())["rows"]
        self.assertEqual(len(rows),96)
        passes={(3,8),(3,12),(4,8)}
        for x in rows:
            allowed=(x["alpha"],x["rho_0"]) in passes
            self.assertEqual(x["status"]=="SCREEN_DEFINED",allowed)
            self.assertEqual(not x["structural_reasons"],allowed)
            if allowed:
                A=int(x["A"]);h=int(x["h_max"]);D=list(map(int,x["D_j"]));q=int(x["q"])
                self.assertTrue(all(2*(A+d*h)<q for d in D))
                self.assertTrue(any(2*(A+d*(h+1))>=q for d in D))
            else: self.assertIsNone(x["h_max"]); self.assertIsNone(x["D_j"])
        self.assertIn("WEIGHT_API_RANGE",model.structural(3,16,256)[0])
        self.assertEqual(set(model.structural(4,16,256)[0]),{"WEIGHT_API_RANGE","NATIVE_WIDTH"})
        self.assertIn("RADIX_CAPACITY",model.structural(2,8,256,w=15)[0])

    def test_product_union_monotonicity_and_no_extra_factors(self):
        # Exhaustively enumerate a toy independent bad-coordinate event.
        p=F(1,5);K=4
        exact=sum(p**sum(bits)*(1-p)**(K-sum(bits)) for bits in itertools.product((0,1),repeat=K) if any(bits))
        self.assertEqual(exact,1-(1-p)**K)
        for L,alpha in itertools.product((1,3,7),(1,2,4)):
            # Duplicating block/target labels creates no additional random coordinates.
            labelled=sum(p**sum(bits)*(1-p)**(K-sum(bits))
                         for bits in itertools.product((0,1),repeat=K)
                         if any(any(bits) for _ in range(L*alpha)))
            self.assertEqual(labelled,exact)
        self.assertLessEqual(exact,K*p)
        r=mp.mpf(5)/4;N=3;n=4
        previous=mp.mpf(1)
        for h in (0,1,3,8,16):
            prob=tail(r,h);ep=product_failure(prob,N*n)
            self.assertTrue(0<ep<=min(1,N*n*prob))
            self.assertLess(ep,previous);previous=ep
            NUMERICS.append({"check":"global_event","r":"5/4","h":h,"K":N*n,
                             "product":mp.nstr(ep,190),"union":mp.nstr(N*n*prob,190)})

    def test_symbolic_inverse_region_high_precision_sanity(self):
        # Fixed toy fixtures validate inversion; none is an active-profile r choice.
        for target in (mp.mpf(1)/16,mp.power(2,-128)):
            K=48;h=6
            inv=lambda z: mp.erfinv(1-z) # erfc^{-1} on (0,1)
            r_union=(h+mp.mpf("0.5"))/(mp.sqrt(2)*inv(target/K))
            delta=-mp.expm1(mp.log1p(-target)/K)
            r_product=(h+mp.mpf("0.5"))/(mp.sqrt(2)*inv(delta))
            self.assertGreaterEqual(r_product,r_union)
            self.assertLess(abs(K*tail(r_union,h)/target-1),mp.mpf("1e-145"))
            self.assertLess(abs(product_failure(tail(r_product,h),K)/target-1),mp.mpf("1e-145"))
            self.assertLess(K*tail(r_union*mp.mpf("0.99"),h),target)
            self.assertGreater(K*tail(r_union*mp.mpf("1.01"),h),target)
            NUMERICS.append({"check":"inverse_fixture","K":K,"h":h,"target":mp.nstr(target,190),
                             "r_union_fixture":mp.nstr(r_union,190),"r_product_fixture":mp.nstr(r_product,190)})

    def test_repeated_fresh_key_task_composition(self):
        d1,d2=F(1,8),F(1,16)
        enumerated=d1*d2+d1*(1-d2)+(1-d1)*d2
        self.assertEqual(enumerated,1-(1-d1)*(1-d2))
        self.assertLessEqual(enumerated,d1+d2)
        self.assertEqual(1-(1-d1)**2,2*d1-d1*d1)
        e1,e2=F(1,4),F(1,8)
        self.assertLessEqual(enumerated,1-(1-e1)*(1-e2))
        ceiling=F(1,2**128)
        self.assertGreater(1-(1-ceiling)**2,ceiling)

    def test_good_event_controls_multiblock_ordered_recovery(self):
        rng=random.Random(316)
        n,N,rho,alpha,ell,q,h=4,3,2,2,19,65537,2
        B=2**rho;t=B**alpha
        DB=[[rng.randrange(2) for _ in range(ell)] for _ in range(N)]
        P=[ref.encode(bits,rho,n) for bits in DB]
        J,L,m=model.supports(ell,rho,n)
        self.assertGreater(L,1)
        self.assertTrue(all(2*(B**alpha-1+t*N*v*(B-1)*h)<q for v in m))
        for I in ((2,0),(0,2)):
            s=[rng.randrange(-4,5) for _ in range(n)]
            v=[0]*N
            for k,i in enumerate(I):v[i]=B**k
            errors=[[rng.randrange(-h,h+1) for _ in range(n)] for _ in range(N)]
            Q=[ref.enc(s,v[i],[rng.randrange(q) for _ in range(n)],errors[i],t,q) for i in range(N)]
            recovered=[[[0]*n for _ in range(L)] for _ in I]
            for j in range(L):
                d0=[sum(ref.poly_mul(P[i][j],Q[i][0])[u] for i in range(N))%q for u in range(n)]
                d1=[sum(ref.poly_mul(P[i][j],Q[i][1])[u] for i in range(N))%q for u in range(n)]
                decrypted=[ref.center(a+b,q)%t for a,b in zip(d0,ref.poly_mul(d1,s))]
                for u,y in enumerate(decrypted):
                    for k,x in enumerate(ref.unpack(y,rho,alpha,t)):recovered[k][j][u]=x
            self.assertEqual([ref.decode(x,ell,rho,n) for x in recovered],[DB[i] for i in I])

if __name__=="__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(M3Correctness)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    evidence={"status":"PASS" if result.wasSuccessful() else "BLOCKED","tests_run":result.testsRun,
              "python":sys.version,"platform":platform.platform(),"mpmath_version":mp.__version__,
              "decimal_precision":mp.mp.dps,"numerical_scope":"sanity checks only, not publication certificates",
              "publication_table_arithmetic":"exact integers","estimator_executed":False,
              "selected_r":None,"numerics":NUMERICS,
              "test_source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (ROOT/"revision_notes/M3_A_logs/checks.json").write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n")
    sys.exit(not result.wasSuccessful())
