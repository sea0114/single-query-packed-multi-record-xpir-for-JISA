# Current and historical result map

## Current core evaluation

The current entry point is [core_rebuild/README.md](../experiments/core_rebuild/README.md). Its new run `core_20261001_001` is independent of the historical experiments below: 12 primary conditions and 16 fixed-capacity conditions, all at `N=1024`, with ten sessions, one warmup and six measured blocks per condition/session. All 5,880 physical tasks completed; warmups and tuning do not enter the estimates.

| Evidence | Current path under `experiments/core_rebuild/` | Meaning |
|---|---|---|
| Frozen design | `runs/core_20261001_001/provenance/freeze.json` | Literal schedule, seeds, configurations, resource policy and source/build pins |
| Measurement collection | `runs/core_20261001_001/raw/formal_001/observations.jsonl`, `formal_report.json` | Physical observations and complete-condition gate |
| Estimates and uncertainty | `results/core_20261001_001/summary.json`, `fullprecision.csv` | Absolute latency/CPU/preprocessing costs and paired latency contrasts; pointwise joint-session bootstrap intervals |
| All ten session effects | `results/core_20261001_001/session_effects.csv` | Every condition/contrast/metric session median, without dropping time variation |
| Configurations and actual buffers | `results/core_20261001_001/configurations_and_buffers.csv` | Selected layouts, concurrency, arithmetic threads and validated ciphertext counts/bytes |
| Audit linkage | `results/core_20261001_001/claim_map.json`, `failure_ledger.json`, `analysis_provenance.json` | Exact condition pointers, failure gate and input/output hashes |

The frozen `scripts/plots.py` generates the original `retrieval_performance.pdf` and `capacity_tradeoff.pdf`, with frozen figure, caption and provenance JSON. The current postmeasurement `reproduction/paper_plots.py` selects all 12 independently tuned primary repeated/packed ratios with intervals, shown in two horizontal scope panels with a shared 0.95-1.35 axis and explicit 1.0 tick. The capacity figure shows packed and full-width repeated retrieval in all 16 conditions (32 points), with packed L=1/L=2 regions and full-width L=1. Its saved full-width role remains `R_independent`; this fixed policy is not tuned for capacity conditions. All source estimates, intervals, categories, configurations and buffers remain unchanged. The separator between the second and third capacity categories is a grouping aid, not a measured coordinate. Updated figure metadata, `numeric_preservation.json` and `coverage_mapping.json` distinguish the 44-point main-series subset from the complete 72-point scientific source. The 12 omitted primary matched ratios and CIs remain in complete primary Table S1; the 16 omitted capacity matched medians and paired contrasts remain in complete capacity Table S2, with absolute-time CIs retained in fixed data. Both complete tables belong to Supplement S1. Selection is by role, never effect size.

`reproduction/paper_tables.py` generates four tables and `mapping.json`. The full-width cost table uses two metric groups with adjacent Packed/Repeated columns, retaining all 24 estimates and 48 CI endpoints in six workload rows. Consolidating repeated categorical cells changes the mapping to 284 cells and 498 source pointers. Points use 10 pt type and intervals 9 pt; the other three tables retain their original bytes, font and spacing. Both renderers require unused output directories, run no native code and perform no bootstrap. Generated PDFs and current manuscript materials are excluded from distribution. See [section6-focus-and-discussion.json](../manifests/section6-focus-and-discussion.json) and the core README's separate `analyze`/`redraw` and paper-presentation routes. The earlier [readability receipt](../manifests/section6-readability.json) is retained as historical acceptance. The old display numbers and old paired-trial estimator below do not describe the new evaluation.

## Retained historical presentation

The rest of this map describes the earlier presentation. Files under `paper/` and `submission/` remain frozen historical editorial artifacts; their old figure/table numbers do not identify the new displays. Semantic names and manuscript labels below retain the earlier lineage.

## Redraw without statistical recomputation

Run from the repository root with the analysis dependencies installed:

```bash
python3 -B scripts/present_results.py --root . --out results_redraw_01
```

The output directory must be unused. This command reads the six canonical inputs below, writes only the specified output tree (including caches), and does not unpack data, run native code, or bootstrap. Coordinates/interval endpoints retain the archived estimators. Each figure has PDF, PNG, embedding `.tex` and full-precision `_data.json` outputs; `display_data.json`, `table_data.json` and `presentation_manifest.json` retain source arrays, fields and hashes. Derivative PDF bytes may vary across rendering environments. Plotting needs no LaTeX. The optional `.tex` snippets need `graphicx`/`booktabs` in the embedding document and a `\refocusassets` macro pointing to the output directory; they are not standalone manuscripts.

