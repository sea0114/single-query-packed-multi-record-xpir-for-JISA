# Core experiment rebuild

This directory contains the new native runner and experiment pipeline for the
2026-10-01 core evaluation. It keeps new observations separate from the older
`artifact/`, `native_xpir/` validation campaigns and published canonical summaries.
Its measured results apply to the recorded backend, host, workloads and resource
policy. The experiment does not certify IND-CPA security, a concrete security
level or a native decryption-failure probability.

## Current execution status

Run `core_20261001_001` has completed measurement collection:

- 130 complete native functional tasks with no failures, plus the standalone
  readonly-mapping unit gate and nine invalid-domain rejection checks. See
  [`functional_report.json`](runs/core_20261001_001/functional/functional_001/functional_report.json).
- 288 complete representative pilot tasks and 336 complete candidate-cost pilot
  tasks, with no failed observations. Their reports are
  [`pilot_001/pilot_report.json`](runs/core_20261001_001/pilot/pilot_001/pilot_report.json)
  and [`pilot_002/pilot_report.json`](runs/core_20261001_001/pilot/pilot_002/pilot_report.json).
- 1,408 complete tuning tasks across all 12 provisional workloads, in
  2,220.658 seconds. See
  [`tuning_report.json`](runs/core_20261001_001/tuning/tuning_001/tuning_report.json).
- The frozen minimal measurement matrix: `N=1024`, 28 conditions, ten complete
  sessions and 5,880 complete physical tasks (5,040 measured tasks in 1,680
  paired blocks plus 840 warmup tasks), with no failed or unstarted tasks.
  Collection took 8,605.428 seconds within the 16,200-second budget; its
  measurement lock was released. See
  [`formal_report.json`](runs/core_20261001_001/raw/formal_001/formal_report.json).

