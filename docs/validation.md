# Current and historical validation

## Current core rebuild

The new `core_20261001_001` formal report records 28 complete conditions and 5,880 complete physical tasks across ten sessions. Frozen analysis completed separately. The isolated `native_003` build passed the 130-task functional gate using official Ubuntu OpenSSL `3.0.13-0ubuntu3.16` headers/runtime and a fresh upstream copy verified against all 142 original B0 source pins; that new binary did not replace the measured one or repeat formal performance collection.

Portable `analyze` and `redraw` wrappers both completed in new output roots without native execution. Redraw used no bootstrap; both generated figure PDFs and both figure/caption data files were byte-identical to the original core outputs. All six analysis outputs matched their exact parsed/numeric references: CSV bytes matched, and the three JSON files differed only in CRLF/LF line endings, with exact equality after that normalization. Existing-output and wrong-SHA refusals passed. The receipt is `experiments/core_rebuild/portability/acceptance_002/reproduction_acceptance.json`; consult [core_rebuild/README.md](../experiments/core_rebuild/README.md) for hashes and commands. A future remote fixed-commit check remains a distinct publication gate. These checks do not certify resampling coverage, IND-CPA security, native failure probability or JISA compliance.

The postmeasurement paper-layout renderer passed from an isolated 13-file source/data closure containing no PDFs, raw observations, native code, B0 metadata or manuscript files. Both generated PDFs, exact figure/caption JSON and layout mapping matched the installed assets byte-for-byte; only the capacity subplot bottom margin differs from the frozen figure. The table renderer passed from its six-file closure, and all four generated tables plus numeric-cell mapping matched installed assets byte-for-byte. Neither command resampled or ran native code. The receipt is `experiments/core_rebuild/portability/paper_acceptance_001/paper_reproduction_acceptance.json`. Generated PDF/TeX assets stay outside the incremental publication allowlist.

## Retained historical release checks

The following table and environment records describe the earlier release's isolated checks, not transcriptions of its research PASS flags. Native performance was not rerun during that earlier release validation. Its paper/page counts are historical and do not describe the current manuscript.

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

`manifests/local-validation.json` records those historical results and supporting identities. Their raw native validation/build outputs remain in the local staging workspace and are not shipped as executable dependencies. Compact build and functional receipts from that release are supplied separately; the archive retains the original empirical/functional evidence.

Numerical replay and native checks used Python 3.12.3 on Ubuntu 24.04.1/WSL2. WSL's base environment lacked Matplotlib and mpmath: plotting was validated with Windows Python 3.14.4 / Matplotlib 3.10.9, and pure-Python mpmath 1.3.0 was installed into a local validation directory for the ten correctness tests. No system Python was modified. These platform distinctions are retained rather than claiming an untested all-Linux plotting setup. A subsequent anonymous fresh clone of the published core commit passed archive extraction, checksums, all result/figure replay commands and both manuscript builds; see `manifests/remote-validation.json`. The final documentation/citation update is checked separately by Git content hashes.

Pointwise interval replay validates the estimator implementation, not its coverage under dependence. Functional passes do not establish sampler equivalence or a native negligible-failure/security guarantee. Journal-specific formatting and author declarations remain unresolved.
