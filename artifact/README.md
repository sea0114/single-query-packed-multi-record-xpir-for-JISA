# Recomputable evidence for the M1–M7 revision

This artifact distinguishes recomputing archived observations from collecting new observations. Historical B1 and B2-B records remain at their original repository paths; the revision adds derived outputs and a separate B3 study. No download URL or external dataset is required for the files present in this workspace.

**Current formal B3 status: COMPLETE; raw audit and independent recomputation PASS.** All 702 scheduled pairs completed (540 measured, 162 warmups), with 1404 tasks, 2886 workers, zero failures/retries/unstarted tasks and 99,751 retained monitor samples. The continuous formal run took 2131.221729501 seconds (35.52 minutes) within the 90-minute ceiling. See [run summary](raw/B3-formal-v1/run_summary.json), [raw audit](results/B3_raw_audit_v1/audit_report.json), [descriptive results](results/B3_descriptive_v1/B3_summary.json) and [independent review](../revision_m1_m7/P6_independent_results_review.md). Pilot and synthetic values remain excluded.


**Revised manuscript:** [35-page PDF](compiled_main/main.pdf), [final report](../revision_m1_m7/FINAL_REPORT.md), [M1–M7 dual statuses](../revision_m1_m7/M1_M7_status.json) and [final document QA](../revision_m1_m7/P7_document_validation.json). The root `main.pdf` is still the locked historical version; use the linked revised PDF. All P0–P7 gates passed for the explicitly declared scope, including the premeasurement M6 cost reduction.

**Final regression:** 81/81 tests passed on WSL Python 3.12.3 with `python3 -B -m unittest discover -s artifact/tests -p 'test_*.py'`. The [test-only portability fix](../revision_m1_m7/P7_test_portability.md) preserves the reviewed original test bytes and does not change frozen runtime/config/raw data. The [final arithmetic replay](results/accounting_recompute_p7/recompute_report.json) also passed on Windows Python 3.14.4 with a fresh output directory.

- Revision status and decisions: [STATUS.md](../revision_m1_m7/STATUS.md), [DECISIONS.md](../revision_m1_m7/DECISIONS.md).
- Full experiment definitions and limitations: [SUPPLEMENTARY_METHODS.md](SUPPLEMENTARY_METHODS.md).
- Historical source/data inventory: [P0_raw_inventory.md](../revision_m1_m7/P0_raw_inventory.md).
- Executed historical replay commands and outcomes: [P1_execution_record.json](../revision_m1_m7/P1_execution_record.json).

## 1. Recompute existing observations — no benchmark host required

Run from the repository root. The analysis scripts use the Python standard library. The exact historical replay was executed with **Python 3.12.3** on Ubuntu 24.04.1, matching the archived Python version. Another CPU does not require new native measurements to recompute these statistics. A different Python implementation/version must pass the exact comparisons before being described as the same historical replay.

Always use a **new output directory**; the replay scripts refuse to overwrite earlier derived outputs. The example destination names below are new-run names, not the already completed replay directories.

```bash
python3 -B artifact/scripts/recompute_historical.py \
  --out artifact/results/historical_replay_local_01
```

This command verifies frozen input/source hashes, calls the original analysis **pure functions**, and compares six archived result targets exactly. It does not invoke old runners or reporting CLIs. The verified revision replay reproduced 120 cells, their 360 median/interval-endpoint values, and the full 960,000 archived B1 bootstrap medians, with zero differences. It also checks schedules, pair/worker aggregation and absolute times. The 120-cell separate-median claim is independently checked from raw task records rather than inferred from the paired-ratio estimator.

The completed final-script run is [results/historical_replay_verified/](results/historical_replay_verified/); the earlier [historical_replay/](results/historical_replay/) is retained. Their numerical and diagnostic outputs are byte-identical. Relevant outputs are:

| File | Meaning |
|---|---|
| `status.json`, `exact_comparisons.json` | Accounting and exact comparison results |
| `input_index.json`, `versions.json` | Input SHA256, original analysis-module hashes and interpreter |
| `cells.csv`, `cells.json` | All 96 B1 and 24 B2-B cells; paired ratio/CI, absolute-time summaries and separate-median evidence |
| `normalized_measured_tasks.jsonl` | New view of existing measured task records; source raw files remain unchanged |
| `overlap_eight_cells.json` | Existing eight-cell overlap extended with full absolute summaries |
| `method_order_chronological_diagnostics.json` | Descriptive method-order and time-order diagnostics; post-hoc halves are not sessions |
| `phase_endpoint_diagnostics.json` | Accounting using actual worker phase begin/end; sums are not concurrent latency |
| `output_manifest.json` | Hashes of generated outputs |

