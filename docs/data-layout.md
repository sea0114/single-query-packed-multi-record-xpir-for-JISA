# Evidence layout

## Current core run

The current entry point is [core_rebuild/README.md](../experiments/core_rebuild/README.md). New evidence retains the independent `experiments/core_rebuild/` layout: `runs/core_20261001_001/provenance/freeze.json` freezes the schedule/seeds/configurations; `raw/formal_001/observations.jsonl` and `formal_report.json` record every physical task and completion status. Under `results/core_20261001_001/`, `summary.json`, `fullprecision.csv`, `session_effects.csv`, `configurations_and_buffers.csv`, `claim_map.json`, `failure_ledger.json` and `analysis_provenance.json` provide full precision, all sessions, buffers, claim pointers and exact input/output identities.

The separate portable wrapper copies a verified minimal closure to an explicitly new output root. `analyze` executes the frozen session-cluster estimator, including its prescribed bootstrap; `redraw` reads the accepted summary without resampling. Neither launches native code or opens historical datasets. Original absolute build/environment paths remain provenance records, not portable commands. See the core README for actual execution receipts and public metadata checks. Current manuscript/PDF/submission materials, native binaries, objects, dependency headers/libraries and caches are excluded from this increment.

The historical dependency pin `revision_notes/B0_logs/build_environment.json` is promoted byte-for-byte for the new build route. Its duplicate archive member, original archive hash and license scope remain unchanged. Existing archives, canonical historical summaries and earlier publication history are preserved; no historical samples are merged into the core estimates.

## Retained historical data and replay routes

All sections below describe the earlier evidence and presentation. Assertions about no new measurements apply to that earlier presentation update, not the separately completed core run above.

## Included canonical presentation inputs

The shortest redraw route reads only these already included full-precision references:

- `revision_notes/B1_primary_audit/paired_ratio_recomputed.json`
- `revision_notes/B1_primary_audit/statistics_recomputed.json`
- `revision_notes/B2_B_result_audit/scaling_audit.json`
- `revision_notes/B2_B_result_audit/B1_B2B_sanity_details.json`
- `revision_notes/B2_A_feasibility_frontier.json`
- `artifact/results/B3_descriptive_v1/B3_cells.csv`

[experiment-map.md](experiment-map.md) gives the earlier fields, conditions and output names. `scripts/present_results.py --root . --out UNUSED` reads those files without archive extraction, native code or bootstrap. All generated figures, tables, JSON, manifests and caches go into the unused output tree; `paper/generated/` remains historical evidence.

## Archived observations and detailed checks

`data/research-data-20260926.tar.gz` is the existing deterministic archive. `manifests/data-archives.json` records its SHA256 and all 1,932 restored member hashes/sizes. Extraction restores exact legacy relative paths, IDs and line endings. Metadata may retain historical source-machine/account paths, host/boot IDs and build identities; portable replay does not open those absolute paths. They are provenance records, not machine-access credentials. Frozen headers and hashes were not silently redacted.

Primary task/worker ledgers and bootstrap references are under `revision_notes/B1_primary_logs/`; multiplicity records and the CPU/phase summary are under `revision_notes/B2_B_execution/`. Later task/worker ledgers and 1,404 monitoring files are under `artifact/raw/B3-formal-v1/`; its 99,751 observations join by unchanged task directory/`task_id`. Historical primary/multiplicity individual monitoring time series were not retained and are not reconstructed.

Functional evidence includes `revision_notes/S4_N_status.json`, `revision_notes/B2_A_logs/`, and the separate `artifact/results/native_validation/full-v1/validation_report.json`, `functional_matrix.json` and 448 worker-result records. The [frontier summary](../revision_notes/B2_A_feasibility_frontier.json) points to exact profile evidence. This includes 246 historical two-record cases, ten cases for each of three supported additional profiles, and the separate 208-task/448-process suite. Test data cover zero, maximum-segment, alternating and deterministic pseudorandom records, reversed targets and full-block boundaries. Test bytes and expected/actual outputs are public fixtures. Key fingerprints are hashes, not secret-key material.

The historical prepublication scan found no secret keys, access tokens, OS seeds or PRNG state in its enumerated release files. That is the scope of the recorded check, not clearance of every historical working directory. No new measurements or archives accompanied that earlier presentation update.

## Historical statistical replay

This optional route uses raw records and the original estimators, including bootstrap recomputation. It is separate from result redrawing and was not run during the earlier presentation update. Use Python 3.12.3 for comparison with the recorded exact replay, extract data first, and choose unused output directories:

```bash
python3 -B scripts/unpack_data.py
python3 -B scripts/verify_release.py --data
python3 -B artifact/scripts/recompute_accounting.py --out artifact/results/replay_accounting_01
python3 -B scripts/check_accounting_portability.py --replay-dir artifact/results/replay_accounting_01
python3 -B artifact/scripts/recompute_historical.py --out artifact/results/replay_historical_01
python3 -B artifact/scripts/analyze_b3.py --config artifact/configs/B3_local_protocol.json --raw artifact/raw/B3-formal-v1 --out artifact/results/replay_followup_01
python3 -B artifact/scripts/render_historical_displays.py --out artifact/results/replay_displays_01 --replay-dir artifact/results/replay_historical_01
```

Each `--out` is new; failures/partial outputs remain for diagnosis. The arithmetic wrapper writes only its selected output directory. Its frozen TeX comparison reports `DIFFERENCE` on Linux solely for historical CRLF reference endings; the separate portability check must report `PASS_NUMERICAL_AND_TABLE_CONTENT` and accepts only CRLF/LF changes. Do not ignore other differences. The historical replay's recorded target status is `PASS` for six exact comparisons; the later analyzer's recorded status is `COMPLETE`, 1,404 successful tasks and zero unstarted tasks, with descriptive inference. These are targets and prior validation results, not a new run.

Frozen analysis sources/references remain required even if the current paper no longer prints every long table. The historical display renderer checks its sealed numeric/display lineage; its old captions and layout are not the current presentation. Do not run bare generators that overwrite original `artifact/results/accounting/`, or old mixed release/manuscript gates, to obtain an unused-directory replay.

## Historical and platform-specific material

Existing `paper/`, `submission/`, `presentation_check/`, `release_validation/` and older validation manifests are historical artifacts; they are retained rather than refreshed as part of the current manuscript. Current manuscript/PDF/submission materials are excluded from this incremental update. Native executables, system libraries and rights-uncertain upstream sources are not newly redistributed.

Optional old host-specific preflight inputs are not all distributed. Passing replay does not make a future campaign portable. Native build has a separate [independent-checkout route](building.md); it writes shared derived source and build selectors. New performance work requires a new configuration/identity and must not bypass original pins. `artifact/README.md` and `artifact/SUPPLEMENTARY_METHODS.md` are preserved historical provenance; the repository root README and these active docs are the current entry points.