| Current display | Conditions / meaning | Canonical source and fields | Output |
|---|---|---|---|
| Primary two-record slice (`fig:primary-performance`) | All 32 rho_0=8 conditions; alpha=2; N=256/1024/4096/16384; ell=256/512/1024/2048 bits; both scopes, L=1 | `revision_notes/B1_primary_audit/paired_ratio_recomputed.json`, `cell_results`: `median_paired_ratio`, `CI95`, condition keys | `primary32.pdf`, `primary32.tex` |
| Absolute-time examples (`tab:absolute`) | Four existing corners, two workloads in both scopes; separate method medians | `revision_notes/B1_primary_audit/statistics_recomputed.json`, `points` | `absolute.tex` |
| Two-to-four-record latency (`fig:retrieval-count-latency`) | All 24 conditions; alpha=2/3/4; N=1024/4096; ell=512/2048; rho_0=8, w=8*alpha; both scopes, L=1 | `revision_notes/B2_B_result_audit/scaling_audit.json`, eight workload/scope `rows`: `R2/R3/R4`, `CI95_R2/R3/R4` | `retrieval_count.pdf`, `retrieval_count.tex` |
| Record-length results (`tab:capacity`) | All five lengths, two scopes at alpha=4,N=1024; four L=1 lengths and ell=65536,J=8192,L=2 | `artifact/results/B3_descriptive_v1/B3_cells.csv`, M5 rows: `ratio_median`, `observed_session_min/max`, `J/L` | `capacity.tex` |
| Complete primary supplement (`fig:primary-complete`) | All 96 conditions and 2,160 measured pairs; rho_0=8/12/16 | Same primary canonical `cell_results` | `primary96.pdf`, `primary96.tex` |
| Cross-experiment two-record overlap (`tab:overlap`) | Eight matched workload/scope comparisons; experiments remain separate | `revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json`, `rows` | `overlap.tex` |
| Native support matrix (`tab:native-parameter-support`) | Nine profiles; algebraic capacity, six API-supported profiles and finite encrypted checks distinguished | `revision_notes/B2_A_feasibility_frontier.json`, `cells` | `parameter_support.tex` |

The 32-condition slice uses the same segment width as the multiplicity study; it was selected during presentation revision, not by effect size or preregistration. Ratios are repeated/packed, and bootstrap bars are pointwise 95% paired-bootstrap intervals. Only 3/8 alpha=2 multiplicity intervals exclude one; all 8/8 do for alpha=3 and alpha=4, using unrounded endpoints. Record-length brackets are ranges of three successive session medians, not confidence intervals.

The same B3 CSV contains all eight M6 configuration-sensitivity rows and their three-session ranges. Its paired-ratio median range is 1.1226464262964684–1.2357682810697002 (displayed 1.123–1.236). The study compares extraction/API and resource configurations and does not isolate a unique explanation for the primary/multiplicity difference. See [methodology](methodology.md) for schedule and inference limits.

## Other retained results

| Result | Public evidence | Interpretation |
|---|---|---|
| CPU work in two-to-four-record study | `revision_notes/B2_B_execution/analysis_frozen.json`, 24 `cells`: `CPU_work_ratio_descriptive` and each method's `aggregate_CPU_ns.median` | Quotient of separate repeated/packed CPU medians, excluding coordinator CPU; not the latency estimator |
| Exact buffer accounting | `artifact/results/accounting/full_grid.csv`, `artifact/generated/payload_table.tex`; implementation ciphertext ABI in `native_xpir/s4_n/support.hpp` | One buffer 131072 bytes; packed N/L and same-layout repeated alpha*N/alpha*L; no measured wire sizes |
| Functional coverage | `revision_notes/B2_A_feasibility_frontier.json`; archived `revision_notes/S4_N_status.json`, `revision_notes/B2_A_logs/`; `artifact/results/native_validation/full-v1/validation_report.json` and `functional_matrix.json` | Finite ordered/padding/block recovery and API rejection records, separate from latency and failure-probability claims |
| Monitoring | Archived `artifact/raw/B3-formal-v1/*/monitor_samples.jsonl`, joined by task directory/`task_id` | Actual timestamps, nominal 10 ms; historical primary/multiplicity individual traces are missing |

The frozen CPU summary gives separate-median ratio ranges 1.9722429249428721–2.051552433839185, 3.0333996303584287–3.148757305394123, and 4.084504051946988–4.2952000441763545 at alpha=2,3,4, eight conditions each. Those are the sources of displayed 1.972–2.052 / 3.033–3.149 / 4.085–4.295 ranges. The CPU summary is restored by the existing data archive; its SHA256 is `2fafb1d5e0bcad1ab631dd1fd4ca04640bb07a4a2e3e2ef1b17ab78b3d79ec25`. No raw-observation reanalysis is needed to inspect these fields.

## Historical identifiers and replay routes

| Research name | Immutable identifier | Raw/config lineage | Optional historical recomputation |
|---|---|---|---|
| Primary two-record | B1 | `revision_notes/B1_primary_logs/`; `B0_benchmark_manifest.json`, `B0_run_schedule.json` | `artifact/scripts/recompute_historical.py` |
| Two to four records | B2-B | `revision_notes/B2_B_execution/`; `B2_B_freeze_manifest.json`, `B2_B_run_schedule.json` | Same script, separate cells/estimator |
| Native support frontier | S4-N / B2-A | `S4_N_logs/`, `S4_N_status.json`, `B2_A_logs/` after archive extraction | Frozen functional records; independent native rebuild route in [building](building.md) |
| Configuration sensitivity | B3 / M6 | `artifact/raw/B3-formal-v1/`, `artifact/configs/B3_local_protocol.json` | `artifact/scripts/analyze_b3.py` |
| Record length | B3 / M5 | Same run/config; M5 cells distinct from M6 | Same analyzer, separate cells |
| Integer screens / buffer arithmetic | M5 accounting | `artifact/results/accounting/` and original frozen manifests | `artifact/scripts/recompute_accounting.py` plus portability check |

Record-field extraction maps to I1; full-block extraction/checked API maps to I2. Two-CPU policy maps to R1; four-CPU-coordinator policy maps to R2. These are configurations, not isolated factors. Original IDs are retained in immutable data. [data-layout.md](data-layout.md) supplies separate replay commands, including their output restrictions; this update does not execute them.