Recompute the completed B3 run separately:

```bash
python3 -B artifact/scripts/analyze_b3.py \
  --config artifact/configs/B3_local_protocol.json \
  --raw artifact/raw/B3-formal-v1 \
  --out artifact/results/B3_recompute_local_01
```

This command accepts only `B3_FORMAL` rows carrying the exact supplied config hash. It rejects pilot/synthetic/mixed-config records and duplicate or unscheduled tasks. Missing tasks are counted as unstarted, not given invented timings. It produces `B3_summary.json`, cell CSV, all session results, four-treatment session comparisons, observed payload counters, and compact M6/M5 TeX tables. A stopped run can be analyzed with explicit incomplete accounting; no incomplete task is imputed into latency distributions.

B3 reports medians, quartiles and observed session-median ranges. These ranges are **not confidence intervals**. There is no B3 bootstrap, p-value, historical pooling or claim of pooled 95% coverage.

## 2. Arithmetic and unit verification

These commands do not launch native benchmark tasks:

```bash
python3 -B artifact/tests/test_historical.py
python3 -B -m unittest discover -s artifact/tests -p test_capacity_accounting.py -v
python3 -B artifact/scripts/recompute_accounting.py \
  --out artifact/results/accounting_recompute_local_01
python3 -B artifact/tests/test_b3_analysis.py \
  --out artifact/results/analysis_unit_local_01
```

The historical tests include the explicit counterexample showing that `median(repeated/packed)>1` does not imply an ordering of separate method medians. They also test that a nonlinear reduction transformation need not commute with an even-sample median. The B3 synthetic tests exercise failure/unstarted accounting, session withholding, method order, mixed-config rejection and observed multiblock counters. Synthetic output is visibly labelled `SYNTHETIC_UNIT_ONLY`.

Existing exact arithmetic results are in [results/accounting/](results/accounting/), with [full_grid.csv](results/accounting/full_grid.csv), [correctness_screens.json](results/accounting/correctness_screens.json), input/output hashes and the executed [validation log](results/accounting/validation_log.json). The generated paper table is [generated/payload_table.tex](generated/payload_table.tex). These results cover buffer/raw-database accounting and exact `h_max`/`h_max+1` no-wrap boundaries. They are not native observations or security certificates.

The exclusive `recompute_accounting.py --out` wrapper calls the original arithmetic functions and preserves their fixed destinations. Its executed [verification](results/accounting_recompute_v1/recompute_report.json) found the grid/table byte-identical and every exact screen identical. Use this wrapper for a fresh output. The original `capacity_accounting.py --root` writes fixed accounting/generated destinations and should not be rerun against sealed outputs. Likewise, do not execute the historical B1/B2-B reporting CLIs: some write their historical destinations.

## 3. Collect new observations — separate host, budget and run identity

New native measurements require an available, authorized benchmark host and a new measurement budget. They are not needed to recompute the archived data. A new machine must be labelled a new-host sensitivity study, not same-condition reproduction of the Ryzen/WSL2 timings.

The selected B3 design has **18 cells**:

- M6: `(N,ell_bits)=(1024,512)`, COLD/ONLINE, I1R1/I1R2/I2R1/I2R2: 8 cells, `alpha=2`, `rho0=8`.
- M5: `N=1024`, `alpha=4`, `rho0=8`, lengths `4096,8192,12288,16384,65536`, COLD/ONLINE: 10 cells. The last length has `J=8192,L=2,u=8`.
- Three sessions, each with 3 warmup pairs and 10 measured pairs per cell: **162 warmup pairs + 540 measured pairs**.
- Formal wall-time ceiling: **5,400 seconds (90 minutes)**. The selected candidate's cost estimate is approximately **54.653 minutes**, including the prescribed cost margin and overhead. This is a pilot-based budget estimate, not an observed formal-run duration.

The originally proposed M6 workload `(4096,2048)` is omitted by the premeasurement cost-only selection. B3 therefore does not claim an M6 workload-size comparison or independently identify `N` and record-length scaling. The candidate priority, per-cell whole-wall costs, selected/excluded cells and fixed sampling schedule belong in [configs/B3_local_protocol.json](configs/B3_local_protocol.json). The protocol is a **local premeasurement freeze**, not public preregistration.

The frozen protocol SHA256 is `c01a2a4294c2332aaff25231e2ed73c7956187ba3df36674ab0f8548d44b7198`; its preflight passed on the verified WSL host before formal launch. Actual completion is established separately by the run summary and post-run audits linked above.

