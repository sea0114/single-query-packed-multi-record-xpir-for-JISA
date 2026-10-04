# Implementation and data layout

| Path | Contents |
|---|---|
| `experiments/core_rebuild/src/` | Native packed/repeated retrieval implementation |
| `experiments/core_rebuild/scripts/` | Build, functional tests, resource control, tuning, measurement and analysis |
| `experiments/core_rebuild/tests/` | Native unit checks and analysis tests |
| `experiments/core_rebuild/reproduction/` | Portable analysis and figure/table generation |
| `experiments/core_rebuild/runs/core_20261001_001/` | Frozen design, source/build identities, functional/pilot/tuning evidence and raw observations |
| `experiments/core_rebuild/results/core_20261001_001/` | Full-precision summaries, all session effects, configuration/buffer counts and analysis provenance |
| `experiments/core_rebuild/portability/` | Recorded native and analysis validation |
| `manifests/upstream-build-environment.json` | Exact backend commit and 142 upstream source-file hashes |
| `manifests/release-files.csv` | Distributed-file sizes and SHA256 values |

The formal ledger is `runs/core_20261001_001/raw/formal_001/observations.jsonl`; its completeness report is adjacent. `provenance/freeze.json` fixes the schedule, seeds, configurations and expected observations. Pilot and tuning data remain separate from formal estimates. The [result map](experiment-map.md) identifies the outputs used by each figure and table.

The [portable reproduction wrapper](../experiments/core_rebuild/README.md#reproduce-the-frozen-analysis-or-figures) verifies and copies only its required inputs to a new output root. Analysis repeats the frozen estimator and bootstrap; redrawing reads the fixed results. Original absolute paths and earlier source identities in measurement manifests are provenance records, not commands for the current checkout. Preserve the `experiments/core_rebuild/` nesting and use the documented portable commands.

Dependency binaries, system libraries, manuscript sources, revision notes and generated displays are outside the tracked tree. The native fetcher creates the ignored `native_xpir/upstream/` directory. Generated output directories must be new and must not replace published results.
