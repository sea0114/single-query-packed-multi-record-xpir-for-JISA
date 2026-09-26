# Validation performed for this release

These are new checks in an isolated checkout, not transcriptions of historical PASS flags. Native **performance** was not rerun.

| Check | Actual result |
|---|---|
| Fixed source acquisition | Official download; all 142 upstream SHA256 pins matched |
| Arithmetic replay | 68 rows and all exact screens matched; frozen TeX byte check reported DIFFERENCE on Linux, fully explained by CRLF/LF; new content-only classifier passed without altering either file/report |
| Historical replay | 120 cells, 360 median/CI values, six exact targets, 960,000 stored bootstrap samples; zero differences |
| Sensitivity/capacity replay | 18 cells, 540 measured pairs, 1,404 complete tasks; entire cell CSV byte-identical |
| Frozen display compatibility | Numerical/table checks passed; original primary PDF bytes matched on Windows |
| New presentation | Independently regenerated semantic displays byte-matched the paper outputs |
| Source/analysis/runner tests | 81 passed on Ubuntu/WSL2 |
| Encoding/correctness tests | 16 + 10 passed; mpmath 1.3.0 was installed locally after an initial missing-dependency error |
| Fresh native build | Passed; new binary/compiler/library manifest; no historical binary identity claimed |
| Native functional-only suite | 208 tasks, 448 successful fresh-key workers, zero failures; timing fields suppressed |
| Adapter rejection checker | Six invalid public domains rejected, one supported profile accepted |
| Paper build and QA | Final 23-page main paper and 5-page supplement compiled in authoring and clean release trees; the earlier published core build had 24 main pages; no undefined refs/cites, duplicate labels or overfull boxes; all pages visually reviewed |

`manifests/local-validation.json` records the results and supporting identities. Raw current native validation/build outputs remain in the local staging workspace and are not shipped as executable dependencies. Compact current build and functional receipts are supplied separately; the archive retains the original empirical/functional evidence.

Numerical replay and native checks used Python 3.12.3 on Ubuntu 24.04.1/WSL2. WSL's base environment lacked Matplotlib and mpmath: plotting was validated with Windows Python 3.14.4 / Matplotlib 3.10.9, and pure-Python mpmath 1.3.0 was installed into a local validation directory for the ten correctness tests. No system Python was modified. These platform distinctions are retained rather than claiming an untested all-Linux plotting setup. A subsequent anonymous fresh clone of the published core commit passed archive extraction, checksums, all result/figure replay commands and both manuscript builds; see `manifests/remote-validation.json`. The final documentation/citation update is checked separately by Git content hashes.

Pointwise interval replay validates the estimator implementation, not its coverage under dependence. Functional passes do not establish sampler equivalence or a native negligible-failure/security guarantee. Journal-specific formatting and author declarations remain unresolved.
