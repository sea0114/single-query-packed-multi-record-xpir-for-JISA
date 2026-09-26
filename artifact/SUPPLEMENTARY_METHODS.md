# Supplementary experimental methods

This supplement records the interpretation contract for historical B1/B2-B evidence and the separate M1–M7 revision studies. It is not a replacement for raw observations. [README.md](README.md) provides commands, dependencies and file maps.

**Current formal B3 status: COMPLETE; raw audit and independent recomputation PASS.** All 702 scheduled pairs completed (540 measured, 162 warmups), with 1404 tasks, 2886 workers, zero failures/retries/unstarted tasks and 99,751 retained monitor samples. The continuous formal run took 2131.221729501 seconds (35.52 minutes) within the 90-minute ceiling. See [run summary](raw/B3-formal-v1/run_summary.json), [raw audit](results/B3_raw_audit_v1/audit_report.json), [descriptive results](results/B3_descriptive_v1/B3_summary.json) and [independent review](../revision_m1_m7/P6_independent_results_review.md). Pilot and synthetic values remain excluded.

## 1. Common mathematical/native profile and task

The pinned upstream XPIR revision is `75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c`. The native profile fixes `n=4096`, `q=5316911983137472318178862960259203073`, with primes `2305843009213317121` and `2305843009213120513`; their product is 122 bits. Recursion dimension and database aggregation factor both equal one. Native `Berr=200` and OS-seeded Salsa20 remain unchanged. `alpha` counts retrieved records; it is not a database-aggregation parameter.

The retrieval target is an ordered tuple of distinct indices. Packed execution uses one query/worker to recover the tuple. Repeated execution is a single completed task containing `alpha` concurrent single-record workers, each with private client and raw/encoded/imported database state. Within each pair, both methods use the same raw database, targets, profile and layout. Every worker obtains a fresh key and fresh native cryptographic randomness. Fixture/order/analysis seeds are public reproducibility inputs; they do not replace cryptographic randomness or expose secret keys.

The layout is `B=2^rho0`, `w=alpha*rho0`, `t=2^w`, `J=ceil(ell/rho0)`, `L=ceil(J/n)`. Canonical encoding, padding, direct constant encryption and ordered recovery are tested separately from timing. Historical workloads all have `L=1`; B3 explicitly includes an `L=2` capacity point in its selected design.

## 2. Timing and state lifecycle

TaskTotal uses `CLOCK_MONOTONIC_RAW`. A packed task is one worker span; a repeated task is `max(worker_end)-min(worker_start)`, including dispatch skew inside those endpoints. It is not the sum of worker wall times. Fresh client configuration, key generation, query generation, reply generation and extraction are timed in both views.

| Component | COLD | ONLINE |
|---|---|---|
| Fresh client configuration/key generation | Inside TaskTotal | Inside TaskTotal |
| Private server configuration/encoding/import | Inside TaskTotal | Staged before TaskTotal |
| Query/reply generation and extraction | Inside TaskTotal | Inside TaskTotal |
| Query/reply buffer copying | Corresponding timed phases | Corresponding timed phases |
| Fixture creation/process startup | Outside TaskTotal | Outside TaskTotal |
| Correctness validation | After every peer's TaskTotal endpoint | After every peer's TaskTotal endpoint |
| Teardown and file logging | Outside TaskTotal | Outside TaskTotal |

ONLINE reports a conditionally staged task, not an amortized multiple-query service or key reuse. Preprocessing is worker-private, including each repeated worker. The experiment does not model a persistent shared server or isolate radix arithmetic from setup, copying, workers and their lifecycle. Same-profile comparison is controlled; it is not a claim of superiority over independently optimized XPIR configurations, all PIR systems or full download.

## 3. Contract matrix

CPU identifiers below are OS-visible logical CPUs, not a proof of physical-core isolation. Each arithmetic worker uses one thread.