Protocol/hash/host preflight uses the driver's actual CLI:

```bash
python3 -B artifact/scripts/execute_b3.py \
  --config artifact/configs/B3_local_protocol.json \
  --validate-only
```

This preflight launches zero native tasks. The original formal execution command, used only once for that run identity, is:

```bash
python3 -B artifact/scripts/execute_b3.py \
  --config artifact/configs/B3_local_protocol.json \
  --output artifact/raw/B3-formal-v1
```

Do not use that existing directory for another measurement. A future rerun must use a new `artifact/raw/B3-*` destination, be accepted by the driver's output-path validation, and have explicit host/budget and contract provenance. Never delete an existing directory to make a command run. The driver does not resume or replace stopped observations. If it stops at a correctness, lifecycle, runtime, integrity or fixed-resource limit, retain all attempts and failure/unstarted accounting; a later run is a different observation set.

After those new-run prerequisites are satisfied, the rerun uses the same CLI with an unused run identity, for example:

```bash
python3 -B artifact/scripts/execute_b3.py \
  --config artifact/configs/B3_local_protocol.json \
  --output artifact/raw/B3-rerun-REVIEW01
```

That example is an additional measurement command, not a step performed by the recomputation instructions. Analyze its raw directory into its own new result directory and retain its run/host provenance. Do not silently merge it with `B3-formal-v1`.

Use the pinned existing B3 binaries for a repetition of that contract. Rebuilding is a different provenance operation: the current builder accepts `--build-id`, but also writes shared derived sources and `artifact/native/current_build.json`. Run new builds in an isolated workspace and establish a new freeze. Do not mutate the active frozen build while a run is executing. The recorded build command used `python3 -B artifact/scripts/build_b3.py --build-id P0-additive-v1`; the exact compiler commands and flags are in its manifest.

## 4. Host and build provenance

The verified local host is AMD Ryzen 7 3700X, Ubuntu 24.04.1 under WSL2, Linux `6.6.87.2-microsoft-standard-WSL2`, with Python 3.12.3. See [P0_host_probe.json](../revision_m1_m7/P0_host_probe.json). CPU IDs are Linux-visible logical CPUs; WSL topology does not establish host scheduling isolation or control of turbo/governor/frequency. Sessions are successive blocks on this host, not independent days or machines.

All native studies retain XPIR commit `75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c`, `n=4096`, `q=5316911983137472318178862960259203073`, two RNS primes, flat recursion dimension 1 and database aggregation factor 1. The public `Berr=200` setting and OS-seeded native Salsa20 path remain unchanged. Query/profile width depends on the explicit study configuration; target multiplicity is not XPIR database aggregation.

The historical binaries, build flags, source and library hashes are in [B0_benchmark_manifest.json](../revision_notes/B0_benchmark_manifest.json) and [B2_B_freeze_manifest.json](../revision_notes/B2_B_freeze_manifest.json). B3 variants are **reconstructed source variants**, not the archived binaries:

| Variant | Binary | SHA256 |
|---|---|---|
| I1 | `artifact/native/build/P0-additive-v1/I1_worker` | `2265fe7e7fb78dce9a5161484a9a3fbc13f61f718f3aeddb3a73b8daf19aa2b3` |
| I2 | `artifact/native/build/P0-additive-v1/I2_worker` | `ea33c8887caa159269f085168106f0c18dbc58acd314db3402cadd5385210c07` |

[current_build.json](native/current_build.json) selects [build_manifest.json](native/build/P0-additive-v1/build_manifest.json), whose SHA256 is `9959aefb5fafc38c9a51d4e8864425978e123769bddcbaeef621fbd8d35fe668`. The manifest records g++/dependency hashes, exact compile and link commands, source derivation and the unchanged native arithmetic inputs. Compile flags include `-O2 -g -fopenmp -maes -mavx2 -DSHARED_C`; PGO, LTO and arithmetic `MULTI_THREAD` are disabled. Required native build libraries include GMP, MPFR, Boost thread/system and OpenSSL, as recorded by the actual build rather than an untested package-install recipe.

The finite [functional validation](results/native_validation/full-v1/validation_report.json) records **208 passing tasks, 448 workers, zero failures**, including padding/block boundaries and fresh-key checks. It is labelled `FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE`. The full [pilot summary](results/pilot/full-v1/pilot_summary.json) records 26 pilot cells for compatibility/cost, with zero formal observations. Neither source establishes a security level or enters formal timing estimates.

## 5. Data and manuscript display map

