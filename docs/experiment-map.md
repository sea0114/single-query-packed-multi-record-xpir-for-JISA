# Experiment and display map

| Research name | Immutable identifier | Source/config | Recompute |
|---|---|---|---|
| Primary two-record comparison | B1 | `revision_notes/B1_primary_logs/`; `revision_notes/B0_benchmark_manifest.json` and `B0_run_schedule.json` | `artifact/scripts/recompute_historical.py` |
| Multiplicity experiment | B2-B | `revision_notes/B2_B_execution/`; `B2_B_freeze_manifest.json`, `B2_B_run_schedule.json` | Same historical replay, separate cells/estimator |
| Native feasibility frontier | S4-N / B2-A | `S4_N_logs/`, `S4_N_status.json`, `B2_A_feasibility_frontier.json`, `B2_A_logs/` | Frozen functional records plus new-build functional checks |
| Bundle sensitivity | B3 / M6 | `artifact/raw/B3-formal-v1/`; `artifact/configs/B3_local_protocol.json`, study M6 | `artifact/scripts/analyze_b3.py` |
| Capacity experiment | B3 / M5 | Same run/config, study M5 | Same analyzer, distinct cells |
| Exact capacity and buffer accounting | M5 arithmetic | `artifact/results/accounting/`; frozen manifests | `artifact/scripts/recompute_accounting.py` plus portability check |

Record-field extraction/API bundle maps to I1; full-block extraction/checked API bundle maps to I2. Two-CPU resource allowance maps to R1; four-CPU parent allowance maps to R2. These are bundles, not isolated factors. The four sensitivity treatment IDs and all raw IDs are preserved.

| Final paper item | Meaning | Evidence / presentation output |
|---|---|---|
| Fig. 1 | Query–reply–extraction flow | `paper/sections/construction.tex`, formal interfaces; no timing data |
| Fig. 2 | All 96 primary cells | Historical replay → checked primary reference → `scripts/present_results.py` → `primary.pdf` |
| Table 1 | Mechanism comparison | Cited original papers; `paper/sections/related.tex` and [expanded matrix](prior-work-comparison.md) |
| Tables 2–3 | Notation and ownership | Formal model; no empirical estimator |
| Table 4 | Four designs | Frozen schedules/config; `paper/sections/evaluation.tex` |
| Table 5 | Four absolute-time examples | Raw primary task medians / `statistics_recomputed.json`; `absolute.tex` |
| Table 6 | All 24 multiplicity cells | Historical replay / `scaling_audit.json`; `multiplicity.tex` |
| Table 7 | Ten capacity cells | Follow-up replay / `B3_cells.csv`; `capacity.tex` |
| Table 8 | Native-buffer accounting | Exact arithmetic; `payload.tex` |
| Supplement tables and §3.3 | Frontier, complete primary grid, multiplicity, eight overlaps, sensitivity, capacity | Same separate references, `frontier.tex` and `supplement_tables.tex` |

All named presentation outputs reside in `paper/generated/`; regenerating with `scripts/present_results.py --out NEW` creates the same set in NEW. `display_data.json` retains full source precision and source hashes. Main/supplement compact ratios use three decimals, primary and overlap long tables use six. Classification uses unrounded endpoints: a displayed endpoint of 1.000 can be slightly below one. There is no pooled estimator across experiments. `presentation_manifest.json` records the derivative output hashes.

The frozen historical display renderer is a separate compatibility check; its archival captions need not match the new paper's natural-language captions. It uses the same coordinates and statistics and never creates new observations.

The uncaptioned eight-row overlap long table is identified by supplement §3.3, not by a visible table title. The subsequent sensitivity and capacity tables retain their displayed numbering.