| Dimension | B1 primary | B2-B multiplicity | B3 I/R sensitivity and capacity |
|---|---|---|---|
| Workload | `alpha=2`; `N=256,1024,4096,16384`; `ell=256,512,1024,2048`; `rho0=8,12,16` | `alpha=2,3,4`; `N=1024,4096`; `ell=512,2048`; `rho0=8` | M6: only `N=1024,ell=512,alpha=2`; M5: `N=1024,alpha=4,ell=4096,8192,12288,16384,65536`; `rho0=8` |
| COLD/ONLINE cells | 96 | 24 | Selected design: 8 M6 + 10 M5 = 18 |
| Width and blocks | `w=2*rho0`, `L=1` | `w=8*alpha`, `L=1` | M6 `w=16,L=1`; M5 `w=32`, `L=1` except `ell=65536,L=2` |
| Packed affinity | `{0,2}` with one arithmetic thread | `{0}` | R1 `{0,2}`; R2 `{0}` |
| Repeated affinity | Workers `{0}`, `{2}` | First `alpha` CPUs from `{0,2,4,6}` | R1 two workers `{0}`, `{2}`; R2 first `alpha` CPUs from `{0,2,4,6}` |
| Parent affinity | `{0,2}` | `{0,2,4,6}` for every alpha | R1 `{0,2}`; R2 `{0,2,4,6}` |
| Per-worker address space | Packed 16 GiB; repeated 8 GiB each | 8 GiB each | R1 packed 16 GiB/repeated 8 GiB; R2 8 GiB each |
| Aggregate virtual-memory cap | Per-task RLIMIT_AS allocation; no separately sampled aggregate VmSize gate | 16 GiB sampled | R1 no sampled aggregate VmSize gate; R2 16 GiB sampled |
| Aggregate worker RSS cap | 16 GiB sampled | 16 GiB sampled | 16 GiB sampled |
| Measured pairs/cell | 30/30/20/10 with increasing N | 10 | Completed 30 = 3 sessions × 10 |
| Warmup pairs/cell | 3 | 3 | Completed 9 = 3 sessions × 3 |
| Method order | Balanced per cell, interleaved rounds | Balanced 5/5 per cell, interleaved rounds | Balanced 5/5 within each cell/session; rounds interleave treatments/cells |
| Main estimator | Median paired ratio and historical pointwise bootstrap CI | Same estimator, own samples/seed | Descriptive paired median/IQR; every session median and observed range; no CI/p-value |
| Fixture | Public B0 seed `0x42305f4441544131` | Public seed `0x8c3f47282900cee8` | Same common public B2-B-seed fixture for I1 and I2 |
| Resource trace archival | No individual 10 ms time series | No individual 10 ms time series | Common new runner buffers nominal 10 ms samples and saves actual timestamps after task execution |

B3 R1/R2 are **bundles**: affinity, parent activity and memory policies change together. They do not isolate individual resource mechanisms. I1/I2 are reconstructed implementation bundles with a common public fixture and common new instrumentation. I1 preserves the B1 record-used-field extraction; I2 preserves all-field extraction and checked direct-encryption handling. The new I1 additional full-coefficient validation is after peer TaskTotal completion. B3 does not simply drop old binaries into a new runner and call the result historical replication.

B3 M5 uses I2R2 because it supports checked APIs, complete block extraction, `alpha=4` and validated `L=2`; selection is made before formal outcomes and is not based on speedup.

## 4. Historical data completeness and exact replay

| Stage | Task rows | Worker rows | Warmup pairs | Measured pairs | Measured cells |
|---|---:|---:|---:|---:|---:|
| B1 | 4,896 | 7,344 | 288 | 2,160 | 96 |
| B2-B | 624 | 1,248 | 72 | 240 | 24 |

All archived task and worker rows are COMPLETE. Every scheduled pair has one packed and one repeated task; no measured pair is omitted, replaced, imputed or filtered as an outlier. Workers are not independent latency samples. The additive replay rechecks worker/task endpoints and validation ordering, invokes the original hash-verified pure analysis functions, and matches six archived outputs exactly. Full B1 bootstrap vectors also match.

For a complete pair `k`, `R_k=T_repeated,k/T_packed,k`; the estimator is `median_k(R_k)`. Historical intervals use 10,000 with-replacement pair resamples, the original `random.Random(...).choices` implementation, medians, and type-7 percentile endpoints. Seeds reset per cell: B1 `2026092401`, B2-B `2026092501`. The original analysis environment is Python 3.12.3; the replay records actual module hashes. The number of resamples is not the number of measured independent observations.

