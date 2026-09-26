"""Render existing audited summaries; never estimate or resample observations."""
from pathlib import Path
import json,hashlib,os
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(OUT/'plot_config')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def read(n):return json.loads((ROOT/n).read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(n,s):
    p=OUT/n;p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(s+'\n',encoding='utf-8',newline='\n')
def main():
    claims=read('revision_notes/integrated_experimental_audit/master_claim_registry.json')['claims']
    for c in claims:
        for e in c['supporting_artifact']:assert sha(ROOT/e['path'])==e['sha256']
    b1=read('revision_notes/B1_primary_audit/paired_ratio_recomputed.json')
    b2=read('revision_notes/B2_B_result_audit/scaling_audit.json')
    frontier=read('revision_notes/B2_A_feasibility_frontier.json')['cells']
    overlap=read('revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json')['rows']
    out=OUT/'displays';out.mkdir(exist_ok=True)
    rows=[]
    for c in frontier:
        power=int(c['max_weight']).bit_length()-1
        assert 2**power==int(c['max_weight'])
        if c['native_final_status']=='NATIVE_E2E_PASS':
            native='Supported';provenance='Inherited: 82/82' if c['alpha']==2 else 'New: 10/10'
            assert (c['inherited_case_count']==82 and not c['new_execution']) if c['alpha']==2 else c['e2e_pass_count']==10
        else:
            native='Weight + width' if c['w']==64 else 'Weight limit';provenance='Not executed'
            assert c['e2e_case_count']==0
        rows.append(f"{c['alpha']} & {c['rho_0']} & {c['w']} & $2^{{{power}}}$ & {c['structural_status']} & {native} & {provenance} \\")
    # Add the second backslash explicitly to avoid ambiguous literal escapes.
    rows=[r+'\\' for r in rows]
    t1=r'''% CLAIMS: C1 C9; source: B2_A_feasibility_frontier.json; formatting only.
\begin{table}[t]
\centering
\caption{Native feasibility of the nine tested multiplicity/segment-width
profiles on the pinned $n=4096$, Q2 XPIR path. Structural radix capacity is
distinguished from current width/weight API support. $\alpha=2$ results are
inherited from S4-N; B2-A adds ten passing encrypted E2E cases for each of
$(\alpha,\rho_0,w)=(3,8,24),(3,12,36),(4,8,32)$. API-blocked profiles were
not executed. These finite functional checks establish neither performance
nor a native security/failure certificate.}
\label{tab:native-frontier}
\small
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}rrrrlll@{}}
\toprule
$\alpha$ & $\rho_0$ & $w$ & $K_{\max}$ & Structural & Native API & E2E provenance \\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule
\end{tabular}
\par\smallskip
\begin{minipage}{\linewidth}\footnotesize
Structural PASS denotes exact capacity and the zero-noise arithmetic
screen, not a positive calibrated noise parameter. No inherited
$\alpha=2$ case was rerun for this frontier. ``Weight limit'' means a
direct weight above $2^{32}-1$; the $w=64$ row also exceeds the checked
$1\le w\le56$ guard. $K_{\max}$ is the largest direct selector weight.
\end{minipage}
\end{table}
'''
    save('displays/T1_frontier.tex',t1)

    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7,'axes.titlesize':8,
        'axes.labelsize':7,'xtick.labelsize':6.5,'ytick.labelsize':6.2,
        'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(3,2,figsize=(4.92,6.15))
    plotted=[]
    for row,rho in enumerate([8,12,16]):
        for col,view in enumerate(['COLD','ONLINE']):
            ax=axes[row,col]
            cells=sorted([c for c in b1['cell_results'] if c['rho_0']==rho and c['mode']==view],key=lambda c:(c['N'],c['ell_bits']))
            assert len(cells)==16
            for y,c in enumerate(cells):
                lo,hi=c['CI95'];m=c['median_paired_ratio']
                ax.plot([lo,hi],[y,y],color='#294d69',lw=0.9)
                ax.plot(m,y,'o',color='#17374d',ms=2.3)
                plotted.append(dict(c))
            ax.axvline(1,color='#555555',ls='--',lw=.65)
            ax.set_xlim(.98,1.40);ax.set_xticks([1.0,1.1,1.2,1.3,1.4])
            assert all(.98<c['CI95'][0]<=c['CI95'][1]<1.40 for c in cells)
            ax.set_yticks(range(16),[f"{c['N']} / {c['ell_bits']}" for c in cells])
            ax.set_ylim(15.7,-.7)
            ax.tick_params(axis='y',length=0,pad=3)
            ax.tick_params(axis='x',length=2,pad=2)
            ax.grid(axis='x',color='#dddddd',lw=.4)
            ax.set_axisbelow(True)
            for y in [3.5,7.5,11.5]:ax.axhline(y,color='#e5e5e5',lw=.5)
            ax.set_title(view+r', $\rho_0='+str(rho)+'$',pad=5,loc='left')
    fig.subplots_adjust(left=.155,right=.99,bottom=.075,top=.935,hspace=.35,wspace=.57)
    fig.text(.01,.994,r'Rows: $N$ / record length $\ell$ (bits)',va='top',fontsize=7)
    fig.supxlabel(r'Median paired ratio $R=T_{\mathrm{repeated}}/T_{\mathrm{packed}}$',y=.018,fontsize=8)
    fig.savefig(out/'F1_primary.pdf',metadata={'Title':'Primary two-record completed-task ratios','CreationDate':None,'ModDate':None})
    fig.savefig(out/'F1_primary.png',dpi=180)
    plt.close(fig)
    save('displays/F1_primary.tex',r'''% CLAIM: C2; source: audited B1 cell_results; no resampling.
\begin{figure}[p]
\centering
\includegraphics[width=\linewidth]{revision_notes/manuscript_integration/displays/F1_primary.pdf}
\caption{Primary two-record completed-task comparison under the B1 contract.
Points show median paired repeated-to-packed TaskTotal ratios and bars show
the preregistered pointwise 95\% paired-bootstrap intervals for all 48
workload/profile points in COLD and ONLINE views. All 96 medians and
pointwise lower endpoints exceed one; observed cell medians range from
1.059 to 1.190. These are separate cell results on the frozen WSL2 host,
not an overall speedup or family-wise inference.}
\label{fig:primary-performance}
\end{figure}''')

    t2rows=[]
    for c in b2['rows']:
        vals=[]
        for a in [2,3,4]:
            lo,hi=c[f'CI95_R{a}'];m=c[f'R{a}']
            vals.append(r'\shortstack{'+f'{m:.4f}'+r'\\'+r'\scriptsize ['+f'{lo:.4f}, {hi:.4f}'+']}')
        t2rows.append(f"{c['N']} & {c['ell_bits']} & {c['view']} & "+' & '.join(vals)+r' \\[3pt]')
    save('displays/T2_scalability.tex',r'''% CLAIMS: C3 C4 C5 C6; exact audited rows, rounded only for display.
\begin{table}[t]
\centering
\caption{Supplementary multiplicity scaling under the B2-B contract, at
fixed $\rho_0=8$ and $w=8\alpha$, with serial packed execution and
$\alpha$ concurrent repeated workers. All 24 observed median ratios exceed
one; pointwise intervals lie fully above one in 3/8 $\alpha=2$ cells and
all eight cells for each of $\alpha=3$ and $\alpha=4$. All eight tested rows
show observed $R_2<R_3<R_4$; this ordering is descriptive only. B2-B
$\alpha=2$ is the internal reference for this experiment and is reported
separately from B1.}
\label{tab:multiplicity}
\small
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}rrlccc@{}}
\toprule
$N$ & $\ell$ (bits) & View & $R_2$ [95\% CI] & $R_3$ [95\% CI] & $R_4$ [95\% CI] \\
\midrule
'''+ '\n'.join(t2rows)+r'''
\bottomrule
\end{tabular}
\par\smallskip
\begin{minipage}{\linewidth}\footnotesize
Each cell has ten complete measured pairs and zero incomplete pairs.
Intervals are pointwise, not family-wise. All workloads have $L=1$.
This is not a fixed-total-core comparison; parent affinity is
$\{0,2,4,6\}$. Values are rounded to four decimals; full precision is
retained in the accompanying supplement. No universal monotonicity,
combined B1/B2-B estimator or causal explanation is implied.
\end{minipage}
\end{table}
''')
    save('display_data.json',json.dumps(dict(policy='Direct transcription and presentation only; no statistics recomputed.',
        T1=frontier,F1=plotted,T2=b2['rows'],sources={
            p:sha(ROOT/p) for p in ['revision_notes/B2_A_feasibility_frontier.json',
            'revision_notes/B1_primary_audit/paired_ratio_recomputed.json',
            'revision_notes/B2_B_result_audit/scaling_audit.json']}),indent=2))
    supplement=['# Experimental supplement','',
        'Direct transcription of existing audited summaries. B1 is primary; B2-B is supplementary and is never pooled with B1. No new estimator or interval is computed. This supplement is outside the main-text display count.','',
        '## S1. All primary cells','',
        'Source: `revision_notes/B1_primary_audit/paired_ratio_recomputed.json`, `cell_results`. All intervals are pointwise; R is the median of paired ratios.','',
        '| N | ell bits | rho_0 | w | View | Pairs | Median R | 95% CI |','|---:|---:|---:|---:|---|---:|---:|---|']
    for c in b1['cell_results']:
        supplement.append(f"| {c['N']} | {c['ell_bits']} | {c['rho_0']} | {c['w']} | {c['mode']} | {c['n_pairs']} | {c['median_paired_ratio']} | {c['CI95']} |")
    supplement+=['','## S2. Supplementary multiplicity cells','',
        'Source: `revision_notes/B2_B_result_audit/scaling_audit.json`, `rows`. Ten measured pairs/cell; alpha=2 is the internal reference only.','',
        '| N | ell bits | View | alpha | Median R | Pointwise 95% CI |','|---:|---:|---|---:|---:|---|']
    for c in b2['rows']:
        for a in [2,3,4]:supplement.append(f"| {c['N']} | {c['ell_bits']} | {c['view']} | {a} | {c[f'R{a}']} | {c[f'CI95_R{a}']} |")
    supplement+=['','## S3. Eight cross-contract overlaps','',
        'Source: `revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json`, `rows`. All eight B2-B alpha=2 medians are smaller and the stage-specific pointwise intervals are disjoint. The contracts differ and the cause of the gap is not established; the stages are not pooled.','',
        '| N | ell bits | View | B1 pairs | B2-B pairs | B1 median R | B1 CI | B2-B median R | B2-B CI |','|---:|---:|---|---:|---:|---:|---|---:|---|']
    for c in overlap:
        supplement.append('| '+' | '.join(str(c[k]) for k in ['N','ell_bits','view','B1_pairs','B2B_pairs','B1_median_R','B1_CI95','B2B_median_R','B2B_CI95'])+' |')
    supplement+=['','## S4-S6. Resource, API and diagnostic evidence','',
        'Retained source tables and full definitions (not recomputed):',
        '- B1: `revision_notes/B1_primary_audit/cpu_memory_audit.json`, `payload_audit.json`, `phase_audit.json`, `statistics_recomputed.json`.',
        '- B2-B: `revision_notes/B2_B_result_audit/resource_payload_audit.json`, `statistics_recomputed.json`, `resource_evidence_details.json`, `postprocess_diagnostic.md`.',
        '- API frontier: `revision_notes/B2_A_native_api_inventory.md`, `B2_A_feasibility_frontier.json`, `B2_A_native_e2e_matrix.json`.',
        '- Full contract differences: `revision_notes/B2_B_result_audit/B1_B2B_alpha2_sanity.md`.',
        '', 'Copied ciphertext bytes are not transport traffic. Repeated RSS sums worker lifetime maxima, not synchronized peak. CPU ratios describe aggregate worker TaskTotal work; phase sums do not identify causal contributions. Structural PASS and output/import probes do not certify encrypted support for blocked direct weights. Missing retained 10 ms monitor history is a diagnostic limitation, not known material invalidity.']
    save('experimental_supplement.md','\n'.join(supplement))
    print('Rendered T1 (9 rows), F1 (96 cells), T2 (8 rows); no observations or statistics generated.')
if __name__=='__main__':main()
