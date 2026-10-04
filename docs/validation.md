# Validation evidence

The published experiment includes 130 complete native functional tasks, nine invalid-domain checks, and complete validation of 5,880 physical method tasks including warmups. The [functional report](../experiments/core_rebuild/runs/core_20261001_001/functional/functional_001/functional_report.json) and [formal report](../experiments/core_rebuild/runs/core_20261001_001/raw/formal_001/formal_report.json) record these outcomes.

Two separate checks support reproduction:

- [Native portability report](../experiments/core_rebuild/portability/native_003/portability_report.json): a separately built executable passed the unit gate and all 130 functional tasks using official Ubuntu OpenSSL development/runtime packages. The 142 upstream sources matched their pins. This check used a verified source copy on the recorded host; it was not a new operating-system installation or a rerun of formal performance measurements.
- [Analysis and redraw report](../experiments/core_rebuild/portability/acceptance_002/reproduction_acceptance.json): all six analysis outputs matched semantically and numerically; the three CSV files were byte-identical. JSON differences were limited to line endings. Frozen redraw matched its original reference outputs. Use `paper_plots.py` for the current figure presentation, and `reproduce.py redraw` for that frozen layout.

Each report identifies the source and dependency version actually tested. The original source/build hashes remain in the measurement evidence. New builds record their own identities.

Run `python3 -B scripts/verify_release.py` to verify this checkout's distributed files. Current figure/table generators verify their input hashes and write numeric-preservation or source-mapping records with their outputs. The [quick start](../README.md#quick-start-reproduce-the-current-figures-and-tables) performs no native execution or resampling.

Finite functional checks do not establish IND-CPA security or a native failure probability. Statistical replay checks the implemented estimator, not coverage under temporal dependence. See [limitations](limitations.md).