These are historical **pointwise** intervals, not simultaneous/family-wise guarantees. Pair IDs alone do not establish independence. Historical batches preserve rounds, ordering and RAW endpoints, but not independent session IDs; the replay's chronological halves are descriptive diagnostics, not retrospectively designed sessions. Exact computational reproduction does not establish CI coverage in the presence of temporal dependence.

`median(repeated/packed)>1` does not logically imply `median(packed)<median(repeated)`. The separate-median claim is independently checked from all actual task rows: 96/96 B1 and 24/24 B2-B cells have lower packed separate medians. The synthetic counterexample `[100,110,120]` versus `[101,109,122]` is a unit test only. Percentage reductions, if used, are computed per pair as `1-T_packed/T_repeated`; a ratio of 1.19 is not a 19% reduction, and nonlinear transformation need not commute with an even-sample median.

Replay records: [exact comparisons](results/historical_replay_verified/exact_comparisons.json), [full cell summaries](results/historical_replay_verified/cells.json), [versions](results/historical_replay_verified/versions.json), [descriptive ordering diagnostics](results/historical_replay_verified/method_order_chronological_diagnostics.json).

## 5. Eight overlapping historical alpha=2 cells

The true overlap is `alpha=2,rho0=8,w=16,N∈{1024,4096},ell∈{512,2048}`, both views. It is not the whole B1 range. The following table is generated from the existing [sanity comparison](../revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json), independently checked during replay. Absolute medians are displayed in seconds; the linked JSON retains nanoseconds and the [replay overlap](results/historical_replay_verified/overlap_eight_cells.json) also gives quartiles/min/max. `P/R` means packed/repeated absolute TaskTotal medians, not their paired-ratio estimator.

| N | ell bits | View | Pairs B1/B2-B | B1 R [pointwise 95% CI] | B2-B R [pointwise 95% CI] | B1 absolute P/R (s) | B2-B absolute P/R (s) |
|---:|---:|---|---:|---|---|---|---|
| 1024 | 512 | COLD | 30/10 | 1.139262 [1.085824, 1.191560] | 1.050424 [1.005370, 1.078139] | 0.776225 / 0.886442 | 0.997881 / 1.042731 |
| 1024 | 512 | ONLINE | 30/10 | 1.150107 [1.135753, 1.178071] | 1.055142 [1.029526, 1.082148] | 0.646274 / 0.744717 | 0.808264 / 0.853518 |
| 1024 | 2048 | COLD | 30/10 | 1.168316 [1.106926, 1.219878] | 1.035751 [1.005946, 1.056287] | 0.791924 / 0.933262 | 1.014009 / 1.040060 |
| 1024 | 2048 | ONLINE | 30/10 | 1.173708 [1.143952, 1.206580] | 1.032994 [0.980469, 1.066962] | 0.644294 / 0.751217 | 0.807689 / 0.834763 |
| 4096 | 512 | COLD | 20/10 | 1.151662 [1.115323, 1.222798] | 1.024721 [0.999873, 1.052480] | 3.206030 / 3.761338 | 3.998720 / 4.057047 |
| 4096 | 512 | ONLINE | 20/10 | 1.152929 [1.117815, 1.178396] | 1.024121 [0.998385, 1.038569] | 2.693276 / 3.148768 | 3.259441 / 3.342292 |
| 4096 | 2048 | COLD | 20/10 | 1.156052 [1.119723, 1.201635] | 1.013180 [0.985558, 1.026105] | 3.264344 / 3.880651 | 4.099095 / 4.157609 |
| 4096 | 2048 | ONLINE | 20/10 | 1.170338 [1.124527, 1.198264] | 1.014741 [0.993317, 1.033899] | 2.676421 / 3.146918 | 3.307141 / 3.325094 |

All eight B2-B paired medians are lower than their corresponding B1 values, and all eight pairs of stage-specific pointwise intervals are disjoint. This is a descriptive comparison of separate studies, not a cross-study significance test, eight independent causal replications or a reason to substitute B1 for B2-B's alpha=2 reference.

The [archived source diff](../revision_notes/B2_B_result_audit/B1_B2B_worker_source.diff) and [sanity report](../revision_notes/B2_B_result_audit/B1_B2B_alpha2_sanity.md) identify differences in binary/adapter, extraction traversal, wrappers, packed/parent affinity, memory enforcement, fixtures, sample counts and schedules. Same nominal host and backend do not identify which differences caused the gap. Worker phases have real absolute begin/end fields and may be examined, but aggregate phase work is not a causal critical-path decomposition. The historical cause remains unknown; new B3 bundle sensitivity does not automatically identify it.

