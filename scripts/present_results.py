"""Presentation only: preserve archived estimators and datasets without pooling.

SPDX-License-Identifier: GPL-3.0-or-later
Run from a repository root; write to an unused output directory.
"""
from pathlib import Path
import argparse, csv, hashlib, json, os

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.cwd())
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();root=args.root.resolve();out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    used={}
    def read(p):
        b=(root/p).read_bytes();used[p]=hashlib.sha256(b).hexdigest()
        return json.loads(b.decode('utf-8-sig'))
    def save(p,s): (out/p).write_text(s+'\n',encoding='utf-8',newline='\n')
    def table(p,caption,label,spec,head,rows,note=''):
        save(p,r'\begin{table}[tbp]'+'\n'+r'\centering\small'+'\n'+r'\caption{'+caption+'}\n'+r'\label{'+label+'}\n'+r'\setlength{\tabcolsep}{4pt}'+'\n'+r'\begin{tabular}{@{}'+spec+r'@{}}'+'\n'+r'\toprule'+'\n'+head+r' \\'+'\n'+r'\midrule'+'\n'+'\n'.join(rows)+'\n'+r'\bottomrule\end{tabular}'+'\n'+(r'\par\smallskip\begin{minipage}{\linewidth}\footnotesize '+note+r'\end{minipage}' if note else '')+'\n'+r'\end{table}')
    primary=read('revision_notes/B1_primary_audit/paired_ratio_recomputed.json')['cell_results']
    stats=read('revision_notes/B1_primary_audit/statistics_recomputed.json')['points']
    scaling=read('revision_notes/B2_B_result_audit/scaling_audit.json')['rows']
    frontier=read('revision_notes/B2_A_feasibility_frontier.json')['cells']
    overlap=read('revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json')['rows']
    p='artifact/results/B3_descriptive_v1/B3_cells.csv';b=(root/p).read_bytes();used[p]=hashlib.sha256(b).hexdigest()
    follow=list(csv.DictReader(b.decode('utf-8-sig').splitlines()))
    assert len(primary)==96 and len(scaling)==8 and len(follow)==18
    os.environ['MPLCONFIGDIR']=str(out/'plot_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,axes=plt.subplots(3,2,figsize=(6.1,7.2))
    plotted=[]
    for i,rho in enumerate((8,12,16)):
        for j,view in enumerate(('COLD','ONLINE')):
            ax=axes[i,j]
            cells=sorted((c for c in primary if c['rho_0']==rho and c['mode']==view),key=lambda c:(c['N'],c['ell_bits']))
            assert len(cells)==16
            for y,c in enumerate(cells):
                lo,hi=c['CI95'];m=c['median_paired_ratio'];assert .98<lo<=m<=hi<1.40
                ax.plot([lo,hi],[y,y],color='#315973',lw=1)
                ax.plot(m,y,'o',color='#17374d',ms=3);plotted.append(c)
            ax.axvline(1,color='#777',ls='--',lw=.75)
            ax.set(xlim=(.98,1.40),xticks=(1,1.1,1.2,1.3,1.4),ylim=(15.7,-.7))
            ax.set_yticks(range(16),[f"{c['N']} / {c['ell_bits']}" for c in cells],fontsize=7)
            ax.tick_params(length=2);ax.grid(axis='x',color='#ddd',lw=.4)
            for y in (3.5,7.5,11.5):ax.axhline(y,color='#ddd',lw=.4)
            ax.set_title(view.lower()+r', $\rho_0='+str(rho)+'$',loc='left')
    fig.subplots_adjust(left=.15,right=.995,bottom=.075,top=.95,hspace=.34,wspace=.65)
    fig.text(.015,.995,r'Rows: $N$ / record length $\ell$ (bits)',va='top')
    fig.supxlabel(r'Median paired ratio $R=T_{\mathrm{repeated}}/T_{\mathrm{packed}}$',y=.02,fontsize=10)
    fig.savefig(out/'primary.pdf',metadata={'Title':'Primary two-record task latency','CreationDate':None,'ModDate':None});plt.close(fig)
    save('primary.tex',r'''\begin{figure}[p]
\centering\includegraphics[width=\linewidth]{generated/primary.pdf}
\caption{Primary two-record comparison: all 96 cells. Points are median
paired repeated-to-packed task latency ratios; bars are pointwise 95\%
paired-bootstrap intervals. Cells remain separate; the figure makes no
family-wise or across-grid inference.}
\label{fig:primary-performance}
\end{figure}''')
    rows=[]
    for c in scaling:
        vals=[]
        for a in (2,3,4):
            lo,hi=c[f'CI95_R{a}'];vals.append(r'\shortstack{'+f"{c[f'R{a}']:.3f}"+r'\\\scriptsize '+f'[{lo:.3f}, {hi:.3f}]'+'}')
        rows.append(f"{c['N']} & {c['ell_bits']} & {c['view'].lower()} & "+' & '.join(vals)+r' \\[3pt]')
    table('multiplicity.tex',r'Multiplicity experiment at $\rho_0=8$, $w=8\alpha$ and $L=1$. Each cell contains ten measured pairs. Entries are median paired ratios with pointwise 95\% intervals.','tab:multiplicity','rrlccc',r'$N$ & $\ell$ (bits) & View & $\alpha=2$ & $\alpha=3$ & $\alpha=4$',rows,r'The two-record entries are internal references for this experiment. Packed execution is serial; repeated tasks use $\alpha$ concurrent workers. This is not a fixed-total-core comparison.')
    rows=[]
    for c in stats:
        if (c['N'],c['ell_bits'],c['rho_0']) not in ((256,256,8),(16384,2048,8)):continue
        for view in ('COLD','ONLINE'):
            p=c[view]['packed']['TaskTotal_ns']['median']/1e9;r=c[view]['repeated']['TaskTotal_ns']['median']/1e9
            cell=next(x for x in primary if (x['N'],x['ell_bits'],x['rho_0'],x['mode'])==(c['N'],c['ell_bits'],8,view))
            rows.append(f"{c['N']} & {c['ell_bits']} & {view.lower()} & {p:.3f} & {r:.3f} & {cell['median_paired_ratio']:.3f}"+r' \\')
    table('absolute.tex',r'Absolute task latency at the smallest and largest primary workload corners, with $\rho_0=8$. These four cells are descriptive examples; Fig.~\ref{fig:primary-performance} retains the full grid.','tab:absolute','rrlrrr',r'$N$ & $\ell$ (bits) & View & Packed (s) & Repeated (s) & Paired $R$',rows,'Time columns are separate method medians. Their quotient is not the median paired ratio in the last column.')
    def ratio(c):return f"{float(c['ratio_median']):.3f} [{float(c['observed_session_min']):.3f}, {float(c['observed_session_max']):.3f}]"
    rows=[]
    for ell in (4096,8192,12288,16384,65536):
        cells=[next(c for c in follow if c['study']=='M5' and int(c['ell_bits'])==ell and c['view']==v) for v in ('COLD','ONLINE')]
        c=cells[0];rows.append(f"{ell} & {c['J']} & {c['L']} & {float(c['u']):g} & "+' & '.join(map(ratio,cells))+r' \\')
    table('capacity.tex',r'Capacity experiment: $N=1024$, $\alpha=4$, $\rho_0=8$, $w=32$, full-block extraction and the four-CPU parent allowance. Entries are median paired ratios with observed ranges of three session medians.','tab:capacity','rrrrcc',r'$\ell$ (bits) & $J$ & $L$ & $u$ & Cold & Online',rows,'Each cell has 30 measured pairs. Brackets are descriptive session ranges, not confidence intervals. Query buffers are 128/512 MiB for packed/repeated; reply buffers are 128/512 KiB for $L=1$ and 256/1024 KiB for $L=2$.')
    rows=[]
    for impl,name in (('I1','Record-field'),('I2','Full-block')):
        for res,rname in (('R1','Two-CPU'),('R2','Four-CPU parent')):
            cells=[next(c for c in follow if c['study']=='M6' and c['implementation_id']==impl and c['resource_policy_id']==res and c['view']==v) for v in ('COLD','ONLINE')]
            rows.append(f'{name} & {rname} & '+' & '.join(map(ratio,cells))+r' \\')
    table('sensitivity.tex',r'Bundle sensitivity at $N=1024$, $\ell=512$, $\alpha=2$, $\rho_0=8$. Median paired ratios and ranges of three session medians; 30 measured pairs per cell.','tab:sensitivity','llcc','Extraction bundle & Resource bundle & Cold & Online',rows,'Resource labels describe allowances, not packed arithmetic parallelism. Brackets are observed ranges, not confidence intervals. Implementations also differ in API wrappers; resource bundles include affinity and memory limits.')
    rows=[]
    for c in frontier:
        status='Supported' if c['native_final_status']=='NATIVE_E2E_PASS' else ('Weight and width' if c['w']==64 else 'Weight limit')
        count=('82' if c['alpha']==2 else '10') if status=='Supported' else 'Not executed'
        power=int(c['max_weight']).bit_length()-1
        rows.append(f"{c['alpha']} & {c['rho_0']} & {c['w']} & $2^{{{power}}}$ & {status} & {count}"+r' \\')
    table('frontier.tex',r'Tested native profiles. All nine satisfy radix capacity at $w=\alpha\rho_0$ and the zero-noise arithmetic screen. Encrypted checks were executed only for supported profiles.','tab:native-frontier','rrrrll',r'$\alpha$ & $\rho_0$ & $w$ & Largest weight & Native API & Passing cases',rows,'Each two-record profile has 82 cases; each supported additional multiplicity has ten. These are finite functional checks, not latency samples or a failure-probability certificate.')
    rows=[]
    for N,ell,a in ((256,256,2),(16384,2048,2),(1024,8192,4),(1024,16384,4),(1024,65536,4)):
        J=(ell+7)//8;L=(J+4095)//4096
        rows.append(f'{N} & {ell} & {a} & {N*ell/8/1024:g} & {N/8:g}/{a*N/8:g} & {L*128}/{a*L*128}'+r' \\')
    table('payload.tex',r'Exact native buffer accounting for representative byte-aligned workloads with $\rho_0=8$. P/R denotes packed/repeated retrieval. Raw database size counts each record once.','tab:payload','rrrrcc',r'$N$ & $\ell$ (bits) & $\alpha$ & Raw (KiB) & Query P/R (MiB) & Reply P/R (KiB)',rows,'One ciphertext occupies 128 KiB. These are in-memory buffer sizes; transport, framing and metadata are unmeasured.')
    # Long tables preserve full grid precision at six decimals; JSON retains source precision.
    lines=[r'\section{Complete Cell Summaries}',r'Primary and multiplicity intervals are pointwise 95\% paired-bootstrap intervals. All experiments remain separate. Long-table values are rounded to six decimals; other tables use their displayed precision, and the machine-readable archive retains full precision.',r'\subsection{Primary Two-Record Comparison}',r'\small\begin{longtable}{rrrlrrr}',r'\caption{All primary cells.}\\',r'\toprule $N$ & $\ell$ & $\rho_0$ & View & Pairs & Median $R$ & Interval \\ \midrule\endfirsthead',r'\toprule $N$ & $\ell$ & $\rho_0$ & View & Pairs & Median $R$ & Interval \\ \midrule\endhead']
    for c in sorted(primary,key=lambda c:(c['rho_0'],c['N'],c['ell_bits'],c['mode'])):
        lo,hi=c['CI95'];lines.append(f"{c['N']} & {c['ell_bits']} & {c['rho_0']} & {c['mode'].lower()} & {c['n_pairs']} & {c['median_paired_ratio']:.6f} & [{lo:.6f}, {hi:.6f}]"+r' \\')
    lines += [r'\bottomrule\end{longtable}\normalsize',r'\subsection{Multiplicity Comparison}',r'\input{generated/multiplicity}',r'\subsection{Two-Record Overlap Across Experiments}',r'The following matched workload shapes have distinct experimental contracts. Their samples are not pooled, and the difference has no established causal attribution.',r'\begin{longtable}{rrlcc}',r'\toprule $N$ & $\ell$ & View & Primary $R$ [interval] & Multiplicity $R$ [interval] \\ \midrule']
    for c in overlap:
        vals=[]
        for k in ('B1','B2B'):
            lo,hi=c[k+'_CI95'];vals.append(f"{c[k+'_median_R']:.6f} [{lo:.6f}, {hi:.6f}]")
        lines.append(f"{c['N']} & {c['ell_bits']} & {c['view'].lower()} & "+' & '.join(vals)+r' \\')
    lines += [r'\bottomrule\end{longtable}',r'\subsection{Sensitivity and Capacity}',r'\input{generated/sensitivity}',r'\input{generated/capacity}']
    save('supplement_tables.tex','\n'.join(lines))
    save('display_data.json',json.dumps({'policy':'Presentation only; no resampling or pooling','source_sha256':used,'primary':primary,'multiplicity':scaling,'followup':follow,'overlap':overlap,'frontier':frontier},indent=2))
    save('presentation_manifest.json',json.dumps({'inputs':used,'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}},indent=2))
    print(json.dumps({'primary_cells':96,'multiplicity_cells':24,'sensitivity_capacity_cells':18,'estimator_changes':0,'out':str(out)}))

if __name__=='__main__':main()
