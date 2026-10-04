# Single-Query Multi-Record Private Information Retrieval via Radix Packing

Implementation and reproducibility materials for this paper: the XPIR-based native runner, frozen experiment design and observations, full-precision results, and figure/table generators. One packed query is a selector vector containing `N` ciphertexts; radix packing recovers an ordered tuple of complete records. Correctness is conditional on integer no-wrap, and single-challenge index privacy assumes IND-CPA security of the selected symmetric-key encryption. Native tests do not establish that security premise or a native failure probability.

The implementation and complete evaluation are in [experiments/core_rebuild/](experiments/core_rebuild/README.md). The repository contains source code, required dependency metadata, measurement data and reproduction tools.

## Quick start: reproduce the current figures and tables

This route reads published results and performs consistency checks; it does not run native code, collect measurements or bootstrap. Use Python 3.12 and the pinned plotting dependencies. The commands below use a Linux/WSL shell and a virtual environment; tables alone need only the Python standard library.

```bash
git clone https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA.git
cd single-query-packed-multi-record-xpir-for-JISA
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
python3 -B scripts/verify_release.py

core=experiments/core_rebuild
results="$core/results/core_20261001_001"
mkdir -p "$core/portability"
python3 -B "$core/reproduction/paper_plots.py" --results "$results" \
  --summary-sha256 fa4f02c7ea2657c5740d531b42d15ebcbeedcc162de367a834639cb1ce6db863 \
  --out "$core/portability/paper_figures_local_001"
python3 -B "$core/reproduction/paper_tables.py" --results "$results" \
  --summary-sha256 fa4f02c7ea2657c5740d531b42d15ebcbeedcc162de367a834639cb1ce6db863 \
  --out "$core/portability/paper_tables_local_001"
```

Choose unused output leaf directories. Figure outputs include `retrieval_performance.pdf`, `capacity_tradeoff.pdf`, exact plot data and preservation/coverage receipts. Table outputs include `primary_results.tex`, `capacity_results.tex`, `costs.tex`, `selected_configurations.tex` and `mapping.json`. Plotting needs no LaTeX; embedding the table snippets requires `booktabs`, plus a `packed_artifact` bibliography entry for `costs.tex`. Figure caches and temporary files stay under the requested output directory. PDF bytes can vary across rendering environments even when numeric data agree.

## Choose a reproduction route

| Goal | Entry point | Work performed |
|---|---|---|
| Redraw the current paper displays | Quick start above; [core presentation instructions](experiments/core_rebuild/README.md#redraw-the-current-paper-figures-and-tables) | Read fixed results and verify numeric sources; no bootstrap or native execution |
| Recompute the frozen analysis | [core analysis instructions](experiments/core_rebuild/README.md#reproduce-the-frozen-analysis-or-figures), `reproduce.py analyze` | Verify/copy the frozen design and raw ledger, then repeat the original session estimator and 10,000 bootstrap draws in a new output root |
| Build and collect new measurements | [core build and campaign instructions](experiments/core_rebuild/README.md#commands-for-a-new-independent-run), [dependencies](docs/building.md) | Acquire pinned upstream source, compile, validate, probe resources, pilot, tune and freeze a new independent campaign before measurement |

The separate `reproduce.py redraw` route reproduces the original frozen figure layout; use `paper_plots.py` for the current presentation. New measurements require their own run/build identities, reviewed gates, idle-host/resource policies and raw/results directories. They must not overwrite or pool with the published observations. No native executable or system library is bundled.

## What supports the paper

Run `core_20261001_001` contains 12 primary and 16 fixed-capacity conditions at `N=1024`, ten successive sessions, and 5,880 complete physical tasks including warmups. Packed retrieval is compared primarily with independently tuned repeated retrieval; same-width repeated retrieval is an auxiliary comparison. The capacity study uses fixed policies and a full-width 24-bit repeated baseline. All methods share one four-CPU guest affinity pool and the sampled 8 GiB monitoring/abort policy, with one prepared database shared by each method's queries.

Latency is the time for a complete retrieval task, reported separately with preprocessing included and excluded. The latency contrast is the median across ten sessions of each session's median of six paired `baseline/packed` ratios. Pointwise intervals resample whole sessions. [Measurement definitions](docs/methodology.md) and the [core README](experiments/core_rebuild/README.md) specify timing boundaries, configuration selection, seeds, failure rules and CPU/buffer accounting.

| Evidence | Location |
|---|---|
| Native implementation and pipeline | [core source, scripts and tests](experiments/core_rebuild/README.md#files-and-dependencies) |
| Frozen design, schedule, seeds and source/build pins | [freeze.json](experiments/core_rebuild/runs/core_20261001_001/provenance/freeze.json) |
| Physical observations and completeness report | [observations.jsonl](experiments/core_rebuild/runs/core_20261001_001/raw/formal_001/observations.jsonl), [formal_report.json](experiments/core_rebuild/runs/core_20261001_001/raw/formal_001/formal_report.json) |
| Full-precision estimates and intervals | [summary.json](experiments/core_rebuild/results/core_20261001_001/summary.json), [fullprecision.csv](experiments/core_rebuild/results/core_20261001_001/fullprecision.csv) |
| All session effects and actual layouts/buffers | [session_effects.csv](experiments/core_rebuild/results/core_20261001_001/session_effects.csv), [configurations_and_buffers.csv](experiments/core_rebuild/results/core_20261001_001/configurations_and_buffers.csv) |
| Complete result and dependency map | [experiment-map.md](docs/experiment-map.md), [data-layout.md](docs/data-layout.md) |
| Native and analysis validation | [validation.md](docs/validation.md) |

The two current figures contain 44 of the 72 source points; the other 28 same-width comparison points remain in the complete supporting tables and fixed data. Selection is by method role, never effect size. The four table mappings contain 380 cells, 492 visible-value source pointers and 48 archived interval pointers. The selected-configuration table shows 18 method rows and all 72 configuration values.

The weaker results remain visible: four 32,768-bit records with preprocessing included have a primary paired ratio of 1.017 and interval `[0.983, 1.037]`; in the fixed-capacity study, two-record packing is slower than full-width repetition at the two tested lengths beyond its one-block boundary when preprocessing is included. Results apply to the measured backend, host, workloads and resources. Ciphertext-buffer bytes are neither network traffic nor peak memory. See [limitations.md](docs/limitations.md).

## Citation and licenses

Use the authors and software title in [CITATION.cff](CITATION.cff), and record the exact checkout with `git rev-parse HEAD`. The software retains its established artifact title; the paper's current title is shown above. Cite a fixed commit URL for the version actually used.

Project-owned programs listed in [LICENSE_SCOPE.csv](LICENSE_SCOPE.csv) use **GPL-3.0-or-later**, with the GPLv3 text in [LICENSE](LICENSE). Third-party notices remain intact; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Text, figures, documentation and data are **not automatically covered by the code license**, and no separate blanket license is granted here. Rights-uncertain upstream files are acquired separately from the official source.

Report reproducibility problems through Issues with the commit, platform, command, output path and error summary. Do not attach credentials, secret keys or confidential datasets.