## 6. B3 cost-only selection and descriptive analysis

The selected design contains **18 cells, 540 measured pairs and 162 warmup pairs**. It retains one M6 workload and all five M5 lengths including multiblock coverage. The original two-workload M6 proposal included `(4096,2048)`; those eight cells are omitted before formal measurement on the cost-only rule, not on effect direction or interval significance. No M6 claim comparing sizes or isolating N/ell scaling follows from the reduced design.

Candidate priority is full 26 cells, default 24 without multiblock, reduced 18 with multiblock, then reduced 16 without multiblock. The freeze selects the first candidate meeting the fixed budget using `1.5 × 39 pairs × sum(one-pilot-pair whole-wall cost per cell) + 150 s session breaks + 60 s bookkeeping`. The selected estimate is approximately **54.653 minutes**; the authorized formal ceiling is **90 minutes** from first launch. Estimation uses whole-wall compatibility/cost pilot data, never ratios, CIs or winner direction. Pilot samples are excluded from formal observations.

The selected local protocol is [B3_local_protocol.json](configs/B3_local_protocol.json), SHA256 `c01a2a4294c2332aaff25231e2ed73c7956187ba3df36674ab0f8548d44b7198`. Host/protocol preflight passed before formal launch. This identifier fixes design and source provenance; separate run/audit records establish actual completion.

The frozen plan records three successive sessions per study, 3 warmup and 10 measured pairs per cell/session, balanced method order, shuffled cell order within rounds, and 30-second breaks. These are same-host time blocks, not independent days/machines. Only repeated workers within a task run concurrently; different cells do not compete concurrently.

The driver stops on the first non-COMPLETE task, integrity/fresh-key failure or fixed wall/resource limit. It preserves launch intent, failure records and all unstarted schedule entries. It does not retry, replace or extend sampling after viewing ratios. The analysis withholds a cell/session's latency summaries if any scheduled warmup is failed or missing, while retaining complete eligible sessions and all accounting. Incomplete tasks are not assigned timings.

B3 descriptive output includes:

- Complete-pair ratio median, Q1/Q3, IQR, min/max and pair counts.
- Absolute successful TaskTotal summaries for each method, separately from failure/incomplete/unstarted counts.
- Every session's estimates/counts plus the observed range of available session medians.
- All four M6 treatments by workload/view/session; no pooled treatment estimate or p-value.
- M5 J/L/u and native query/reply counters validated against actual complete worker/task records.

The observed session range is **not a confidence interval**. There is no B3 bootstrap, pooled 95% coverage claim, significance testing, or pooling into B1/B2-B. Three sessions offer limited robustness evidence. Results that cross one, fail to increase, or favor repeated execution remain valid observations if the functional and measurement contracts hold.

## 7. Capacity and buffer accounting

`u=alpha*J/n=1` is the boundary for placing alpha complete fixed-J segment blocks into disjoint coefficient intervals of one polynomial. `J=n` is the separate boundary for a single record to need more than one polynomial block. Thus `u>1` does not imply `L>1`.

| M5 ell bits | J | L | u, alpha=4 | Role |
|---:|---:|---:|---:|---|
| 4096 | 512 | 1 | 0.5 | Below fixed coefficient-position boundary |
| 8192 | 1024 | 1 | 1 | Fixed-encoding single-polynomial block capacity |
| 12288 | 1536 | 1 | 1.5 | Above that boundary |
| 16384 | 2048 | 1 | 2 | Higher coefficient-position demand |
| 65536 | 8192 | 2 | 8 | Explicit multiblock coverage |

The direct coefficient-position expression `sum_r X^((r-1)J) P_i_r(X)` is an analytical comparison for fixed segmentation. Its direct disjoint blocks fit one polynomial only when `alpha*J<=n`. This is not an implemented second PIR scheme; `ceil(alpha*J/n)` is a slot-space lower bound, not an established alternative protocol's exact reply count. It does not rule out different encodings, hybrid packing or multiblock schemes, and no competitor speed ranking is claimed.

For byte-aligned records and native ciphertext buffer `C=131072` bytes:

```text
raw_DB = N*ell/8
packed_query = N*C           packed_reply = L*C
repeated_query = alpha*N*C   repeated_reply = alpha*L*C
```

Full download is one raw database, not alpha databases. Non-byte-aligned arithmetic rows distinguish `ceil(N*ell/8)` global bit packing from `N*ceil(ell/8)` per-record byte storage. Binary units use KiB=1024, MiB=2^20, GiB=2^30 bytes.

The native representation contains two ciphertext components × two RNS residues × 4096 64-bit words = 131,072 bytes. Query/reply counts concern copied local buffers, not wire traffic, framing, compression, key distribution or network E2E latency. Packed query/raw DB ratio is `8*C/ell`; even at ell=16384 it equals 64. Capacity coverage therefore does not establish communication superiority over full download.

[Exact accounting](results/accounting/full_grid.csv) retains all historical and new arithmetic rows. [Correctness screens](results/accounting/correctness_screens.json) verify integer `h_max` and `h_max+1` boundaries for each relevant block under `B^alpha-1+t*N*m_j*(B-1)*h<q/2`. No positive r is selected; these checks are correctness-admissibility screens under the formal good event, not native reliability/security certificates. The exclusive [recompute wrapper](scripts/recompute_accounting.py) reproduces the grid/table and screens without overwriting their original outputs.

## 8. Resource, monitor and instrumentation semantics

Worker aggregate CPU is the sum of user+system deltas over TaskTotal. Parent CPU is separate; B3's parent measure includes the whole runner task and must not be silently added to worker TaskTotal CPU. Repeated phase durations are sums of worker work spans, not wall latency. Phase first-begin/last-end envelopes may overlap and include gaps; their sum is also not a partition of TaskTotal.

Packed lifetime RSS includes staging. Repeated lifetime RSS is the sum of worker lifetime peaks; these peaks need not be simultaneous. Even when aggregate RSS is sampled, the largest recorded sample is an observed sampled peak, not the unobserved true instantaneous maximum. Parent RSS is separate. Native pre-exit RSS and final `wait4` lifetime RSS can differ; the historical B2-B postprocessing checker correction recorded this distinction without editing measurements or rerunning tasks.

Historical nominal 10 ms `/proc` time series are unavailable. B2-B `resource_samples.jsonl` is explicitly an endpoint/lifetime ledger with null sample timestamps, not a time series. No synthetic trace is reconstructed from aggregates. Original historical start/end/incident evidence remains available but cannot certify every transient host condition.

The B3 runner uses common new monitoring across treatments, buffers samples during execution and persists them afterward. Parent sampling itself can consume resources; the study does not claim zero instrumentation overhead or isolate a monitoring factor. Actual sample timestamps, process affinity and host/session snapshots must be retained and checked. A nominal interval is not a guarantee of exact scheduling cadence. WSL host-managed turbo/frequency/governor and physical scheduler isolation remain unverified.

## 9. Provenance and security boundaries

Historical contract and raw sources remain under `revision_notes/B1_primary_logs/` and `revision_notes/B2_B_execution/`, with SHA256 lineage in the frozen manifests, final audit packages and new [input index](results/historical_replay_verified/input_index.json). B3 uses `artifact/native/current_build.json`, the additive build manifest, the frozen protocol, and a new raw directory. The build manifest labels I1/I2 as reconstructed variants and records compiler, flags, libraries, source hashes and exact commands. No raw record is migrated into a preferred stage or relabelled as an earlier observation.

The original papers and software are literature/software references; local stage identifiers are artifact provenance, not external research publications. The paper reports interpretation-critical methodology; this supplement carries detailed contracts/diagnostics; README supplies reproducibility commands; raw/config/code remain the underlying evidence.

The formal construction has conditional correctness, a distribution-specific ideal-law failure analysis, and a single-challenge privacy reduction. Native execution has finite correctness/performance evidence under a pinned implementation. Those chains remain distinct. The native sampler/PRNG joint-law bridge, concrete security assessment and a native decryption-failure certificate are not supplied by this artifact. `Berr=200`, successful functional cases, API acceptance, a `2^-128` reliability policy and old nominal security fields do not establish 128-bit security. No native security claim is inferred from performance, scope wording or a formal arithmetic screen.