| Paper/evidence item | Archived source | Numeric replay / display-generation status |
|---|---|---|
| Primary Figure 2 / 96 cells (`F1_primary`) | `revision_notes/B1_primary_logs/task_rows.jsonl`, `raw_rows.jsonl`; audited paired-ratio JSON | `scripts/recompute_historical.py` reproduces the numeric cells in JSON/CSV; `render_historical_displays.py` separately regenerates the byte-identical F1 PDF and redirects its TeX wrapper. Archived displays remain unchanged |
| Multiplicity Table 4 / 24 cells (`T2_scalability`) | `revision_notes/B2_B_execution/task_rows.jsonl`, `worker_rows.jsonl` | Historical replay reproduces numeric cells; `render_historical_displays.py` separately regenerates byte-identical T2 TeX |
| Historical native frontier Table 3 (`T1_frontier`) | `revision_notes/B2_A_feasibility_frontier.json`, native validation ledgers | Existing finite correctness evidence; not derived from timing rows. `render_historical_displays.py` separately regenerates byte-identical T1 TeX |
| Eight-cell B1/B2-B disclosure | `revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json` | Historical replay `overlap_eight_cells.json`; full table/absolute times in supplementary methods |
| Raw DB/native-buffer table | Frozen workload configs and representation; no timings | Exclusive `scripts/recompute_accounting.py --out ...` calls original arithmetic; retained `results/accounting/*`, `generated/payload_table.tex` |
| B3 M6/M5 tables | Matching frozen config plus genuine `B3_FORMAL` task/worker ledgers | `scripts/analyze_b3.py` → `M6_compact.tex`, `M5_compact.tex`, complete CSV/JSON |

The archived display-generation script is `revision_notes/manuscript_integration/build_displays.py`; it writes its original integration directory. Inspect it for the retained Figure 2/Table 3/Table 4 mapping, **do not run it against sealed outputs**. Historical displayed numerical content is checked against the new replay/source evidence, and original display artifacts remain available at `revision_notes/manuscript_integration/displays/`.

Historical displays now have a separate additive rebuild command (Matplotlib required; Poppler optional for text comparison):

```bash
python3 -B artifact/scripts/render_historical_displays.py \
  --out artifact/results/historical_displays_local_01
```

The wrapper hash-checks the sealed generator and its numerical sources, then runs only the extracted rendering block in a new directory. It does not import the old module or invoke its overwrite workflow. The executed [display rebuild](results/historical_displays_v1/render_report.json) found all 120 plotted/tabulated timing cells exact, T1/T2 TeX byte-identical, and the F1 PDF byte-identical. The F1 TeX wrapper only redirects the PDF path and removes the unqualified word `preregistered`; values and intervals are unchanged. The active manuscript uses these new display files. PDF layout is checked separately in the final revision QA; numerical/byte checks alone are not a visual check.

For post-run structural auditing on Linux/WSL:

```bash
python3 -B artifact/scripts/audit_b3_raw.py \
  --raw artifact/raw/B3-formal-v1 \
  --out artifact/results/B3_raw_audit_local_01
```

This full-success audit checks the schedule, attempts, task/worker files, ordered targets, native counters, clock/barrier boundaries, saved monitor samples and fixed budget; it creates a new raw-file hash manifest. Incomplete runs are accounted for by `analyze_b3.py` instead of being certified complete.

## 6. Boundaries that remain

- Correctness, finite native execution, performance and cryptographic security are different evidence levels. The formal Gaussian law and reduction are not proved to describe the native sampler/PRNG joint law. No concrete 128-bit security or native failure-probability certificate is supplied.
- TaskTotal is wall latency. Worker CPU/phase sums, parent CPU, lifetime RSS and sampled aggregate RSS are distinct metrics. None may be silently substituted for another.
- Native buffers are 131,072 bytes per ciphertext. They are not measured wire traffic. Full download counts the raw database once, not once per target; flat packed queries remain linear in `N` and can greatly exceed raw-database size.
- Historical nominal 10 ms monitor traces were not retained. New B3 trace archival cannot reconstruct those old samples. The B2-B file named `resource_samples.jsonl` contains endpoint/lifetime observations, not a time series.
- B1/B2-B results and CIs remain separate. New bundle sensitivity cannot by itself uniquely explain the historical effect-size gap. An observed session range is not a confidence interval, and three successive sessions are limited evidence of robustness.

The historical display wrapper was actually validated on Windows Python 3.14.4, Matplotlib 3.10.9 and TeX Live Poppler. Its Linux rendering invocation is an example, not a separately executed Linux PDF-byte-identity check. Future fresh-name rerun examples are not measurements already performed. See the final report for actual commands and environments.