The exact freeze SHA256 is
`ad85f163d6d9a93edc2780815fdeba40e2f4495be9ea0fd275203ad65622b217`;
the measurement ledger SHA256 is
`d0585c402b78fa0f89f40f1b8a4cd3f8d2eb9fc8ee62593dceba235a035f6652`.
The complete frozen summary and vector figures have been generated. Separate
isolated native rebuilding and portable analyze/redraw acceptance have also
passed; their evidence is described below. The completed core data and original
presentation are published at
[fixed version b7185589](https://github.com/sea0114/single-query-packed-multi-record-xpir-for-JISA/tree/b7185589ba16d8374b9744ae39f9fd4a360ffa85).
The current readability revision changes presentation only; its new fixed public
version and paper page acceptance are separate steps.

The functional gate's diagnostic timestamps do not enter performance analysis.
Pilots estimate complete execution cost; tuning chooses configurations. Neither
is pooled with later measurement observations or with historical measurements.

## Files and dependencies

| Path | Purpose |
| --- | --- |
| `src/core_native.hpp`, `src/core_native.cpp` | Bit-exact layout helpers, ownership wrappers and native `prepare`/`query` executable |
| `tests/test_native_unit.cpp` | Finite layout, padding, domain and readonly-mapping checks |
| `scripts/common.py` | Fixed backend parameters, candidate configurations, public fixtures, seeds and integer screens |
| `scripts/build.py`, `scripts/build_unit.py` | Isolated native builds and dependency manifests |
| `scripts/resources.py`, `scripts/resource_probe.py` | Exclusive measurement lock, CPU assignment and accepted memory policy |
| `scripts/runner.py` | Fresh processes, shared preprocessing, task endpoints, collection and validation |
| `scripts/functional.py` | Finite native correctness gate |
| `scripts/pilot.py`, `scripts/pilot_refine.py`, `scripts/tune.py` | Separate cost and configuration-selection stages |
| `scripts/freeze.py`, `scripts/formal.py` | Literal schedule freeze and measurement execution |
| `scripts/analyze.py` | Read-only session-level estimation API; it does not launch native code |
| `scripts/summarize.py`, `scripts/plots.py` | Frozen measurement-summary CLI and summary-only vector figure CLI |
| `reproduction/reproduce.py` | Accepted separate analyze/frozen-redraw wrapper that copies an exact closure to an explicitly new root |
| `reproduction/paper_plots.py`, `reproduction/paper_tables.py` | Accepted current paper presentation from verified fixed results; numeric and cell mappings are retained |
| `runs/<run-id>/` | Build, provenance, functional, pilot, tuning and measurement evidence |

The source checkout must retain this directory at `experiments/core_rebuild/`.
`common.ROOT` resolves the checkout root from that layout. The builder reads
`native_xpir/upstream/` and the unchanged
`revision_notes/B0_logs/build_environment.json`; the latter pins all 142 upstream
files. No old measurement overlay is substituted for the original reply source.
The new build uses the upstream block-parallel path with `-DMULTI_THREAD`.

The executable requires Linux x86-64, AES/AVX2, GNU C++/OpenMP, Boost development
headers and thread/system libraries, GMP/GMPXX, MPFR and OpenSSL 3 development
files. The coordinator uses `random.randbytes`, Linux `memfd`, seals, `/proc`,
affinity and `CLOCK_MONOTONIC_RAW`; the current execution uses Python 3.12 and
GNU C++ 13.3.0 under Ubuntu/WSL2. Other Python versions have not been validated.
Native builds and measurement coordination use the Python standard library.
Plotting dependencies are separate: the accepted redraw used Python 3.12.14 and
Matplotlib 3.10.9. The local verification loaded the existing dependency directory
read-only; it did not copy manuscript material into the portable closure.

Typical Ubuntu package names are `build-essential`, `libboost-thread-dev`,
`libboost-system-dev`, `libgmp-dev`, `libmpfr-dev` and `libssl-dev`. These are
dependency names, not a promise that an untested package combination reproduces
the recorded binary. The build manifest records actual flags, commands, source,
compiler, headers and linked-library hashes.

The successful current `build_002` also used
`/var/tmp/s4f-sage/include/openssl/{sha.h,macros.h,opensslconf.h,configuration.h,opensslv.h,e_os2.h}`.
`build.py` adds that directory only if it exists. Their six hashes match the
preserved B0 build manifest. The historical Sage conda lock records an OpenSSL
package, but its version/license metadata has not yet been checked against these
installed header bytes. The present Ubuntu installation has OpenSSL runtime
`libssl3t64:amd64 3.0.13-0ubuntu3.4`, but no `libssl-dev` or system OpenSSL header
directories. A separate isolated build used the official Ubuntu noble-security
`libssl-dev` and `libssl3t64` packages, both version `3.0.13-0ubuntu3.16`, extracted
inside the workspace without system installation. The Ubuntu archive-keyring
signature, signed index hash and both package hashes were verified before use.
`CPLUS_INCLUDE_PATH`, `LIBRARY_PATH` and `LD_LIBRARY_PATH` selected this matching
development/runtime pair. Actual dependency and loader readback confirmed six
official OpenSSL headers, the staged `libcrypto.so.3`, and no consumed Sage header.
The frozen builder's conditional fallback flag remains unchanged.

The new build passed the unit gate and all 130 finite native functional tasks;
see [`portability_report.json`](portability/native_003/portability_report.json).
Its SHA256 is
`7fd6d2d0a8e4baf3e339b1cce32cc1e79ee239b9ed9410d810d8deb91f3e286a`.
It has a distinct identity from measured `build_002`, whose SHA256 remains
`02418781d12e1b1641c4f0072d54492a02a4aacb8795db24800241bae4476724`.
No performance tasks were rerun. This acceptance covers a fresh source
closure on the recorded host with official workspace-staged dependencies, not a
new operating-system installation or binary identity across machines.

The isolated checkout contains nine frozen native code files, the unchanged B0
manifest and exactly 142 original upstream files verified against its pins. The
official XPIR codeload connection was unavailable for this check, so those 142
files were copied from the existing original tree only after exact verification.
Native execution in the new root did not need manuscript files, old raw data or
the measured executable. Failed WSL download and stale-package 404 attempts were
retained in `portability/native_001/` and `native_002/`. Dependency packages,
headers, libraries and executables are local acceptance artifacts and are not
publicly vendored or included in the project-owned GPL grant.

## Native parameters and layout

The fixed backend is XPIR commit
`75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c`. Native readback checks polynomial degree
`n=4096`, width `w=24`, `t=2^24`, and
`q=5316911983137472318178862960259203073`, with RNS primes
`2305843009213317121` and `2305843009213120513`. Recursion dimension and database
aggregation are both one. Native width is set and its noise amplifiers are
recomputed explicitly; the upstream parameter routine that overwrites this
width is not called.

For a record of `ell_bits` bits and segment width `rho_0`,
`J=ceil(ell_bits/rho_0)` and `L=ceil(J/4096)`. Encoding preserves unused bits in
the final segment and unused coefficients in the final block as zeros. Extraction
removes both padding layers and returns every requested record in target order;
post-task validation checks all decrypted coefficients, segments and padding.
Each selected weight
is encrypted directly through the native unsigned-integer API; it is not formed
by scaling another ciphertext.

Packed candidates use `rho_0` in `{4,6,8,12,16,24}` subject to
`alpha*rho_0 <= 24`; single-record queries use the same width set with
`rho_0 <= 24`. The functional gate includes the `alpha=1` case. The selected native
`Berr=200` path has an actual coefficient bound of 398. The exact per-block
integer screen uses this bound and includes all database records' error
contributions. The recorded checks are in
[`source_gate.json`](runs/core_20261001_001/functional/source_gate.json) and each
selected condition's `arithmetic_screens` in `freeze.json`; repeated queries use
the single-record condition with multiplicity one. The source gate's
runtime-pending status is historical: the later native functional report supplies
the execution result. Source inspection, finite error checks and this arithmetic screen
do not establish the sampler's formal distribution, joint independence,
IND-CPA security or a probabilistic reliability guarantee.

## Shared preprocessing and task protocol

One coordinator owns a public fixture `memfd` and a preprocessed-database
`memfd`. Fixtures are generated and sealed before task timing. A unique native
preparation process encodes the records, imports them into the XPIR NTT/RNS
representation and exports the shared database. It releases the imported native
allocation and writable buffers before declaring completion. The coordinator
then seals the database against writes, growth and shrinkage. Query processes
borrow it through `mmap(PROT_READ, MAP_SHARED)`; they retain private pointer tables
and cryptographic state, not independent imported database copies.

All preparation and query workers are new executable processes. They load public
inputs and signal `R` (ready) before any cryptographic object is created. The
coordinator sends `G` (go) to start a worker's timed work. A query generates its
fresh key, directly encrypts all `N` selector components, computes the native
reply, decrypts and extracts full records, writes those raw record bytes to the
collection pipe and signals `D` (done). It waits for `V` before validation,
fingerprinting, error auditing and metadata output. Native stdout is drained to
memory during execution; logs are written to disk after the task.

Each retrieval process has one fresh key and a fresh initialization of the native
RNG. Ordinary selector encryptions, including zeros, use that process's key.
The gate records key-generation and Salsa-call counts and verifies different
first-ciphertext fingerprints across fresh processes. Fingerprint checks are
initialization diagnostics, not a proof of independence or security. Secret keys,
RNG keys and nonce values are not emitted into experiment evidence.

The preparation process also performs the backend configuration/key-constructor
work required for import. That work is part of included preprocessing and is
reported in its native metadata; it is outside the excluded task interval.
Observation-level `key_generation_calls` counts retrieval processes. Read the
preparation report separately when accounting for the import owner's key work.

## Timing, CPU and memory

Task latency uses the coordinator's `CLOCK_MONOTONIC_RAW` endpoints. For
preprocessing **included**, timing starts immediately before preparation `G` and
includes encoding, import, shared-data construction/sealing, retrieval dispatch,
fresh query keys, queries, replies, extraction and full-record collection. For
preprocessing **excluded**, the sealed shared database is ready before timing
starts; timing then starts before query dispatch. Both intervals end after every
required full-record byte and query `D` have been collected. Fresh-exec startup,
public-fixture generation/loading, post-`V` validation, audits, hashing and disk
result writing are outside these task intervals. `wall_elapsed_ns` separately
records complete execution overhead used for budget planning.

All methods use one total pool of four logical CPUs visible to the WSL2 guest. Query
concurrency `c` and per-process arithmetic threads `t_threads` satisfy
`c*t_threads <= 4`; queries are assigned nonoverlapping subsets while active.
The current pool is `0,2,4,6`. This affinity assignment does not establish
exclusive physical cores or memory isolation on the Windows host.

The accepted current memory policy is **monitor**, with a frozen 8 GiB abort
threshold. A one-second sample combines private resident memory, proportional
non-database shared memory and unique shared storage. The public fixture's
storage and the preprocessed database are included; database mappings are not
summed repeatedly as independent physical copies. Unavailable samples are
recorded. This is sampled monitoring, not an OS hard memory limit or an exact
instantaneous peak. The attempted cgroup hard-limit setup was unavailable and
cleaned up before this fallback was accepted. A future run must probe and freeze
its own policy rather than silently change it mid-run.

With the current monitor policy, task CPU time is the coordinator's self-rusage
delta plus every query's native user/system CPU time between `G` and `D`;
included scope additionally counts the single preparation owner. Native reports
retain CPU time even after a child exits. A separately accepted cgroup policy uses
its group counters over the task span. CPU accounting differs from wall latency
and does not count post-task validation. Monitoring and pipe/log collection costs
inside the coordinator's timed work remain part of the recorded task cost.

Preprocessing wall time is recorded directly from the native preparation span
(`preprocess_total_ns`) in both scopes. It is elapsed time, whereas CPU time sums
user and system work across the timed process group. Preprocessing is included in
task latency only in included scope; its cost is not estimated by subtracting
the two scope summaries.

Each native ciphertext buffer is `2*4096*2*8 = 131072` bytes. Query and reply
accounting sums the actual processes' `N` selector buffers and `L` reply buffers.
These are cumulative ciphertext-buffer bytes, not serialized messages, network
traffic, peak resident memory or a claim about transport.

## Selection, schedules and statistics

Primary roles are packed retrieval `P`, repeated single-record retrieval at the
packed layout `R_matched`, and independently tuned repeated retrieval
`R_independent`. Tuning compares legal layout/concurrency/thread candidates using
one warmup and three measured tasks in preprocessing-excluded scope, selects the
median task latency, and breaks exact ties by lexical configuration ID. The
matched stage holds the chosen packed layout fixed. If the two repeated roles
select the same configuration, one physical observation supplies both contrasts;
it is not treated as two independent samples. The separate capacity study uses
its predeclared fixed layouts and lengths.
Both timing scopes use the same selected primary configurations.

Measurement execution is permitted only after functional, pilot, tuning, source,
resource and budget gates pass. `freeze.json` records the actual workload tier,
winning configurations, arithmetic screens, seeds, literal schedule, binary and
source hashes. That immutable design snapshot retains its original
`FROZEN_NOT_FORMALLY_MEASURED` status; the separate formal report now records
`COMPLETE`. The measurement budget check uses actual complete configuration costs plus block
overhead and a 50% margin; the margin is not a runtime guarantee.

The completed frozen measurement protocol has ten sessions, one warmup block and six
measured paired blocks per condition/session. Within each block every method
shares public records and ordered targets. Condition order is randomized; all
six permutations of three physical methods are balanced within a session. If
there are two physical methods after aliasing, each of the two orders occurs
three times. Public fixtures and targets use separately recorded seeded Python
generators; they do not seed the cryptographic RNG. Base seeds are in
[`common.py`](scripts/common.py), and schedules retain every derived seed and
target tuple. The native standalone seed-based fallback is a different public
fixture generator; campaign workers receive the coordinator's actual sealed
fixture bytes.

The measurement estimator is the median across sessions of each session's median
paired `baseline/P` latency ratio. Absolute costs use within-session method
medians followed by a median across sessions. The analysis API jointly resamples
whole sessions 10,000 times with the same draw indices for both contrasts and all
metrics. It reports pointwise 95% percentile intervals using linear interpolation
at `(B-1)*p`, and preserves the resampling seed/draw digest. These are approximate
resampling summaries, not guaranteed coverage or cross-host predictions.

Failures, wrong outputs, timeouts, threshold aborts and unstarted tasks are
retained. There is no retry that replaces a failed observation. A failed method
invalidates its paired block; a condition with any missing or failed expected
task, including warmups, receives no performance estimate. No successful subset,
cross-version repair or historical-data pooling is used.

## Commands for a new independent run

Do not start these commands on a host where another measurement is active.
Compilation, functional testing, analysis and rendering are separate phases from
performance collection. Every run/build/output identity must be unused; outputs
stay under this directory. Scripts refuse existing result paths.

From a checkout root with the pinned upstream tree already present, the initial
stages are:

```bash
run_id=core_local_001
core=experiments/core_rebuild
python3 -B "$core/scripts/preflight.py" --out "$core/runs/$run_id/provenance/preflight.json"
python3 -B "$core/scripts/resource_probe.py" --run-dir "$core/runs/$run_id"
python3 -B "$core/scripts/build.py" --run-id "$run_id" --build-id build_001
manifest="$core/runs/$run_id/build/build_001/build_manifest.json"
binary="$core/runs/$run_id/build/build_001/core_native"
python3 -B "$core/scripts/build_unit.py" --manifest "$manifest"
python3 -B "$core/scripts/check_scripts.py" --run-id "$run_id"
```

Read the recorded CPU pool and memory policy, then pass those actual values to
the gate. This example uses the current host's accepted values; other machines
must use their own probe:

```bash
python3 -B "$core/scripts/functional.py" --run-id "$run_id" \
  --binary "$binary" --unit-binary "$core/runs/$run_id/build/build_001/unit/test_native_unit" \
  --policy monitor --cpus 0,2,4,6
```

Requesting cgroup writes is an explicit resource setup action through
`resource_probe.py --authorize-cgroup-write`; use the gate's corresponding flag
only for a cgroup policy actually accepted by the probe. The default probe does
not write to cgroups.

With the authorized budgets and complete previous gates, campaign stages are
sequential:

```bash
python3 -B "$core/scripts/pilot.py" --run-id "$run_id" --binary "$binary"
python3 -B "$core/scripts/pilot_refine.py" --run-id "$run_id" --binary "$binary"
python3 -B "$core/scripts/tune.py" --run-id "$run_id" --binary "$binary"
python3 -B "$core/scripts/freeze.py" --run-id "$run_id" --manifest "$manifest"
python3 -B "$core/scripts/formal.py" --freeze "$core/runs/$run_id/provenance/freeze.json"
```

The resource and source review records required by `freeze.py` must also be
present and verified; command success in earlier stages does not substitute for
those reviews. Pilot/tuning/measurement budgets are 1,800/3,600/16,200 seconds. If the
minimum permitted matrix cannot fit, freezing records that author decision is
required and measurement collection must not start. `scripts/analyze.py` exposes the
estimation API; `scripts/summarize.py --run-id RUN --freeze-sha256 SHA` is the
complete-measurement summary CLI, and `scripts/plots.py --run-id RUN
--summary-sha256 SHA` draws the verified summary without bootstrapping. Both
require unused output locations through their preserved directory layout. The
new `reproduction/reproduce.py` wrapper provides separately accepted `analyze`
and `redraw` routes with an explicit unused `--output-root`, copied exact
dependencies and confined temporary/cache paths.

## Redraw the current paper figures and tables

This is the shortest accepted presentation route. It reads the fixed results,
does not launch native code or bootstrap, and does not need manuscript sources,
the B0 archive, old raw data or the measured executable. Install the plotting
dependency before drawing figures; tables use the Python standard library only.
Choose new output directories:

```bash
core=experiments/core_rebuild
results="$core/results/core_20261001_001"
output_parent="$core/portability" # Or another existing writable directory you choose.
python3 -B "$core/reproduction/paper_plots.py" --results "$results" \
  --summary-sha256 fa4f02c7ea2657c5740d531b42d15ebcbeedcc162de367a834639cb1ce6db863 \
  --out "$output_parent/paper_figures_local_001"
python3 -B "$core/reproduction/paper_tables.py" --results "$results" \
  --summary-sha256 fa4f02c7ea2657c5740d531b42d15ebcbeedcc162de367a834639cb1ce6db863 \
  --out "$output_parent/paper_tables_local_001"
```

The figure closure contains 13 files: the presentation renderer, frozen
`plots.py`/`common.py`, six analysis outputs, analysis provenance and three frozen
figure JSON files. Reference PDFs are optional integrity references, not inputs
required for plotting. Tables need six files: their renderer, summary, three
analytical CSV files and analysis provenance. Current program SHA256 values are
`c362183d5772ca6878af53469df7a94fbcff553ee8166cb752e6368236c8814f`
for `paper_plots.py` and
`c01b16a370cdbd3e36d16bd47d086cd2b7e4e7fc985986a2a52aa13b02162e19`
for `paper_tables.py`.

The retrieval figure uses two horizontal panels (preprocessing excluded/included)
with the same six workload rows and a common `0.95`-`1.35` repeated/packed ratio
axis. It contains all 12 independently tuned repeated/packed estimates and CIs.
The capacity figure retains four panels and all four categorical lengths per
panel, showing packed and full-width repeated latency with CIs (32 points).
Packed `L=1`/`L=2` regions and full-width `L=1` remain explicit. The capacity
full-width role still reads the saved `R_independent` key; it is a fixed policy,
not a tuned capacity result. Connecting lines do not model unmeasured lengths.

The source figure matrix still has 72 points. The new role whitelist selects
44 main-figure points without changing any estimate, interval, workload,
configuration or scope. The coverage map accounts for the other 28 points:
12 primary matched paired ratios and their CIs remain in the complete primary
table; 16 capacity matched medians and paired contrasts remain in the complete
capacity table, with their absolute-time CIs retained in the fixed summary.
Both complete tables belong to Supplement S1; capacity absolute CIs are not
all printed in the table. Selection is by role, never by effect size.

The full-width cost table displays 24 median estimates in six scope/alpha
rows, with adjacent Packed/Repeated columns, two-level headings and 10 pt type.
All 48 interval endpoints remain in `results/core_20261001_001/summary.json`,
under `conditions/<condition_id>/absolute/{P,R_independent}/{cpu_time_ns,preprocessing_ns}/CI95`
(in nanoseconds); select primary workloads with `ell_bits=32768`, both scopes
and alpha 2, 3, 4. The table mapping separates 450 visible-value source pointers
for 284 cells from 48 `archived_interval_sources`; archived endpoints are not
claimed as displayed values. The three other tables remain unchanged.

`numeric_preservation.json`, `figure_data.json`, `layout_mapping.json`, the
`coverage_mapping.json` and `paper_figure_provenance.json` distinguish subset selection
from the frozen full-series reference. Existing receipts describing all 72
points in the main figures or 314/528 table mapping are historical, not current
acceptance. Figure temporary files and Matplotlib caches stay in the new output
directory. Table snippets use `booktabs`; final document compilation and page
acceptance remain separate from numeric preservation. The incremental
implementation receipt is [section6-focus-and-discussion.json](../../manifests/section6-focus-and-discussion.json).

The earlier
[`paper_reproduction_acceptance.json`](portability/paper_acceptance_001/paper_reproduction_acceptance.json)
is historical acceptance of the margin-only renderer published in b7185589.
Its unchanged-limit/caption and byte-identical-PDF checks apply to that version;
it is retained alongside the frozen scientific references rather than rewritten
to describe the current display.

## Reproduce the frozen analysis or figures

These commands read the fixed completed run and do not execute native code or
repeat measurements. Both first verify the published freeze, measurement report and
complete raw ledger. `analyze` copies four frozen scripts and those three inputs,
then repeats the frozen session-level resampling. `redraw` copies two plotting
scripts and seven verified result files; it performs no bootstrap and needs no
native executable, B0 archive or upstream source. The verified raw ledger remains
necessary for the wrapper's input-integrity check, even on the redraw route.

From the checkout root, choose output leaf names that do not already exist:

```bash
core=experiments/core_rebuild
run_id=core_20261001_001
mkdir -p "$core/portability"
python3 -B "$core/reproduction/reproduce.py" analyze --run-id "$run_id" \
  --output-root "$core/portability/analyze_local_001" \
  --freeze-sha256 ad85f163d6d9a93edc2780815fdeba40e2f4495be9ea0fd275203ad65622b217 \
  --observations-sha256 d0585c402b78fa0f89f40f1b8a4cd3f8d2eb9fc8ee62593dceba235a035f6652 \
  --formal-report-sha256 822763d3f0294865f103d2c32e425135389259f81775950fd3f0f0cea82384f1
python3 -B "$core/reproduction/reproduce.py" redraw --run-id "$run_id" \
  --output-root "$core/portability/redraw_local_001" \
  --freeze-sha256 ad85f163d6d9a93edc2780815fdeba40e2f4495be9ea0fd275203ad65622b217 \
  --summary-sha256 fa4f02c7ea2657c5740d531b42d15ebcbeedcc162de367a834639cb1ce6db863 \
  --analysis-provenance-sha256 ace1b3800cd46fa78f65f1759f4ef5cc54d55b358fe520732bbabb8e0ee60ba7
```

The isolated checks are recorded in
[`reproduction_acceptance.json`](portability/acceptance_002/reproduction_acceptance.json).
All six analysis outputs have exact semantic and numeric parity: the three CSV
files are byte-identical, while the three JSON files differ only in Linux/Windows
line endings and match exactly after CRLF-to-LF normalization. The estimator,
source identities and bootstrap draw digest are unchanged. Generation timestamps
and resulting JSON serialization hashes are recorded separately.

Frozen redraw produced byte-identical `retrieval_performance.pdf`,
`capacity_tradeoff.pdf`, `figure_data.json` and `caption_data.json`; its provenance
differs only in the generation timestamp. It reproduces the frozen layout,
including its identified capacity-figure spacing defect. Existing output roots
and incorrect freeze hashes were rejected before writes; original inputs and
existing outputs remained unchanged. Temporary files and Matplotlib caches stayed
inside the explicit output root. The accepted corrected paper presentation route
above is separate from this historical frozen redraw.

## Incremental publication and portability

The public reproduction repository supplies GPL text, dependency notices and
hash-verifying `scripts/fetch_upstream.py`. Fixed version b7185589 preserves the
unchanged B0 manifest inside the existing data archive and also promotes its
original bytes directly to
`revision_notes/B0_logs/build_environment.json`, SHA256
`19acb1fe7b90ada0160b403c4fff0b52645b1ca2dd54db9c7cf0ab8e118128c1`.
The file is necessary dependency-pin metadata, not a new copy of B0 raw
observations or manuscript materials. Its existing non-program license scope is
retained and the distributed-file list records the exact bytes.

A checkout of that fixed version can run
`python3 -B scripts/fetch_upstream.py --root .` directly, without extracting the
full old archive. This creates `native_xpir/upstream/` from the fixed official
source; it must not overwrite an existing upstream tree. Earlier historical
versions still need `python3 -B scripts/unpack_data.py` first. Preserve the pins and the
`experiments/core_rebuild/` nesting. No new archive or package is created, and
existing archives and release history remain intact.

The local source/analysis dependency closure, actual staged compiler/header
environment, fresh-root finite functional gate and native-free analysis/redraw
routes have passed the recorded core acceptance and are published in b7185589.
New presentation changes require their own numeric-preservation and public-version
verification; the completed native and analysis gates are not rerun for this revision.
Frozen run manifests include original absolute commands and environment paths;
they are provenance, not executable instructions for another checkout. A release
needs an explicit portable path map and public metadata review, while retaining
original local evidence unchanged. Include schedules, seeds, raw observations,
failed/unstarted statuses, accepted resource policy, source/binary identity and
full-precision verified summaries needed by the final figures. Do not infer
completion of a later revision from an older receipt.

Project-owned programs use the author's existing GPL-3.0-or-later grant. The
unchanged upstream tree is acquired separately; its original notices and known
file-specific rights gaps remain. See the public repository's
`THIRD_PARTY_NOTICES.md` and `LICENSE_SCOPE.csv`. Documentation,
data, logs and figures are not automatically granted the program license.
Update the release's explicit allowlist, license map and file checksums for the
actual additions without changing scientific pins. Do not distribute system
libraries, native executables, current manuscript/PDF or submission materials.

This directory does not package, publish or remove historical materials. A later
authorized incremental implementation update must preserve repository history,
verify the remote fixed commit, and report publication separately from native
validation and manuscript completion.
